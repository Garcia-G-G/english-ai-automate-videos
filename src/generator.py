#!/usr/bin/env python3
"""Generador de scripts de inglés"""

import json, random
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOPICS = ROOT / "content" / "topics"

def load(cat): 
    return json.load(open(TOPICS / f"{cat}.json"))

def prompt(cat, t):
    if cat == "phrasal_verbs":
        return f'''Script de 45seg para "{t["topic"]}" ({t["spanish"]})
Ejemplos: {", ".join(t["examples"])}
JSON: {{"hook":"..","content":"..","examples":[..],"tip":"..","cta":"..","full_script":"..","hashtags":[..]}}'''
    
    if cat == "false_friends":
        return f'''Script de 45seg: "{t["english"]}" parece "{t["spanish_trap"]}" pero es "{t["real_meaning"]}"
Correcto: {t["correct_english"]}
JSON: {{"hook":"..","content":"..","examples":[..],"tip":"..","cta":"..","full_script":"..","hashtags":[..]}}'''
    
    if cat == "common_mistakes":
        return f'''Script de 45seg: Error "{t["wrong"]}" → Correcto "{t["correct"]}"
Explicación: {t["explanation"]}
JSON: {{"hook":"..","content":"..","examples":[..],"tip":"..","cta":"..","full_script":"..","hashtags":[..]}}'''

def cats(): 
    return [f.stem for f in TOPICS.glob("*.json")]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "-l":
        for c in cats(): print(f"  {c}: {len(load(c))} temas")
    else:
        c = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "-c" else random.choice(cats())
        t = random.choice(load(c))
        n = t.get("topic") or t.get("english") or t.get("wrong")
        print(f"\n🎯 {c} → {n}\n{'='*50}")
        print(prompt(c, t))
