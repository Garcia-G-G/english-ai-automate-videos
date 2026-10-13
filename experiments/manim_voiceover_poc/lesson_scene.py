"""One Manim scene that renders any lesson.json — the voice leads, the picture follows.

    LESSON=lessons/third-person-s.json VOICE_DIR=audio/third-person-s/matilda \
        manim -qm lesson_scene.py Lesson
    THEME=dark SFX=0 …                      # another look; no sound effects

Each beat is one `with self.voiceover(...)` block: the pre-generated narration
(see gen_audio.py) sets the pace, and the beat's drawing waits for the words it
animates on (`lesson.marked_narration`). Nothing has a fixed duration.

Look: brand.json → manim.themes (sand by default, stone, dark; see theme.py), on a paper
with a soft vignette and grain that is the camera's background image. Fredoka Bold for
chips, headings and English, Manrope for Spanish and captions, both registered from
assets/fonts (never a system font). One grammar colour code in every lesson: subject
blue, auxiliary yellow, main verb green, error red. Sizes are cap heights in pixels at
1080p, for a phone: English chips ≥ 64 px, glosses ≥ 44, captions ≥ 40.

The camera eases in (≈ 1.06×) on a transform morph, a sentence fix and a sort, and back
on the next beat; the captions and the chapter bar are pinned to the frame, so a push
never crops them. Sound effects (sfx.py) sit 22 dB under the voice; SFX=0 turns them off.
"""
import json
import math
import os
from pathlib import Path

import manimpango
from manim import (
    BOLD, DOWN, LEFT, NORMAL, ORIGIN, PI, RIGHT, UP, AnimationGroup, Arc, Circle, Create, Dot,
    DashedLine, DashedVMobject, FadeIn, FadeOut, GrowFromCenter, ImageMobject, LaggedStart, Line,
    MovingCameraScene, Polygon, Rectangle, ReplacementTransform, RoundedRectangle, Text, Transform,
    Succession, ValueTracker, VGroup, VMobject, Wait, Wiggle, Write, config, rush_into, smooth, there_and_back,
)
from manim_voiceover import VoiceoverScene

import lesson as L
import sfx as S
import theme as TH
from voices import PrerecordedService

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BRAND_DIR = REPO / "assets" / "branding" / "english-unlimited"
BRAND = json.loads((BRAND_DIR / "brand.json").read_text(encoding="utf-8"))
LESSON_PATH = HERE / os.environ.get("LESSON", "lessons/third-person-s.json")
try:
    _LESSON = L.load(LESSON_PATH)
except (OSError, ValueError):
    _LESSON = {}
THEME = L.theme_name(_LESSON)
P = TH.palette(THEME)
BG, CARD, TEXT, MUTED = P["bg"], P["card"], P["text"], P["muted"]
YELLOW, BLUE, GREEN, RED = P["yellow"], P["blue"], P["green"], P["red"]
SURFACE, LINE_C, SOFT, DIM, EN_DIM = P["surface"], P["line"], P["soft"], P["dim"], P["en_dim"]
ACCENT_TEXT, ACCENT_LINE = P["accent_text"], P["accent_line"]
PAPER = BRAND["color"]["paper"]
mix = TH.mix
ROLE = {"blue": BLUE, "yellow": YELLOW, "green": GREEN, "red": RED}          # highlight colours = the code
ROLE_WORDS = {"sujeto": BLUE, "subject": BLUE, "auxiliar": YELLOW, "aux": YELLOW, "modal": YELLOW,
              "verbo": GREEN, "verb": GREEN, "verbo principal": GREEN, "error": RED, "incorrecto": RED}
LANE_COLORS = (ACCENT_LINE, BLUE, GREEN)
SFX_ON = os.environ.get("SFX", "1") != "0"


def ink(fill):
    return TH.ink_on(fill, P)


# Fonts: brand.json names the files; registered here so Pango never substitutes.
DISPLAY, BODY = BRAND["font"]["display"]["family"], BRAND["font"]["body"]["family"]
for _key in ("display", "body"):
    if not manimpango.register_font(str(REPO / BRAND["font"][_key]["file"])):
        raise SystemExit(f"could not register {BRAND['font'][_key]['file']}")

# Sizes: cap height in px at 1080p (the frame is 8 units tall at every quality).
PX = 8 / 1080
CHIP_PX, GLOSS_PX, CAPTION_PX = 68, 46, 42
TITLE_PX, HEADING_PX, QUESTION_PX, BODY_PX = 100, 84, 60, 48
DIALOG_EN_PX, DIALOG_ES_PX, TABLE_PX, LABEL_PX, BIN_PX = 54, 44, 56, 46, 56
BAR_PX, TAG_PX, SMALL_PX = 26, 32, 36

FRAME_W, FRAME_H = config.frame_width, config.frame_height
STAGE_W = 0.8 * FRAME_W                            # layouts use ~80 % of the width, centred
BAR_Y = 3.62
CAPTION_Y, CAPTION_H = -3.19, 1.34                 # the karaoke band at the bottom
STAGE_TOP, STAGE_BOTTOM = 3.25, -2.38
STAGE_MID = (STAGE_TOP + STAGE_BOTTOM) / 2
CAP_LINE_W, CAP_LINES = 12.6, 2
CHIP_H = 2.0 * CHIP_PX * PX
END_SCREEN_S = L.END_SCREEN_S
PUSH = 1.06                                        # camera focus: how far in, and how fast
PUSH_S = 0.6

config.background_color = BG
config.background_image = str(TH.background_png(THEME, config.pixel_width, config.pixel_height))

_cap_units, _widths = {}, {}


def _cap(font, weight):
    key = (font, weight)
    if key not in _cap_units:
        _cap_units[key] = Text("H", font=font, weight=weight).height
    return _cap_units[key]


def text(s, px, color=TEXT, font=DISPLAY, weight=None, **kw):
    """A Text whose capital letters are `px` pixels tall at 1080p."""
    weight = weight or (BOLD if font == DISPLAY else NORMAL)
    t = Text(s, font=font, weight=weight, color=color, disable_ligatures=True, **kw)
    return t.scale(px * PX / _cap(font, weight))


def measure(s, px, font=DISPLAY, weight=None):
    weight = weight or (BOLD if font == DISPLAY else NORMAL)
    key = (s, font, weight)
    if key not in _widths:
        _widths[key] = Text(s, font=font, weight=weight, disable_ligatures=True).width / _cap(font, weight)
    return _widths[key] * px * PX


def wrap(s, px, max_w, font=DISPLAY, weight=None):
    """Greedy line breaking on measured widths — text is wrapped, never shrunk below its size."""
    lines, line = [], []
    for word in s.split():
        if line and measure(" ".join(line + [word]), px, font, weight) > max_w:
            lines.append(" ".join(line))
            line = []
        line.append(word)
    if line:
        lines.append(" ".join(line))
    return lines or [s]


def para(s, px, max_w, color=TEXT, font=DISPLAY, weight=None, align="center", buff=None):
    lines = VGroup(*[text(line, px, color, font, weight) for line in wrap(s, px, max_w, font, weight)])
    edge = {"center": ORIGIN, "left": LEFT}[align]
    return lines.arrange(DOWN, buff=buff if buff is not None else 0.55 * px * PX, aligned_edge=edge)


def fit(mobj, max_w=STAGE_W, max_h=None, grow=1.0):
    """Scale to fit the box; with grow > 1, also scale UP (by at most `grow`) to fill it."""
    k = max_w / mobj.width if mobj.width else 1
    if max_h and mobj.height:
        k = min(k, max_h / mobj.height)
    k = min(k, grow)
    if k < 1 or grow > 1:
        mobj.scale(k)
    return mobj


def card(inner, fill=SURFACE, pad=0.4, stroke=LINE_C, radius=0.25, stroke_width=2):
    box = RoundedRectangle(corner_radius=radius, width=inner.width + 2 * pad, height=inner.height + 2 * pad,
                           fill_color=fill, fill_opacity=1, stroke_color=stroke, stroke_width=stroke_width).move_to(inner)
    return VGroup(box, inner)


def centre_on(*mobjs, y=STAGE_MID):
    """Move a block (several mobjects) so its middle sits at `y`: the space above the captions."""
    block = VGroup(*mobjs)
    block.shift(UP * (y - block.get_center()[1]))
    return block


# ── chips: one per word, punctuation attached, all on one baseline ─────────────

def chips_for(words, px=CHIP_PX, max_w=STAGE_W, center=ORIGIN, pitch=None):
    """VGroup of chips (VGroup(box, label)) laid out in centred rows. The words are set as
    ONE Text and sliced, so every chip shares the sentence's baseline; a row breaks
    instead of shrinking the type. With ligatures off, glyph n is character n (a space
    is an empty glyph), so a word is the slice of its characters."""
    string = " ".join(words)
    glyphs = text(string, px).submobjects
    labels, k = [], 0
    for w in words:
        labels.append(VGroup(*[g for g in glyphs[k:k + len(w)] if g.has_points()]))
        k += len(w) + 1
    if len(glyphs) != len(string) or not all(len(lab) for lab in labels):   # unexpected shaping: one Text per word
        labels = [text(w, px) for w in words]
        for lab in labels:
            lab.shift(UP * (0 - lab.get_bottom()[1]))
    bottoms = sorted(g.get_bottom()[1] for lab in labels for g in lab if g.has_points())
    baseline = bottoms[len(bottoms) // 2]
    cap = px * PX
    pad_x, gap = 0.6 * cap, 0.26
    chips = []
    for lab in labels:
        box = RoundedRectangle(corner_radius=0.55 * cap, width=lab.width + 2 * pad_x,
                               height=2.0 * cap, fill_color=SURFACE, fill_opacity=1, stroke_color=LINE_C, stroke_width=2)
        box.move_to([lab.get_center()[0], baseline + 0.5 * cap, 0])
        chips.append(VGroup(box, lab))
    rows, row, width = [], [], 0.0
    for c in chips:
        w = c[0].width
        if row and width + gap + w > max_w:
            rows.append(row)
            row, width = [], 0.0
        width += (gap if row else 0) + w
        row.append(c)
    if row:
        rows.append(row)
    pitch = pitch or 2.0 * cap + 0.5
    top = center[1] + (len(rows) - 1) * pitch / 2
    for r, row in enumerate(rows):
        total = sum(c[0].width for c in row) + gap * (len(row) - 1)
        x = center[0] - total / 2
        for c in row:
            c.shift([x + c[0].width / 2, top - r * pitch, 0] - c[0].get_center())
            x += c[0].width + gap
    group = VGroup(*chips)
    group.rows = len(rows)
    return group


def paint(c, color):
    """A chip in a role colour: the fill takes the colour, the word takes the ink that reads on it."""
    c[0].set_fill(color).set_stroke(color)
    c[1].set_color(ink(color))
    return c


def check_mark(center, r=0.24, color=GREEN):
    ring = Circle(radius=r, color=color, stroke_width=4).move_to(center)
    tick = VGroup(Line(center + LEFT * 0.11 + DOWN * 0.01, center + DOWN * 0.09, color=color, stroke_width=4),
                  Line(center + DOWN * 0.09, center + RIGHT * 0.13 + UP * 0.11, color=color, stroke_width=4))
    return VGroup(ring, tick)


def pause_icon(h=0.36, color=TEXT):
    bar = lambda: RoundedRectangle(corner_radius=0.04, width=h * 0.3, height=h, fill_color=color, fill_opacity=1,
                                   stroke_width=0)
    return VGroup(bar(), bar()).arrange(RIGHT, buff=h * 0.22)


def caret(x, top, bottom):
    """The proofreader's ‸ in red, drawn (no font has to carry the glyph): a thin bar where
    the missing word goes and the caret under the line."""
    bar = Line([x, top, 0], [x, bottom, 0], color=RED, stroke_width=6)
    hat = VMobject(color=RED, stroke_width=7).set_points_as_corners(
        [[x - 0.17, bottom - 0.3, 0], [x, bottom - 0.04, 0], [x + 0.17, bottom - 0.3, 0]])
    return VGroup(bar, hat)


class Lesson(VoiceoverScene, MovingCameraScene):
    def construct(self):
        self.lesson = L.load(LESSON_PATH)
        problems = L.validate(self.lesson)
        if problems:
            raise SystemExit("lesson.json is not renderable:\n  " + "\n  ".join(problems))
        voice_dir = HERE / os.environ["VOICE_DIR"]
        self.set_speech_service(PrerecordedService(voice_dir))
        manifest = json.loads((voice_dir / "manifest.json").read_text(encoding="utf-8"))
        self.word_files = {b["id"]: voice_dir / b["words"] for b in manifest["beats"]}

        self.hud = None            # the top bar (lesson title + chapter progress), once the title card has played
        self.hud_ready = not any(b["type"] == "title" for b in self.lesson["beats"])
        self.stage = VGroup()      # everything a beat may leave behind
        self.sentence = None       # the chips of the current sentence, for `same` and for continuity
        self.pushed = False        # the camera is eased in
        self.speech = []           # [(start, end)] of the current beat's words, absolute — sfx duck under them
        self.effects = []          # every sound effect played: the render's timeline records them
        self.cues = []             # every cue: its bookmark time and when its animation really started
        self.captions_on = os.environ.get("CAPTIONS", "1") != "0"
        self.timeline = []         # [{id, type, text?, start}] — chapters and the WP-38 poster read it
        self.parts = self.chapter_plan()
        self.clock = None          # (start, duration) of the beat playing, for the progress bar
        for n, beat in enumerate(self.lesson["beats"]):
            self.beat_index = n
            self.play_beat(beat)
        self.wait(L.FINAL_HOLD_S)
        self.end_screen()
        self.write_timeline()
        self.report_sync()

    def report_sync(self):
        report = L.sync_report(self.cues)
        if report["late"]:
            lines = [f"  {c['beat']} {c['key']} «{c['word']}»: started {c['start'] - c['cue']:+.2f} s after its word"
                     for c in report["late"]]
            bar = "!" * 78
            print(f"\n{bar}\nOUT OF SYNC: {len(report['late'])} cue(s) start more than {L.MAX_CUE_LAG} s after the "
                  f"word they animate on\n" + "\n".join(lines) + f"\n{bar}\n", flush=True)

    def write_timeline(self):
        out = Path(os.environ.get("TIMELINE_OUT", HERE / "media" / "timeline" / f"{self.lesson['id']}.json"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"lesson": self.lesson["id"], "theme": THEME, "sfx": SFX_ON,
                                   "duration": round(float(self.renderer.time), 2), "beats": self.timeline,
                                   "effects": self.effects, "cues": self.cues,
                                   "sync": {k: v for k, v in L.sync_report(self.cues).items() if k != "late"}},
                                  ensure_ascii=False, indent=1))

    # ── plumbing ──────────────────────────────────────────────────────────────

    def continues(self, beat):
        """A transform whose `from` is the sentence already on screen morphs from it."""
        return (beat["type"] == "transform" and self.sentence is not None
                and [L.norm(w) for w in beat["from"].split()] == [L.norm(w) for w in self.sentence["words"]])

    def play_beat(self, beat):
        kind = beat["type"]
        keep_sentence = (kind == "sentence" and beat.get("same") and self.sentence is not None) or self.continues(beat)
        if not keep_sentence:
            self.clear_stage()
        elif self.pushed:
            self.play(self.release())
        narration, marks = L.marked_narration(beat)
        self.timeline.append({"id": beat["id"], "type": kind, "text": beat.get("text") or beat.get("heading"),
                              "start": round(float(self.renderer.time), 2)})
        with self.voiceover(text=narration, beat_id=beat["id"]) as tracker:
            self.beat_id = beat["id"]
            self.clock = (tracker.start_t, tracker.duration)
            self.speech = self._speech(beat["id"], tracker.start_t)
            caption = self.mount_captions(beat, tracker) if self.captions_on and kind != "title" else None
            getattr(self, f"beat_{kind}")(beat, tracker, marks)
            self.safe_wait(tracker.get_remaining_duration())
        if caption is not None:
            caption.clear_updaters()
            self.remove(caption)
        # A breath between beats: longer after a section card, so the ear resets with the eye.
        self.wait(0.6 if kind == "heading" else 0.35)

    def _speech(self, beat_id, start):
        path = self.word_files.get(beat_id)
        if not path or not path.exists():
            return []
        return [(start + w["start"], start + w["end"]) for w in json.loads(path.read_text(encoding="utf-8"))]

    # ── sound effects ─────────────────────────────────────────────────────────

    def sfx(self, name, offset=0.0):
        """Play an effect `offset` seconds from now, 22 dB under the voice — 6 dB lower still
        if it lands on a spoken word."""
        if not SFX_ON:
            return
        at = float(self.renderer.time) + max(0.0, offset)
        on_word = any(a - 0.03 <= at <= b + 0.03 for a, b in self.speech)
        self.add_sound(str(S.path(name)), time_offset=max(0.0, offset), gain=-S.DUCK_DB if on_word else None)
        self.effects.append({"name": name, "t": round(at, 2), "on_word": on_word})

    # ── camera focus ──────────────────────────────────────────────────────────

    def push(self, point, delay=0.0):
        """Ease the frame ≈ 1.06× in, towards `point`, never past the original frame
        (`delay`: when, from now, the push will start — for its whoosh)."""
        frame = self.camera.frame
        w, h = FRAME_W / PUSH, FRAME_H / PUSH
        dx, dy = (FRAME_W - w) / 2, (FRAME_H - h) / 2
        target = [max(-dx, min(dx, point[0])), max(-dy, min(dy, point[1])), 0]
        self.pushed = True
        self.sfx("whoosh", delay)
        return frame.animate(run_time=PUSH_S, rate_func=smooth).set(width=w).move_to(target)

    def release(self):
        self.pushed = False
        return self.camera.frame.animate(run_time=PUSH_S, rate_func=smooth).set(width=FRAME_W).move_to(ORIGIN)

    def pin(self, mobj):
        """Keep `mobj` fixed on screen whatever the camera does (captions, the top bar)."""
        state = {"s": 1.0, "c": ORIGIN.copy()}

        def follow(m, dt=0):
            frame = self.camera.frame
            s, c = frame.width / FRAME_W, frame.get_center()
            if abs(s - state["s"]) > 1e-9 or abs(c - state["c"]).max() > 1e-9:
                m.shift(-state["c"]).scale(s / state["s"], about_point=ORIGIN).shift(c)
                state["s"], state["c"] = s, c

        follow(mobj)
        mobj.add_updater(follow)
        return mobj

    # ── karaoke captions ──────────────────────────────────────────────────────

    def mount_captions(self, beat, tracker):
        """The narration at the bottom, sentence by sentence, each word lighting up when it is
        spoken. Times come from the recorded word boundaries (ElevenLabs alignment) so the
        highlight lands on the spoken word; English (what sat in [[ ]]) is blue and bold.
        One Text per line (true baseline and kerning); words are coloured by glyph slice
        (ligatures off: glyph n is character n)."""
        words = L.tokens(beat["narration"])
        if not words:
            return None
        times = self._word_times(words, tracker)
        pages = self._caption_pages(words)          # [[line, line], ...]; line = [word, ...]
        band = RoundedRectangle(corner_radius=0.22, width=CAP_LINE_W + 0.7, height=CAPTION_H, fill_color=SURFACE,
                                fill_opacity=1, stroke_color=LINE_C, stroke_width=1.5).move_to([0, CAPTION_Y, 0])
        group, page_starts, lit_map = VGroup(band), [], []
        for page in pages:
            line_mobjs = VGroup()
            page_words = []
            for line in page:
                string = " ".join(w["text"] for w in line)
                t2w, pos = {}, 0
                for w in line:
                    if w["en"]:
                        t2w[f"[{pos}:{pos + len(w['text'])}]"] = BOLD
                    w["glyphs"] = (pos, pos + len(w["text"]))
                    pos += len(w["text"]) + 1
                mobj = text(string, CAPTION_PX, DIM, BODY, NORMAL, t2w=t2w)
                for w in line:
                    if w["en"]:
                        mobj[w["glyphs"][0]:w["glyphs"][1]].set_color(EN_DIM)
                if mobj.width > CAP_LINE_W:                       # measured layout makes this rare
                    mobj.scale_to_fit_width(CAP_LINE_W)
                line_mobjs.add(mobj)
                page_words += [(w, mobj) for w in line]
            line_mobjs.arrange(DOWN, buff=0.16).move_to([0, CAPTION_Y, 0])
            line_mobjs.set_opacity(0)
            group.add(line_mobjs)
            page_starts.append(tracker.start_t + times[page[0][0]["index"]])
            lit_map.append(page_words)
        state = {"page": -1, "lit": set()}

        def tick(mobj, dt):
            now = float(self.renderer.time)
            active = max((i for i, t0 in enumerate(page_starts) if t0 <= now + 1e-3), default=0)
            if active != state["page"]:
                for i, page_group in enumerate(mobj[1:]):
                    page_group.set_opacity(1 if i == active else 0)
                state["page"] = active
            for w, line_mobj in lit_map[active]:
                if w["index"] not in state["lit"] and tracker.start_t + times[w["index"]] <= now + 1e-3:
                    a, b = w["glyphs"]
                    line_mobj[a:b].set_color(BLUE if w["en"] else TEXT)
                    state["lit"].add(w["index"])

        group.add_updater(tick)
        self.pin(group)
        self.add(group)
        return group

    def _word_times(self, words, tracker):
        """Seconds from the beat's start for each token, from the recorded boundaries; tokens
        the alignment skipped get the time interpolated between their neighbours."""
        by_offset = {}
        for b in tracker.data.get("word_boundaries", []):
            by_offset.setdefault(b["text_offset"], b["audio_offset"] / 10_000_000)
        times = [by_offset.get(w["offset"]) for w in words]
        known = [(i, t) for i, t in enumerate(times) if t is not None]
        if not known:
            return [tracker.duration * i / max(1, len(words)) for i in range(len(words))]
        for i in range(len(times)):
            if times[i] is None:
                before = [(j, t) for j, t in known if j < i]
                after = [(j, t) for j, t in known if j > i]
                if before and after:
                    (j0, t0), (j1, t1) = before[-1], after[0]
                    times[i] = t0 + (t1 - t0) * (i - j0) / (j1 - j0)
                elif before:
                    times[i] = before[-1][1]
                else:
                    times[i] = after[0][1]
        return times

    def _caption_pages(self, words):
        """Sentences → lines (greedy, on measured word widths) → pages of CAP_LINES lines."""
        space = measure("a a", CAPTION_PX, BODY, NORMAL) - 2 * measure("a", CAPTION_PX, BODY, NORMAL)
        for i, w in enumerate(words):
            w["index"] = i
        sentences, current = [], []
        for w in words:
            current.append(w)
            if w["text"][-1] in ".?!…":
                sentences.append(current)
                current = []
        if current:
            sentences.append(current)
        pages = []
        for sentence in sentences:
            lines, line, width = [], [], 0.0
            for w in sentence:
                w_width = measure(w["text"], CAPTION_PX, BODY, BOLD if w["en"] else NORMAL)
                if line and width + space + w_width > CAP_LINE_W:
                    lines.append(line)
                    line, width = [], 0.0
                width += (space if line else 0) + w_width
                line.append(w)
            if line:
                lines.append(line)
            for k in range(0, len(lines), CAP_LINES):
                pages.append(lines[k:k + CAP_LINES])
        return pages

    # ── the top bar: lesson title and chapter progress ────────────────────────

    def chapter_plan(self):
        """[(name, first beat, last beat)] — one segment per `heading`. A lesson without
        headings is one segment from its first beat after the title."""
        beats = self.lesson["beats"]
        heads = [i for i, b in enumerate(beats) if b["type"] == "heading"]
        if not heads:
            first = next((i + 1 for i, b in enumerate(beats) if b["type"] == "title"), 0)
            return [("", first, len(beats) - 1)]
        return [(beats[h]["text"], h, (heads[k + 1] - 1) if k + 1 < len(heads) else len(beats) - 1)
                for k, h in enumerate(heads)]

    def show_bar(self):
        if self.hud is not None or not self.hud_ready:
            return
        title = text(self.lesson["title"], BAR_PX, MUTED, BODY, BOLD)
        fit(title, 5.6)
        title.move_to([-STAGE_W / 2 + title.width / 2, BAR_Y, 0])
        x0, x1, gap, h = 0.4, STAGE_W / 2, 0.1, 0.075
        n = len(self.parts)
        seg_w = (x1 - x0 - gap * (n - 1)) / n
        tracks, fills = VGroup(), VGroup()
        for k in range(n):
            left = x0 + k * (seg_w + gap)
            tracks.add(RoundedRectangle(corner_radius=h / 2, width=seg_w, height=h, stroke_width=0,
                                        fill_color=LINE_C, fill_opacity=1).move_to([left + seg_w / 2, BAR_Y + 0.08, 0]))
            fills.add(Rectangle(width=seg_w, height=h, stroke_width=0, fill_color=ACCENT_LINE, fill_opacity=1)
                      .move_to(tracks[k]))
        label = VGroup()
        state = {"part": None, "frac": [None] * n}

        def update(group, dt=0):
            k, frac = self.progress()
            for i, f in enumerate(fills):
                want = 1.0 if (k is not None and i < k) else (frac if i == k else 0.0)
                if state["frac"][i] != round(want, 4):
                    state["frac"][i] = round(want, 4)
                    f.set_opacity(1 if want > 0 else 0)
                    f.stretch_to_fit_width(max(1e-3, tracks[i].width * max(want, 1e-3)))
                    f.align_to(tracks[i], LEFT)
            name = self.parts[k][0] if k is not None else ""
            if name != state["part"]:                  # the part's name, small, under the bar
                state["part"] = name
                label.remove(*label.submobjects)
                if name:
                    scale = self.camera.frame.width / FRAME_W          # the bar is pinned: match its scale
                    new = fit(text(name, BAR_PX - 2, MUTED, BODY, NORMAL), x1 - x0).scale(scale)
                    new.next_to(tracks, DOWN, buff=0.1 * scale).align_to(tracks[-1], RIGHT)
                    label.add(new)

        hud = VGroup(title, tracks, fills, label)
        hud.add_updater(update)
        self.pin(hud)
        self.hud = hud
        self.add(hud)

    def progress(self):
        """(segment, fraction of it done) from the beat index and how far into the beat we are."""
        n, (start, dur) = self.beat_index, self.clock or (0, 1)
        inside = max(0.0, min(1.0, (float(self.renderer.time) - start) / max(dur, 1e-3)))
        for k, (_, a, b) in enumerate(self.parts):
            if a <= n <= b:
                return k, (n - a + inside) / (b - a + 1)
        return (None, 0.0) if n < self.parts[0][1] else (len(self.parts) - 1, 1.0)

    def clear_stage(self):
        anims = []
        if len(self.stage) > 0:
            anims.append(FadeOut(self.stage, run_time=0.35))
        if self.pushed:
            anims.append(self.release())
        if anims:
            self.play(*anims)
            self.remove(*self.stage)
        self.stage = VGroup()
        self.sentence = None

    def keep(self, *mobjs):
        for m in mobjs:
            self.stage.add(m)
        return mobjs[0] if len(mobjs) == 1 else mobjs

    def cue_time(self, tracker, marks, key, fraction):
        """When `key` is spoken (absolute scene time, from its bookmark) or, if the narration
        never says it, when `fraction` of the narration has elapsed."""
        if key in marks:
            return tracker.bookmark_times[marks[key]]
        return tracker.start_t + fraction * tracker.duration

    def until(self, tracker, marks, key, fraction):
        """Seconds from now until the cue (negative: it has passed)."""
        return self.cue_time(tracker, marks, key, fraction) - float(self.renderer.time)

    def record(self, key, word, cue, fallback, start=None):
        rec = {"beat": self.beat_id, "key": key, "word": word, "cue": round(cue, 3), "fallback": fallback,
               "start": round(float(self.renderer.time) if start is None else start, 3)}
        self.cues.append(rec)
        return rec

    def at(self, tracker, marks, key, fraction, word=None):
        """Wait for the cue, and record it: the animation the caller plays next starts now."""
        cue = self.cue_time(tracker, marks, key, fraction)
        self.safe_wait(cue - float(self.renderer.time))
        return self.record(key, word or key, cue, key not in marks)

    def run_until(self, nominal, next_cue, floor=0.12):
        """An animation's run time, shortened so it is done CUE_MARGIN before the next cue."""
        if next_cue is None:
            return nominal
        return max(floor, min(nominal, next_cue - float(self.renderer.time) - L.CUE_MARGIN))

    # ── beats ─────────────────────────────────────────────────────────────────

    def beat_title(self, beat, tracker, marks):
        title = para(beat.get("text", self.lesson["title"]), TITLE_PX, STAGE_W)
        fit(title, STAGE_W, 3.2)
        kicker_text = beat.get("kicker") or self.lesson.get("kicker") or ""
        rule = Line(LEFT * 1.6, RIGHT * 1.6, color=YELLOW, stroke_width=12).next_to(title, DOWN, buff=0.45)
        group = VGroup(title, rule)
        anims = [Write(title), Create(rule)]
        if kicker_text:
            kicker = text(kicker_text.upper(), SMALL_PX, ACCENT_TEXT, BODY, BOLD).next_to(title, UP, buff=0.5)
            group.add(kicker)
            anims.append(FadeIn(kicker, shift=DOWN * 0.15))
        centre_on(group)
        if self.hud is not None:
            self.hud.set_opacity(0)
        self.play(*anims, run_time=min(1.6, tracker.duration * 0.5))
        self.safe_wait(tracker.get_remaining_duration() - 0.9)
        self.play(FadeOut(group), run_time=0.5)
        self.remove(group)
        self.hud_ready = True
        if self.hud is None:
            self.show_bar()
        else:
            self.hud.set_opacity(1)

    def beat_heading(self, beat, tracker, marks):
        self.show_bar()
        heading = fit(para(beat["text"], HEADING_PX, STAGE_W), STAGE_W, 3.0)
        rule = Line(LEFT * 1.4, RIGHT * 1.4, color=YELLOW, stroke_width=10).next_to(heading, DOWN, buff=0.45)
        centre_on(heading, rule)
        self.keep(heading, rule)
        self.play(FadeIn(heading, shift=UP * 0.2), Create(rule), run_time=min(1.0, tracker.duration * 0.5))

    def beat_sentence(self, beat, tracker, marks):
        self.show_bar()
        if not (beat.get("same") and self.sentence is not None):
            words = beat["text"].split()                  # punctuation stays on its word: «seven.»
            chips = chips_for(words, center=[0, STAGE_MID, 0], pitch=CHIP_H + 0.6)
            gloss = None
            if beat.get("gloss"):
                gloss = para(beat["gloss"], GLOSS_PX, STAGE_W, SOFT, BODY).next_to(chips, DOWN, buff=0.75)
            centre_on(chips, *([gloss] if gloss else []))
            self.sentence = {"chips": chips, "words": words, "tags": {}, "colors": {}}
            self.keep(chips)
            first = [w for w in list((beat.get("highlight") or {})) + list((beat.get("tags") or {}))
                     + ([beat["fix"]["to"]] if beat.get("fix") else [])]
            first_at = self.cue_time(tracker, marks, L.cue_key(first[0]), 0.15) if first else None
            entrance = [LaggedStart(*[FadeIn(c, scale=0.75) for c in chips], lag_ratio=0.25)]
            if gloss:
                self.keep(gloss)
                entrance.append(FadeIn(gloss))
            self.play(AnimationGroup(*entrance, lag_ratio=0.5),             # done before the first cue is said
                      run_time=self.run_until(min(1.2, 0.18 * len(chips) + 0.6), first_at, floor=0.1))
        chips, words = self.sentence["chips"], self.sentence["words"]

        def find(word):
            for i, w in enumerate(words):
                if L.norm(w) == L.norm(word):
                    return i
            return None

        # the cues in the order they play: highlights, tags, the fix — each animation is done
        # before the next cue
        steps = [("hl", w, c) for w, c in (beat.get("highlight") or {}).items() if find(w) is not None]
        steps += [("tag", w, t) for w, t in (beat.get("tags") or {}).items() if find(w) is not None]
        if beat.get("fix") and find(beat["fix"]["from"]) is not None:
            steps.append(("fix", beat["fix"]["to"], beat["fix"]["from"]))
        n_cues = max(1, len(steps))
        times = [self.cue_time(tracker, marks, L.cue_key(w), (0.55 if kind == "fix" else 0.15 + 0.6 * (k + 1) / n_cues))
                 for k, (kind, w, _) in enumerate(steps)]
        nxt = lambda k: times[k + 1] if k + 1 < len(times) else None
        for k, (kind, word, value) in enumerate(steps):
            if kind != "hl":
                continue
            i = find(word)
            color = value
            self.at(tracker, marks, L.cue_key(word), 0.15 + 0.6 * (k + 1) / n_cues, word=word)
            self.sentence["colors"][i] = ROLE[color]
            self.play(chips[i][0].animate.set_fill(ROLE[color]).set_stroke(ROLE[color]),
                      chips[i][1].animate.set_color(ink(ROLE[color])), run_time=self.run_until(0.35, nxt(k)))
        for k, (kind, word, label) in enumerate(steps):
            if kind != "tag":
                continue
            i = find(word)
            self.at(tracker, marks, L.cue_key(word), 0.15 + 0.6 * (k + 1) / n_cues, word=word)
            role = ROLE_WORDS.get(label.lower().strip()) or self.sentence["colors"].get(i, MUTED)
            if role == YELLOW and not P["dark"]:
                role = ACCENT_LINE                         # yellow is never text on paper
            tag = text(label.upper(), TAG_PX, role, BODY, BOLD).next_to(chips[i], DOWN, buff=0.16)
            self.sentence["tags"][word] = tag
            self.keep(tag)
            self.play(FadeIn(tag, shift=UP * 0.1), run_time=self.run_until(0.3, nxt(k)))
        if steps and steps[-1][0] == "fix":
            src, dst = beat["fix"]["from"], beat["fix"]["to"]
            i = find(src)
            if i is not None:
                self.at(tracker, marks, L.cue_key(dst), 0.55, word=dst)
                fixed = words[:i] + [dst + words[i][len(words[i].rstrip(L.PUNCT)):]
                                     if L.norm(dst) != L.norm(words[i]) else words[i]] + words[i + 1:]
                layout = chips_for(fixed, center=chips.get_center(), pitch=CHIP_H + 0.6)
                anims = []
                for k, c in enumerate(chips):
                    if k == i:
                        anims.append(Transform(c, paint(layout[k], GREEN)))
                    else:
                        anims.append(c.animate.shift(layout[k][0].get_center() - c[0].get_center()))
                self.sfx("pop", 0.55)
                self.play(AnimationGroup(*anims, run_time=0.6), self.push(layout[i].get_center()))
                words[:] = fixed
                self.sentence["colors"][i] = GREEN

    def beat_dialogue(self, beat, tracker, marks):
        """Bubbles at reading size; when the next one would not fit, the conversation
        scrolls up instead of shrinking."""
        self.show_bar()
        lines = beat["lines"]
        bubble_w = 0.66 * STAGE_W
        column = VGroup()
        y = STAGE_TOP - 0.1
        for n, line in enumerate(lines):
            left = n % 2 == 0
            en = para(line["en"], DIALOG_EN_PX, bubble_w - 0.6, TEXT, DISPLAY, align="left")
            parts = VGroup(en)
            if line.get("es"):
                es = para(line["es"], DIALOG_ES_PX, bubble_w - 0.6, SOFT, BODY, align="left")
                es.next_to(en, DOWN, buff=0.16, aligned_edge=LEFT)
                parts.add(es)
            bubble = card(parts, SURFACE if left else mix(BG, BLUE, 0.16), pad=0.28,
                          stroke=LINE_C if left else mix(BG, BLUE, 0.45))
            speaker = text(str(line.get("speaker", "A" if left else "B")).upper(), TAG_PX, MUTED, BODY, BOLD)
            x_edge = -STAGE_W / 2 if left else STAGE_W / 2
            bubble.move_to([x_edge + (bubble.width / 2 if left else -bubble.width / 2), 0, 0])
            speaker.next_to(bubble, UP, buff=0.08, aligned_edge=LEFT if left else RIGHT)
            unit = VGroup(speaker, bubble)
            top = y if not len(column) else column[-1].get_bottom()[1] - 0.3
            unit.shift(UP * (top - unit.get_top()[1]))
            overflow = STAGE_BOTTOM + 0.1 - unit.get_bottom()[1]
            self.at(tracker, marks, f"#{n}", 0.05 + 0.85 * n / len(lines), word=line["en"].split()[0])
            later = (self.cue_time(tracker, marks, f"#{n + 1}", 0.05 + 0.85 * (n + 1) / len(lines))
                     if n + 1 < len(lines) else None)
            anims, leaving = [FadeIn(unit, shift=(RIGHT if left else LEFT) * 0.25)], []
            if overflow > 0:
                unit.shift(UP * overflow)
                for u in column:
                    if u.get_bottom()[1] + overflow > STAGE_TOP:
                        leaving.append(u)
                        anims.append(u.animate.shift(UP * overflow).set_opacity(0))
                    else:
                        anims.append(u.animate.shift(UP * overflow))
            self.play(*anims, run_time=self.run_until(0.45, later))
            for u in leaving:
                column.remove(u)
                self.stage.remove(u)
                self.remove(u)
            column.add(unit)
            self.keep(unit)

    def beat_table(self, beat, tracker, marks):
        self.show_bar()
        rows, emphasis = beat["rows"], set(beat.get("emphasis", []))
        table = VGroup()
        if beat.get("headers"):
            table.add(VGroup(*[text(h.upper(), TAG_PX, MUTED, BODY, BOLD) for h in beat["headers"]]))
        for row in rows:
            table.add(VGroup(*[text(str(c), TABLE_PX, GREEN if str(c) in emphasis else TEXT) for c in row]))
        ncols = max(len(r) for r in table)
        col_w = [max(r[i].width for r in table if i < len(r)) for i in range(ncols)]
        gap = 1.0
        for r in table:
            x = 0
            for i, cell in enumerate(r):
                cell.move_to([x + cell.width / 2, 0, 0])
                x += col_w[i] + gap
        table.arrange(DOWN, aligned_edge=LEFT, buff=0.42)
        width = sum(col_w) + gap * (ncols - 1)
        rules = VGroup(*[Line([0, 0, 0], [width + 0.6, 0, 0], color=LINE_C, stroke_width=2)
                         .move_to([table.get_left()[0] + width / 2, (table[k].get_bottom()[1] + table[k + 1].get_top()[1]) / 2, 0])
                         for k in range(len(table) - 1)])
        whole = VGroup(table, rules)
        fit(whole, STAGE_W, STAGE_TOP - STAGE_BOTTOM - 0.5, grow=1.5).move_to([0, STAGE_MID, 0])
        self.keep(whole)
        start = 1 if beat.get("headers") else 0
        first = self.cue_time(tracker, marks, "#0", 0.1)
        self.play(*([FadeIn(table[0])] if start else []), Create(rules),        # the frame is up before row 1 is said
                  run_time=self.run_until(0.5, first, floor=0.1))
        for n, row in enumerate(table[start:]):
            self.at(tracker, marks, f"#{n}", 0.1 + 0.8 * n / len(rows), word=str(rows[n][0]))
            later = (self.cue_time(tracker, marks, f"#{n + 1}", 0.1 + 0.8 * (n + 1) / len(rows))
                     if n + 1 < len(rows) else None)
            self.play(FadeIn(row, shift=RIGHT * 0.2), run_time=self.run_until(0.3, later))

    def beat_list(self, beat, tracker, marks, checks=False):
        self.show_bar()
        items = beat["items"]
        group = VGroup()
        for item in items:
            label = para(item, BODY_PX, STAGE_W - 1.0, TEXT, BODY, align="left")
            bullet = check_mark(ORIGIN, 0.24) if checks else Dot(radius=0.11, color=ACCENT_LINE)
            bullet.next_to(label[0], LEFT, buff=0.4)
            group.add(VGroup(bullet, label))
        group.arrange(DOWN, aligned_edge=LEFT, buff=0.42)
        head = None
        if beat.get("heading"):
            head = para(beat["heading"], HEADING_PX * 0.78, STAGE_W).next_to(group, UP, buff=0.6)
        whole = VGroup(*([head] if head else []), group)
        fit(whole, STAGE_W, STAGE_TOP - STAGE_BOTTOM - 0.2, grow=1.3).move_to([0, STAGE_MID, 0])
        if head:
            head.set_x(0)
        self.keep(whole)
        if head:
            self.play(FadeIn(head), run_time=self.run_until(0.35, self.cue_time(tracker, marks, "#0", 0.1), floor=0.1))
        for n, (row, item) in enumerate(zip(group, items)):
            self.at(tracker, marks, f"#{n}", 0.1 + 0.8 * n / len(items), word=item.split()[0])
            later = (self.cue_time(tracker, marks, f"#{n + 1}", 0.1 + 0.8 * (n + 1) / len(items))
                     if n + 1 < len(items) else None)
            self.play(FadeIn(row, shift=RIGHT * 0.2), run_time=self.run_until(0.3, later))

    def beat_recap(self, beat, tracker, marks):
        self.beat_list(beat, tracker, marks, checks=True)

    def beat_tip(self, beat, tracker, marks):
        self.show_bar()
        body = para(beat["text"], BODY_PX + 2, STAGE_W - 1.4, TEXT, BODY, align="left")
        label = card(text("TIP", TAG_PX, ink(YELLOW), BODY, BOLD), YELLOW, pad=0.14, stroke=YELLOW, radius=0.12)
        inner = VGroup(label, body).arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        box = card(inner, mix(BG, YELLOW, 0.10 if P["dark"] else 0.22), pad=0.55, stroke=ACCENT_LINE, stroke_width=3)
        fit(box, STAGE_W, STAGE_TOP - STAGE_BOTTOM).move_to([0, STAGE_MID, 0])
        self.keep(box)
        self.play(FadeIn(box, scale=0.95), run_time=min(0.6, tracker.duration * 0.3))

    def beat_quiz(self, beat, tracker, marks):
        self.show_bar()
        question = para(beat["question"], QUESTION_PX, STAGE_W)
        options = VGroup()
        for n, option in enumerate(beat["options"]):
            letter = text("ABCD"[n], BODY_PX, ACCENT_TEXT)
            label = para(option, BODY_PX, 7.4, TEXT, BODY, align="left")
            row = VGroup(letter, label).arrange(RIGHT, buff=0.45)
            options.add(card(row, SURFACE, pad=0.26))
        options.arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        width = max(o.width for o in options)
        for o in options:                                    # one width: the cards read as a set
            o[0].stretch_to_fit_width(width).align_to(o[1], LEFT).shift(LEFT * 0.26)
        whole = VGroup(question, options).arrange(DOWN, buff=0.55)
        fit(whole, STAGE_W, STAGE_TOP - STAGE_BOTTOM - 0.8, grow=1.15).move_to([0, STAGE_MID, 0])
        self.keep(question, options)
        self.play(FadeIn(question, shift=DOWN * 0.15), run_time=0.4)
        self.play(LaggedStart(*[FadeIn(o, shift=RIGHT * 0.15) for o in options], lag_ratio=0.4, run_time=0.6))

        # {{pause:N}} in the narration = time to think: a ring fills over those seconds,
        # beside it «Pausa y piénsalo» — the viewer may pause the video. A quiet tick a second.
        pause_marks = [k for k in marks if k.startswith("pause:")]
        if pause_marks:
            secs = (L.pauses(beat["narration"]) or [3.0])[0]
            until_resume = tracker.time_until_bookmark(marks[pause_marks[0]])
            self.safe_wait(until_resume - secs)
            for k in range(int(secs)):
                self.sfx("tick", 0.3 + k)
            ring_r = 0.42
            track = Circle(radius=ring_r, color=LINE_C, stroke_width=7)
            arc = Arc(radius=ring_r, start_angle=PI / 2, angle=-2 * PI, color=ACCENT_LINE, stroke_width=8)
            words = VGroup(pause_icon(0.34, TEXT), text("Pausa y piénsalo", GLOSS_PX, TEXT, BODY, BOLD)).arrange(RIGHT, buff=0.25)
            pill = card(words, mix(BG, YELLOW, 0.12 if P["dark"] else 0.35), pad=0.24, stroke=ACCENT_LINE, radius=0.35,
                        stroke_width=3)
            ponder = VGroup(VGroup(track, arc), pill).arrange(DOWN, buff=0.3)
            # beside the options: slide them left when the card needs the room
            need = options.get_right()[0] + 0.5 + ponder.width - STAGE_W / 2
            slide = [options.animate.shift(LEFT * need)] if need > 0 else []
            ponder.move_to([STAGE_W / 2 - ponder.width / 2 if need > 0 else options.get_right()[0] + 0.5 + ponder.width / 2,
                            options.get_center()[1], 0])
            arc.move_to(track)
            self.play(*slide, FadeIn(track), FadeIn(pill, shift=LEFT * 0.2), run_time=0.3)
            self.play(Create(arc), run_time=max(0.5, secs - 0.5), rate_func=lambda t: t)
            back = [options.animate.shift(RIGHT * need)] if need > 0 else []
            self.play(*back, FadeOut(track), FadeOut(arc), FadeOut(pill), run_time=0.2)
            self.remove(track, arc, pill)

        answer = beat["answer"]
        self.at(tracker, marks, L.cue_key(beat["options"][answer].split()[0]), 0.6)
        anims = []
        for n, opt in enumerate(options):
            if n == answer:
                anims += [opt[0].animate.set_fill(mix(BG, GREEN, 0.22)).set_stroke(GREEN), opt[1][1].animate.set_color(GREEN)]
            else:
                anims.append(opt.animate.set_opacity(0.35))
        mark = check_mark(options[answer].get_right() + RIGHT * 0.55)
        self.keep(mark)
        self.play(*anims, Create(mark), run_time=0.5)

    # ── grammar in motion ─────────────────────────────────────────────────────

    def beat_transform(self, beat, tracker, marks):
        """`from` morphs into `to`: shared words glide (a word that changed places arcs
        over), words only in `from` turn red, shake and fall away, words only in `to`
        drop in green. When a word is missing, a red caret marks the gap at once and
        becomes that word. Starts when the narration says the first new or moved word;
        if `from` is the sentence already on screen, the morph starts from it."""
        self.show_bar()
        plan = L.transform_plan(beat["from"], beat["to"])
        morph_at = self.cue_time(tracker, marks, "#0", 0.55)
        if self.continues(beat):
            src = self.sentence["chips"]
            rest = [m for m in self.stage if m is not src]
            if rest:
                self.play(*[FadeOut(m) for m in rest], run_time=self.run_until(0.3, morph_at))
                for m in rest:
                    self.stage.remove(m)
                    self.remove(m)
            dst = chips_for(plan["to"], center=src.get_center())
            gloss = (para(beat["gloss"], GLOSS_PX, STAGE_W, SOFT, BODY).next_to(dst, DOWN, buff=0.75)
                     if beat.get("gloss") else None)
        else:
            dst = chips_for(plan["to"], center=[0, STAGE_MID, 0])
            gloss = (para(beat["gloss"], GLOSS_PX, STAGE_W, SOFT, BODY).next_to(dst, DOWN, buff=0.75)
                     if beat.get("gloss") else None)
            centre_on(dst, *([gloss] if gloss else []))
            src = chips_for(plan["from"], center=dst.get_center())
            self.keep(src)
            self.play(LaggedStart(*[FadeIn(c, scale=0.75) for c in src], lag_ratio=0.25,
                                  run_time=self.run_until(min(1.0, 0.18 * len(src) + 0.3), morph_at)))
        self.sentence = None

        # The error at once. A missing word: a red caret in the gap, which becomes the word.
        # A wrong word (a substitution — no gap to mark): its outline pulses red.
        mark, gap = None, L.insertion_gap(plan)
        if gap is not None:
            left, right = gap
            box = src[left if left is not None else right][0]
            if left is not None and right is not None and src[left][0].get_y() == src[right][0].get_y():
                x = (src[left][0].get_right()[0] + src[right][0].get_left()[0]) / 2
            elif left is not None:
                x = src[left][0].get_right()[0] + 0.13
            else:
                x = src[right][0].get_left()[0] - 0.13
            mark = caret(x, box.get_top()[1] - 0.12, box.get_bottom()[1] + 0.12)
            self.keep(mark)
            self.play(Create(mark), run_time=self.run_until(0.25, morph_at, floor=0.1))
            pulse = lambda: mark.animate(rate_func=there_and_back).scale(1.35).set_stroke(width=9)
        elif plan["removed"]:
            wrong = src[plan["removed"][0]][0]
            self.play(wrong.animate.set_stroke(RED, width=5), run_time=self.run_until(0.2, morph_at, floor=0.1))
            pulse = lambda: wrong.animate(rate_func=there_and_back).scale(1.12).set_stroke(width=9)
        else:
            pulse = None
        if pulse is not None:
            room = morph_at - float(self.renderer.time) - L.CUE_MARGIN
            for _ in range(2 if room >= 0.8 else 1 if room >= 0.3 else 0):     # two pulses if there is time
                self.play(pulse(), run_time=min(0.4, room / 2 if room >= 0.8 else room))

        self.at(tracker, marks, "#0", 0.55, word=plan["to"][plan["cue"]])
        gone = [src[i] for i in plan["removed"]]
        if gone:
            self.play(*[c[0].animate.set_fill(RED).set_stroke(RED) for c in gone],
                      *[c[1].animate.set_color(ink(RED)) for c in gone], run_time=0.25)
            self.play(*[Wiggle(c, scale_value=1.08, rotation_angle=0.05 * PI, n_wiggles=3) for c in gone], run_time=0.5)
        moved = set(plan["moved"])
        glide = [c.animate(rate_func=rush_into).shift(DOWN * 1.6).set_opacity(0) for c in gone]
        glide += [Transform(src[i], dst[j], path_arc=-PI / 2 if j in moved else 0) for i, j in plan["pairs"]]
        landing = [paint(dst[j], GREEN) for j in plan["added"]]
        drop = []
        for k, (j, c) in enumerate(zip(plan["added"], landing)):
            if k == 0 and mark is not None:
                drop.append(ReplacementTransform(mark, c))     # the caret becomes the word
            else:
                drop.append(FadeIn(c, shift=DOWN * 1.0))
        focus = dst[plan["cue"]].get_center()
        if landing:
            self.sfx("pop", 0.95)
        if glide and drop:
            self.play(LaggedStart(AnimationGroup(*glide), AnimationGroup(*drop), lag_ratio=0.35, run_time=1.1),
                      self.push(focus))
        else:
            self.play(AnimationGroup(*(glide + drop), run_time=0.9), self.push(focus))
        if mark is not None:
            self.stage.remove(mark)
        for c in gone:
            self.remove(c)
            self.stage.remove(c)
        for c in landing:
            self.keep(c)
        if moved:                                       # a short flash on what moved: word order is the lesson
            self.play(*[src[i][0].animate.set_stroke(ACCENT_LINE, width=5) for i, j in plan["pairs"] if j in moved],
                      run_time=0.25)
        if gloss:
            self.keep(gloss)
            self.play(FadeIn(gloss, shift=UP * 0.1), run_time=0.4)

    def beat_timeline(self, beat, tracker, marks):
        """Tenses as shapes: an axis −10…+10 with «ahora» glowing at 0; a point is a dot,
        a span a bar that grows from start to end (closed in the past, an arrow when it
        reaches now), a repeat a row of dots that pop one by one. A future point gets a
        dashed line from now. Each event draws when its label's first word is said."""
        self.show_bar()
        axis_y = STAGE_BOTTOM + 1.0
        half = STAGE_W / 2
        x = lambda v: v * half / 10
        axis = Line([x(-10.3), axis_y, 0], [x(10.3), axis_y, 0], color=DIM, stroke_width=5)
        ticks = VGroup(*[Line([x(v), axis_y - 0.07, 0], [x(v), axis_y + 0.07, 0], color=DIM, stroke_width=3)
                         for v in range(-10, 11) if v])
        events = beat["events"]
        lane_top = STAGE_TOP - 0.25
        pitch = min(1.45, (lane_top - (axis_y + 0.95)) / max(1, len(events)))
        lanes = [lane_top - 0.75 - n * pitch for n in range(len(events))]
        glow_top = lane_top
        now = VGroup(*[Line([0, axis_y - 0.3, 0], [0, glow_top, 0], color=YELLOW, stroke_width=w, stroke_opacity=o)
                       for w, o in ((26, 0.10), (16, 0.18), (9, 0.35))],
                     Line([0, axis_y - 0.3, 0], [0, glow_top, 0], color=ACCENT_LINE, stroke_width=4))
        ahora = text("ahora", SMALL_PX, ACCENT_TEXT, BODY, BOLD).next_to([0, axis_y - 0.3, 0], DOWN, buff=0.12)
        past = text("pasado", SMALL_PX, MUTED, BODY).move_to([x(-7.5), ahora.get_y(), 0])
        future = text("futuro", SMALL_PX, MUTED, BODY).move_to([x(7.5), ahora.get_y(), 0])
        frame = VGroup(axis, ticks, now, ahora, past, future)
        self.keep(frame)
        first = self.cue_time(tracker, marks, "#0", 0.1)       # one entrance, done before the first event is said
        self.play(AnimationGroup(AnimationGroup(Create(axis), FadeIn(ticks)),
                                 AnimationGroup(FadeIn(now), FadeIn(ahora, shift=UP * 0.1), FadeIn(past), FadeIn(future)),
                                 lag_ratio=0.6),
                  run_time=self.run_until(1.0, first, floor=0.12))
        for n, event in enumerate(events):
            color = LANE_COLORS[n % len(LANE_COLORS)]
            y = lanes[n]
            start = float(event["start"])
            end = float(event.get("end", start))
            kind = event["kind"]
            guide = lambda v: DashedLine([x(v), y, 0], [x(v), axis_y, 0], color=LINE_C, stroke_width=2, dash_length=0.08)
            draw, extra = [], VGroup()
            if kind == "point":
                shape = Dot([x(start), y, 0], radius=0.17, color=color)
                if start > 0:                        # going to: a dot in the future, a dashed line from now
                    lead = DashedLine([0, y, 0], [x(start), y, 0], color=color, stroke_width=4, dash_length=0.12)
                    extra.add(lead)
                    draw.append(Create(lead))
                draw.append(GrowFromCenter(shape))
                guides = VGroup(guide(start))
                center_x = x(start)
            elif kind == "span":
                shape = VGroup(Line([x(start), y, 0], [x(end), y, 0], color=color, stroke_width=18))
                if end == 0 and start < 0:           # present perfect: reaches now, an arrow
                    shape[0].put_start_and_end_on([x(start), y, 0], [x(end) - 0.18, y, 0])
                    tip = Polygon([x(end) - 0.24, y + 0.2, 0], [x(end) + 0.02, y, 0], [x(end) - 0.24, y - 0.2, 0],
                                  color=color, fill_color=color, fill_opacity=1, stroke_width=0)
                    shape.add(tip)
                elif end <= 0:                       # used to: closed in the past, caps at both ends
                    shape.add(*[Line([x(v), y - 0.2, 0], [x(v), y + 0.2, 0], color=color, stroke_width=6) for v in (start, end)])
                draw.append(Create(shape[0], rate_func=smooth))
                draw += [FadeIn(m) for m in shape[1:]]
                guides = VGroup(guide(start), guide(end))
                center_x = x((start + end) / 2)
            else:                                    # repeat: a habit, dots that pop one by one
                values = list(range(math.ceil(start), math.floor(end) + 1))
                if len(values) < 3:
                    values = [start + (end - start) * k / 2 for k in range(3)]
                shape = VGroup(*[Dot([x(v), y, 0], radius=0.12, color=color) for v in values])
                draw.append(LaggedStart(*[GrowFromCenter(d) for d in shape], lag_ratio=0.6))
                guides = VGroup(guide(values[0]), guide(values[-1]))
                center_x = x((values[0] + values[-1]) / 2)
            label = text(event["label"], LABEL_PX, TEXT)
            if label.width > STAGE_W:
                label.scale_to_fit_width(STAGE_W)
            lx = max(-half + label.width / 2, min(half - label.width / 2, center_x))
            label.move_to([lx, y + 0.5, 0])
            label = VGroup(RoundedRectangle(corner_radius=0.12, width=label.width + 0.3, height=label.height + 0.2,
                                            fill_color=BG, fill_opacity=0.9, stroke_width=0).move_to(label), label)
            self.keep(guides, extra, shape, label)
            self.at(tracker, marks, f"#{n}", 0.1 + 0.8 * n / len(events), word=event["label"].split()[0])
            later = (self.cue_time(tracker, marks, f"#{n + 1}", 0.1 + 0.8 * (n + 1) / len(events))
                     if n + 1 < len(events) else None)
            run = self.run_until(min(1.6, 0.12 * len(shape) + 0.4) if kind == "repeat" else 0.8, later, floor=0.25)
            self.play(*draw, FadeIn(label, shift=DOWN * 0.12), FadeIn(guides), run_time=run)

    def beat_sort(self, beat, tracker, marks):
        """Bins along the bottom; each item pops in at the centre when it is said, holds,
        then arcs into its bin with a soft pop. Driven by one clock so items may overlap in
        flight; the camera eases towards the bins as the first item flies."""
        self.show_bar()
        n_bins = len(beat["bins"])
        gap = 0.5
        bin_w = min(5.0, (STAGE_W - gap * (n_bins - 1)) / n_bins)
        bin_h = 3.0
        bins, slots = VGroup(), []
        total = n_bins * bin_w + gap * (n_bins - 1)
        for b, name in enumerate(beat["bins"]):
            color = LANE_COLORS[b % len(LANE_COLORS)]
            cx = -total / 2 + bin_w / 2 + b * (bin_w + gap)
            box = RoundedRectangle(corner_radius=0.3, width=bin_w, height=bin_h, fill_color=mix(BG, color, 0.10),
                                   fill_opacity=1, stroke_color=color, stroke_width=4)
            box.move_to([cx, STAGE_BOTTOM + bin_h / 2 + 0.05, 0])
            label = text(name, BIN_PX, color).move_to([cx, box.get_top()[1] - 0.42, 0])
            bins.add(VGroup(box, label))
            cols = 2
            rows = max(1, math.ceil(sum(1 for _, bb in beat["items"] if bb == b) / cols))     # rows the bin needs
            top = box.get_top()[1] - 0.85
            cell_w, cell_h = (bin_w - 0.3) / cols, (bin_h - 1.0) / rows
            slots.append([[cx - (bin_w - 0.3) / 2 + cell_w * (c + 0.5), top - cell_h * (r + 0.5), 0]
                          for r in range(rows) for c in range(cols)])
        self.keep(bins)
        self.play(LaggedStart(*[FadeIn(b, shift=UP * 0.3) for b in bins], lag_ratio=0.3,
                              run_time=self.run_until(0.6, self.cue_time(tracker, marks, "#0", 0.15), floor=0.15)))

        pop_at = [0, STAGE_TOP - 1.4, 0]
        n_items = len(beat["items"])
        keys = [f"#{n}" for n in range(n_items)]
        cues = [self.cue_time(tracker, marks, k, 0.15 + 0.75 * n / n_items) for n, k in enumerate(keys)]
        # pop + hold + fly, squeezed so each item has landed before the next item's cue
        phases = L.squeeze(cues, (0.25, 0.3, 0.6), floor=0.35)
        now = float(self.renderer.time)
        items, plan, used = [], [], [0] * n_bins
        for n, (word, b) in enumerate(beat["items"]):
            chip = chips_for([str(word)], center=pop_at)[0]
            dest = slots[b][min(used[b], len(slots[b]) - 1)]
            used[b] += 1
            cell_w = (bin_w - 0.3) / 2
            cell_h = (bin_h - 1.0) / max(1, math.ceil(sum(1 for _, bb in beat["items"] if bb == b) / 2))
            shrink = min(0.72, (cell_w - 0.1) / chip.width, (cell_h - 0.08) / chip.height)
            pop, hold, fly = phases[n]
            rec = self.record(keys[n], str(word), cues[n], keys[n] not in marks, start=cues[n])
            rec["start"] = None                       # filled in by the first frame the item is visible
            items.append(chip)
            plan.append({"t": max(0.0, cues[n] - now), "dest": dest, "shrink": shrink, "pop": pop, "hold": hold,
                         "fly": fly, "rec": rec, "bend": 1 if dest[0] >= 0 else -1})
            self.sfx("pop", max(0.0, cues[n] - now) + pop + hold + fly)       # the landing
        clock = ValueTracker(0.0)
        for chip, p in zip(items, plan):
            chip.save_state()
            chip.set_opacity(0)

            def place(m, dt=0, p=p):
                tau = clock.get_value() - p["t"]
                m.restore()
                if tau <= 0:
                    m.set_opacity(0)
                    return
                if p["rec"]["start"] is None:                 # sync proof: when it really appeared
                    p["rec"]["start"] = round(float(self.renderer.time), 3)
                if tau < p["pop"]:
                    k = smooth(tau / p["pop"])
                    m.scale(0.6 + 0.4 * k).set_opacity(k)
                    return
                tau -= p["pop"] + p["hold"]
                if tau <= 0:
                    return
                k = smooth(min(1.0, tau / p["fly"]))
                a, b = m[0].get_center(), p["dest"]
                ctrl = [(a[0] + b[0]) / 2 + p["bend"] * 0.6, max(a[1], b[1]) + 1.0, 0]
                pos = [(1 - k) ** 2 * a[i] + 2 * (1 - k) * k * ctrl[i] + k ** 2 * b[i] for i in range(3)]
                m.scale(1 - (1 - p["shrink"]) * k).shift(pos - m[0].get_center())

            chip.add_updater(place)
            self.add(chip)
        end = max(p["t"] + p["pop"] + p["hold"] + p["fly"] for p in plan) + 0.05
        first_fly = plan[0]["t"] + plan[0]["pop"] + plan[0]["hold"]
        push = self.push(bins.get_center(), delay=first_fly)
        camera = Succession(Wait(run_time=first_fly), push) if first_fly > 0.01 else push
        self.play(clock.animate(run_time=end, rate_func=lambda t: t).set_value(end), camera)
        for chip in items:
            chip.clear_updaters()
        self.keep(*items)

    def beat_syllables(self, beat, tracker, marks):
        """The word in syllable chips with a gap between them, the stressed one 1.3× and
        yellow. While the narration says the word a dot hops chip to chip across it; then
        the chips close the gaps into the whole word."""
        self.show_bar()
        parts, stress = beat["parts"], beat["stress"]
        chips = VGroup()
        for k, part in enumerate(parts):
            px = CHIP_PX * 1.3 if k == stress else CHIP_PX
            c = chips_for([part], px=px)[0]
            c.shift(UP * 0.5 * px * PX)                       # every baseline on y = 0
            if k == stress:
                paint(c, YELLOW)
            chips.add(c)
        gap = 0.4
        x = -(sum(c[0].width for c in chips) + gap * (len(chips) - 1)) / 2
        for c in chips:
            c.shift(RIGHT * (x + c[0].width / 2 - c[0].get_center()[0]))
            x += c[0].width + gap
        gloss = para(beat["gloss"], GLOSS_PX, STAGE_W, SOFT, BODY).next_to(chips, DOWN, buff=0.8) if beat.get("gloss") else None
        centre_on(chips, *([gloss] if gloss else []))
        said_at = self.cue_time(tracker, marks, "#0", 0.4)
        self.keep(chips)                                   # the entrance is done before the word is said
        self.play(LaggedStart(*[FadeIn(c, shift=DOWN * 0.4) for c in chips], lag_ratio=0.3,
                              run_time=self.run_until(0.8, said_at - (0.3 if gloss else 0), floor=0.2)))
        if gloss:
            self.keep(gloss)
            self.play(FadeIn(gloss), run_time=self.run_until(0.3, said_at, floor=0.1))

        # the dot hops across the word as it is spoken: on chip k at word start + k·span/n
        t0 = self.at(tracker, marks, "#0", 0.4, word=beat["word"])["cue"]
        spoken = [(a, b) for a, b in self.speech if b >= t0 - 0.05]    # the word being said from its cue
        span = max(0.45, min(1.6, spoken[0][1] - max(spoken[0][0], t0) if spoken else 0.8))
        hop = span / len(chips)
        tops = [c[0].get_top() + UP * 0.32 for c in chips]
        dot = Dot(tops[0], radius=0.13, color=BLUE)
        self.keep(dot)
        self.play(FadeIn(dot, scale=0.4), chips[0].animate(rate_func=there_and_back).scale(1.08), run_time=min(0.12, hop))
        for k in range(1, len(chips)):
            planned = t0 + (k - 1) * hop + min(0.12, hop)
            self.safe_wait(planned - float(self.renderer.time))
            self.record(f"hop{k}", parts[k], planned, False)
            self.play(dot.animate(path_arc=-PI * 0.8).move_to(tops[k]),
                      chips[k].animate(rate_func=there_and_back).scale(1.08),
                      run_time=max(0.1, t0 + k * hop + min(0.12, hop) - float(self.renderer.time)))
        self.wait(0.3)
        # close the gaps: the syllables become the word
        total = sum(c[0].width for c in chips)
        x = chips.get_center()[0] - total / 2
        anims = [FadeOut(dot)]
        for c in chips:
            anims.append(c.animate.shift(RIGHT * (x + c[0].width / 2 - c[0].get_center()[0])))
            x += c[0].width
        self.play(*anims, run_time=0.6)
        self.stage.remove(dot)

    # ── the end card ──────────────────────────────────────────────────────────

    def end_screen(self):
        """20 s, silent: the logo, «Sigue aprendiendo», and two empty frames where YouTube
        places its end-screen elements. On the dark stage the logo sits on a light plate."""
        self.clear_stage()
        if self.hud is not None:
            self.play(FadeOut(self.hud), run_time=0.3)
            self.hud.clear_updaters()
            self.remove(self.hud)
        start = float(self.renderer.time)
        self.timeline.append({"id": "end", "type": "end_screen", "start": round(start, 2), "seconds": END_SCREEN_S})
        logo = ImageMobject(str(BRAND_DIR / "logo_horizontal.png")).scale_to_fit_width(4.4).move_to([0, 2.75, 0])
        head = [FadeIn(logo)]
        if P["dark"]:
            plate = RoundedRectangle(corner_radius=0.3, width=logo.width + 0.7, height=logo.height + 0.5,
                                     fill_color=PAPER, fill_opacity=1, stroke_width=0).move_to(logo)
            head = [FadeIn(plate)] + head
        title = text("Sigue aprendiendo", TITLE_PX * 0.9, ACCENT_TEXT).move_to([0, 1.35, 0])
        frame_w = 5.4
        frames = VGroup(*[DashedVMobject(RoundedRectangle(corner_radius=0.18, width=frame_w, height=frame_w * 9 / 16,
                                                          stroke_color=DIM, stroke_width=3), num_dashes=60)
                          for _ in range(2)]).arrange(RIGHT, buff=0.8).move_to([0, -1.75, 0])
        extra = []
        if not P["dark"]:                                  # yellow as a highlighter under the words
            mark = Rectangle(width=title.width + 0.5, height=title.height * 0.45, stroke_width=0, fill_color=YELLOW,
                             fill_opacity=1).move_to(title.get_bottom() + UP * title.height * 0.2)
            mark.z_index = -1
            extra.append(FadeIn(mark))
        self.play(*head, *extra, FadeIn(title, shift=UP * 0.2), Create(frames), run_time=0.9)
        self.wait(END_SCREEN_S - (float(self.renderer.time) - start))

