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

BROAD_HASHTAGS = ["#LearnEnglish", "#AprendeIngles"]

TYPE_HASHTAGS = {
    "educational": ["#EnglishTips", "#InglesFacil"],
    "quiz": ["#EnglishQuiz", "#QuizTime"],
    "true_false": ["#TrueOrFalse", "#VerdaderoOFalso"],
    "fill_blank": ["#FillInTheBlank", "#CompletaLaFrase"],
    "pronunciation": ["#Pronunciation", "#SpeakEnglish"],
    "vocabulary": ["#Vocabulary", "#EnglishWords"],
}


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


def adapt_for_platform(metadata: dict, platform: str) -> dict:
    """Adapt metadata for a specific platform's requirements."""
    title = metadata["title"]
    description = metadata["description"]
    hashtags = metadata["hashtags"]
    hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in hashtags)

    if platform == "youtube":
        yt_title = title[:95]
        if "#Shorts" not in yt_title:
            yt_title = f"{yt_title[:90]} #Shorts" if len(yt_title) > 90 else f"{yt_title} #Shorts"
        yt_title = yt_title[:100]
        yt_desc = f"{description}\n\n{hashtag_str}"
        return {"title": yt_title, "description": yt_desc[:5000], "hashtags": hashtags}

    elif platform == "instagram":
        ig_caption = f"{title}\n\n{description}\n\n{hashtag_str}"
        return {"title": "", "description": ig_caption[:2200], "hashtags": hashtags}

    else:  # tiktok
        tk_caption = f"{title}\n\n{description}\n\n{hashtag_str}"
        return {"title": title[:150], "description": tk_caption[:2200], "hashtags": hashtags}


def regenerate_for_platform(script_data: dict, platform: str, video_type: str) -> dict:
    """Use GPT to regenerate metadata optimized for a specific platform."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        meta = generate_metadata(script_data, video_type)
        return adapt_for_platform(meta, platform)

    client = OpenAI(api_key=api_key)

    platform_instructions = {
        "tiktok": "TikTok: caption visible ~80 chars before '...more'. Use emojis, curiosity gaps, bilingual hooks. Hashtags inline.",
        "youtube": "YouTube Shorts: title max 100 chars (searchable!). Include keywords. Description for SEO. Add #Shorts.",
        "instagram": "Instagram Reels: caption max 2200 chars. Visual hook, storytelling, emojis. Hashtags at the end.",
    }

    hook = script_data.get("hook") or script_data.get("question") or script_data.get("statement") or ""
    full_script_preview = (script_data.get("full_script") or "")[:200]

    prompt = f"""Generate an optimized title and description for a {platform} video about learning English (for Spanish speakers).

Platform: {platform_instructions.get(platform, "")}

Video type: {video_type}
Topic/Hook: {hook}
Content preview: {full_script_preview}

Return JSON only:
{{
  "title": "Bilingual attention-grabbing title (Spanish + English keywords)",
  "description": "2-3 line description with emojis, value prop, and CTA",
  "hashtags": ["5-7 hashtags without #, mix of broad and niche"]
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
    """Ensure hashtags meet quality bar: 5-7 tags, tiered."""
    clean = []
    seen = set()
    for h in hashtags:
        h = h.strip().lstrip("#")
        if h and h.lower() not in seen:
            clean.append(f"#{h}")
            seen.add(h.lower())

    existing_lower = {h.lstrip("#").lower() for h in clean}
    for broad in BROAD_HASHTAGS:
        if broad.lstrip("#").lower() not in existing_lower:
            clean.insert(0, broad)

    for type_tag in TYPE_HASHTAGS.get(video_type, []):
        if type_tag.lstrip("#").lower() not in existing_lower and len(clean) < 7:
            clean.append(type_tag)

    return clean[:7]
