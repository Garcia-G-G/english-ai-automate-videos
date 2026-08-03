"""
Video metadata generator — titles, descriptions, hashtags with platform adaptation.

Generates attention-grabbing bilingual metadata from script data,
with platform-specific formatting for TikTok, YouTube, and Instagram.
"""

import json
import logging
import os
import random
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Platform limits
PLATFORM_LIMITS = {
    "tiktok": {"title": 150, "description": 2200},
    "youtube": {"title": 100, "description": 5000},
    "instagram": {"title": 0, "description": 2200},
}

# Fallback title templates by video type
TITLE_TEMPLATES = {
    "educational": [
        "¿Sabías que '{word}' NO significa lo que crees? 😱",
        "El error que TODOS los hispanohablantes cometen 🚫",
        "Esta regla del inglés te va a volar la cabeza 🤯",
    ],
    "quiz": [
        "¿Puedes acertar las 3? 🧠 English Quiz",
        "Solo el 10% acierta la última pregunta 😱",
        "Quiz de inglés: ¿Cuántas aciertas? 🎯",
    ],
    "true_false": [
        "¿Verdadero o Falso? 🤔 Te va a sorprender",
        "Esta palabra engaña a TODOS los hispanohablantes",
        "¿True or False? Pon a prueba tu inglés 🧐",
    ],
    "fill_blank": [
        "¿Puedes completar la frase? 💬 Test your English",
        "Solo fluent speakers completan esta frase 👀",
        "Completa y demuestra tu nivel de inglés ✍️",
    ],
    "pronunciation": [
        "Llevas TODA tu vida diciendo '{word}' MAL 😬",
        "La pronunciación que NADIE te enseñó 🗣️",
        "¿Puedes pronunciar '{word}' correctamente? 🎤",
    ],
    "vocabulary": [
        "Vocabulario que vas a usar TODOS los días 📚",
        "Palabras en inglés que NECESITAS saber 🔥",
        "{title} — aprende en 30 segundos ⚡",
    ],
}

# ── Hashtag strategy ────────────────────────────────────────────────
#
# Researched 2026-08-01; sources in docs/metadata-best-practices.md.
#
# The recommended mix everywhere is TIERED, not a flat list:
#   broad    high volume, low specificity  — reach
#   type     what kind of video this is    — categorisation
#   niche    the actual topic/audience     — the people who convert
#
# PER-PLATFORM COUNTS DIFFER, and one number for all three is wrong:
#
#   youtube    3-5 recommended. HARD CLIFF: more than 15 and YouTube
#              ignores EVERY hashtag on the video, so the cap is a
#              correctness constraint, not a preference.
#   instagram  5-15 targeted; 30 allowed. 10+ sits comfortably in band.
#   tiktok     3-5 recommended; diminishing returns past 10-15; 30 max.
#
# HASHTAG_TARGET is the requested floor for the generated POOL. Each
# platform then takes its own slice in adapt_for_platform, so the pool can
# be rich without spamming a platform that punishes volume.
HASHTAG_TARGET = 12

PLATFORM_HASHTAGS = {
    "youtube": 10,     # above the 3-5 guidance, deliberately — see the doc
    "instagram": 12,
    "tiktok": 10,
}

#: Exceeding this makes YouTube discard ALL hashtags on the video. Never
#: raise it; it is a platform rule, not a style choice.
YOUTUBE_HASHTAG_HARD_CAP = 15

BROAD_HASHTAGS = ["#LearnEnglish", "#AprendeIngles", "#InglesOnline"]

TYPE_HASHTAGS = {
    "educational": ["#EnglishTips", "#InglesFacil", "#ClasesDeIngles"],
    "quiz": ["#EnglishQuiz", "#QuizTime", "#RetoDeIngles"],
    "true_false": ["#TrueOrFalse", "#VerdaderoOFalso", "#RetoDeIngles"],
    "fill_blank": ["#FillInTheBlank", "#CompletaLaFrase", "#PracticaIngles"],
    "pronunciation": ["#Pronunciation", "#SpeakEnglish", "#PronunciacionIngles"],
    "vocabulary": ["#Vocabulary", "#EnglishWords", "#VocabularioIngles"],
}

#: Audience/intent tags. Spanish-first, because the audience searches in
#: Spanish even when the subject is English.
NICHE_HASHTAGS = [
    "#InglesParaHispanohablantes", "#AprenderIngles", "#EnglishForSpanishSpeakers",
    "#IdiomasEnCasa", "#EstudiaIngles", "#InglesDiario", "#EnglishPractice",
    "#HablarIngles", "#InglesRapido", "#EnglishLearning",
]


def generate_metadata(script_data: dict, video_type: str, category: str = "") -> dict:
    """Extract or generate video metadata from script data.

    Returns dict with: title, description, hashtags.
    Uses GPT-generated fields if present, falls back to templates.
    """
    title = script_data.get("video_title", "")
    description = script_data.get("video_description", "")
    hashtags = script_data.get("hashtags", [])

    if isinstance(hashtags, str):
        hashtags = [h.strip() for h in hashtags.split() if h.strip()]

    if not title:
        title = _build_fallback_title(script_data, video_type)

    if not description:
        description = _build_fallback_description(script_data, video_type, title)

    hashtags = _ensure_hashtags(hashtags, video_type, category)

    return {
        "title": title[:150],
        "description": description,
        "hashtags": hashtags,
    }


def compose_description(description: str, hashtags: List[str]) -> str:
    """Attach the hashtag block to a description. THE ONLY PLACE THIS HAPPENS.

    Composition is owned HERE, upstream, not by the uploader. The uploader's
    job is to send what it is given; it has no platform knowledge and cannot
    tell an already-composed description from a raw one. When both appended,
    every published video carried its hashtag block twice.

    Idempotent as a backstop — if the block is already present it is not added
    again — but callers should still append exactly once. The guard is there so
    a future third caller cannot silently reintroduce the defect, not as a
    licence to append blindly.
    """
    body = (description or "").rstrip()
    if not hashtags:
        return body
    block = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    first = f"#{hashtags[0].lstrip('#')}"
    if first and first in body:
        return body
    return f"{body}\n\n{block}" if body else block


def adapt_for_platform(metadata: dict, platform: str) -> dict:
    """Adapt metadata for one platform's rules.

    Returns `hashtags` ALREADY SLICED to that platform's count, and a
    description that already contains them. Callers must NOT append the
    hashtag list again — see the note in uploader.VideoMetadata.
    """
    title = metadata["title"]
    description = metadata["description"]
    all_tags = metadata["hashtags"]

    limit = PLATFORM_HASHTAGS.get(platform, HASHTAG_TARGET)
    if platform == "youtube":
        # Hard platform rule, not a preference: past this, YouTube discards
        # every hashtag on the video.
        limit = min(limit, YOUTUBE_HASHTAG_HARD_CAP)
    tags = all_tags[:limit]

    if platform == "youtube":
        # Hashtags go in the DESCRIPTION, not the title: the first three
        # render as clickable links above the title, and a clean title keeps
        # the keywords readable. #Shorts is the exception — it must appear
        # for the Shorts shelf.
        yt_title = title[:95]
        if "#Shorts" not in yt_title:
            yt_title = f"{yt_title[:90]} #Shorts" if len(yt_title) > 90 else f"{yt_title} #Shorts"
        yt_title = yt_title[:100]
        yt_desc = compose_description(description, tags)
        return {"title": yt_title, "description": yt_desc[:5000], "hashtags": tags}

    elif platform == "instagram":
        # No title field; the caption is everything. Keyword-first, because
        # Instagram now indexes caption text more heavily than tags.
        ig_caption = compose_description(f"{title}\n\n{description}", tags)
        return {"title": "", "description": ig_caption[:2200], "hashtags": tags}

    else:  # tiktok
        tk_caption = compose_description(f"{title}\n\n{description}", tags)
        return {"title": title[:150], "description": tk_caption[:2200], "hashtags": tags}


def regenerate_for_platform(script_data: dict, platform: str, video_type: str) -> dict:
    """Use GPT to regenerate metadata optimized for a specific platform."""
    from openai import OpenAI

    # Load .env at the ENTRY POINT, not at import.
    #
    # Without this the key is absent when this module is invoked standalone,
    # the function silently takes its fallback branch, and the result looks
    # exactly like "the API call never fires" — which is the wrong conclusion
    # and the one I nearly reported while diagnosing the dashboard.
    from env_setup import ensure_env_loaded
    ensure_env_loaded()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        meta = generate_metadata(script_data, video_type)
        return adapt_for_platform(meta, platform)

    client = OpenAI(api_key=api_key)

    # Per-platform guidance, researched 2026-08-01. Full sources and the
    # numbers behind each line are in docs/metadata-best-practices.md.
    platform_instructions = {
        "tiktok": (
            "TikTok. Ideal caption 150-300 characters — that band measurably "
            "outperforms longer captions on reach. The FIRST 80-120 characters "
            "must carry the whole hook, because that is all a viewer sees "
            "before the 'more' cut. Everything after it is for search. Front-"
            "load the concrete payoff, not a greeting."
        ),
        "youtube": (
            "YouTube Shorts. The title is a SEARCH SURFACE — put the real "
            "keyword a learner would type ('significado', 'cómo se dice', the "
            "English word itself) in the first 40 characters, and keep it "
            "under 70 so nothing is truncated on mobile. No hashtags in the "
            "title; they belong in the description. Description line 1 is one "
            "sentence of context that repeats the main keyword naturally."
        ),
        "instagram": (
            "Instagram Reels. The caption hook must land in under 80 "
            "characters, before the 'Read More' cut. Instagram now indexes "
            "caption KEYWORDS more heavily than hashtags, so write the topic "
            "in plain words in the first line rather than relying on tags."
        ),
    }

    # The audience searches in SPANISH even though the subject is English.
    audience_note = (
        "AUDIENCE: Spanish speakers learning English. Write the hook in "
        "Spanish; keep the English term itself in English. A title that is "
        "entirely in English will not be found by the people it is for."
    )

    hook = script_data.get("hook") or script_data.get("question") or script_data.get("statement") or ""
    full_script_preview = (script_data.get("full_script") or "")[:200]

    prompt = f"""Generate an optimized title and description for a {platform} video about learning English (for Spanish speakers).

Platform: {platform_instructions.get(platform, "")}

Video type: {video_type}
Topic/Hook: {hook}
Content preview: {full_script_preview}

{audience_note}

Return JSON only:
{{
  "title": "Spanish hook + the English term. Front-load the searchable keyword.",
  "description": "First line = the hook, self-contained. Then 1-2 lines of value. Then a CTA. Emojis sparingly, where they replace a word rather than decorate one.",
  "hashtags": ["at least {HASHTAG_TARGET} hashtags without #, TIERED: 2-3 broad reach tags, 2-3 that name the video format, and the rest niche/audience tags a Spanish-speaking learner would actually follow"]
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            temperature=0.8,
            messages=[
                {"role": "system", "content": "You create viral social media metadata for English learning content targeting Spanish speakers. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ]
        )

        text = response.choices[0].message.content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)

        try:
            from cost_tracker import get_tracker
            if hasattr(response, 'usage') and response.usage:
                get_tracker().log_openai_chat(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    model="gpt-4o-mini", label=f"metadata_{platform}")
        except Exception:
            pass

        hashtags = result.get("hashtags", [])
        if isinstance(hashtags, str):
            hashtags = [h.strip().lstrip("#") for h in hashtags.split()]
        result["hashtags"] = [h.lstrip("#") for h in hashtags]

        return result

    except Exception as e:
        logger.warning("GPT metadata regeneration failed: %s, using fallback", e)
        meta = generate_metadata(script_data, video_type)
        return adapt_for_platform(meta, platform)


def _build_fallback_title(script_data: dict, video_type: str) -> str:
    """Build title from script content using proven templates."""
    templates = TITLE_TEMPLATES.get(video_type, TITLE_TEMPLATES["educational"])
    template = random.choice(templates)

    word = (script_data.get("word") or
            (script_data.get("english_phrases", [""])[0] if script_data.get("english_phrases") else "") or "")
    title_field = script_data.get("title", "")

    try:
        return template.format(word=word, title=title_field)
    except (KeyError, IndexError):
        fallback = (script_data.get("hook") or
                    script_data.get("question") or
                    script_data.get("statement") or
                    script_data.get("title") or
                    "Aprende inglés hoy 🦊")
        return fallback[:80]


def _build_fallback_description(script_data: dict, video_type: str, title: str) -> str:
    """Build description from script content — never repeats the title."""
    hook = script_data.get("hook") or script_data.get("question") or script_data.get("statement") or ""
    tip = script_data.get("tip", "")
    cta = script_data.get("cta", "Sígueme para más tips de inglés 🦊")
    explanation = script_data.get("explanation", "")

    parts = []

    # Use hook if it's different from the title
    if hook and hook[:30] != title[:30]:
        parts.append(hook)

    # Add tip if available
    if tip:
        parts.append(f"💡 {tip}")

    # Add short explanation snippet for quiz/true_false types
    if explanation and not tip:
        parts.append(explanation[:120])

    # Always end with CTA
    if cta:
        parts.append(cta)

    # If we still have nothing meaningful, use script preview
    if not parts:
        script_preview = (script_data.get("full_script") or "")[:150]
        if script_preview:
            parts.append(script_preview)
        parts.append("Sígueme para más tips de inglés 🦊")

    return "\n\n".join(parts)


def _ensure_hashtags(hashtags: list, video_type: str, category: str = "") -> list:
    """Build a tiered pool of at least HASHTAG_TARGET tags.

    Tiers, in order: whatever the script already produced, then broad, then
    type-specific, then niche/audience. Order matters — the first three are
    what YouTube surfaces as clickable links above the title, and on Instagram
    the earliest tags carry the most weight.

    Deduplication is case-insensitive and runs against a LIVE set. The previous
    version snapshotted `existing_lower` once and then appended without
    updating it, so a tag appearing in two tiers could be emitted twice.
    """
    out: List[str] = []
    seen = set()

    def add(tag: str) -> None:
        name = tag.strip().lstrip("#")
        if not name:
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(f"#{name}")

    for h in hashtags or []:
        add(h)
    for tier in (BROAD_HASHTAGS, TYPE_HASHTAGS.get(video_type, [])):
        for tag in tier:
            add(tag)
    if category:
        add(f"#{category.replace('_', '').title()}")
    for tag in NICHE_HASHTAGS:
        if len(out) >= HASHTAG_TARGET:
            break
        add(tag)

    return out
