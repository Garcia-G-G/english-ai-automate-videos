#!/usr/bin/env python3
"""Write a lesson script with a language model — the "lots of dialogue and content" step.

    python3 gen_script.py --topic "Present simple vs present continuous" --level A2 --minutes 6
    python3 gen_script.py --topic "Phrasal verbs de la mañana: get up, wake up, turn off" --model gpt-4o

Reads OPENAI_API_KEY from english-ai-videos/.env (overridden by ./.env), asks for JSON
that follows prompts/lesson_script.md, validates it with lesson.validate(), and if the
model broke a rule sends the problems back once for a repair. Saves lessons/<id>.json
and prints the path. Standard library only.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lesson as L  # noqa: E402
from gen_audio import read_env, DEFAULT_ENV  # noqa: E402

PROMPT = (HERE / "prompts" / "lesson_script.md").read_text(encoding="utf-8")
DEFAULT_MODEL = "gpt-4o-mini"
PRICES = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00), "gpt-4.1-mini": (0.40, 1.60)}  # USD per 1M in/out


def slugify(text: str) -> str:
    text = re.sub(r"[áàä]", "a", text.lower()); text = re.sub(r"[éèë]", "e", text); text = re.sub(r"[íìï]", "i", text)
    text = re.sub(r"[óòö]", "o", text); text = re.sub(r"[úùü]", "u", text); text = text.replace("ñ", "n")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "lesson"


def user_prompt(topic: str, level: str, minutes: int, extra: str = "") -> str:
    return (f"Topic: {topic}\nLevel: {level}\nTarget length: {minutes} minutes (about {minutes * 5} beats).\n"
            f"Narration language: Spanish (Latin American, neutral). English inside [[ ]].\n"
            + (f"Extra guidance: {extra}\n" if extra else "") + "Return the JSON object only.")


def chat(api_key: str, model: str, messages: list, timeout: int = 240) -> tuple:
    """(content, usage) from the Chat Completions API, JSON mode."""
    body = {"model": model, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0.7}
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                     method="POST", headers={"Authorization": f"Bearer {api_key}",
                                                             "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def normalize(lesson: dict, topic: str, level: str, minutes: int) -> dict:
    """Fill what the model tends to forget, without changing what it wrote."""
    lesson.setdefault("title", topic)
    lesson["id"] = slugify(lesson.get("id") or lesson["title"])
    lesson.setdefault("kicker", f"Inglés · {level}")
    lesson.setdefault("level", level)
    lesson.setdefault("language", "es")
    lesson.setdefault("target_minutes", minutes)
    for n, beat in enumerate(lesson.get("beats", []), 1):
        if isinstance(beat, dict):
            beat["id"] = f"b{n:02d}"
    return lesson


def cost_usd(model: str, usage: dict) -> float:
    inp, out = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return round(usage.get("prompt_tokens", 0) / 1e6 * inp + usage.get("completion_tokens", 0) / 1e6 * out, 4)


def generate(api_key: str, topic: str, level: str, minutes: int, model: str = DEFAULT_MODEL,
             extra: str = "", log=print) -> tuple:
    """(lesson, problems, cost). Problems is [] when the script is renderable."""
    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": user_prompt(topic, level, minutes, extra)}]
    total = 0.0
    lesson, problems = {}, ["no answer"]
    for attempt in range(2):
        content, usage = chat(api_key, model, messages)
        total += cost_usd(model, usage)
        try:
            lesson = normalize(json.loads(content), topic, level, minutes)
        except (json.JSONDecodeError, TypeError) as error:
            problems = [f"model did not return valid JSON: {error}"]
        else:
            problems = L.validate(lesson)
        log(f"attempt {attempt + 1}: {len(lesson.get('beats', []))} beats, {len(problems)} problem(s), "
            f"≈{L.estimate_minutes(lesson) if lesson else 0} min, ${total:.3f} so far")
        if not problems:
            break
        messages += [{"role": "assistant", "content": content},
                     {"role": "user", "content": "Fix these problems and return the complete corrected JSON object only:\n- "
                      + "\n- ".join(problems[:40])}]
    return lesson, problems, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--level", default="A2")
    parser.add_argument("--minutes", type=int, default=6)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--extra", default="", help="extra guidance for the writer")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--out", type=Path, default=HERE / "lessons")
    args = parser.parse_args()

    api_key = read_env(args.env).get("OPENAI_API_KEY", "")
    if len(api_key) < 10:
        sys.exit("OPENAI_API_KEY missing (english-ai-videos/.env or ./.env).")
    try:
        lesson, problems, cost = generate(api_key, args.topic, args.level, args.minutes, args.model, args.extra)
    except urllib.error.HTTPError as error:
        sys.exit(f"OpenAI answered {error.code}: {error.read()[:300].decode('utf-8', 'replace')}")
    if not lesson.get("beats"):
        sys.exit("The model returned no beats.")
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{lesson['id']}.json"
    if path.exists():
        path = args.out / f"{lesson['id']}-{len(list(args.out.glob(lesson['id'] + '*')))}.json"
        lesson["id"] = path.stem
    L.save(lesson, path)
    print(f"saved {path.relative_to(HERE)} — {len(lesson['beats'])} beats, ≈{L.estimate_minutes(lesson)} min, "
          f"{L.character_count(lesson)} chars of narration, writer cost ${cost:.3f}")
    if problems:
        print("still has problems (fix them in the editor before generating audio):\n  " + "\n  ".join(problems))
        return 2
    for note in L.warnings(lesson):
        print("note:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
