#!/usr/bin/env python3
"""
Script Generator for English AI Videos
Uses OpenAI GPT to generate lesson scripts from topic database.
Supports multiple video types: educational, quiz, true_false, fill_blank, pronunciation
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

# Load .env file from project root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# Paths
TOPICS_DIR = ROOT / "content" / "topics"
OUTPUT_DIR = ROOT / "output" / "scripts"

# OpenAI settings
MODEL = "gpt-4o-mini"
MAX_TOKENS = 2000

# Supported video types
VIDEO_TYPES = ["educational", "quiz", "true_false", "fill_blank", "pronunciation"]


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


def get_topic_name(topic: dict) -> str:
    """Extract display name from any topic format."""
    return (topic.get("english") or topic.get("topic") or topic.get("wrong")
            or topic.get("word") or topic.get("word_a") or topic.get("id") or "unknown")


def find_topic(category: str, topic_name: str) -> dict:
    """Find a specific topic by name in a category."""
    topics = load_topics(category)
    topic_name_lower = topic_name.lower()

    # Search all common name fields
    search_fields = ["english", "topic", "wrong", "id", "word", "word_a",
                     "phrasal_verb", "english_word"]
    for t in topics:
        for field in search_fields:
            if t.get(field, "").lower() == topic_name_lower:
                return t

    raise ValueError(f"Topic '{topic_name}' not found in category '{category}'")


def get_random_topic() -> tuple:
    """Get a random topic from a random category."""
    categories = list_categories()
    category = random.choice(categories)
    topics = load_topics(category)
    topic = random.choice(topics)
    return category, topic


def _topic_context(category: str, topic: dict) -> str:
    """Build context string from any topic format for GPT prompts."""
    if category == "false_friends":
        return (f"False Friend - \"{topic['english']}\"\n"
                f"- Los hispanohablantes piensan que significa: \"{topic['spanish_trap']}\"\n"
                f"- En realidad significa: \"{topic['real_meaning']}\"\n"
                f"- La palabra correcta en inglés para \"{topic['spanish_trap']}\" es: \"{topic.get('correct_english', '')}\"")
    elif category == "phrasal_verbs":
        examples = ", ".join(topic.get("examples", []))
        return (f"Phrasal Verb - \"{topic['topic']}\"\n"
                f"- Significado en español: \"{topic['spanish']}\"\n"
                f"- Ejemplos de uso: {examples}")
    elif category == "common_mistakes":
        return (f"Error Común\n"
                f"- Error frecuente: \"{topic['wrong']}\"\n"
                f"- Forma correcta: \"{topic['correct']}\"\n"
                f"- Explicación: \"{topic['explanation']}\"")
    elif category == "pronunciation":
        return (f"Pronunciación - \"{topic.get('word', '')}\"\n"
                f"- Fonética: \"{topic.get('phonetic', '')}\"\n"
                f"- Error común: \"{topic.get('common_mistake', '')}\"\n"
                f"- Tip: \"{topic.get('tip', '')}\"")
    elif category == "grammar":
        return (f"Gramática - \"{topic['topic']}\"\n"
                f"- Error: \"{topic.get('wrong', '')}\"\n"
                f"- Correcto: \"{topic.get('correct', '')}\"\n"
                f"- Explicación: \"{topic.get('explanation', '')}\"")
    elif category == "idioms":
        return (f"Idiom/Expresión - \"{topic['topic']}\"\n"
                f"- Significado: \"{topic.get('meaning', topic.get('spanish', ''))}\"\n"
                f"- Traducción literal: \"{topic.get('literal', '')}\"\n"
                f"- Ejemplo: \"{topic.get('example', '')}\"")
    elif category == "slang":
        return (f"Slang - \"{topic['topic']}\"\n"
                f"- Significado: \"{topic.get('meaning', '')}\"\n"
                f"- En español: \"{topic.get('spanish', '')}\"\n"
                f"- Ejemplo: \"{topic.get('example', '')}\"")
    elif category == "confusing_words":
        return (f"Palabras Confusas - \"{topic['topic']}\"\n"
                f"- {topic.get('word_a', '')}: {topic.get('meaning_a', '')}\n"
                f"- {topic.get('word_b', '')}: {topic.get('meaning_b', '')}\n"
                f"- Ejemplo A: \"{topic.get('example_a', '')}\"\n"
                f"- Ejemplo B: \"{topic.get('example_b', '')}\"\n"
                f"- Tip: \"{topic.get('tip', '')}\"")
    elif category == "business":
        phrases = ", ".join(topic.get("phrases", [])[:3])
        return (f"Business English - \"{topic['topic']}\"\n"
                f"- Tema: \"{topic.get('spanish', '')}\"\n"
                f"- Frases clave: {phrases}\n"
                f"- Error: \"{topic.get('wrong', '')}\"\n"
                f"- Correcto: \"{topic.get('correct', '')}\"")
    elif category == "travel":
        phrases = ", ".join(topic.get("phrases", [])[:3])
        vocab = ", ".join(topic.get("vocabulary", [])[:5])
        return (f"Travel English - \"{topic['topic']}\"\n"
                f"- Situación: \"{topic.get('spanish', '')}\"\n"
                f"- Frases clave: {phrases}\n"
                f"- Vocabulario: {vocab}")
    elif category == "social":
        formal = ", ".join(topic.get("formal", [])[:3])
        informal = ", ".join(topic.get("informal", [])[:3])
        return (f"Social English - \"{topic['topic']}\"\n"
                f"- Tema: \"{topic.get('spanish', '')}\"\n"
                f"- Formal: {formal}\n"
                f"- Informal: {informal}\n"
                f"- Error: \"{topic.get('wrong', '')}\"\n"
                f"- Correcto: \"{topic.get('correct', '')}\"")
    elif category == "cultural":
        return (f"Diferencia Cultural - \"{topic['topic']}\"\n"
                f"- En países anglosajones: \"{topic.get('english_culture', '')}\"\n"
                f"- En países hispanos: \"{topic.get('spanish_culture', '')}\"\n"
                f"- Tip: \"{topic.get('tip', '')}\"")
    elif category == "spanish_specific":
        pairs = ", ".join(topic.get("pairs", topic.get("examples_correct", []))[:3])
        return (f"Desafío para Hispanohablantes - \"{topic['topic']}\"\n"
                f"- Problema: \"{topic.get('problem', '')}\"\n"
                f"- Ejemplos: {pairs}\n"
                f"- Tip: \"{topic.get('tip', '')}\"")
    else:
        # Generic fallback - dump key fields
        name = get_topic_name(topic)
        return f"Tema: \"{name}\"\nDatos: {json.dumps(topic, ensure_ascii=False)[:500]}"


def _category_hashtags(category: str) -> list:
    """Get relevant hashtags for a category."""
    base = ["#AprendeIngles", "#InglesConTiktok"]
    extra = {
        "false_friends": ["#FalseFriends", "#FalsosAmigos"],
        "phrasal_verbs": ["#PhrasalVerbs", "#VerbosEnIngles"],
        "common_mistakes": ["#ErroresComunes", "#CommonMistakes"],
        "pronunciation": ["#Pronunciacion", "#SpeakEnglish"],
        "grammar": ["#GramaticaIngles", "#EnglishGrammar"],
        "idioms": ["#Idioms", "#ExpresionesEnIngles"],
        "slang": ["#Slang", "#InglesInformal"],
        "confusing_words": ["#ConfusingWords", "#PalabrasConfusas"],
        "business": ["#BusinessEnglish", "#InglesDeNegocios"],
        "travel": ["#TravelEnglish", "#InglesParaViajar"],
        "social": ["#SocialEnglish", "#Conversacion"],
        "cultural": ["#CulturalDifferences", "#CulturaInglesa"],
        "spanish_specific": ["#SpanishSpeakers", "#TipsDeIngles"],
    }
    return base + extra.get(category, ["#LearnEnglish"])


def build_prompt_educational(category: str, topic: dict) -> str:
    """Build educational video prompt for any category."""
    context = _topic_context(category, topic)
    hashtags = _category_hashtags(category)

    return f"""Genera un script de 30-45 segundos para un video de TikTok/Reels enseñando inglés a hispanohablantes.

TEMA: {context}

REGLAS IMPORTANTES:
1. El script debe ser en ESPAÑOL, con las palabras en inglés entre comillas simples
2. Ejemplo: "La palabra 'embarrassed' NO significa embarazada"
3. Incluye un ejemplo práctico de uso en inglés
4. Usa un tono energético y educativo como profesor de TikTok
5. Incluye un tip memorable para recordar
6. Termina con una pregunta o call-to-action

FORMATO JSON REQUERIDO:
{{
  "type": "educational",
  "hook": "Frase inicial que capte atención (con palabra inglés en 'comillas')",
  "full_script": "Script completo en español con palabras inglés en 'comillas simples'. Debe fluir naturalmente para ser leído en voz alta.",
  "english_phrases": ["lista", "de", "palabras", "inglés", "usadas"],
  "translations": {{"palabra_ingles": "traduccion_español"}},
  "tip": "Tip memorable para recordar",
  "cta": "Call to action final",
  "hashtags": {json.dumps(hashtags, ensure_ascii=False)}
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""


def build_prompt_quiz(category: str, topic: dict) -> str:
    """Build quiz video prompt."""
    context = _topic_context(category, topic)
    hashtags = ["#QuizIngles", "#AprendeIngles", "#TestTuIngles"] + _category_hashtags(category)[:1]

    return f"""Genera un QUIZ de 20-30 segundos para TikTok/Reels enseñando inglés a hispanohablantes.

TEMA: {context}

FORMATO DEL VIDEO:
1. Pregunta en español (¿Cómo se dice X en inglés? o ¿Qué significa X?)
2. 4 opciones DIFERENTES: A, B, C, D - solo UNA correcta
3. Cuenta regresiva EN ESPAÑOL: "Piensa bien... Tres... dos... uno..."
4. Revelar respuesta con explicación CORTA

REGLAS ABSOLUTAS (NUNCA VIOLAR):
1. Las 4 opciones DEBEN ser palabras/frases DIFERENTES. NUNCA repetir la misma palabra.
   - MAL: A:'sensible', B:'sensible', C:'sensible', D:'sensible' ← PROHIBIDO
   - BIEN: A:'sensitive', B:'sensible', C:'reasonable', D:'careful' ← CORRECTO
2. La respuesta correcta debe ser la traducción EXACTA del tema
3. Las opciones incorrectas deben ser confusiones comunes o palabras similares
4. CUENTA REGRESIVA SIEMPRE EN ESPAÑOL: "Tres... dos... uno..." (NO "Three... two... one...")
5. La explicación debe explicar POR QUÉ la respuesta correcta es correcta
6. Explicación CORTA: 1-2 oraciones + un ejemplo simple

EJEMPLO CORRECTO:
Tema: False Friend 'library' significa 'biblioteca', NO 'librería'
{{
  "question": "¿Qué significa 'library' en inglés?",
  "options": {{
    "A": "'librería'",
    "B": "'biblioteca'",
    "C": "'libro'",
    "D": "'lectura'"
  }},
  "correct": "B",
  "explanation": "'Library' significa biblioteca. Por ejemplo: 'I study at the library' - Estudio en la biblioteca."
}}

EJEMPLO DE FULL_SCRIPT:
"¿Qué significa 'library' en inglés? ... A, 'librería'. ... B, 'biblioteca'. ... C, 'libro'. ... D, 'lectura'. ... Piensa bien... Tres... dos... uno... ¡Correcto! 'Library' significa biblioteca. Por ejemplo: 'I study at the library' - Estudio en la biblioteca."

FORMATO JSON:
{{
  "type": "quiz",
  "question": "Pregunta en español",
  "options": {{
    "A": "opción 1 (DIFERENTE)",
    "B": "opción 2 (DIFERENTE)",
    "C": "opción 3 (DIFERENTE)",
    "D": "opción 4 (DIFERENTE)"
  }},
  "correct": "letra correcta",
  "explanation": "1-2 oraciones explicando POR QUÉ es correcta + ejemplo",
  "full_script": "Script completo EN ESPAÑOL con countdown 'Tres... dos... uno...'",
  "translations": {{"palabra_ingles": "traduccion_español"}},
  "hashtags": {json.dumps(hashtags[:4], ensure_ascii=False)}
}}

Responde SOLO con el JSON válido."""


def build_prompt_true_false(category: str, topic: dict) -> str:
    """Build true/false video prompt."""
    context = _topic_context(category, topic)

    return f"""Genera un video de VERDADERO O FALSO de 15-25 segundos para TikTok/Reels enseñando inglés a hispanohablantes.

TEMA: {context}

IDIOMA CRÍTICO:
- TODO en ESPAÑOL excepto la palabra/frase en inglés que enseñamos
- La afirmación debe estar en ESPAÑOL
- Solo la palabra inglés entre comillas simples

FORMATO DEL VIDEO:
1. Afirmación en ESPAÑOL (con palabra inglés en comillas): "¿'Library' significa librería? ¿Verdadero o falso?"
2. Pausa para pensar: "Piensa bien... Tres... dos... uno..."
3. Revelar respuesta con explicación CORTA (1-2 oraciones máximo)

EJEMPLO CORRECTO de full_script:
"¿'Give up' significa rendirse? ¿Verdadero o falso? ... Piensa bien... Tres... dos... uno... ¡Verdadero! 'Give up' sí significa rendirse. Por ejemplo: 'I give up' - Me rindo."

EJEMPLO INCORRECTO (NO hacer esto):
"Is 'library' the same as 'librería'?" ← MAL, debe ser en español

REGLAS:
1. Afirmación EN ESPAÑOL con solo la palabra inglés en inglés
2. Puede ser verdadera o falsa (varía)
3. Explicación CORTA: 1-2 oraciones máximo + un ejemplo simple
4. Incluir cuenta regresiva: "Piensa bien... Tres... dos... uno..."

FORMATO JSON REQUERIDO:
{{
  "type": "true_false",
  "statement": "¿'palabra_ingles' significa X? ¿Verdadero o falso?",
  "correct": true,
  "explanation": "1-2 oraciones máximo. Corta y memorable.",
  "full_script": "Script EN ESPAÑOL. Palabra inglés en 'comillas'. Explicación CORTA al final.",
  "translations": {{"palabra_clave": "traduccion"}},
  "hashtags": {json.dumps(["#VerdaderoOFalso", "#AprendeIngles"] + _category_hashtags(category)[:1], ensure_ascii=False)}
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""


def build_prompt_fill_blank(category: str, topic: dict) -> str:
    """Build fill-in-the-blank video prompt."""
    context = _topic_context(category, topic)

    return f"""Genera un video de COMPLETA LA FRASE de 25-35 segundos para TikTok/Reels enseñando inglés.

TEMA: {context}

FORMATO DEL VIDEO:
1. Mostrar frase en inglés con un espacio en blanco (___)
2. Mostrar 4 opciones
3. Pausa para pensar
4. Revelar respuesta correcta

REGLAS:
1. La frase debe ser práctica y común
2. El espacio en blanco debe testar el concepto clave
3. Las opciones incorrectas deben ser errores comunes
4. Incluir traducción de la frase completa

FORMATO JSON REQUERIDO:
{{
  "type": "fill_blank",
  "sentence": "I ___ to the store yesterday",
  "blank_position": "went",
  "options": ["go", "went", "gone", "going"],
  "correct": "went",
  "explanation": "Explicación gramatical COMPLETA - no la acortes",
  "full_script": "Script narrado completo. DEBE terminar con explicación COMPLETA.",
  "translation": "Traducción de la frase completa",
  "hashtags": ["#CompletaLaFrase", "#AprendeIngles", "#GramaticaIngles"]
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""


def build_prompt_pronunciation(category: str, topic: dict) -> str:
    """Build pronunciation video prompt."""
    word = get_topic_name(topic)

    return f"""Genera un video de PRONUNCIACIÓN de 20-30 segundos para TikTok/Reels enseñando inglés.

PALABRA: "{word}"

FORMATO DEL VIDEO:
1. Mostrar la palabra en grande
2. "¿Cómo se pronuncia?"
3. Mostrar error común de pronunciación
4. Mostrar pronunciación correcta (fonética simplificada)
5. Tip para recordar

REGLAS:
1. Usa fonética simplificada que hispanohablantes entiendan (ej: "KUMF-ter-bul")
2. Identifica el error de pronunciación más común
3. Da un tip memorable
4. El script debe incluir cómo pronunciar la palabra

FORMATO JSON REQUERIDO:
{{
  "type": "pronunciation",
  "word": "{word}",
  "phonetic": "Pronunciación fonética simplificada en mayúsculas",
  "common_mistake": "Error de pronunciación común",
  "tip": "Tip para recordar la pronunciación",
  "full_script": "Script narrado con la palabra, error común, pronunciación correcta y tip.",
  "translation": "traducción de la palabra",
  "hashtags": ["#Pronunciacion", "#AprendeIngles", "#SpeakEnglish"]
}}

Responde SOLO con el JSON, sin explicaciones adicionales."""


def build_prompt(category: str, topic: dict, video_type: str = "educational") -> str:
    """Build prompt based on video type."""
    if video_type == "educational":
        return build_prompt_educational(category, topic)
    elif video_type == "quiz":
        return build_prompt_quiz(category, topic)
    elif video_type == "true_false":
        return build_prompt_true_false(category, topic)
    elif video_type == "fill_blank":
        return build_prompt_fill_blank(category, topic)
    elif video_type == "pronunciation":
        return build_prompt_pronunciation(category, topic)
    else:
        raise ValueError(f"Unknown video type: {video_type}. Choose from: {VIDEO_TYPES}")


def generate_script(category: str, topic: dict, video_type: str = "educational") -> dict:
    """Call OpenAI API to generate a script."""

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable not set. Add it to .env file.")

    client = OpenAI(api_key=api_key)
    prompt = build_prompt(category, topic, video_type)

    print(f"Calling OpenAI API ({MODEL}) for {video_type} video...")

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = response.choices[0].message.content.strip()

    # Parse JSON from response
    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        script = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON response: {e}")
        print(f"Raw response:\n{response_text}")
        raise

    # Ensure type is set
    script["type"] = video_type

    # VALIDATION: For quiz type, ensure all 4 options are different
    if video_type == "quiz" and "options" in script:
        options = script["options"]
        option_values = [v.lower().strip("'\"") for v in options.values()]
        unique_values = set(option_values)

        if len(unique_values) < len(option_values):
            print(f"  WARNING: Quiz has duplicate options: {list(options.values())}")
            print(f"  Regenerating with different options...")
            # Retry once with explicit instruction
            retry_prompt = prompt + "\n\nIMPORTANTE: Las 4 opciones A, B, C, D DEBEN ser palabras COMPLETAMENTE DIFERENTES. No repitas ninguna opción."
            retry_response = client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": retry_prompt}]
            )
            retry_text = retry_response.choices[0].message.content.strip()
            try:
                if "```json" in retry_text:
                    retry_text = retry_text.split("```json")[1].split("```")[0].strip()
                elif "```" in retry_text:
                    retry_text = retry_text.split("```")[1].split("```")[0].strip()
                script = json.loads(retry_text)
                script["type"] = video_type
            except:
                print("  Retry failed, using original")

    # Add metadata
    script["_meta"] = {
        "category": category,
        "topic_id": topic.get("id", "unknown"),
        "video_type": video_type,
        "generated_at": datetime.now().isoformat(),
        "model": MODEL
    }

    return script


def save_script(script: dict, name: str) -> Path:
    """Save script to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{name}.json"
    path = OUTPUT_DIR / filename

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    return path


def main():
    parser = argparse.ArgumentParser(
        description="Generate English lesson scripts using OpenAI GPT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Video Types: {', '.join(VIDEO_TYPES)}

Examples:
  python src/script_generator.py --list
  python src/script_generator.py --random
  python src/script_generator.py --random --type quiz
  python src/script_generator.py --category false_friends --topic embarrassed
  python src/script_generator.py --category false_friends --topic embarrassed --type true_false
  python src/script_generator.py -c phrasal_verbs -t "give up" --type fill_blank
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
    parser.add_argument("--type", type=str, default="educational",
                        choices=VIDEO_TYPES,
                        help="Video type (default: educational)")
    parser.add_argument("--output", "-o", type=str,
                        help="Output file name (without extension)")
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
        print(f"\nVideo Types: {', '.join(VIDEO_TYPES)}")
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
        print(f"PROMPT ({args.type} - dry run):")
        print("=" * 50)
        print(build_prompt(category, topic, args.type))
        return

    # Generate script
    print(f"\nGenerating {args.type} script for: {category} → {topic_name}")
    print("-" * 50)

    try:
        script = generate_script(category, topic, args.type)
    except Exception as e:
        print(f"Error generating script: {e}")
        sys.exit(1)

    # Save script
    type_suffix = f"_{args.type}" if args.type != "educational" else ""
    output_name = args.output if args.output else f"{topic_name.replace(' ', '_').lower()}{type_suffix}"
    path = save_script(script, output_name)

    print(f"\nScript generated successfully!")
    print(f"Saved to: {path}")
    print("\n" + "=" * 50)
    print("SCRIPT PREVIEW:")
    print("=" * 50)
    print(f"\nType: {script.get('type', 'N/A')}")

    if args.type == "educational":
        print(f"Hook: {script.get('hook', 'N/A')}")
        print(f"Script: {script.get('full_script', 'N/A')[:200]}...")
    elif args.type == "quiz":
        print(f"Question: {script.get('question', 'N/A')}")
        print(f"Options: {script.get('options', {})}")
        print(f"Correct: {script.get('correct', 'N/A')}")
    elif args.type == "true_false":
        print(f"Statement: {script.get('statement', 'N/A')}")
        print(f"Correct: {script.get('correct', 'N/A')}")
    elif args.type == "fill_blank":
        print(f"Sentence: {script.get('sentence', 'N/A')}")
        print(f"Options: {script.get('options', [])}")
        print(f"Correct: {script.get('correct', 'N/A')}")
    elif args.type == "pronunciation":
        print(f"Word: {script.get('word', 'N/A')}")
        print(f"Phonetic: {script.get('phonetic', 'N/A')}")
        print(f"Common mistake: {script.get('common_mistake', 'N/A')}")

    print(f"\nFull Script:\n{script.get('full_script', 'N/A')}")

    return script


if __name__ == "__main__":
    main()
