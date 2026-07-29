"""Educational renderer v2 — profile-aware, design-token driven.

Timeline of a video (duration D):
    [0 .. hook_end]        HOOK   — display-XL phrase, per-word pop stagger.
    [hook_end .. D-2.5]    BODY   — rounded card with karaoke sentence and,
                                    when present, an English highlight panel
                                    (display word + translation).
    [D-2.5 .. D]           CTA    — "Sígueme para más" + handle.

Chrome on every frame: top progress bar, brand tag, profile background
(adults: animated ink mesh; kids: cream + shapes + rounded clip window).

The instance is callable: ``renderer(t) -> np.ndarray`` (RGB, 1080x1920),
fully deterministic in ``t``.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import design as D
from .design import Tokens, get_tokens, load_font
from .background import AdultsBackground, KidsBackground
from . import motion as M
from . import timing_engine as TE

logger = logging.getLogger(__name__)

# Timeline
HOOK_END = 3.0
CTA_LEN = 2.5
WORD_ANTICIPATION = 0.08  # highlight words slightly before their audio
# NOTE: group visibility windows/fades now live in timing_engine.py

# Layout
PROGRESS_Y = 204
PROGRESS_H = 8
CARD_PAD = 56
# Kids clip window (top third, framed — not fullscreen)
WIN_X, WIN_Y, WIN_W, WIN_H = 100, 252, 880, 660
WIN_BORDER = 16
WIN_RADIUS = 52


def _norm(text: str) -> str:
    """Lowercase and strip punctuation for translation lookups."""
    return re.sub(r"[^\w\s'-]", "", text or "").strip().lower()


def _lookup_translation(en_text: str, translations: Dict[str, str]) -> str:
    """Normalized exact/overlap lookup of a translation for an English phrase."""
    key = _norm(en_text)
    if not key or not translations:
        return ""
    norm_map = {_norm(k): v for k, v in translations.items() if _norm(k)}
    if key in norm_map:
        return norm_map[key]
    kw = set(key.split())
    for nk, v in norm_map.items():
        ks = set(nk.split())
        overlap = kw & ks
        if overlap and len(overlap) / max(len(kw), len(ks)) >= 0.6:
            return v
    return ""


class EducationalRendererV2:
    """Callable frame generator: ``f(t) -> np.ndarray`` RGB (1920, 1080, 3)."""

    def __init__(self, data: Dict, duration: float, profile_name: str = "adults"):
        self.T: Tokens = get_tokens(profile_name)
        self.duration = duration
        self.translations: Dict[str, str] = data.get("translations", {}) or {}
        self.cta_start = max(0.0, duration - CTA_LEN)
        self.hook_end = min(HOOK_END, self.cta_start)

        # Display windows: audio timestamps stay untouched; the timing
        # engine derives when each group is VISIBLE (golden rule: never
        # off-screen before its last word + 350ms, min hold, no gaps).
        self.groups: List[Dict] = TE.compute_display_windows(
            data.get("_groups", []), duration, content_end=self.cta_start)
        logger.info("v2 timing windows:\n%s", TE.debug_table(self.groups))

        self._words: List[Dict] = data.get("words", []) or []

        english_phrases = data.get("english_phrases", []) or []
        self._english_words = {
            _norm(w) for p in english_phrases for w in p.split() if len(_norm(w)) > 1
        }

        hook_text = (data.get("hook") or "").strip()
        if not hook_text and self.groups:
            hook_text = self.groups[0].get("text", "")
        self.hook_words = hook_text.split()

        logger.info("v2 educational: profile=%s groups=%d hook=%r",
                    self.T.name, len(self.groups), hook_text[:60])

        # ── Precomputed static assets ─────────────────────────────
        self._measure = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        self._card_cache: Dict[tuple, Image.Image] = {}
        self._group_layout: Dict[int, dict] = {}

        if self.T.name == "kids":
            self._bg = KidsBackground(D.WIDTH, D.HEIGHT, self.T)
        else:
            self._bg = AdultsBackground(D.WIDTH, D.HEIGHT, self.T)

        self._clip_bg = None
        self._win_frame = None
        if self.T.has_clip_window:
            self._init_clip_window(duration)

        # Body vertical zone (kids text lives below the clip window);
        # bottom stays clear of the brand tag line.
        if self.T.has_clip_window and self._clip_bg is not None:
            self._body_top = WIN_Y + WIN_H + 44
        else:
            self._body_top = D.SAFE_TOP + 110
        self._body_bottom = D.CONTENT_BOTTOM - 76

        self._brand_layer = self._build_brand_layer()
        self._hook_layout = self._layout_hook()

    # ══════════════════════════════════════════════════════════════
    #  Static asset builders
    # ══════════════════════════════════════════════════════════════

    def _init_clip_window(self, duration: float) -> None:
        """Prepare the rounded character-clip window (kids profile).

        The window is driven by CharacterDirector: clips are chosen by
        narration state (talking/idle/reaction/celebrate) using the word
        timestamps, instead of a random playlist.
        """
        clips_dir = next((d for d in self.T.clip_dirs
                          if Path(d).exists() and list(Path(d).rglob("*.mp4"))), None)
        if not clips_dir:
            logger.warning("v2: no clips found for %s — window disabled", self.T.name)
            return

        inner_w = WIN_W - 2 * WIN_BORDER
        inner_h = WIN_H - 2 * WIN_BORDER
        try:
            from .character_director import CharacterDirector
            self._clip_bg = CharacterDirector(
                clips_dir, inner_w, inner_h, duration=duration,
                words=self._words, groups=self.groups,
                cta_start=self.cta_start, seed=7)
        except Exception as e:
            logger.warning("CharacterDirector failed (%s) — falling back to "
                           "random clip playlist", e)
            from ..clip_background import ClipLibraryBackground
            self._clip_bg = ClipLibraryBackground(
                clips_dir, inner_w, inner_h, duration=duration, seed=7, dim=0.0)

        # Inner rounded mask for the video
        self._win_mask = Image.new("L", (inner_w, inner_h), 0)
        ImageDraw.Draw(self._win_mask).rounded_rectangle(
            [0, 0, inner_w - 1, inner_h - 1], radius=WIN_RADIUS - WIN_BORDER, fill=255)

        # Frame layer: soft shadow + thick white border, prerendered once
        m = 60
        layer = Image.new("RGBA", (WIN_W + 2 * m, WIN_H + 2 * m), (0, 0, 0, 0))
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [m, m + 16, m + WIN_W, m + WIN_H + 16], radius=WIN_RADIUS,
            fill=(120, 72, 20, 70))
        sh = sh.filter(ImageFilter.GaussianBlur(22))
        layer.alpha_composite(sh)
        ImageDraw.Draw(layer).rounded_rectangle(
            [m, m, m + WIN_W, m + WIN_H], radius=WIN_RADIUS, fill=(255, 255, 255, 255))
        self._win_frame = layer
        self._win_margin = m

    def _build_brand_layer(self) -> Image.Image:
        """Small brand tag, bottom-left inside the safe area."""
        layer = Image.new("RGBA", (D.WIDTH, D.HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = load_font(self.T.name, "text", D.TYPE_SCALE["micro"]["size"])
        x, y = D.SAFE_SIDE, D.CONTENT_BOTTOM - 44
        d.ellipse([x, y + 8, x + 14, y + 22], fill=(*self.T.accent, 230))
        tx = x + 26
        color = ((235, 240, 252, 200) if self.T.name == "adults"
                 else (*self.T.text_secondary, 235))
        for ch in self.T.brand_tag:
            d.text((tx, y), ch, font=f, fill=color)
            tx += d.textlength(ch, font=f) + D.TYPE_SCALE["micro"]["tracking"]
        return layer

    def _card_layer(self, w: int, h: int, radius: int,
                    fill: Tuple[int, int, int], alpha: int,
                    border: Tuple[int, int, int, int],
                    key: str = "") -> Image.Image:
        """Prerendered rounded card with a soft blurred drop shadow."""
        ck = (w, h, radius, key)
        if ck in self._card_cache:
            return self._card_cache[ck]
        m = 56
        layer = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        shadow_col = (10, 12, 22, 120) if self.T.name == "adults" else (150, 96, 30, 60)
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [m, m + 18, m + w, m + h + 18], radius=radius, fill=shadow_col)
        layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(24)))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle([m, m, m + w, m + h], radius=radius, fill=(*fill, alpha))
        d.rounded_rectangle([m, m, m + w, m + h], radius=radius, outline=border, width=2)
        self._card_cache[ck] = layer
        return layer

    # ── Text measurement helpers ─────────────────────────────────

    def _wrap(self, text: str, font, max_w: int) -> List[str]:
        """Greedy word wrap using real glyph widths."""
        words, lines, cur = text.split(), [], []
        for w in words:
            trial = " ".join(cur + [w])
            if self._measure.textlength(trial, font=font) <= max_w or not cur:
                cur.append(w)
            else:
                lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return lines

    def _fit(self, text: str, role: str, start: int, minimum: int,
             max_w: int, max_lines: int) -> Tuple[int, List[str]]:
        """Largest size in the scale step-down that fits within max_lines."""
        for size in range(start, minimum - 1, -4):
            f = load_font(self.T.name, role, size)
            lines = self._wrap(text, f, max_w)
            if len(lines) <= max_lines:
                return size, lines
        f = load_font(self.T.name, role, minimum)
        return minimum, self._wrap(text, f, max_w)

    # ══════════════════════════════════════════════════════════════
    #  Layout precomputation
    # ══════════════════════════════════════════════════════════════

    def _layout_hook(self) -> dict:
        """Precompute per-word positions for the hook display block.

        Auto-fits both line count and total block height so the hook never
        collides with the clip window or the brand tag.
        """
        text = " ".join(self.hook_words)
        label_h = 70
        avail_h = self._body_bottom - self._body_top - label_h - 24
        lh_factor = D.TYPE_SCALE["display"]["line"]
        size = D.TYPE_SCALE["display"]["size"]
        minimum = 60 if self.T.has_clip_window else D.TYPE_SCALE["display"]["min"]
        lines: List[str] = []
        while size > minimum:
            f = load_font(self.T.name, "display", size)
            lines = self._wrap(text or " ", f, D.CONTENT_W)
            if len(lines) <= 4 and len(lines) * int(size * lh_factor) <= avail_h:
                break
            size -= 4
        f = load_font(self.T.name, "display", size)
        lines = self._wrap(text or " ", f, D.CONTENT_W)
        line_h = int(size * lh_factor)
        placed, idx = [], 0
        for li, line in enumerate(lines):
            ws = line.split()
            widths = [self._measure.textlength(w, font=f) for w in ws]
            space = self._measure.textlength(" ", font=f)
            total = sum(widths) + space * (len(ws) - 1)
            x = (D.WIDTH - total) / 2
            for w, wd in zip(ws, widths):
                is_en = _norm(w).strip("'\"") in self._english_words
                placed.append({"text": w, "cx": x + wd / 2, "line": li,
                               "index": idx, "english": is_en})
                x += wd + space
                idx += 1
        return {"words": placed, "font": f, "line_h": line_h,
                "n_lines": len(lines), "size": size}

    def _layout_group(self, gi: int) -> dict:
        """Precompute card geometry + word slots for group ``gi`` (cached)."""
        if gi in self._group_layout:
            return self._group_layout[gi]

        g = self.groups[gi]
        words = g.get("words") or []
        text = g.get("text", "")
        card_w = D.CONTENT_W
        inner_w = card_w - 2 * CARD_PAD
        avail_h = self._body_bottom - self._body_top

        body_max = 58 if not self.T.has_clip_window else 50
        size, lines = self._fit(text or " ", "text", body_max,
                                D.TYPE_SCALE["body"]["min"], inner_w, 3)
        f = load_font(self.T.name, "text", size)
        line_h = int(size * 1.32)
        # Wider word gap leaves room for the active-word pulse scale
        space = self._measure.textlength(" ", font=f) * 1.45

        # Word slots (center positions relative to card top-left)
        slots, wi = [], 0
        for li, line in enumerate(lines):
            ws = line.split()
            widths = [self._measure.textlength(w, font=f) for w in ws]
            total = sum(widths) + space * (len(ws) - 1)
            x = (card_w - total) / 2
            for wtext, wd in zip(ws, widths):
                wdata = words[wi] if wi < len(words) else None
                slots.append({"text": wtext, "cx": x + wd / 2,
                              "line": li, "word": wdata})
                x += wd + space
                wi += 1
        text_h = len(lines) * line_h

        # English highlight panel (display word + translation)
        en_text = " ".join(w["word"] for w in words if w.get("is_english")) \
            if words else (text if g.get("english") else "")
        trans = _lookup_translation(en_text, self.translations) if en_text else ""
        if trans and _norm(trans) == _norm(en_text):
            trans = ""
        def _build_panel(en_start: int, tr_size: int) -> dict:
            en_size, en_lines = self._fit(en_text, "display", en_start, 54,
                                          inner_w - 48, 2)
            en_f = load_font(self.T.name, "display", en_size)
            en_lh = int(en_size * D.TYPE_SCALE["display"]["line"])
            tr_f = load_font(self.T.name, "text", tr_size)
            tr_lines = self._wrap(trans, tr_f, inner_w - 48)
            tr_lh = int(tr_size * 1.3)
            panel_h = 36 + len(en_lines) * en_lh + 14 + len(tr_lines) * tr_lh + 36
            return {"en_lines": en_lines, "en_font": en_f, "en_lh": en_lh,
                    "tr_lines": tr_lines, "tr_font": tr_f, "tr_lh": tr_lh,
                    "h": panel_h}

        panel = None
        if en_text and trans:
            panel = _build_panel(104, 44)

        def _total(p) -> int:
            return CARD_PAD + text_h + (24 + p["h"] if p else 0) + CARD_PAD

        card_h = _total(panel)
        if panel and card_h > avail_h:
            # Compress the panel so tall cards never spill out of the zone
            panel = _build_panel(80, 40)
            card_h = _total(panel)
        layout = {"slots": slots, "font": f, "size": size, "line_h": line_h,
                  "text_h": text_h, "card_w": card_w, "card_h": card_h,
                  "panel": panel}
        self._group_layout[gi] = layout
        return layout

    # ══════════════════════════════════════════════════════════════
    #  Frame generation
    # ══════════════════════════════════════════════════════════════

    def __call__(self, t: float) -> np.ndarray:
        # Frame stays in RGB mode: ImageDraw in "RGBA" mode then *blends*
        # semi-transparent fills instead of overwriting pixels.
        if self.T.name == "kids":
            frame = self._bg.frame(t)                     # PIL RGB
        else:
            frame = Image.fromarray(self._bg.frame(t))
        draw = ImageDraw.Draw(frame, "RGBA")

        if self._clip_bg is not None:
            self._draw_clip_window(frame, t)

        self._draw_progress(draw, t)

        if t < self.hook_end:
            self._draw_hook(frame, draw, t)
        elif t < self.cta_start:
            self._draw_body(frame, draw, t)
        if t >= self.cta_start:
            self._draw_cta(frame, draw, t)

        frame.paste(self._brand_layer, (0, 0), self._brand_layer)
        return np.asarray(frame)

    # ── Chrome ───────────────────────────────────────────────────

    def _draw_progress(self, draw: ImageDraw.ImageDraw, t: float) -> None:
        x0, x1 = D.SAFE_SIDE, D.WIDTH - D.SAFE_SIDE
        r = PROGRESS_H // 2
        draw.rounded_rectangle([x0, PROGRESS_Y, x1, PROGRESS_Y + PROGRESS_H],
                               radius=r, fill=self.T.progress_track)
        p = M.clamp01(t / max(self.duration, 0.01))
        fill_w = max(PROGRESS_H, int((x1 - x0) * p))
        draw.rounded_rectangle([x0, PROGRESS_Y, x0 + fill_w, PROGRESS_Y + PROGRESS_H],
                               radius=r, fill=(*self.T.progress_fill, 255))

    def _draw_clip_window(self, frame: Image.Image, t: float) -> None:
        dy = int(M.slide_up(t, 0.05, 0.55, 46))
        a = M.fade(t, 0.05, 0.4)
        m = self._win_margin
        win = self._win_frame
        if a < 1.0:
            win = win.copy()
            win.putalpha(win.getchannel("A").point(lambda v: int(v * a)))
        frame.paste(win, (WIN_X - m, WIN_Y - m + dy), win)
        raw = self._clip_bg.get_frame(t)
        clip_img = Image.fromarray(raw)
        if a < 1.0:
            mask = self._win_mask.point(lambda v: int(v * a))
        else:
            mask = self._win_mask
        frame.paste(clip_img, (WIN_X + WIN_BORDER, WIN_Y + WIN_BORDER + dy), mask)

    # ── Hook ─────────────────────────────────────────────────────

    def _draw_hook(self, frame: Image.Image, draw: ImageDraw.ImageDraw,
                   t: float) -> None:
        H = self._hook_layout
        out = M.fade_out(t, self.hook_end, 0.30)
        if out <= 0:
            return

        block_h = H["n_lines"] * H["line_h"]
        zone_top, zone_bot = self._body_top, self._body_bottom
        label_f = load_font(self.T.name, "text", D.TYPE_SCALE["caption"]["size"])
        label = "MINI CLASE DE INGLÉS" if self.T.name == "adults" else "¡INGLÉS PARA PEQUES!"
        label_h = 70
        y0 = zone_top + (zone_bot - zone_top - block_h - label_h) // 2 + label_h
        y0 = max(y0, zone_top + label_h + 12)

        # Kicker label
        la = M.fade(t, 0.1, 0.3) * out
        if la > 0:
            tw = sum(draw.textlength(c, font=label_f) + 3 for c in label)
            lx = (D.WIDTH - tw) / 2
            ly = y0 - label_h
            dot_c = self.T.accent
            draw.rounded_rectangle(
                [lx - 28, ly - 12, lx + tw + 24, ly + 48], radius=30,
                fill=(*dot_c, int(36 * la)) if self.T.name == "adults"
                else (255, 255, 255, int(210 * la)))
            cx = lx
            lc = (*self.T.accent, int(255 * la))
            for ch in label:
                draw.text((cx, ly), ch, font=label_f, fill=lc)
                cx += draw.textlength(ch, font=label_f) + 3

        for w in H["words"]:
            start = 0.22 + M.stagger(w["index"], 0.075)
            scale, a = M.pop_in(t, start, 0.34)
            a *= out
            if a <= 0:
                continue
            cy = y0 + w["line"] * H["line_h"] + H["line_h"] // 2
            hero = self.T.accent_warm if self.T.name == "adults" else self.T.accent
            color = hero if w["english"] else self.T.text_primary
            if self.T.name == "kids" and not w["english"]:
                color = self.T.text_primary
            f = H["font"]
            if abs(scale - 1.0) > 0.01 and scale > 0:
                f = load_font(self.T.name, "display", max(8, int(H["size"] * scale)))
            draw.text((w["cx"], cy), w["text"], font=f,
                      fill=(*color, int(255 * a)), anchor="mm")

    # ── Body (karaoke card) ──────────────────────────────────────

    def _active_group(self, t: float) -> Tuple[Optional[int], float]:
        """Return (group index, alpha) for the group visible at t.

        Uses the timing engine's display windows: windows never overlap,
        entrance/exit fades live INSIDE the window and alpha is clamped
        to [0,1] — no flicker, no double-draw, no premature exit.
        """
        for gi, g in enumerate(self.groups):
            a = TE.group_alpha(g, t)
            if a > 0.0:
                return gi, a
        return None, 0.0

    def _draw_body(self, frame: Image.Image, draw: ImageDraw.ImageDraw,
                   t: float) -> None:
        gi, galpha = self._active_group(t)
        if gi is None or galpha <= 0.01:
            return
        g = self.groups[gi]
        L = self._layout_group(gi)

        # Entrance rise (fade already handled by the timing engine alpha)
        appear = max(g.get("display_start", g["start"]), self.hook_end - 0.15)
        dy = int(M.slide_up(t, appear, 0.4, 54))
        if galpha <= 0.01:
            return

        card_w, card_h = L["card_w"], L["card_h"]
        card_x = (D.WIDTH - card_w) // 2
        zone_top, zone_bot = self._body_top, self._body_bottom
        card_y = zone_top + max(0, (zone_bot - zone_top - card_h) // 2) + dy
        card_y = min(card_y, zone_bot - card_h) if card_h < zone_bot - zone_top else zone_top

        layer = self._card_layer(card_w, card_h, self.T.card_radius,
                                 self.T.card_fill, self.T.card_alpha,
                                 self.T.card_border)
        m = 56
        if galpha < 1.0:
            layer = layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * galpha)))
        frame.paste(layer, (card_x - m, card_y - m), layer)

        # Karaoke words
        base_y = card_y + CARD_PAD
        for slot in L["slots"]:
            self._draw_karaoke_word(draw, slot, t, g, L, card_x,
                                    base_y, galpha)

        # English panel
        if L["panel"]:
            self._draw_panel(frame, draw, L, g, t, card_x, card_w,
                             base_y + L["text_h"] + 24, galpha)

    def _draw_karaoke_word(self, draw, slot, t, g, L, card_x, base_y,
                           galpha: float) -> None:
        T = self.T
        w = slot["word"]
        cy = base_y + slot["line"] * L["line_h"] + L["line_h"] // 2
        cx = card_x + slot["cx"]

        scale = 1.0
        if w is not None:
            ws, we = w["start"], w["end"]
            active = (ws - WORD_ANTICIPATION) <= t <= we
            if w.get("is_english"):
                color = T.word_english
                if active:
                    scale = M.pulse(t, ws - WORD_ANTICIPATION, hi=1.08)
            elif active:
                color = T.word_active
                scale = M.pulse(t, ws - WORD_ANTICIPATION, hi=1.07)
            elif t > we:
                color = T.word_past
            else:
                color = T.word_upcoming
        else:
            color = T.text_primary

        f = L["font"]
        if scale > 1.01:
            f = load_font(T.name, "text", int(L["size"] * scale))
        draw.text((cx, cy), slot["text"], font=f,
                  fill=(*color, int(255 * galpha)), anchor="mm")

    def _draw_panel(self, frame, draw, L, g, t, card_x, card_w, py,
                    galpha: float) -> None:
        """Accent-tinted inner panel: English display word + translation."""
        T = self.T
        P = L["panel"]
        appear = max(g.get("display_start", g["start"]) + 0.18,
                     self.hook_end - 0.1)
        scale, pa = M.pop_in(t, appear, 0.36)
        pa *= galpha
        if pa <= 0.01:
            return

        px0, px1 = card_x + CARD_PAD - 16, card_x + card_w - CARD_PAD + 16
        r = 32
        draw.rounded_rectangle(
            [px0, py, px1, py + P["h"]], radius=r,
            fill=(*T.inner_panel_fill[:3], int(T.inner_panel_fill[3] * pa)))
        # Accent tick on the left edge
        draw.rounded_rectangle([px0, py + 24, px0 + 8, py + P["h"] - 24],
                               radius=4, fill=(*T.accent, int(230 * pa)))

        hero = T.accent_warm if T.name == "adults" else T.word_english
        cy = py + 36 + P["en_lh"] // 2
        for line in P["en_lines"]:
            f = P["en_font"]
            if abs(scale - 1.0) > 0.02 and scale > 0:
                f = load_font(T.name, "display",
                              max(8, int(P["en_font"].size * min(scale, 1.08))))
            draw.text(((px0 + px1) / 2, cy), line, font=f,
                      fill=(*hero, int(255 * pa)), anchor="mm")
            cy += P["en_lh"]
        cy += 14 - P["en_lh"] // 2 + P["tr_lh"] // 2
        for line in P["tr_lines"]:
            draw.text(((px0 + px1) / 2, cy), line, font=P["tr_font"],
                      fill=(*T.text_secondary, int(255 * pa)), anchor="mm")
            cy += P["tr_lh"]

    # ── CTA ──────────────────────────────────────────────────────

    def _draw_cta(self, frame: Image.Image, draw: ImageDraw.ImageDraw,
                  t: float) -> None:
        T = self.T
        scale, a = M.pop_in(t, self.cta_start + 0.1, 0.42)
        if a <= 0:
            return
        zone_top, zone_bot = self._body_top, self._body_bottom
        cy = zone_top + (zone_bot - zone_top) // 2 - 40

        size = 84
        f = load_font(T.name, "display", max(8, int(size * scale)) if scale > 0 else size)
        draw.text((D.WIDTH / 2, cy), T.cta_text, font=f,
                  fill=(*T.text_primary, int(255 * a)), anchor="mm")
        # Accent underline bar beneath the headline
        bw = int(280 * M.clamp01(scale))
        if bw > 8:
            draw.rounded_rectangle(
                [D.WIDTH / 2 - bw / 2, cy + 62, D.WIDTH / 2 + bw / 2, cy + 74],
                radius=6, fill=(*T.accent_warm, int(255 * a)))

        # Handle pill
        ha = M.fade(t, self.cta_start + 0.35, 0.3)
        if ha > 0:
            hf = load_font(T.name, "text", D.TYPE_SCALE["caption"]["size"] + 6)
            tw = draw.textlength(T.brand_handle, font=hf)
            hy = cy + 96
            pad_x, pad_y = 36, 20
            x0 = (D.WIDTH - tw) / 2 - pad_x
            x1 = (D.WIDTH + tw) / 2 + pad_x
            dy2 = int(M.slide_up(t, self.cta_start + 0.35, 0.4, 30))
            draw.rounded_rectangle(
                [x0, hy - pad_y + dy2, x1, hy + 42 + pad_y + dy2],
                radius=48, fill=(*T.accent, int(255 * ha)))
            draw.text((D.WIDTH / 2, hy + 21 + dy2), T.brand_handle, font=hf,
                      fill=(255, 255, 255, int(255 * ha)), anchor="mm")
