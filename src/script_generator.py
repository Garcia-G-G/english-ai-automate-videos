#!/usr/bin/env python3
"""
Script Generator for English AI Videos
Uses Claude API to generate lesson scripts from topic database.
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
import anthropic

# Load .env file from project root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


# Paths (already defined above)
TOPICS_DIR = ROOT / "content" / "topics"
OUTPUT_DIR = ROOT / "output" / "scripts"

# Claude settings
MODEL = "claude-3-haiku-20240307"  # Using Haiku for cost efficiency
MAX_TOKENS = 2000


def load_topics(category: str) -> list:
    """Load topics from a category JSON file."""
    path = TOPICS_DIR / f"{category}.json"
    if not path.exists():
        raise FileNotFoundError(f"Category not found: {category}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def list_categories() -> list:
    """List all available categories."""
    return [f.stem for f in TOPICS_DIR.glob("*.json")]


def find_topic(category: str, topic_name: str) -> dict:
    """Find a specific topic by name in a category."""
    topics = load_topics(category)
    topic_name_lower = topic_name.lower()

    for t in topics:
        # Check various fields for match
        if t.get("english", "").lower() == topic_name_lower:
            return t
        if t.get("topic", "").lower() == topic_name_lower:
            return t
        if t.get("wrong", "").lower() == topic_name_lower:
            return t
        if t.get("id", "").lower() == topic_name_lower:
            return t

    raise ValueError(f"Topic '{topic_name}' not found in category '{category}'")


def get_random_topic() -> tuple:
    """Get a random topic from a random category."""
    categories = list_categories()
    category = random.choice(categories)
    topics = load_topics(category)
    topic = random.choice(topics)
    return category, topic


def build_prompt(category: str, topic: dict) -> str:
    """Build the prompt for Claude based on category and topic."""

    if category == "false_friends":
        return f"""Genera un script de 30-45 segundos para un video de TikTok/Reels enseñando inglés a hispanohablantes.

TEMA: False Friend - "{topic['english']}"
- Los hispanohablantes piensan que significa: "{topic['spanish_trap']}"
- En realidad significa: "{topic['real_meaning']}"
- La palabra correcta en inglés para "{topic['spanish_trap']}" es: "{topic['correct_english']}"

REGLAS IMPORTANTES:
1. El script debe ser en ESPAÑOL, con las palabras en inglés entre comillas simples
2. Ejemplo: "La palabra 'embarrassed' NO significa embarazada"
3. Incluye un ejemplo práctico de uso en inglés
4. Usa un tono energético y educativo como profesor de TikTok
5. Incluye un tip memorable para recordar la diferencia
6. Termina con una pregunta o call-to-action

FORMATO JSON REQUERIDO:
{{
  "hook": "Frase inicial que capte atención (con palabra inglés en 'comillas')",
  "full_script": "Script completo en español con palabras inglés en 'comillas simples'. Debe fluir naturalmente para ser leído en voz alta.",
  "english_phrases": ["lista", "de", "palabras", "inglés", "usadas"],
  "translations": {{"palabra_ingles": "traduccion_español"}},
  "tip": "Tip memorable para recordar",
  "cta": "Call to action final",
  "hashtags": ["#AprendeIngles", "#FalseFriends", "#InglesConTiktok"]
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""

    elif category == "phrasal_verbs":
        examples = ", ".join(topic.get("examples", []))
        return f"""Genera un script de 30-45 segundos para un video de TikTok/Reels enseñando inglés a hispanohablantes.

TEMA: Phrasal Verb - "{topic['topic']}"
- Significado en español: "{topic['spanish']}"
- Ejemplos de uso: {examples}

REGLAS IMPORTANTES:
1. El script debe ser en ESPAÑOL, con las palabras en inglés entre comillas simples
2. Ejemplo: "El phrasal verb 'give up' significa rendirse"
3. Incluye 2-3 ejemplos prácticos de uso
4. Usa un tono energético y educativo
5. Incluye un tip para recordar el significado
6. Termina con una pregunta o call-to-action

FORMATO JSON REQUERIDO:
{{
  "hook": "Frase inicial que capte atención",
  "full_script": "Script completo en español con palabras inglés en 'comillas simples'",
  "english_phrases": ["lista", "de", "frases", "inglés"],
  "translations": {{"frase_ingles": "traduccion_español"}},
  "tip": "Tip memorable para recordar",
  "cta": "Call to action final",
  "hashtags": ["#AprendeIngles", "#PhrasalVerbs", "#InglesConTiktok"]
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""

    elif category == "common_mistakes":
        return f"""Genera un script de 30-45 segundos para un video de TikTok/Reels enseñando inglés a hispanohablantes.

TEMA: Error Común
- Error frecuente: "{topic['wrong']}"
- Forma correcta: "{topic['correct']}"
- Explicación: "{topic['explanation']}"

REGLAS IMPORTANTES:
1. El script debe ser en ESPAÑOL, con las palabras en inglés entre comillas simples
2. Muestra el error y luego la corrección
3. Incluye ejemplos prácticos
4. Usa un tono energético y educativo
5. Incluye un tip para evitar el error
6. Termina con una pregunta o call-to-action

FORMATO JSON REQUERIDO:
{{
  "hook": "Frase inicial que capte atención",
  "full_script": "Script completo en español con palabras inglés en 'comillas simples'",
  "english_phrases": ["lista", "de", "frases", "inglés"],
  "translations": {{"frase_ingles": "traduccion_español"}},
  "tip": "Tip memorable para recordar",
  "cta": "Call to action final",
  "hashtags": ["#AprendeIngles", "#ErroresComunes", "#InglesConTiktok"]
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""

    else:
        raise ValueError(f"Unknown category: {category}")


def generate_script(category: str, topic: dict) -> dict:
    """Call Claude API to generate a script."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(category, topic)

    print(f"Calling Claude API ({MODEL})...")

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = message.content[0].text.strip()

    # Parse JSON from response
    try:
        # Try to extract JSON if wrapped in markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        script = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON response: {e}")
        print(f"Raw response:\n{response_text}")
        raise

    # Add metadata
    script["_meta"] = {
        "category": category,
        "topic_id": topic.get("id", "unknown"),
        "generated_at": datetime.now().isoformat(),
        "model": MODEL
    }

    return script


def save_script(script: dict, name: str) -> Path:
    """Save script to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.json"
    path = OUTPUT_DIR / filename

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    return path


def main():
    parser = argparse.ArgumentParser(
        description="Generate English lesson scripts using Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/script_generator.py --list
  python src/script_generator.py --random
  python src/script_generator.py --category false_friends --topic embarrassed
  python src/script_generator.py -c phrasal_verbs -t "give up"
        """
    )

    parser.add_argument("--list", "-l", action="store_true",
                        help="List all categories and topics")
    parser.add_argument("--random", "-r", action="store_true",
                        help="Generate script for a random topic")
    parser.add_argument("--category", "-c", type=str,
                        help="Topic category (false_friends, phrasal_verbs, common_mistakes)")
    parser.add_argument("--topic", "-t", type=str,
                        help="Specific topic name")
    parser.add_argument("--output", "-o", type=str,
                        help="Output file path (default: auto-generated)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling API")

    args = parser.parse_args()

    # List mode
    if args.list:
        print("\nAvailable Categories and Topics:")
        print("=" * 50)
        for cat in list_categories():
            topics = load_topics(cat)
            print(f"\n{cat} ({len(topics)} topics):")
            for t in topics:
                name = t.get("english") or t.get("topic") or t.get("wrong")
                print(f"  - {name}")
        return

    # Determine category and topic
    if args.random:
        category, topic = get_random_topic()
        topic_name = topic.get("english") or topic.get("topic") or topic.get("wrong")
        print(f"\nRandom selection: {category} → {topic_name}")
    elif args.category and args.topic:
        category = args.category
        topic = find_topic(category, args.topic)
        topic_name = args.topic
    else:
        parser.print_help()
        print("\nError: Use --random or specify --category and --topic")
        sys.exit(1)

    # Dry run - show prompt only
    if args.dry_run:
        print("\n" + "=" * 50)
        print("PROMPT (dry run):")
        print("=" * 50)
        print(build_prompt(category, topic))
        return

    # Generate script
    print(f"\nGenerating script for: {category} → {topic_name}")
    print("-" * 50)

    try:
        script = generate_script(category, topic)
    except Exception as e:
        print(f"Error generating script: {e}")
        sys.exit(1)

    # Save script
    output_name = args.output if args.output else topic_name.replace(" ", "_").lower()
    path = save_script(script, output_name)

    print(f"\nScript generated successfully!")
    print(f"Saved to: {path}")
    print("\n" + "=" * 50)
    print("SCRIPT PREVIEW:")
    print("=" * 50)
    print(f"\nHook: {script.get('hook', 'N/A')}")
    print(f"\nFull Script:\n{script.get('full_script', 'N/A')}")
    print(f"\nEnglish Phrases: {script.get('english_phrases', [])}")
    print(f"\nTip: {script.get('tip', 'N/A')}")
    print(f"\nCTA: {script.get('cta', 'N/A')}")
    print(f"\nHashtags: {' '.join(script.get('hashtags', []))}")

    return script


if __name__ == "__main__":
    main()
