"""Pydantic contract for script JSON — the single source of truth for shape.

Before this module the contract lived in three unsynchronised places:

  1. the GPT prompt f-strings          src/script_generator.py:255-581
  2. a manual required-key dict        src/script_generator.py:620-627
  3. ``dict.get(key, default)`` at every read site in src/video/

(3) is the dangerous one: every renderer default was a *plausible wrong
answer*, so a script that lost its ``correct`` key still rendered a polished,
confidently incorrect lesson. This module exists so that failure raises
instead.

DERIVATION
----------
The models below were derived from tests/fixtures/ (12 real historical
scripts, all six video types) cross-checked against the ``required_fields``
dict at script_generator.py:620-627 — NOT hand-written from the prompts. Where
the prompts disagree with reality the prompt is treated as suspect; see
docs/schema-prompt-mismatches.md for the full diff and the ruling on each.

STRICTNESS — two models, two policies
-------------------------------------
``Script*`` models use ``extra="forbid"``. Their producer is GPT, which is
untrusted: a hallucinated key is a signal, not noise.

``*RenderData`` models use ``extra="allow"``. Their producer is our own
pipeline (``merge_script_into_tts`` folds TTS output into the script dict),
and typos there are caught by tests rather than by pydantic. Left loose on
purpose — it gets tightened in Step 2, when the audio contract has to be
precise anyway and a typed ``segment_times`` becomes a direct asset.

THE RULE FOR ``forbid`` IN PRODUCTION: an unknown key must be VISIBLE but
NOT FATAL. Fatal in the test suite; logged and dropped in the pipeline. A
hallucinated extra key from GPT must never kill an unattended batch run —
whereas a *missing* ``correct`` must, because that ships a wrong lesson.
``validate_script(..., drop_unknown=True)`` implements the lenient half.

Two severities:
  * model validation  — hard. Raises ScriptValidationError. Reserved for
    fields whose absence or wrong shape produces a wrong video.
  * ``lint_script()`` — advisory. Returns strings. Reserved for things that
    are merely off-contract (hashtag count, prompt-vs-reality drift).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Type, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    model_validator,
)

VIDEO_TYPES = ("educational", "quiz", "true_false", "fill_blank",
               "pronunciation", "vocabulary")

VideoType = Literal["educational", "quiz", "true_false", "fill_blank",
                    "pronunciation", "vocabulary"]

OptionLetter = Literal["A", "B", "C", "D"]

#: The blank marker fill_blank sentences are built around. The renderer splits
#: the sentence on it to place the answer card (video/fill_blank.py:332).
BLANK_MARKER = "___"


# ─────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────

class ScriptValidationError(ValueError):
    """A script does not satisfy the contract for its video type.

    Carries the video type, the offending fields and the file path, because
    the whole point of this module is that a failure is readable at 3am from
    a log line and nothing else.
    """

    def __init__(self, video_type: Optional[str], problems: List[str],
                 source: Optional[str] = None):
        self.video_type = video_type
        self.problems = problems
        self.source = source
        where = source or "<in-memory script>"
        head = (f"Invalid {video_type or 'unknown-type'} script: {where}")
        body = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{head}\n{body}")


def _format_pydantic_errors(exc: ValidationError) -> List[str]:
    """Flatten a pydantic ValidationError into 'field: reason' lines."""
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        out.append(f"{loc}: {err['msg']}")
    return out


# ─────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────

class ScriptBase(BaseModel):
    """Fields every video type carries.

    Deliberately small. Anything that differs by type — and most things do —
    lives on the subclass, because the differences ARE the contract.
    """

    # forbid: the producer is GPT. See the module docstring for why this is
    # fatal in tests but lenient (log + drop) in the pipeline.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # `type` selects both the TTS path (pipeline.py:143) and the renderer
    # (video/__init__.py:100). Both currently default it to "educational" on
    # a miss, which silently routes a quiz through the wrong renderer, so it
    # is required here.
    type: VideoType

    # The narration. pipeline.generate_tts already refuses anything under 10
    # chars (pipeline.py:240); this makes the same rule a contract.
    full_script: str = Field(min_length=10)

    # Publishing metadata. Optional in the model because 9 of 12 historical
    # fixtures predate it — validate_and_clean_script:703-714 synthesises a
    # fallback, so scripts validated at the generator-output point always
    # have them. Consumed only by metadata_generator.py:75-76.
    video_title: Optional[str] = None
    video_description: Optional[str] = None

    hashtags: List[str] = Field(default_factory=list)

    # Private bookkeeping. Named without the underscore because pydantic
    # treats leading-underscore attributes as private; the alias maps them.
    # Declared rather than tolerated, because extra="forbid".
    meta: Dict[str, Any] = Field(default_factory=dict, alias="_meta")
    validation_warnings: List[str] = Field(default_factory=list,
                                           alias="_validation_warnings")
    validation_errors: List[str] = Field(default_factory=list,
                                         alias="_validation_errors")

    def lint(self) -> List[str]:
        """Advisory checks. Never raises, never blocks a render."""
        out = []
        if self.video_title and len(self.video_title) > 80:
            out.append(
                f"video_title is {len(self.video_title)} chars; prompts "
                f"specify <=80")
        if not 5 <= len(self.hashtags) <= 7:
            out.append(
                f"hashtags has {len(self.hashtags)} entries; prompts specify "
                f"5-7")
        lowered = [h.lower() for h in self.hashtags]
        if len(set(lowered)) != len(lowered):
            out.append("hashtags contains duplicates (case-insensitive)")
        return out


class _TranslationsMixin(BaseModel):
    """Types that carry `translations` — a DICT of english -> spanish.

    Distinct from `translation` (a single string) on fill_blank and
    pronunciation. This split is real, not an accident of one bad file: it
    holds across all 12 fixtures and both read paths
    (video/karaoke.py:76 reads the dict, video/fill_blank.py:316 the string).
    """
    translations: Dict[str, str] = Field(default_factory=dict)


class _TranslationMixin(BaseModel):
    """Types that carry `translation` — a single STRING. See above."""
    translation: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────
# educational
# ─────────────────────────────────────────────────────────────────────────

class EducationalScript(ScriptBase, _TranslationsMixin):
    type: Literal["educational"]

    # Both required per script_generator.py:621.
    hook: str = Field(min_length=1)
    english_phrases: List[str] = Field(min_length=1)

    tip: Optional[str] = None
    cta: Optional[str] = None

    # LEGACY narration blocks, [{id, text}]. No prompt in
    # script_generator.py's history ever emitted this key — the one fixture
    # carrying it (educational/fabric_20260116_192025.json) came from a
    # generator that no longer exists. video/__init__.py:175-180 still has a
    # live fallback that estimates word timings from it.
    #
    # NOTE this key COLLIDES with pipeline.TTS_OWNED_KEYS, which claims
    # `segments` for timing data. Declared here unshaped, and again on
    # _RenderExtras, precisely because the two producers disagree. Do not
    # tighten either without resolving which one wins.
    segments: Optional[List[Dict[str, Any]]] = None


# ─────────────────────────────────────────────────────────────────────────
# quiz
# ─────────────────────────────────────────────────────────────────────────

class QuizItem(BaseModel):
    """One entry of the `questions` array. See QuizScript.questions."""
    model_config = ConfigDict(extra="allow")

    question: str = Field(min_length=1)
    options: Dict[str, str]
    correct: OptionLetter
    explanation: str = ""


class QuizScript(ScriptBase, _TranslationsMixin):
    type: Literal["quiz"]

    question: str = Field(min_length=1)

    # HAZARD: for quiz, `options` is a DICT keyed A-D (video/quiz.py:581).
    # For fill_blank the same key name holds a LIST (video/fill_blank.py:314).
    # Do not unify them without changing both renderers.
    options: Dict[str, str]

    # HAZARD: for quiz, `correct` is an option LETTER. It is a bool on
    # true_false and a word on fill_blank. Three types under one key name.
    correct: OptionLetter

    explanation: str = Field(min_length=1)

    # DEAD PAYLOAD. The prompt (script_generator.py:321-340) demands three
    # questions and GPT emits them, but NOTHING in the TTS or render path
    # reads `questions` — verified by grep across src/ and main.py. Only the
    # root-level question/options/correct/explanation are ever rendered, so
    # questions[1] and questions[2] are generated, paid for, and discarded.
    # Encoded as optional and left in place deliberately; deleting it is a
    # separate decision from validating it.
    questions: Optional[List[QuizItem]] = None

    @model_validator(mode="after")
    def _check_options(self):
        keys = set(self.options)
        if keys != {"A", "B", "C", "D"}:
            raise ValueError(
                f"options must have exactly keys A, B, C, D; got "
                f"{sorted(keys) or '[]'}")
        if self.correct not in self.options:
            raise ValueError(
                f"correct={self.correct!r} is not a key of options "
                f"{sorted(keys)}")
        return self

    def lint(self):
        out = super().lint()
        values = [v.strip().strip("'\"").lower() for v in self.options.values()]
        if len(set(values)) != len(values):
            out.append(
                "options contains duplicate values — prompt rule 1 forbids it")
        if any(v.startswith("'") and v.endswith("'")
               for v in self.options.values()):
            out.append(
                "some option values are wrapped in literal single quotes; "
                "the renderer draws them verbatim")
        if self.questions:
            first = self.questions[0]
            if (first.question != self.question
                    or first.correct != self.correct
                    or first.options != self.options):
                out.append(
                    "questions[0] does not match the root-level question / "
                    "options / correct, which the prompt requires")
        return out


# ─────────────────────────────────────────────────────────────────────────
# true_false
# ─────────────────────────────────────────────────────────────────────────

class TrueFalseItem(BaseModel):
    """One entry of the `statements` array. See TrueFalseScript.statements."""
    model_config = ConfigDict(extra="allow")

    statement: str = Field(min_length=1)
    correct: StrictBool
    explanation: str = ""


class TrueFalseScript(ScriptBase, _TranslationsMixin):
    type: Literal["true_false"]

    statement: str = Field(min_length=1)

    # HAZARD: a real bool here, not a letter or a word. StrictBool on
    # purpose — the string "true" is truthy in Python, so lax coercion would
    # let a quoted value through and render FALSE statements as TRUE.
    correct: StrictBool

    explanation: str = Field(min_length=1)

    # DEAD PAYLOAD — same story as QuizScript.questions. Demanded by the
    # prompt at script_generator.py:396-412, read by nothing. Note that
    # unlike `questions`, no fixture in the corpus actually carries it.
    statements: Optional[List[TrueFalseItem]] = None


# ─────────────────────────────────────────────────────────────────────────
# fill_blank
# ─────────────────────────────────────────────────────────────────────────

class FillBlankItem(BaseModel):
    """One entry of the `sentences` array. See FillBlankScript.sentences."""
    model_config = ConfigDict(extra="allow")

    sentence: str = Field(min_length=1)
    options: List[str]
    correct: str = Field(min_length=1)
    blank_position: Optional[str] = None
    explanation: str = ""
    translation: Optional[str] = None


class FillBlankScript(ScriptBase, _TranslationMixin):
    type: Literal["fill_blank"]

    # Must contain the blank marker: the renderer splits on it to place the
    # answer highlight (video/fill_blank.py:332). A sentence with no blank is
    # not a fill-blank video.
    sentence: str = Field(min_length=1)

    # HAZARD: a LIST here. The same key is a DICT on quiz. See QuizScript.
    options: List[str]

    # HAZARD: the answer WORD here, not a letter and not a bool.
    correct: str = Field(min_length=1)

    blank_position: Optional[str] = None

    # Not in required_fields (script_generator.py:624) and not read by the
    # renderer — only the prompt demands it. Optional.
    explanation: Optional[str] = None

    # DEAD PAYLOAD — see QuizScript.questions. Demanded at
    # script_generator.py:465-490, read by nothing, absent from both fixtures.
    sentences: Optional[List[FillBlankItem]] = None

    @model_validator(mode="after")
    def _check_blank_and_options(self):
        if BLANK_MARKER not in self.sentence:
            raise ValueError(
                f"sentence must contain the blank marker {BLANK_MARKER!r}; "
                f"got {self.sentence!r}")
        if len(self.options) != 4:
            raise ValueError(
                f"options must have exactly 4 entries; got "
                f"{len(self.options)}")
        if self.correct not in self.options:
            raise ValueError(
                f"correct={self.correct!r} is not one of options "
                f"{self.options}")
        return self

    def lint(self):
        out = super().lint()
        if self.blank_position and self.blank_position != self.correct:
            out.append(
                f"blank_position={self.blank_position!r} differs from "
                f"correct={self.correct!r}")
        if len({o.lower() for o in self.options}) != len(self.options):
            out.append("options contains duplicate values")
        return out


# ─────────────────────────────────────────────────────────────────────────
# pronunciation
# ─────────────────────────────────────────────────────────────────────────

class PronunciationScript(ScriptBase, _TranslationMixin):
    type: Literal["pronunciation"]

    # video/pronunciation.py:42 defaults this to the literal string "word",
    # which renders a lesson teaching how to pronounce "word". Required.
    word: str = Field(min_length=1)
    phonetic: str = Field(min_length=1)

    common_mistake: Optional[str] = None
    tip: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────
# vocabulary
# ─────────────────────────────────────────────────────────────────────────

class VocabPair(BaseModel):
    model_config = ConfigDict(extra="allow")

    spanish: str = Field(min_length=1)
    english: str = Field(min_length=1)


class VocabularyScript(ScriptBase, _TranslationsMixin):
    type: Literal["vocabulary"]

    title: str = Field(min_length=1)

    # The prompt asks for 6-10 (script_generator.py:558). Hard floor is 2 —
    # anything less is not a list — with the 6-10 window enforced as a lint.
    pairs: List[VocabPair] = Field(min_length=2)

    # Free string rather than a Literal: the prompt names four values but the
    # renderer only prints it (video/vocabulary.py:81), so an unexpected word
    # is cosmetic. Checked in lint().
    difficulty: Optional[str] = None

    english_phrases: List[str] = Field(default_factory=list)

    def lint(self):
        out = super().lint()
        if not 6 <= len(self.pairs) <= 10:
            out.append(
                f"pairs has {len(self.pairs)} entries; prompt specifies 6-10")
        if self.difficulty and self.difficulty not in (
                "facil", "medio", "dificil", "experto"):
            out.append(
                f"difficulty={self.difficulty!r} is not one of "
                f"facil/medio/dificil/experto")
        return out


# ─────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────

AnyScript = Union[EducationalScript, QuizScript, TrueFalseScript,
                  FillBlankScript, PronunciationScript, VocabularyScript]

SCRIPT_MODELS: Dict[str, Type[ScriptBase]] = {
    "educational": EducationalScript,
    "quiz": QuizScript,
    "true_false": TrueFalseScript,
    "fill_blank": FillBlankScript,
    "pronunciation": PronunciationScript,
    "vocabulary": VocabularyScript,
}


# ─────────────────────────────────────────────────────────────────────────
# Renderer input — script merged with TTS output
# ─────────────────────────────────────────────────────────────────────────

class _RenderExtras(BaseModel):
    """The keys pipeline.merge_script_into_tts folds in on top of a script.

    ``extra="allow"`` here, unlike the Script models: the producer is our own
    pipeline rather than GPT. Deliberately loose for now — Step 2 tightens it,
    when a typed ``segment_times`` becomes a direct asset for the drift table.
    Until then, over-specifying it would only invent a contract nobody has
    measured.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # pipeline.TTS_OWNED_KEYS — never overwritten by script data.
    words: Optional[List[Dict[str, Any]]] = None
    segment_times: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None
    segments: Optional[List[Dict[str, Any]]] = None


class EducationalRenderData(_RenderExtras, EducationalScript):
    # Explicit, not inherited: pydantic merges model_config across bases
    # and the Script side's extra="forbid" wins the merge otherwise.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class QuizRenderData(_RenderExtras, QuizScript):
    # Explicit, not inherited: pydantic merges model_config across bases
    # and the Script side's extra="forbid" wins the merge otherwise.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class TrueFalseRenderData(_RenderExtras, TrueFalseScript):
    # Explicit, not inherited: pydantic merges model_config across bases
    # and the Script side's extra="forbid" wins the merge otherwise.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class FillBlankRenderData(_RenderExtras, FillBlankScript):
    # Explicit, not inherited: pydantic merges model_config across bases
    # and the Script side's extra="forbid" wins the merge otherwise.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PronunciationRenderData(_RenderExtras, PronunciationScript):
    # Explicit, not inherited: pydantic merges model_config across bases
    # and the Script side's extra="forbid" wins the merge otherwise.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class VocabularyRenderData(_RenderExtras, VocabularyScript):
    # Explicit, not inherited: pydantic merges model_config across bases
    # and the Script side's extra="forbid" wins the merge otherwise.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


RENDER_MODELS: Dict[str, Type[ScriptBase]] = {
    "educational": EducationalRenderData,
    "quiz": QuizRenderData,
    "true_false": TrueFalseRenderData,
    "fill_blank": FillBlankRenderData,
    "pronunciation": PronunciationRenderData,
    "vocabulary": VocabularyRenderData,
}


def model_for(video_type: str) -> Type[ScriptBase]:
    try:
        return SCRIPT_MODELS[video_type]
    except KeyError:
        raise ScriptValidationError(
            video_type,
            [f"unknown video type; expected one of {', '.join(VIDEO_TYPES)}"])


def _resolve_type(data: Dict[str, Any], video_type: Optional[str],
                  source: Optional[str]) -> str:
    if not isinstance(data, dict):
        raise ScriptValidationError(
            video_type, [f"script must be a JSON object, got "
                         f"{type(data).__name__}"], source)

    declared = data.get("type")

    if video_type is None:
        if not declared:
            raise ScriptValidationError(
                None,
                ["type: field required (and no video_type was passed, so it "
                 "cannot be inferred)"],
                source)
        return declared

    if declared is not None and declared != video_type:
        raise ScriptValidationError(
            video_type,
            [f"type: script declares {declared!r} but caller expected "
             f"{video_type!r}"],
            source)
    return video_type


def _validate_with(model: Type[ScriptBase], data: Dict[str, Any],
                   video_type: str, source: Optional[str],
                   drop_unknown: bool, on_drop) -> ScriptBase:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        unknown = sorted({
            str(e["loc"][0]) for e in exc.errors()
            if e["type"] == "extra_forbidden" and e["loc"]
        })
        if drop_unknown and unknown:
            # VISIBLE BUT NOT FATAL. A hallucinated extra key from GPT must
            # not kill an unattended batch run; a missing `correct` still
            # must, so we drop only the unknown keys and re-validate.
            if on_drop is not None:
                on_drop(unknown)
            trimmed = {k: v for k, v in data.items() if k not in set(unknown)}
            try:
                return model.model_validate(trimmed)
            except ValidationError as exc2:
                raise ScriptValidationError(
                    video_type, _format_pydantic_errors(exc2),
                    source) from None
        raise ScriptValidationError(
            video_type, _format_pydantic_errors(exc), source) from None


def validate_script(data: Dict[str, Any],
                    video_type: Optional[str] = None,
                    source: Optional[str] = None,
                    *,
                    drop_unknown: bool = False,
                    on_drop=None) -> ScriptBase:
    """Validate a script dict, or raise ScriptValidationError.

    Args:
        data: the parsed script JSON.
        video_type: expected type. When given it selects the model AND is
            checked against ``data["type"]`` — a caller that knows it asked
            for a quiz should not silently get an educational model back.
            When omitted the type is read from the data, which is required.
        source: file path, for the error message.
        drop_unknown: when True, unknown keys are removed and reported
            through ``on_drop`` instead of failing. Pipeline call sites pass
            True; tests pass False so a stray key is fatal there.
        on_drop: callable taking the sorted list of dropped key names.

    Returns:
        The validated model. Use ``.model_dump(by_alias=True)`` to get a dict
        back with ``_meta`` / ``_validation_warnings`` spelled correctly.
    """
    video_type = _resolve_type(data, video_type, source)
    return _validate_with(model_for(video_type), data, video_type, source,
                          drop_unknown, on_drop)


def validate_render_data(data: Dict[str, Any],
                         video_type: Optional[str] = None,
                         source: Optional[str] = None) -> ScriptBase:
    """Validate renderer input — a script merged with TTS output.

    Same per-type requirements as validate_script, plus tolerance for the
    TTS-owned keys and anything else our own pipeline attaches. There is no
    ``drop_unknown`` because these models already allow extras.
    """
    video_type = _resolve_type(data, video_type, source)
    return _validate_with(RENDER_MODELS[video_type], data, video_type, source,
                          False, None)


def check_script(data: Dict[str, Any],
                 video_type: Optional[str] = None,
                 source: Optional[str] = None):
    """Non-raising sibling of validate_script, for reporting over a corpus.

    Returns ``(model_or_None, errors, warnings)``.
    """
    try:
        model = validate_script(data, video_type=video_type, source=source)
    except ScriptValidationError as exc:
        return None, exc.problems, []
    return model, [], model.lint()


def lint_script(data: Dict[str, Any],
                video_type: Optional[str] = None,
                source: Optional[str] = None) -> List[str]:
    """Advisory-only checks. Returns [] for a script that fails validation."""
    _, _, warnings = check_script(data, video_type=video_type, source=source)
    return warnings
