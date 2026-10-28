#!/usr/bin/env python3
"""Validate the three level-family drafts against content/drafts/LEVEL_TYPES_SPEC.md.

    python3 tools/level_drafts_check.py [level_test|say_it_level|pronounce_level ...] [--quiet]

Written with the drafts (2026-10-13). When the types land, script_schema takes
over these rules; until then this is the check the 300 drafts pass with 0 errors.
Spelling uses `hunspell` (es_ES/es_MX/en_US) and stress uses `cmudict` when
installed -- both only produce warnings, and both are skipped if missing.

Errors are spec violations (must be fixed). Warnings are for a human eye
(spellchecker unknowns, CMU stress disagreement, cross-video repeats).
"""
import json, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "content" / "drafts"
sys.path.insert(0, str(REPO / "src"))
from emoji_font import emoji_problem  # noqa: E402

TYPES = {
    "level_test":      {"cat": "level_vocab", "pre": "lv", "tag": "#NivelDeInglés"},
    "say_it_level":    {"cat": "say_it",      "pre": "sy", "tag": "#DiloEnInglés"},
    "pronounce_level": {"cat": "pron_level",  "pre": "pl", "tag": "#PronunciaciónEnInglés"},
}
ALLOWED_TAGS = {"excited", "happy", "curious", "cheerful", "warm", "surprised",
                "thoughtful", "calm", "serious"}
CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
TAG_RE = re.compile(r"\[([a-zA-Z][a-zA-Z ']{0,24})\]")

import subprocess, functools



def _unknown(dic, words):
    if not words:
        return set()
    try:
        out = subprocess.run(["hunspell", "-i", "utf-8", "-d", dic, "-l"],
                             input="\n".join(words), capture_output=True,
                             text=True, timeout=30).stdout
    except Exception:
        return set()
    return set(out.split())


ES = EN = True
try:
    import cmudict
    CMU = cmudict.dict()
except Exception:  # pragma: no cover
    CMU = {}

IPA_VOWELS = set("iɪeɛæaɑɒɔoʊuʌəɚɝɜɐy")
DIPH = ("eɪ", "aɪ", "oʊ", "aʊ", "ɔɪ")


def ipa_nuclei(ipa):
    """[(index_in_string, is_stressed)] per vowel nucleus."""
    s = ipa.replace("ː", "").replace("ˌ", "").replace(".", "")
    out, i, stress_next = [], 0, False
    while i < len(s):
        ch = s[i]
        if ch == "ˈ":
            stress_next = True; i += 1; continue
        if s[i:i + 2] in DIPH:
            out.append(stress_next); stress_next = False; i += 2; continue
        if ch in IPA_VOWELS:
            out.append(stress_next); stress_next = False
        i += 1
    return out


def ipa_stress_index(ipa):
    """Index of the syllable carrying ˈ: count nuclei before the mark."""
    s = ipa.replace("ː", "").replace("ˌ", "").replace(".", "")
    if "ˈ" not in s:
        return None
    before = s[: s.index("ˈ")]
    return len(ipa_nuclei(before))


def emoji_tail(text):
    """The trailing emoji (with optional VS16) and the text before it."""
    t = text.rstrip()
    if not t:
        return None, t
    j = len(t)
    if t[j - 1] == "️":
        j -= 1
    if j == 0:
        return None, t
    ch = t[j - 1]
    if unicodedata.category(ch) != "So" and ord(ch) < 0x2000:
        return None, t
    return t[j - 1:], t[: j - 1].rstrip()


def count_emoji(text):
    return sum(1 for ch in text if ord(ch) >= 0x1F000 or unicodedata.category(ch) == "So")


ES_OK = set("""inglés ingles ok comentarios cuéntamelo dímelo escríbelo te nivel básico
intermedio experto""".split())


def spell_es(text):
    if not ES:
        return []
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", TAG_RE.sub("", text))
    words = [w for w in words if not w.isupper() and len(w) > 2]
    unk = _unknown("es_ES", words) & _unknown("es_MX", words)
    return sorted(w for w in unk if w.lower() not in ES_OK)


def spell_en(text):
    if not EN:
        return []
    words = re.findall(r"[A-Za-z']+", text)
    words = [w.strip("'") for w in words if len(w) > 2]
    unk = _unknown("en_US", words)
    return sorted(w for w in unk if w.lower() not in CMU)


def check_tagged(label, text, limit, errs):
    tags = TAG_RE.findall(text)
    if len(tags) > 1:
        errs.append(f"{label}: more than one audio tag")
    for t in tags:
        if t.lower() not in ALLOWED_TAGS:
            errs.append(f"{label}: tag [{t}] not allowed")
    if tags and not text.startswith("["):
        errs.append(f"{label}: tag must be at the start")
    body = TAG_RE.sub("", text).strip()
    if len(body) > limit:
        errs.append(f"{label}: {len(body)} chars > {limit}")
    if not body:
        errs.append(f"{label}: empty")
    return body


def validate_file(path, vtype):
    errs, warns = [], []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"invalid JSON: {e}"], [], None
    cfg = TYPES[vtype]
    m = re.fullmatch(rf"({cfg['pre']})(\d{{3}})_[a-z0-9_]+\.json", path.name)
    if not m:
        errs.append(f"bad filename {path.name}")
    meta = d.get("_meta") or {}
    tid = meta.get("topic_id")
    if m and tid != m.group(1) + m.group(2):
        errs.append(f"_meta.topic_id {tid} != filename")
    if meta.get("category") != cfg["cat"]:
        errs.append(f"_meta.category {meta.get('category')} != {cfg['cat']}")
    if meta.get("video_type") != vtype or d.get("type") != vtype:
        errs.append("type / _meta.video_type mismatch")
    if meta.get("draft") is not True:
        errs.append("_meta.draft must be true")

    required = ["type", "video_title", "video_description", "title", "theme", "intro",
                "items", "verdict", "outro", "hashtags", "_meta"]
    for k in required:
        if k not in d:
            errs.append(f"missing {k}")
    if errs and any(e.startswith("missing") for e in errs):
        return errs, warns, d

    for k in ("video_title", "video_description"):
        lim = 70 if k == "video_title" else 120
        v = d[k]
        if len(v) > lim:
            errs.append(f"{k}: {len(v)} chars > {lim}")
        emo, rest = emoji_tail(v)
        if not emo:
            errs.append(f"{k}: must end with one emoji")
        else:
            prob = emoji_problem(emo)
            if prob:
                errs.append(f"{k}: emoji {emo!r}: {prob}")
            if count_emoji(rest):
                errs.append(f"{k}: more than one emoji")
        if TAG_RE.search(v):
            errs.append(f"{k}: audio tag in title/description")

    intro = check_tagged("intro", d["intro"], 110, errs)
    outro = check_tagged("outro", d["outro"], 90, errs)
    if TAG_RE.search(d["verdict"]):
        errs.append("verdict: no audio tags allowed")
    if len(d["verdict"]) > 130:
        errs.append(f"verdict: {len(d['verdict'])} chars > 130")
    vlow = d["verdict"].lower()
    for num, word in (("3", "tres"), ("7", "siete"), ("10", "diez")):
        if num not in re.findall(r"\d+", vlow) and word not in vlow:
            errs.append(f"verdict: does not name tier boundary {word}")

    tags = d["hashtags"]
    if len(tags) != 5 or any((not t.startswith("#")) or " " in t for t in tags):
        errs.append("hashtags: need exactly 5 #tags without spaces")
    elif tags[0] != cfg["tag"]:
        errs.append(f"hashtags[0] must be {cfg['tag']}")
    if len(set(tags)) != len(tags):
        errs.append("hashtags: duplicates")

    items = d["items"]
    if len(items) != 10:
        errs.append(f"items: {len(items)} != 10")
    for fld in ("english", "spanish"):
        vals = [str(it.get(fld, "")).strip().lower() for it in items if it.get(fld)]
        dup = [v for v, c in Counter(vals).items() if c > 1]
        if dup:
            errs.append(f"items: duplicate {fld}: {dup}")

    es_texts = [intro, outro, d["verdict"], d["video_description"], d["video_title"]]
    en_texts = []

    if vtype == "level_test":
        levels = []
        for i, it in enumerate(items, 1):
            extra = set(it) - {"english", "spanish", "cefr"}
            if extra:
                errs.append(f"item {i}: unexpected keys {extra}")
            en, es, c = it.get("english", ""), it.get("spanish", ""), it.get("cefr")
            if not en or len(en) > 24:
                errs.append(f"item {i}: english '{en}' empty or > 24")
            if not es or len(es) > 28:
                errs.append(f"item {i}: spanish '{es}' empty or > 28")
            if es and not es[0].isupper() and es[0] not in "¿¡":
                errs.append(f"item {i}: spanish must start with a capital")
            if c not in CEFR:
                errs.append(f"item {i}: cefr {c!r}")
                continue
            levels.append(CEFR.index(c))
            es_texts.append(es); en_texts.append(en)
        if len(levels) == 10:
            if levels != sorted(levels):
                errs.append(f"cefr not non-decreasing: {[CEFR[x] for x in levels]}")
            if max(levels[:3]) > 1:
                errs.append("items 1-3 must be A1-A2")
            if not all(1 <= x <= 3 for x in levels[3:7]):
                errs.append("items 4-7 must be A2-B2")
            if sum(1 for x in levels[3:7] if x >= 2) < 2:
                errs.append("items 4-7 need at least two B1/B2")
            if not all(3 <= x for x in levels[7:]):
                errs.append("items 8-10 must be B2-C2")
            if sum(1 for x in levels[7:] if x >= 4) < 2:
                errs.append("items 8-10 need at least two C1/C2")

    elif vtype == "say_it_level":
        levels = []
        for i, it in enumerate(items, 1):
            extra = set(it) - {"english", "spanish", "cefr", "alt", "tip"}
            if extra:
                errs.append(f"item {i}: unexpected keys {extra}")
            en, es, c = it.get("english", ""), it.get("spanish", ""), it.get("cefr")
            for fld, v in (("english", en), ("spanish", es), ("alt", it.get("alt"))):
                if v is None and fld == "alt":
                    continue
                if not v or len(v) > 42:
                    errs.append(f"item {i}: {fld} '{v}' empty or > 42")
                elif v[-1] not in ".?!":
                    errs.append(f"item {i}: {fld} needs final punctuation")
            if es and es.endswith("?") and "¿" not in es:
                errs.append(f"item {i}: spanish question without ¿")
            if es and es.endswith("!") and "¡" not in es:
                errs.append(f"item {i}: spanish exclamation without ¡")
            if it.get("alt") and it["alt"].strip().lower() == en.strip().lower():
                errs.append(f"item {i}: alt equals english")
            tip = it.get("tip")
            if i >= 8 and not tip:
                errs.append(f"item {i}: tip required on items 8-10")
            if tip is not None:
                if not tip or len(tip) > 60:
                    errs.append(f"item {i}: tip empty or > 60 ({len(tip or '')})")
                else:
                    es_texts.append(re.sub(r"«[^»]*»", "", tip))
            if c not in CEFR:
                errs.append(f"item {i}: cefr {c!r}")
                continue
            levels.append(CEFR.index(c))
            es_texts.append(es); en_texts.append(en)
            if it.get("alt"):
                en_texts.append(it["alt"])
        if len(levels) == 10:
            if levels != sorted(levels):
                errs.append(f"cefr not non-decreasing: {[CEFR[x] for x in levels]}")
            if max(levels[:3]) > 1:
                errs.append("items 1-3 must be A1-A2")
            if not all(1 <= x <= 3 for x in levels[3:7]):
                errs.append("items 4-7 must be A2-B2")
            if not all(2 <= x <= 4 for x in levels[7:]):
                errs.append("items 8-10 must be B1-C1")

    elif vtype == "pronounce_level":
        for i, it in enumerate(items, 1):
            extra = set(it) - {"english", "respelling", "ipa", "trap"}
            if extra:
                errs.append(f"item {i}: unexpected keys {extra}")
            en, rs, ipa, trap = (it.get(k, "") for k in ("english", "respelling", "ipa", "trap"))
            if not en or len(en) > 18:
                errs.append(f"item {i}: english '{en}' empty or > 18")
            if not trap or len(trap) > 45:
                errs.append(f"item {i}: trap empty or > 45 ({len(trap or '')})")
            else:
                es_texts.append(re.sub(r"«[^»]*»|[A-Z]{2,}[A-Za-z-]*", "", trap))
            if not ipa or "/" in ipa or "ˌ" in ipa or "̩" in ipa:
                errs.append(f"item {i}: ipa '{ipa}' missing, has slashes, secondary stress or syllabic mark")
                continue
            if not re.fullmatch(r"[A-Za-z]+(-[A-Za-z]+)*", rs or ""):
                errs.append(f"item {i}: respelling '{rs}' must be letters joined by '-'")
                continue
            sylls = rs.split("-")
            caps = [k for k, s in enumerate(sylls) if s.isupper()]
            mixed = [s for s in sylls if not (s.isupper() or s.islower())]
            if mixed:
                errs.append(f"item {i}: respelling syllables mix case {mixed}")
            nuc = ipa_nuclei(ipa)
            if ipa.count("ˈ") != 1 and len(nuc) > 1:
                errs.append(f"item {i}: ipa '{ipa}' needs exactly one ˈ")
            if len(sylls) != len(nuc):
                errs.append(f"item {i} {en}: respelling {len(sylls)} syllables vs ipa {len(nuc)} ({rs} / {ipa})")
            if len(caps) != 1:
                errs.append(f"item {i} {en}: respelling needs exactly one CAPS syllable ({rs})")
            else:
                si = ipa_stress_index(ipa) if len(nuc) > 1 else 0
                if si is not None and caps[0] != si:
                    errs.append(f"item {i} {en}: stress mismatch respelling #{caps[0]+1} vs ipa #{si+1} ({rs} / {ipa})")
                prons = CMU.get(en.lower())
                if prons and len(nuc) > 1:
                    ok = False
                    for p in prons:
                        vow = [ph for ph in p if ph[-1].isdigit()]
                        prim = [k for k, ph in enumerate(vow) if ph.endswith("1")]
                        if prim and si is not None and prim[0] == si:
                            ok = True
                    if not ok:
                        warns.append(f"item {i} {en}: CMU primary stress differs ({' | '.join(' '.join(p) for p in prons[:2])}) vs {ipa}")
            en_texts.append(en)

    for t in es_texts:
        bad = spell_es(t)
        if bad:
            warns.append(f"es spell? {bad} in «{t[:60]}»")
    for t in en_texts:
        bad = spell_en(t)
        if bad:
            warns.append(f"en spell? {bad} in «{t[:60]}»")
    return errs, warns, d


def main(argv):
    quiet = "--quiet" in argv
    types = [a for a in argv if a in TYPES] or list(TYPES)
    total_err = 0
    for vtype in types:
        files = sorted((ROOT / vtype).glob("*.json"))
        print(f"\n=== {vtype}: {len(files)} files")
        seen_en = defaultdict(list)
        seen_theme = defaultdict(list)
        seen_title = defaultdict(list)
        ids = []
        for f in files:
            errs, warns, d = validate_file(f, vtype)
            if d:
                for it in d.get("items", []):
                    if it.get("english"):
                        seen_en[it["english"].strip().lower()].append(f.name[:5])
                seen_theme[str(d.get("theme", "")).lower()].append(f.name[:5])
                seen_title[str(d.get("video_title", "")).lower()].append(f.name[:5])
                ids.append(f.name[:5])
            total_err += len(errs)
            if errs or (warns and not quiet):
                print(f"-- {f.name}")
                for e in errs:
                    print("   ERROR", e)
                if not quiet:
                    for w in warns:
                        print("   warn ", w)
        dups = {k: v for k, v in seen_en.items() if len(v) > 1}
        tdup = {k: v for k, v in seen_theme.items() if len(v) > 1}
        ttl = {k: v for k, v in seen_title.items() if len(v) > 1}
        iddup = [k for k, c in Counter(ids).items() if c > 1]
        if iddup:
            print("   ERROR duplicate topic ids", iddup); total_err += len(iddup)
        if tdup:
            print("   ERROR duplicate themes", tdup); total_err += len(tdup)
        if ttl:
            print("   ERROR duplicate titles", ttl); total_err += len(ttl)
        print(f"   cross-video english repeats: {len(dups)}"
              + (f" e.g. {dict(list(dups.items())[:15])}" if dups else ""))
    print(f"\nTOTAL ERRORS: {total_err}")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
