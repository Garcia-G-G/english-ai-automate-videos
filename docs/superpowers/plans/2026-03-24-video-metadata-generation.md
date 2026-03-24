# Video Title, Description & Hashtag Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every generated video automatically gets an attention-grabbing bilingual title, engaging description, and 5-7 tiered hashtags — with per-platform adaptation at upload time and dashboard regeneration buttons.

**Architecture:** Add `video_title`, `video_description`, and enriched `hashtags` fields to all 6 GPT prompt templates so metadata is generated alongside the script. Create `src/metadata_generator.py` for platform adaptation and GPT-powered per-platform regeneration. Update `main.py` upload flow and `admin.py` dashboard to use the new metadata.

**Tech Stack:** OpenAI GPT-4o-mini (existing), Streamlit (existing dashboard), Python

---

### Task 1: Add metadata fields to GPT prompt templates

**Files:**
- Modify: `src/script_generator.py` (all 6 `build_prompt_*` functions)

- [ ] **Step 1: Add metadata generation instructions to `build_prompt_educational`**

Add to the prompt's REGLAS section and JSON format:

```python
# In build_prompt_educational, add to the REGLAS section after rule 8:
"""
9. Genera un título viral bilingüe (español + palabras clave en inglés) de máximo 80 caracteres
10. Genera una descripción atractiva de 2-3 líneas con emojis, CTA y mezcla bilingüe
11. Los hashtags deben ser 5-7: 2 amplios (#LearnEnglish #AprendeIngles), 2 medianos (categoría), 1-3 específicos del tema
"""

# Add to the JSON format:
"""
  "video_title": "Título viral bilingüe ≤80 chars. Usa: curiosidad, reto, identidad. Ej: 'Esta palabra NO significa lo que crees 😱 #English'",
  "video_description": "Descripción 2-3 líneas con emoji + CTA. Ej: '¿Sabías que embarrassed NO significa embarazada? 🤯\\n\\nAprende los false friends más comunes 👇\\nSígueme para más tips de inglés cada día 🦊'",
  "hashtags": ["#LearnEnglish", "#AprendeIngles", "#FalseFriends", "#ErroresComunes", "#InglesFacil", "#EnglishTips"]
"""
```

- [ ] **Step 2: Add metadata fields to `build_prompt_quiz`**

Same pattern — add `video_title`, `video_description` fields to the JSON format. Quiz-specific title templates:

```python
# Quiz title examples in prompt:
# "¿Puedes acertar las 3? 🧠 English Quiz"
# "Solo el 10% acierta la pregunta 3 😱"
```

- [ ] **Step 3: Add metadata fields to `build_prompt_true_false`**

```python
# True/false title examples in prompt:
# "¿Verdadero o Falso? 🤔 Te va a sorprender"
# "Esta palabra engaña a TODOS los hispanohablantes"
```

- [ ] **Step 4: Add metadata fields to `build_prompt_fill_blank`**

```python
# Fill blank title examples in prompt:
# "¿Puedes completar la frase? 💬 Test your English"
# "Solo fluent speakers completan esta frase"
```

- [ ] **Step 5: Add metadata fields to `build_prompt_pronunciation`**

```python
# Pronunciation title examples in prompt:
# "Llevas toda tu vida diciendo '{word}' MAL 😬"
# "La pronunciación que NADIE te enseñó: '{word}'"
```

- [ ] **Step 6: Add metadata fields to `build_prompt_vocabulary`**

```python
# Vocabulary title examples in prompt:
# "10 palabras en inglés que NECESITAS saber 📚"
# "Vocabulario de {tema} que vas a usar TODOS los días"
```

- [ ] **Step 7: Update `validate_and_clean_script` to handle new fields**

Add `video_title` and `video_description` to validation — generate fallbacks if GPT omits them:

```python
# In validate_and_clean_script, after existing validation:
if "video_title" not in script or not script.get("video_title"):
    # Fallback: build from hook/question/statement
    fallback = script.get("hook") or script.get("question") or script.get("statement") or script.get("word", "")
    script["video_title"] = fallback[:80] if fallback else "Aprende inglés hoy 🦊"
    warnings.append("Generated fallback video_title from script content")

if "video_description" not in script or not script.get("video_description"):
    title = script.get("video_title", "")
    cta = script.get("cta", "Sígueme para más tips de inglés 🦊")
    script["video_description"] = f"{title}\n\n{cta}"
    warnings.append("Generated fallback video_description")

# Ensure hashtags is a list of 5-7 items
hashtags = script.get("hashtags", [])
if isinstance(hashtags, str):
    hashtags = [h.strip() for h in hashtags.split() if h.startswith("#")]
# Ensure minimum broad hashtags are present
broad = {"#LearnEnglish", "#AprendeIngles"}
existing = {h.lstrip("#").lower() for h in hashtags}
for tag in broad:
    if tag.lstrip("#").lower() not in existing:
        hashtags.append(tag)
script["hashtags"] = hashtags[:7]
```

- [ ] **Step 8: Verify by running script generator dry-run**

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from script_generator import build_prompt_educational, load_topics
topics = load_topics('false_friends')
prompt = build_prompt_educational('false_friends', topics[0])
assert 'video_title' in prompt
assert 'video_description' in prompt
print('Prompt contains metadata fields: OK')
print(f'Prompt length: {len(prompt)} chars')
"
```
Expected: Both assertions pass.

- [ ] **Step 9: Commit**

```bash
git add src/script_generator.py
git commit -m "feat: add video_title, video_description to all GPT prompt templates"
```

---

### Task 2: Create metadata generator module

**Files:**
- Create: `src/metadata_generator.py`

- [ ] **Step 1: Create `metadata_generator.py` with core functions**

```python
"""
Video metadata generator — titles, descriptions, hashtags with platform adaptation.

Generates attention-grabbing bilingual metadata from script data,
with platform-specific formatting for TikTok, YouTube, and Instagram.
"""

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Platform limits
PLATFORM_LIMITS = {
    "tiktok": {"title": 150, "description": 2200, "hashtags_in_caption": True},
    "youtube": {"title": 100, "description": 5000, "hashtags_in_caption": False, "shorts_tag": True},
    "instagram": {"title": 0, "description": 2200, "hashtags_in_caption": True},
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

# Broad hashtags always included
BROAD_HASHTAGS = ["#LearnEnglish", "#AprendeIngles"]

# Medium hashtags by video type
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

    Returns dict with: title, description, hashtags, platform_adapted.
    Uses GPT-generated fields if present, falls back to templates.
    """
    # Try GPT-generated fields first
    title = script_data.get("video_title", "")
    description = script_data.get("video_description", "")
    hashtags = script_data.get("hashtags", [])

    if isinstance(hashtags, str):
        hashtags = [h.strip() for h in hashtags.split() if h.strip()]

    # Fallback title from script content
    if not title:
        title = _build_fallback_title(script_data, video_type)

    # Fallback description
    if not description:
        description = _build_fallback_description(script_data, video_type, title)

    # Ensure hashtag quality
    hashtags = _ensure_hashtags(hashtags, video_type, category)

    return {
        "title": title[:150],  # safe max across platforms
        "description": description,
        "hashtags": hashtags,
    }


def adapt_for_platform(metadata: dict, platform: str) -> dict:
    """Adapt metadata for a specific platform's requirements.

    Args:
        metadata: dict with title, description, hashtags
        platform: 'tiktok', 'youtube', or 'instagram'

    Returns:
        Platform-adapted dict with title, description, hashtags.
    """
    limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["tiktok"])
    title = metadata["title"]
    description = metadata["description"]
    hashtags = metadata["hashtags"]
    hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in hashtags)

    if platform == "youtube":
        # YouTube: short title with #Shorts, hashtags in description
        yt_title = title[:95]
        if "#Shorts" not in yt_title:
            yt_title = f"{yt_title[:90]} #Shorts" if len(yt_title) > 90 else f"{yt_title} #Shorts"
        yt_title = yt_title[:100]
        yt_desc = f"{description}\n\n{hashtag_str}"
        return {"title": yt_title, "description": yt_desc[:5000], "hashtags": hashtags}

    elif platform == "instagram":
        # Instagram: everything in caption
        ig_caption = f"{title}\n\n{description}\n\n{hashtag_str}"
        return {"title": "", "description": ig_caption[:2200], "hashtags": hashtags}

    else:  # tiktok (default)
        # TikTok: title is caption, hashtags inline
        tk_caption = f"{title}\n\n{description}\n\n{hashtag_str}"
        return {"title": title[:150], "description": tk_caption[:2200], "hashtags": hashtags}


def regenerate_for_platform(script_data: dict, platform: str, video_type: str) -> dict:
    """Use GPT to regenerate metadata optimized for a specific platform.

    Makes a focused API call to create platform-native title + description.
    """
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Fallback to template-based
        meta = generate_metadata(script_data, video_type)
        return adapt_for_platform(meta, platform)

    client = OpenAI(api_key=api_key)

    platform_instructions = {
        "tiktok": "TikTok: caption visible ~80 chars before '...more'. Use emojis, curiosity gaps, bilingual hooks. Hashtags inline.",
        "youtube": "YouTube Shorts: title max 100 chars (searchable!). Include keywords. Description for SEO. Add #Shorts.",
        "instagram": "Instagram Reels: caption max 2200 chars. Visual hook, storytelling, emojis. Hashtags at the end.",
    }

    hook = script_data.get("hook") or script_data.get("question") or script_data.get("statement") or ""
    topic = script_data.get("word") or script_data.get("title") or ""
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

        # Track cost
        try:
            from cost_tracker import get_tracker
            if hasattr(response, 'usage') and response.usage:
                get_tracker().log_openai_chat(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    model="gpt-4o-mini", label=f"metadata_{platform}")
        except Exception:
            pass

        # Ensure hashtags are a list
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
    import random

    templates = TITLE_TEMPLATES.get(video_type, TITLE_TEMPLATES["educational"])
    template = random.choice(templates)

    # Extract key content for template substitution
    word = (script_data.get("word") or
            (script_data.get("english_phrases", [""])[0] if script_data.get("english_phrases") else "") or "")
    title_field = script_data.get("title", "")

    try:
        return template.format(word=word, title=title_field)
    except (KeyError, IndexError):
        # If template substitution fails, use hook/question/statement
        fallback = (script_data.get("hook") or
                    script_data.get("question") or
                    script_data.get("statement") or
                    script_data.get("title") or
                    "Aprende inglés hoy 🦊")
        return fallback[:80]


def _build_fallback_description(script_data: dict, video_type: str, title: str) -> str:
    """Build description from script content."""
    cta = script_data.get("cta", "Sígueme para más tips de inglés 🦊")
    tip = script_data.get("tip", "")

    parts = [title]
    if tip:
        parts.append(f"💡 {tip}")
    parts.append(f"\n{cta}")

    return "\n\n".join(parts)


def _ensure_hashtags(hashtags: list, video_type: str, category: str = "") -> list:
    """Ensure hashtags meet quality bar: 5-7 tags, tiered."""
    # Normalize
    clean = []
    for h in hashtags:
        h = h.strip().lstrip("#")
        if h and h not in [c.lstrip("#") for c in clean]:
            clean.append(f"#{h}")

    # Ensure broad hashtags
    existing_lower = {h.lstrip("#").lower() for h in clean}
    for broad in BROAD_HASHTAGS:
        if broad.lstrip("#").lower() not in existing_lower:
            clean.insert(0, broad)

    # Ensure type hashtags
    for type_tag in TYPE_HASHTAGS.get(video_type, []):
        if type_tag.lstrip("#").lower() not in existing_lower and len(clean) < 7:
            clean.append(type_tag)

    return clean[:7]
```

- [ ] **Step 2: Verify module imports and works**

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from metadata_generator import generate_metadata, adapt_for_platform

# Test with mock script data
script = {
    'video_title': 'Esta palabra NO significa lo que crees 😱',
    'video_description': '¿Sabías que embarrassed NO es embarazada? 🤯\nAprende más 👇',
    'hashtags': ['#LearnEnglish', '#FalseFriends', '#AprendeIngles', '#ErroresComunes', '#InglesFacil'],
    'hook': 'Test hook',
}
meta = generate_metadata(script, 'educational', 'false_friends')
print(f'Title: {meta[\"title\"]}')
print(f'Description: {meta[\"description\"]}')
print(f'Hashtags: {meta[\"hashtags\"]}')

# Test platform adaptation
for platform in ['tiktok', 'youtube', 'instagram']:
    adapted = adapt_for_platform(meta, platform)
    print(f'{platform}: title={len(adapted[\"title\"])} chars, desc={len(adapted[\"description\"])} chars')

# Test fallback (no GPT fields)
script2 = {'hook': 'Test hook fallback', 'cta': 'Follow for more!'}
meta2 = generate_metadata(script2, 'educational')
print(f'Fallback title: {meta2[\"title\"]}')
print('ALL OK')
"
```
Expected: Metadata generated, all platforms adapted, fallback works.

- [ ] **Step 3: Commit**

```bash
git add src/metadata_generator.py
git commit -m "feat: add metadata_generator module for titles, descriptions, hashtags"
```

---

### Task 3: Update main.py upload flow to use metadata generator

**Files:**
- Modify: `main.py:229-286` (`upload_video` function)

- [ ] **Step 1: Replace basic metadata extraction with `generate_metadata` + `adapt_for_platform`**

Replace the `upload_video` function body (lines 250-266) with:

```python
def upload_video(video_path: Path, video_type: str, script_data: dict = None, platforms: list = None):
    """Upload a video to configured social platforms."""
    try:
        from uploader import UploadManager, VideoMetadata
        from metadata_generator import generate_metadata, adapt_for_platform
        import yaml

        config_path = ROOT / "config.yaml"
        config = {}
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

        upload_config = config.get("upload", {})
        if platforms is None:
            platforms = upload_config.get("platforms", [])

        if not platforms:
            logger.warning("No upload platforms configured. Add platforms to config.yaml upload.platforms")
            return

        # Generate rich metadata from script
        category = ""
        if script_data:
            category = script_data.get("_meta", {}).get("category", "")
        meta = generate_metadata(script_data or {}, video_type, category)

        platform_map = {"tiktok": "tiktok", "youtube": "youtube", "instagram": "instagram"}
        manager = UploadManager()

        for platform_name in platforms:
            platform_key = platform_map.get(platform_name.lower(), platform_name.lower())

            # Adapt metadata for this specific platform
            adapted = adapt_for_platform(meta, platform_key)

            metadata = VideoMetadata(
                title=adapted["title"],
                description=adapted["description"],
                hashtags=[h.lstrip("#") for h in adapted["hashtags"]],
                privacy="public",
            )

            logger.info("Uploading to %s: '%s'", platform_name, adapted["title"][:60])

            result = manager.upload(
                platform_key,
                str(video_path),
                title=metadata.title,
                description=metadata.full_description,
                hashtags=metadata.hashtags,
            )

            if hasattr(result, 'success'):
                if result.success:
                    logger.info("Uploaded to %s: %s", platform_name, result.url or result.upload_id)
                else:
                    logger.error("Upload to %s failed: %s", platform_name, result.error)
            elif isinstance(result, dict):
                if result.get("success"):
                    logger.info("Uploaded to %s", platform_name)
                else:
                    logger.error("Upload to %s failed: %s", platform_name, result.get("error"))

    except ImportError as e:
        logger.error("Upload module not available: %s", e)
    except Exception as e:
        logger.error("Upload failed: %s", e)
```

- [ ] **Step 2: Verify main.py imports work**

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
# Just verify the import chain works
from metadata_generator import generate_metadata, adapt_for_platform
print('Import OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: use metadata_generator for rich upload metadata"
```

---

### Task 4: Update dashboard Upload page with platform regeneration buttons

**Files:**
- Modify: `src/admin.py:1149-1255` (Upload page section)

- [ ] **Step 1: Update single-video upload section with auto-generated metadata and regeneration buttons**

Replace the upload page video loop (lines 1152-1214) with enhanced version that:
1. Auto-generates title + description using `generate_metadata()`
2. Shows them in editable text areas
3. Adds 3 platform-specific regenerate buttons (TikTok / YouTube / Instagram)
4. Uses the adapted metadata when uploading

```python
        for video in approved:
            with st.container():
                col1, col2 = st.columns([3, 2])

                with col1:
                    st.write(f"**{video['name']}**")
                    st.caption(f"{video['type']} | {video['created'].strftime('%Y-%m-%d %H:%M')}")

                with col2:
                    # Generate metadata from script
                    script = {}
                    category = ""
                    if video.get("meta") and "script_data" in video["meta"]:
                        script = video["meta"]["script_data"]
                        category = script.get("_meta", {}).get("category", "")

                    try:
                        from metadata_generator import generate_metadata, adapt_for_platform, regenerate_for_platform
                        meta = generate_metadata(script, video.get("type", "educational"), category)
                    except ImportError:
                        meta = {
                            "title": script.get("hook", script.get("question", script.get("statement", ""))),
                            "description": "",
                            "hashtags": script.get("hashtags", ["#LearnEnglish"]),
                        }

                    # Session state keys for this video
                    title_key = f"meta_title_{video['name']}"
                    desc_key = f"meta_desc_{video['name']}"
                    tags_key = f"meta_tags_{video['name']}"

                    if title_key not in st.session_state:
                        st.session_state[title_key] = meta["title"]
                        st.session_state[desc_key] = meta["description"]
                        st.session_state[tags_key] = " ".join(meta["hashtags"])

                    with st.expander("Edit Title & Description"):
                        st.session_state[title_key] = st.text_input(
                            "Title", value=st.session_state[title_key], key=f"ti_{video['name']}"
                        )
                        st.session_state[desc_key] = st.text_area(
                            "Description", value=st.session_state[desc_key], key=f"de_{video['name']}",
                            height=80
                        )
                        st.session_state[tags_key] = st.text_input(
                            "Hashtags", value=st.session_state[tags_key], key=f"ht_{video['name']}"
                        )

                        # Platform regeneration buttons
                        regen_cols = st.columns(3)
                        for i, (icon, pname, pkey) in enumerate([
                            ("🎵", "TikTok", "tiktok"),
                            ("▶️", "YouTube", "youtube"),
                            ("📸", "Instagram", "instagram"),
                        ]):
                            with regen_cols[i]:
                                if st.button(f"{icon} {pname}", key=f"regen_{pkey}_{video['name']}",
                                             use_container_width=True, help=f"Regenerate for {pname}"):
                                    try:
                                        with st.spinner(f"Generating for {pname}..."):
                                            result = regenerate_for_platform(
                                                script, pkey, video.get("type", "educational")
                                            )
                                            st.session_state[title_key] = result.get("title", "")
                                            st.session_state[desc_key] = result.get("description", "")
                                            tags = result.get("hashtags", [])
                                            st.session_state[tags_key] = " ".join(
                                                f"#{t.lstrip('#')}" for t in tags
                                            )
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"Regeneration failed: {e}")

                # Upload buttons
                if target_platforms:
                    if st.button("📤 Upload", key=f"upload_{video['name']}", use_container_width=True):
                        try:
                            from uploader import get_upload_manager
                            manager = get_upload_manager()
                            vid_title = st.session_state.get(title_key, "")
                            vid_desc = st.session_state.get(desc_key, "")
                            vid_tags = st.session_state.get(tags_key, "").split()

                            platform_map = {
                                "TikTok": "tiktok",
                                "YouTube Shorts": "youtube",
                                "Instagram Reels": "instagram",
                            }
                            for platform_name in target_platforms:
                                platform_key = platform_map.get(platform_name, platform_name.lower())
                                with st.spinner(f"Uploading to {platform_name}..."):
                                    result = manager.upload(
                                        platform_key,
                                        str(video["path"]),
                                        title=vid_title[:100],
                                        description=f"{vid_desc}\n\n{' '.join(vid_tags)}",
                                        hashtags=[t.lstrip("#") for t in vid_tags]
                                    )
                                    if isinstance(result, dict) and result.get("success"):
                                        st.success(f"Uploaded to {platform_name}!")
                                    elif hasattr(result, 'success') and result.success:
                                        st.success(f"Uploaded to {platform_name}!")
                                    else:
                                        err = result.get("error", "Unknown") if isinstance(result, dict) else getattr(result, 'error', 'Unknown')
                                        st.error(f"Failed: {err}")
                        except ImportError:
                            st.error("Upload module not available.")
                        except Exception as e:
                            st.error(f"Upload error: {str(e)}")
                else:
                    st.button("📤 Upload", key=f"upload_{video['name']}", disabled=True, use_container_width=True)

                st.markdown("---")
```

- [ ] **Step 2: Update bulk upload to use metadata generator**

Replace the bulk upload section (lines 1222-1254) to use `generate_metadata` + `adapt_for_platform`:

```python
        # Bulk upload
        if target_platforms and len(approved) > 1:
            st.markdown("---")
            st.markdown("**Bulk Upload**")
            if st.button(f"📤 Upload All {len(approved)} Videos", type="primary"):
                progress = st.progress(0)
                try:
                    from uploader import get_upload_manager
                    from metadata_generator import generate_metadata, adapt_for_platform
                    manager = get_upload_manager()

                    bulk_platform_map = {
                        "TikTok": "tiktok",
                        "YouTube Shorts": "youtube",
                        "Instagram Reels": "instagram",
                    }
                    for i, video in enumerate(approved):
                        script = {}
                        category = ""
                        if video.get("meta") and "script_data" in video["meta"]:
                            script = video["meta"]["script_data"]
                            category = script.get("_meta", {}).get("category", "")

                        meta = generate_metadata(script, video.get("type", "educational"), category)

                        for pname in target_platforms:
                            pkey = bulk_platform_map.get(pname, pname.lower())
                            adapted = adapt_for_platform(meta, pkey)
                            manager.upload(
                                pkey,
                                str(video["path"]),
                                title=adapted["title"],
                                description=adapted["description"],
                                hashtags=[h.lstrip("#") for h in adapted["hashtags"]],
                            )
                        progress.progress((i + 1) / len(approved))

                    st.success(f"Uploaded {len(approved)} videos!")
                except Exception as e:
                    st.error(f"Bulk upload error: {str(e)}")
```

- [ ] **Step 3: Commit**

```bash
git add src/admin.py
git commit -m "feat: dashboard upload page with auto-generated metadata and platform regen buttons"
```

---

### Task 5: Update dashboard Review page to show generated metadata

**Files:**
- Modify: `src/admin.py:1016-1047` (Review page video loop)

- [ ] **Step 1: Add metadata preview to review page**

After the script details expander (line 1032), add a metadata preview:

```python
                    # Show generated metadata preview
                    try:
                        from metadata_generator import generate_metadata
                        category = script.get("_meta", {}).get("category", "")
                        meta = generate_metadata(script, video["type"], category)
                        st.markdown("**Generated Metadata:**")
                        st.markdown(f"**Title:** {meta['title']}")
                        st.markdown(f"**Description:** {meta['description'][:100]}...")
                        st.markdown(f"**Hashtags:** {' '.join(meta['hashtags'][:5])}")
                    except ImportError:
                        pass
```

- [ ] **Step 2: Commit**

```bash
git add src/admin.py
git commit -m "feat: show generated metadata preview on review page"
```

---

### Task 6: Final integration test

**Files:** None (testing only)

- [ ] **Step 1: Test full metadata flow**

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from script_generator import build_prompt_educational, load_topics, validate_and_clean_script
from metadata_generator import generate_metadata, adapt_for_platform

# 1. Verify prompts include metadata fields
topics = load_topics('false_friends')
prompt = build_prompt_educational('false_friends', topics[0])
assert 'video_title' in prompt, 'Prompt missing video_title'
assert 'video_description' in prompt, 'Prompt missing video_description'
print('1. Prompts include metadata fields: OK')

# 2. Test validation fallbacks
script = {'type': 'educational', 'full_script': 'test', 'hook': 'Test hook', 'english_phrases': ['test'], 'cta': 'Follow!'}
cleaned = validate_and_clean_script(script, 'educational')
assert 'video_title' in cleaned, 'Validation missing video_title fallback'
assert 'video_description' in cleaned, 'Validation missing video_description fallback'
print(f'2. Fallback title: {cleaned[\"video_title\"][:50]}')

# 3. Test metadata generation
meta = generate_metadata(cleaned, 'educational', 'false_friends')
assert meta['title'], 'No title generated'
assert meta['hashtags'], 'No hashtags generated'
assert len(meta['hashtags']) >= 4, f'Too few hashtags: {len(meta[\"hashtags\"])}'
print(f'3. Metadata: title={meta[\"title\"][:40]}..., {len(meta[\"hashtags\"])} hashtags')

# 4. Test platform adaptation
for platform in ['tiktok', 'youtube', 'instagram']:
    adapted = adapt_for_platform(meta, platform)
    print(f'4. {platform}: title={len(adapted[\"title\"])}ch, desc={len(adapted[\"description\"])}ch')
    if platform == 'youtube':
        assert '#Shorts' in adapted['title'], 'YouTube missing #Shorts'

print('\\nALL INTEGRATION TESTS PASS')
"
```

- [ ] **Step 2: Test dashboard imports**

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from metadata_generator import generate_metadata, adapt_for_platform, regenerate_for_platform
print('Dashboard imports OK')
"
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete video metadata generation system — titles, descriptions, hashtags"
```
