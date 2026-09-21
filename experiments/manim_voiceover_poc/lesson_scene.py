"""One Manim scene that renders any lesson.json — the voice leads, the picture follows.

    LESSON=lessons/third-person-s.json VOICE_DIR=audio/third-person-s/matilda \
        manim -qm lesson_scene.py Lesson

Each beat is one `with self.voiceover(...)` block: the pre-generated narration
(see gen_audio.py) sets the pace, and the beat's drawing waits for the words it
animates on (`lesson.marked_narration`). Nothing has a fixed duration.
"""
import json
import os
import textwrap
from pathlib import Path

from manim import (
    DOWN, LEFT, ORIGIN, RIGHT, UP, Arc, Circle, Create, FadeIn, FadeOut, Line, PI,
    RoundedRectangle, Text, Transform, VGroup, Write, config,
)
from manim_voiceover import VoiceoverScene

import lesson as L
from voices import PrerecordedService

HERE = Path(__file__).resolve().parent

# Learning Routes light-theme tokens.
PAPER, INK, SUB, MUTED = "#FEFDFB", "#1C1812", "#6D665B", "#887F72"
HI, HI2, OK, BAD, CARD, LINE = "#F2D66B", "#9AD1F0", "#2F8F5B", "#C0453A", "#F5F1EB", "#E4DED4"
FILLS = {"yellow": (HI, INK), "blue": (HI2, INK), "green": ("#E3F1E9", OK), "red": ("#F3D9D6", BAD)}
FONT = os.environ.get("LESSON_FONT", "DejaVu Sans")
STAGE_W, STAGE_TOP, STAGE_BOTTOM = 12.4, 2.6, -2.6
CAPTION_Y, CAPTION_H = -3.3, 1.15                 # the karaoke band at the bottom
CAP_ES, CAP_ES_ON, CAP_EN, CAP_EN_ON = "#B3AB9E", INK, "#93BFDD", "#1B6FA8"
CAP_SIZE, CAP_LINE_W, CAP_LINES = 0.46, 12.6, 2

config.background_color = PAPER


def text(s, size=1.0, color=INK, weight="NORMAL", slant="NORMAL", wrap=None):
    if wrap:
        s = "\n".join(textwrap.wrap(s, wrap)) or s
    return Text(s, font=FONT, color=color, weight=weight, slant=slant, line_spacing=0.9).scale(size)


def fit(mobj, max_w=STAGE_W, max_h=None):
    if mobj.width > max_w:
        mobj.scale_to_fit_width(max_w)
    if max_h and mobj.height > max_h:
        mobj.scale_to_fit_height(max_h)
    return mobj


def chip(word, fill=CARD, color=INK):
    label = text(word, 1.0, color, "BOLD")
    box = RoundedRectangle(corner_radius=0.2, width=label.width + 0.6, height=label.height + 0.5,
                           fill_color=fill, fill_opacity=1, stroke_color=MUTED, stroke_width=1.5)
    return VGroup(box, label)


def card(inner, fill=CARD, pad=0.45, stroke=LINE):
    box = RoundedRectangle(corner_radius=0.25, width=inner.width + 2 * pad, height=inner.height + 2 * pad,
                           fill_color=fill, fill_opacity=1, stroke_color=stroke, stroke_width=1.5).move_to(inner)
    return VGroup(box, inner)


def check_mark(center, r=0.22):
    ring = Circle(radius=r, color=OK, stroke_width=3).move_to(center)
    tick = VGroup(Line(center + LEFT * 0.1 + DOWN * 0.01, center + DOWN * 0.08, color=OK, stroke_width=3),
                  Line(center + DOWN * 0.08, center + RIGHT * 0.12 + UP * 0.1, color=OK, stroke_width=3))
    return VGroup(ring, tick)


class Lesson(VoiceoverScene):
    def construct(self):
        self.lesson = L.load(HERE / os.environ.get("LESSON", "lessons/third-person-s.json"))
        problems = L.validate(self.lesson)
        if problems:
            raise SystemExit("lesson.json is not renderable:\n  " + "\n  ".join(problems))
        self.set_speech_service(PrerecordedService(HERE / os.environ["VOICE_DIR"]))

        self.bar = None            # the small title at the top, once the title card has played
        self.stage = VGroup()      # everything a beat may leave behind
        self.sentence = None       # the chips of the current sentence, for `same`
        self.captions_on = os.environ.get("CAPTIONS", "1") != "0"
        self.timeline = []         # [{id, type, text?, start}] — chapters and the WP-38 poster read it
        for beat in self.lesson["beats"]:
            self.play_beat(beat)
        self.wait(1.0)
        self.write_timeline()

    def write_timeline(self):
        out = Path(os.environ.get("TIMELINE_OUT", HERE / "media" / "timeline" / f"{self.lesson['id']}.json"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"lesson": self.lesson["id"], "duration": round(float(self.renderer.time), 2),
                                   "beats": self.timeline}, ensure_ascii=False, indent=1))

    # ── plumbing ──────────────────────────────────────────────────────────────

    def play_beat(self, beat):
        kind = beat["type"]
        if not (kind == "sentence" and beat.get("same") and self.sentence is not None):
            self.clear_stage()
        narration, marks = L.marked_narration(beat)
        self.timeline.append({"id": beat["id"], "type": kind, "text": beat.get("text") or beat.get("heading"),
                              "start": round(float(self.renderer.time), 2)})
        with self.voiceover(text=narration, beat_id=beat["id"]) as tracker:
            caption = self.mount_captions(beat, tracker) if self.captions_on and kind != "title" else None
            getattr(self, f"beat_{kind}")(beat, tracker, marks)
            self.safe_wait(tracker.get_remaining_duration())
        if caption is not None:
            caption.clear_updaters()
            self.remove(caption)
        # A breath between beats: longer after a section card, so the ear resets with the eye.
        self.wait(0.6 if kind == "heading" else 0.35)

    # ── karaoke captions ──────────────────────────────────────────────────────

    def mount_captions(self, beat, tracker):
        """The narration at the bottom, sentence by sentence, each word lighting up when it is
        spoken. Times come from the recorded word boundaries (ElevenLabs alignment) so the
        highlight lands on the spoken word; English (what sat in [[ ]]) is blue and bold.
        One Text per line (true baseline and kerning); words are coloured by character slice."""
        words = L.tokens(beat["narration"])
        if not words:
            return None
        times = self._word_times(words, tracker)
        pages = self._caption_pages(words)          # [[line, line], ...]; line = [word, ...] with ["start"] char index
        band = RoundedRectangle(corner_radius=0.2, width=CAP_LINE_W + 0.6, height=CAPTION_H, fill_color=CARD,
                                fill_opacity=1, stroke_color=LINE, stroke_width=1).move_to([0, CAPTION_Y, 0])
        group, page_starts, lit_map = VGroup(band), [], []
        for page in pages:
            line_mobjs = VGroup()
            page_words = []                          # (word, line_mobj, char_start, char_end)
            for line in page:
                string = " ".join(w["text"] for w in line)
                t2c, t2w, pos = {}, {}, 0
                for w in line:
                    key = f"[{pos}:{pos + len(w['text'])}]"
                    t2c[key] = CAP_EN if w["en"] else CAP_ES
                    if w["en"]:
                        t2w[key] = "BOLD"
                    w["span"] = (pos, pos + len(w["text"]))
                    pos += len(w["text"]) + 1
                mobj = Text(string, font=FONT, color=CAP_ES, disable_ligatures=True, t2c=t2c, t2w=t2w).scale(CAP_SIZE)
                fit(mobj, CAP_LINE_W)
                line_mobjs.add(mobj)
                page_words += [(w, mobj) for w in line]
            line_mobjs.arrange(DOWN, buff=0.12).move_to([0, CAPTION_Y, 0])
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
                    a, b = w["span"]
                    line_mobj[a:b].set_color(CAP_EN_ON if w["en"] else CAP_ES_ON)
                    state["lit"].add(w["index"])

        group.add_updater(tick)
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
        """Sentences → lines (greedy, by an estimate of rendered width) → pages of CAP_LINES lines."""
        probe = Text("n", font=FONT, disable_ligatures=True).scale(CAP_SIZE)
        char_w = probe.width * 1.05                 # average glyph width; fit() corrects the rare overflow
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
                w_width = (len(w["text"]) + 1) * char_w
                if line and width + w_width > CAP_LINE_W:
                    lines.append(line)
                    line, width = [], 0.0
                line.append(w)
                width += w_width
            if line:
                lines.append(line)
            for k in range(0, len(lines), CAP_LINES):
                pages.append(lines[k:k + CAP_LINES])
        return pages

    def clear_stage(self):
        if len(self.stage) > 0:
            self.play(FadeOut(self.stage), run_time=0.35)
            self.remove(*self.stage)
        self.stage = VGroup()
        self.sentence = None

    def keep(self, *mobjs):
        for m in mobjs:
            self.stage.add(m)
        return mobjs[0] if len(mobjs) == 1 else mobjs

    def at(self, tracker, marks, word, fraction):
        """Wait until `word` is spoken (bookmark) or, if the narration never says it,
        until `fraction` of the narration has elapsed."""
        if word in marks:
            delay = tracker.time_until_bookmark(marks[word])
        else:
            delay = tracker.start_t + fraction * tracker.duration - float(self.renderer.time)
        self.safe_wait(delay)

    def budget(self, tracker, cap):
        return max(0.15, min(cap, tracker.get_remaining_duration() * 0.5))

    def show_bar(self):
        if self.bar is None:
            self.bar = text(self.lesson["title"], 0.42, SUB, "BOLD").to_edge(UP, buff=0.35)
            fit(self.bar, 11)
            self.add(self.bar)

    # ── beats ─────────────────────────────────────────────────────────────────

    def beat_title(self, beat, tracker, marks):
        title = fit(text(beat.get("text", self.lesson["title"]), 1.0, INK, "BOLD", wrap=34), 12)
        kicker_text = beat.get("kicker") or self.lesson.get("kicker") or ""
        group = VGroup(title)
        anims = [Write(title)]
        if kicker_text:
            kicker = text(kicker_text.upper(), 0.4, MUTED).next_to(title, UP, buff=0.4)
            group.add(kicker)
            anims.append(FadeIn(kicker, shift=DOWN * 0.15))
        group.move_to(ORIGIN)
        if self.bar is not None:
            self.bar.set_opacity(0)
        self.play(*anims, run_time=min(2.0, tracker.duration * 0.6))
        self.safe_wait(tracker.get_remaining_duration() - 0.9)
        self.play(FadeOut(group), run_time=0.5)
        self.remove(group)
        if self.bar is None:
            self.show_bar()
        else:
            self.bar.set_opacity(1)

    def beat_heading(self, beat, tracker, marks):
        self.show_bar()
        heading = fit(text(beat["text"], 0.9, INK, "BOLD"), 12)
        rule = Line(LEFT * 1.2, RIGHT * 1.2, color=HI, stroke_width=6).next_to(heading, DOWN, buff=0.35)
        self.keep(heading, rule)
        self.play(FadeIn(heading, shift=UP * 0.15), Create(rule), run_time=min(1.2, tracker.duration * 0.5))

    def beat_sentence(self, beat, tracker, marks):
        self.show_bar()
        if not (beat.get("same") and self.sentence is not None):
            words = beat["text"].split()
            if words and words[-1][-1] in ".?!" and len(words[-1]) > 1:
                words[-1], tail = words[-1][:-1], words[-1][-1]
                words.append(tail)
            chips = VGroup(*[chip(w) for w in words]).arrange(RIGHT, buff=0.3)
            fit(chips, STAGE_W).move_to(UP * 0.9)
            self.sentence = {"chips": chips, "words": words, "tags": {}}
            self.keep(chips)
            per = self.budget(tracker, 0.45) / max(1, len(chips)) * 2
            for c in chips:
                self.play(FadeIn(c, scale=0.7), run_time=min(0.45, per))
            if beat.get("gloss"):
                gloss = fit(text(beat["gloss"], 0.55, SUB, slant="ITALIC", wrap=80), 11).next_to(chips, DOWN, buff=1.1)
                self.keep(gloss)
                self.play(FadeIn(gloss), run_time=0.4)
        chips, words = self.sentence["chips"], self.sentence["words"]

        def find(word):
            for i, w in enumerate(words):
                if w.strip(".,;:!?¿¡").lower() == word.strip(".,;:!?¿¡").lower():
                    return i
            return None

        n_cues = max(1, len(beat.get("highlight") or {}) + len(beat.get("tags") or {}) + (1 if beat.get("fix") else 0))
        step = 0
        for word, color in (beat.get("highlight") or {}).items():
            i = find(word)
            if i is None:
                continue
            step += 1
            self.at(tracker, marks, word, 0.15 + 0.6 * step / n_cues)
            fill, ink = FILLS[color]
            self.play(chips[i][0].animate.set_fill(fill), chips[i][1].animate.set_color(ink), run_time=0.35)
        for word, label in (beat.get("tags") or {}).items():
            i = find(word)
            if i is None:
                continue
            step += 1
            self.at(tracker, marks, word, 0.15 + 0.6 * step / n_cues)
            tag = text(label.upper(), 0.36, MUTED).next_to(chips[i], DOWN, buff=0.28)
            self.sentence["tags"][word] = tag
            self.keep(tag)
            self.play(FadeIn(tag, shift=UP * 0.1), run_time=0.3)
        if beat.get("fix"):
            src, dst = beat["fix"]["from"], beat["fix"]["to"]
            i = find(src)
            if i is not None:
                self.at(tracker, marks, dst, 0.55)
                target = chip(dst, "#E3F1E9", OK).move_to(chips[i])
                self.play(Transform(chips[i], target), run_time=0.6)
                words[i] = dst

    def beat_dialogue(self, beat, tracker, marks):
        self.show_bar()
        lines = beat["lines"]
        scale = 1.0 if len(lines) <= 3 else 0.88 if len(lines) <= 4 else 0.76
        bubbles, speakers = [], []
        y = STAGE_TOP - 0.05
        for n, line in enumerate(lines):
            left = n % 2 == 0
            en = fit(text(line["en"], 0.62 * scale, INK, "BOLD", wrap=44), 7.4)
            parts = VGroup(en)
            if line.get("es"):
                es = fit(text(line["es"], 0.42 * scale, SUB, slant="ITALIC", wrap=60), 7.4).next_to(en, DOWN, buff=0.1, aligned_edge=LEFT)
                parts.add(es)
            bubble = card(parts, CARD if left else "#EAF4FB", pad=0.26 * scale)
            bubble.move_to([(-6.9 + bubble.width / 2) if left else (6.9 - bubble.width / 2), y - bubble.height / 2, 0])
            speaker = text(str(line.get("speaker", "A" if left else "B")).upper(), 0.3, MUTED)
            speaker.next_to(bubble, UP, buff=0.06, aligned_edge=LEFT if left else RIGHT)
            bubbles.append(bubble)
            speakers.append(speaker)
            y -= bubble.height + 0.42
        whole = VGroup(*bubbles, *speakers)
        if whole.height > STAGE_TOP - STAGE_BOTTOM:      # never into the caption band
            whole.scale_to_fit_height(STAGE_TOP - STAGE_BOTTOM)
        whole.move_to([0, (STAGE_TOP + STAGE_BOTTOM) / 2, 0])
        for n, (line, bubble, speaker) in enumerate(zip(lines, bubbles, speakers)):
            left = n % 2 == 0
            self.keep(bubble, speaker)
            self.at(tracker, marks, line["en"].split()[0], 0.05 + 0.85 * n / len(lines))
            self.play(FadeIn(bubble, shift=RIGHT * 0.2 if left else LEFT * 0.2), FadeIn(speaker), run_time=0.4)

    def beat_table(self, beat, tracker, marks):
        self.show_bar()
        rows, emphasis = beat["rows"], set(beat.get("emphasis", []))
        table = VGroup()
        if beat.get("headers"):
            table.add(VGroup(*[text(h.upper(), 0.36, MUTED, "BOLD") for h in beat["headers"]]))
        for row in rows:
            table.add(VGroup(*[text(str(c), 0.62, OK if str(c) in emphasis else INK,
                                    "BOLD" if str(c) in emphasis else "NORMAL") for c in row]))
        ncols = max(len(r) for r in table)
        col_w = [max(r[i].width for r in table if i < len(r)) for i in range(ncols)]
        for r in table:
            x = 0
            for i, cell in enumerate(r):
                cell.move_to([x + cell.width / 2, 0, 0])
                x += col_w[i] + 0.9
        table.arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        fit(table, 11, STAGE_TOP - STAGE_BOTTOM - 0.4).move_to(DOWN * 0.3)
        self.keep(table)
        start = 0
        if beat.get("headers"):
            self.play(FadeIn(table[0]), run_time=0.3)
            start = 1
        for n, row in enumerate(table[start:]):
            self.at(tracker, marks, str(rows[n][0]), 0.1 + 0.8 * n / len(rows))
            self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.3)

    def beat_list(self, beat, tracker, marks, checks=False):
        self.show_bar()
        items = beat["items"]
        group = VGroup()
        for item in items:
            label = fit(text(item, 0.6, INK, wrap=64), 10)
            bullet = check_mark(ORIGIN, 0.2) if checks else Circle(radius=0.09, color=HI, fill_color=HI, fill_opacity=1)
            bullet.next_to(label, LEFT, buff=0.35)
            group.add(VGroup(bullet, label))
        group.arrange(DOWN, aligned_edge=LEFT, buff=0.35)
        head = None
        if beat.get("heading"):
            head = fit(text(beat["heading"], 0.8, INK, "BOLD"), 11).next_to(group, UP, buff=0.6, aligned_edge=LEFT)
        whole = VGroup(*([head] if head else []), group)
        fit(whole, 11.5, STAGE_TOP - STAGE_BOTTOM).move_to(DOWN * 0.3)
        self.keep(whole)
        if head:
            self.play(FadeIn(head), run_time=0.35)
        for n, (row, item) in enumerate(zip(group, items)):
            self.at(tracker, marks, item.split()[0], 0.1 + 0.8 * n / len(items))
            self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.3)

    def beat_recap(self, beat, tracker, marks):
        self.beat_list(beat, tracker, marks, checks=True)

    def beat_tip(self, beat, tracker, marks):
        self.show_bar()
        body = fit(text(beat["text"], 0.62, INK, wrap=58), 9.5)
        label = text("TIP", 0.34, INK, "BOLD")
        label_chip = card(label, HI, pad=0.12, stroke=HI)
        inner = VGroup(label_chip, body).arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        box = card(inner, "#FBF3D2", pad=0.5, stroke=HI).move_to(DOWN * 0.2)
        self.keep(box)
        self.play(FadeIn(box, scale=0.95), run_time=min(0.6, tracker.duration * 0.3))

    def beat_quiz(self, beat, tracker, marks):
        self.show_bar()
        question = fit(text(beat["question"], 0.7, INK, "BOLD", wrap=60), 11.5).move_to(UP * 2.0)
        options = VGroup()
        for n, option in enumerate(beat["options"]):
            letter = text("ABCD"[n], 0.5, MUTED, "BOLD")
            label = fit(text(option, 0.58, INK, wrap=70), 9)
            row = VGroup(letter, label).arrange(RIGHT, buff=0.4)
            options.add(card(row, CARD, pad=0.22))
        options.arrange(DOWN, buff=0.2, aligned_edge=LEFT).next_to(question, DOWN, buff=0.5)
        fit(options, 11, STAGE_TOP - STAGE_BOTTOM - 1.6)
        self.keep(question, options)
        self.play(FadeIn(question), run_time=0.4)
        for opt in options:
            self.play(FadeIn(opt, shift=RIGHT * 0.1), run_time=0.2)

        # {{pause:N}} in the narration = time to think: a ring fills over those seconds.
        pause_marks = [k for k in marks if k.startswith("pause:")]
        if pause_marks:
            secs = (L.pauses(beat["narration"]) or [3.0])[0]
            until_resume = tracker.time_until_bookmark(marks[pause_marks[0]])
            self.safe_wait(until_resume - secs)
            ring_center = options.get_right() + RIGHT * 0.9
            track = Circle(radius=0.34, color=LINE, stroke_width=5).move_to(ring_center)
            arc = Arc(radius=0.34, start_angle=PI / 2, angle=-2 * PI, color=HI, stroke_width=6).move_to(ring_center)
            label = text("piénsalo", 0.3, MUTED).next_to(track, DOWN, buff=0.12)
            self.add(track, label)
            self.play(Create(arc), run_time=max(0.5, secs - 0.2), rate_func=lambda t: t)
            self.play(FadeOut(track), FadeOut(arc), FadeOut(label), run_time=0.2)
            self.remove(track, arc, label)

        answer = beat["answer"]
        self.at(tracker, marks, beat["options"][answer].split()[0], 0.6)
        anims = []
        for n, opt in enumerate(options):
            if n == answer:
                anims += [opt[0].animate.set_fill("#E3F1E9").set_stroke(OK), opt[1][1].animate.set_color(OK)]
            else:
                anims.append(opt.animate.set_opacity(0.35))
        mark = check_mark(options[answer].get_right() + RIGHT * 0.5)
        self.keep(mark)
        self.play(*anims, Create(mark), run_time=0.5)
