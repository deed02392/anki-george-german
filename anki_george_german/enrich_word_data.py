#!/usr/bin/env python3
"""Build word_data.json — frequency, CEFR, and sense data for all deck words.

Data sources:
  1. dlexDB (local TSV)  — lemma frequency from DWDS 20th-century corpus
  2. DWDS frequency API  — contemporary frequency class (0-6 log scale)
  3. Goethe-Zertifikat   — CEFR level (A1/A2/B1 where available)
  4. English Wiktionary   — sense inventory with labels and English glosses

Usage:
    anki-german enrich worddata              # full build
    anki-german enrich worddata --dwds-only  # just refresh DWDS freq
    anki-german enrich worddata --senses-only # just refresh Wiktionary senses
    anki-german enrich worddata --dry-run    # preview, don't write
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from ._anki import anki, fetch_vocab_notes, strip_article
from . import DATA_DIR

OUTPUT_PATH = DATA_DIR / "word_data.json"
EXTERNAL_DIR = DATA_DIR / "external"

# --- dlexDB ----------------------------------------------------------------

DLEX_PATH = EXTERNAL_DIR / "dlex" / "data" / "lem.tsv"


def load_dlexdb():
    """Load dlexDB lemma table into a dict keyed by lemma."""
    if not DLEX_PATH.exists():
        print(f"  dlexDB not found at {DLEX_PATH}")
        print("  Extract dlex.zip into data/external/dlex/")
        return {}
    dlex = {}
    with open(DLEX_PATH) as f:
        header = f.readline()  # skip header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                continue
            lemma = parts[0]
            try:
                dlex[lemma] = {
                    "abs": int(parts[2]),
                    "per_million": float(parts[3]),
                    "rank": float(parts[6]),
                }
            except (ValueError, IndexError):
                continue
    print(f"  dlexDB: {len(dlex):,} lemmas loaded")
    return dlex


def lookup_dlexdb(dlex, word, pos=None):
    """Look up a word in dlexDB, trying variants."""
    bare = strip_article(word)
    # Also strip "sich " for reflexive verbs
    bare_no_sich = bare.replace("sich ", "").strip()
    # Try candidates in priority order
    candidates = [
        word,                    # exact: "das Essen"
        bare,                    # stripped: "essen"
        bare.capitalize(),       # capitalized: "Essen"
        bare.lower(),            # lowercase: "essen"
        bare_no_sich,            # reflexive stripped: "ergeben"
        bare_no_sich.lower(),    # reflexive + lower: "ergeben"
    ]
    seen = set()
    for candidate in candidates:
        if candidate in seen or not candidate:
            continue
        seen.add(candidate)
        if candidate in dlex:
            return dlex[candidate]
    return None


# --- Goethe CEFR -----------------------------------------------------------

GOETHE_DIR = EXTERNAL_DIR


def load_goethe():
    """Load Goethe A1/A2/B1 wordlists into a lemma -> level dict."""
    cefr = {}
    for level in ("a1", "a2", "b1"):
        path = GOETHE_DIR / f"goethe-{level}.json"
        if not path.exists():
            print(f"  Goethe {level.upper()} not found at {path}")
            continue
        with open(path) as f:
            data = json.load(f)
        count = 0
        for entry in data:
            for sch in entry.get("sch", []):
                lemma = sch.get("lemma", "")
                if lemma and lemma not in cefr:
                    cefr[lemma] = level.upper()
                    count += 1
        print(f"  Goethe {level.upper()}: {count} lemmas")
    print(f"  Goethe total: {len(cefr)} lemmas")
    return cefr


def lookup_goethe(cefr, word):
    """Look up CEFR level, trying variants."""
    bare = strip_article(word)
    bare_no_sich = bare.replace("sich ", "").strip()
    candidates = [word, bare, bare.capitalize(), bare.lower(),
                  bare_no_sich, bare_no_sich.lower()]
    seen = set()
    for candidate in candidates:
        if candidate in seen or not candidate:
            continue
        seen.add(candidate)
        if candidate in cefr:
            return cefr[candidate]
    return None


# --- DWDS frequency API ----------------------------------------------------

DWDS_API = "https://www.dwds.de/api/frequency/"


def fetch_dwds_frequency(words, delay=0.2):
    """Fetch DWDS frequency class for a list of words.

    Returns dict of word -> frequency class (0-6).
    Rate-limited to ~5 req/s.
    """
    results = {}
    total = len(words)
    # Test connectivity with first word
    bare0 = strip_article(words[0])
    try:
        test = requests.get(DWDS_API, params={"q": bare0}, timeout=10)
        test.raise_for_status()
    except requests.RequestException as e:
        print(f"  DWDS API unreachable: {e}")
        print("  Skipping DWDS frequency fetch (re-run when network is available)")
        return {}
    # First word succeeded, record it
    results[words[0]] = test.json().get("frequency")

    for i, word in enumerate(words[1:], 1):
        bare = strip_article(word)
        try:
            resp = requests.get(DWDS_API, params={"q": bare}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results[word] = data.get("frequency")
            elif resp.status_code == 429:
                print(f"  DWDS rate limited at word {i+1}/{total}, waiting 30s...")
                time.sleep(30)
                # retry once
                resp = requests.get(DWDS_API, params={"q": bare}, timeout=10)
                if resp.status_code == 200:
                    results[word] = resp.json().get("frequency")
            if (i + 1) % 50 == 0:
                print(f"  DWDS: {i+1}/{total}...")
        except requests.RequestException as e:
            print(f"  DWDS error for {word}: {e}")
        time.sleep(delay)
    print(f"  DWDS: {len(results)}/{total} frequencies fetched")
    return results


# --- English Wiktionary senses ---------------------------------------------

EN_WIKT_API = "https://en.wiktionary.org/w/api.php"
_WIKT_HEADERS = {"User-Agent": "AnkiGermanDeck/1.0 (https://github.com/george; george@example.com)"}

# Authenticated session (created on first use via _get_wikt_session)
_wikt_session = None


def _get_wikt_session():
    """Get or create an authenticated requests.Session for en.wiktionary.org.

    Uses WIKTIONARY_USER / WIKTIONARY_PASS env vars (CentralAuth / SUL).
    Authenticated users get 5000 req/hr instead of 500.
    """
    global _wikt_session
    if _wikt_session is not None:
        return _wikt_session

    _wikt_session = requests.Session()
    _wikt_session.headers.update(_WIKT_HEADERS)

    user = os.environ.get("WIKTIONARY_USER", "")
    pw = os.environ.get("WIKTIONARY_PASS", "")
    if not user or not pw:
        print("  Wiktionary: no credentials (WIKTIONARY_USER/WIKTIONARY_PASS)")
        return _wikt_session

    try:
        # Get login token
        resp = _wikt_session.get(EN_WIKT_API, params={
            "action": "query", "meta": "tokens", "type": "login", "format": "json",
        }, timeout=10)
        token = resp.json()["query"]["tokens"]["logintoken"]

        # Log in with bot password (CentralAuth propagates across wikis)
        resp = _wikt_session.post(EN_WIKT_API, data={
            "action": "login", "lgname": user, "lgpassword": pw,
            "lgtoken": token, "format": "json",
        }, timeout=10)
        result = resp.json().get("login", {})
        if result.get("result") == "Success":
            print(f"  Wiktionary: logged in as {result.get('lgusername', user)} "
                  f"(5000 req/hr)")
        else:
            print(f"  Wiktionary login failed: {result.get('result', 'unknown')} "
                  f"— {result.get('reason', '')}")
    except Exception as e:
        print(f"  Wiktionary login error: {e}")

    return _wikt_session

# Matches lines like: # {{lb|de|transitive}} to [[beat]]; to [[hit]]
_SENSE_RE = re.compile(r"^# ")
# Extracts {{lb|de|label1|label2|...}} labels
_LABEL_RE = re.compile(r"\{\{lb\|de\|([^}]+)\}\}")
# Strips wiki markup: [[word]] -> word, {{m|en|word}} -> word
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
# Matches sub-definitions like ## or #*
_SUBDEF_RE = re.compile(r"^#[#*:]")


def _clean_gloss(text):
    """Strip wiki markup from a sense line to produce a clean English gloss."""
    # Remove {{lb|de|...}} — already extracted separately
    text = _LABEL_RE.sub("", text)
    # Remove {{senseid|...}}
    text = re.sub(r"\{\{senseid\|[^}]+\}\}", "", text)
    # Convert [[word]] and [[word|display]] to plain text
    text = _WIKI_LINK_RE.sub(r"\1", text)
    # Remove {{m|en|word}} -> word, {{m+|en|word}} -> word
    text = re.sub(r"\{\{m\+?\|en\|([^}|]+)(?:\|[^}]*)?\}\}", r"\1", text)
    # Remove {{+obj|...}} and other templates
    text = _TEMPLATE_RE.sub("", text)
    # Remove leading "# " and clean up whitespace
    text = re.sub(r"^#\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Remove trailing semicolons or ";" left from template removal
    text = text.strip("; ")
    return text


def _extract_labels(line):
    """Extract usage labels from {{lb|de|...}}."""
    m = _LABEL_RE.search(line)
    if not m:
        return []
    raw = m.group(1)
    # Split on | but skip _=... parameters
    labels = [l.strip() for l in raw.split("|") if l.strip() and not l.startswith("_")]
    return labels


def fetch_en_wiktionary_senses(word, pos_hint=None):
    """Fetch sense definitions for a German word from English Wiktionary.

    Returns a list of sense dicts: [{idx, labels, gloss}, ...]
    """
    # Strip article without lowercasing — Wiktionary is case-sensitive
    bare = re.sub(r'^(der|die|das|sich)\s+', '', word).strip()
    # For multi-word entries, try underscore-joined
    page_title = bare.replace(" ", "_") if " " in bare else bare

    try:
        session = _get_wikt_session()
        resp = session.get(EN_WIKT_API, params={
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
        }, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if "error" in data:
            return []
        wikitext = data["parse"]["wikitext"]["*"]
    except (requests.RequestException, KeyError, json.JSONDecodeError):
        return []

    # Parse the German section
    lines = wikitext.split("\n")
    in_german = False
    in_pos_section = False
    senses = []
    sense_idx = 0

    for line in lines:
        stripped = line.strip()

        # Track German section
        if stripped == "==German==":
            in_german = True
            continue
        if in_german and re.match(r"^==[^=]", stripped):
            # Left German section
            break

        if not in_german:
            continue

        # Track POS sections (===Verb===, ===Noun===, ====Verb====, etc.)
        pos_match = re.match(r"^={3,4}(Verb|Noun|Adjective|Adverb|Pronoun|"
                             r"Conjunction|Preposition|Interjection|"
                             r"Phrase|Numeral|Particle|Determiner)={3,4}$",
                             stripped)
        if pos_match:
            in_pos_section = True
            continue

        # End of POS section at next header
        if in_pos_section and re.match(r"^={3,4}[^=]", stripped):
            if not re.match(r"^={3,4}(Verb|Noun|Adjective|Adverb)", stripped):
                in_pos_section = False
                continue

        if not in_pos_section:
            continue

        # Skip sub-definitions and quotations
        if _SUBDEF_RE.match(stripped):
            continue

        # Match sense lines: # ...
        if _SENSE_RE.match(stripped):
            sense_idx += 1
            labels = _extract_labels(stripped)
            gloss = _clean_gloss(stripped)
            if gloss:
                senses.append({
                    "idx": sense_idx,
                    "labels": labels,
                    "gloss": gloss,
                })

    return senses


def fetch_senses_batch(words, delay=None):
    """Fetch senses for a list of words, with rate limiting.

    Returns dict of word -> [senses].
    Delay defaults to 0.1s when authenticated, 1.0s otherwise.
    """
    results = {}
    total = len(words)
    # Establish session (with auth if available)
    session = _get_wikt_session()
    if delay is None:
        delay = 0.1 if session.cookies else 1.0

    # Test connectivity
    try:
        test = session.get(EN_WIKT_API, params={
            "action": "parse", "page": "Haus", "prop": "wikitext", "format": "json",
        }, timeout=10)
        test.raise_for_status()
    except requests.RequestException as e:
        print(f"  English Wiktionary API unreachable: {e}")
        print("  Skipping sense fetch (re-run when network is available)")
        return {}

    for i, word in enumerate(words):
        senses = fetch_en_wiktionary_senses(word)
        if senses:
            results[word] = senses
        if (i + 1) % 20 == 0:
            print(f"  Wiktionary senses: {i+1}/{total} "
                  f"({len(results)} with senses)...")
        time.sleep(delay)
    print(f"  Wiktionary senses: {len(results)}/{total} words have senses")
    return results


# --- Main build logic -------------------------------------------------------

def load_existing():
    """Load existing word_data.json if present."""
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH) as f:
            return json.load(f)
    return {}


def get_deck_words():
    """Fetch all vocab words from the deck via AnkiConnect."""
    notes = fetch_vocab_notes()
    words = {}
    for note in notes:
        f = note["fields"]
        word = f["Word"]["value"]
        if word:
            words[word] = {
                "pos": f["POS"]["value"].split("|")[0],
                "article": f["Article"]["value"],
                "translation": f["WordTranslation"]["value"],
                "note_id": note["noteId"],
            }
    print(f"  Deck: {len(words)} vocab words")
    return words


def build(args):
    """Build or update word_data.json."""
    existing = load_existing()
    senses_only = getattr(args, "senses_only", False)
    dwds_only = getattr(args, "dwds_only", False)
    dry_run = getattr(args, "dry_run", False)

    print("\n=== Fetching deck words ===")
    deck_words = get_deck_words()

    # Determine which words need data
    words_needing_dlexdb = []
    words_needing_dwds = []
    words_needing_goethe = []
    words_needing_senses = []

    for word in deck_words:
        entry = existing.get(word, {})
        if not dwds_only and not senses_only:
            if "frequency" not in entry or "dlexdb_per_million" not in entry.get("frequency", {}):
                words_needing_dlexdb.append(word)
            if "goethe_level" not in entry or entry.get("goethe_level") is None:
                words_needing_goethe.append(word)
        if not senses_only:
            freq = entry.get("frequency", {})
            if "dwds_class" not in freq:
                words_needing_dwds.append(word)
        if not dwds_only:
            if "senses" not in entry or not entry["senses"]:
                words_needing_senses.append(word)

    # Force refresh all for respective --*-only modes
    if dwds_only:
        words_needing_dwds = list(deck_words.keys())
    if senses_only:
        words_needing_senses = list(deck_words.keys())

    print(f"\n  Need dlexDB lookup: {len(words_needing_dlexdb)}")
    print(f"  Need DWDS freq:    {len(words_needing_dwds)}")
    print(f"  Need Goethe CEFR:  {len(words_needing_goethe)}")
    print(f"  Need Wikt senses:  {len(words_needing_senses)}")

    if dry_run:
        print("\n  --dry-run: would process the above, exiting.")
        return

    # 1. dlexDB (local, instant)
    dlex = {}
    if words_needing_dlexdb:
        print("\n=== dlexDB lookup ===")
        dlex = load_dlexdb()

    # 2. Goethe CEFR (local, instant)
    cefr = {}
    if words_needing_goethe:
        print("\n=== Goethe CEFR ===")
        cefr = load_goethe()

    # Now merge local data
    for word, deck_info in deck_words.items():
        if word not in existing:
            existing[word] = {}
        entry = existing[word]

        # Always update deck metadata
        entry["pos"] = deck_info["pos"]
        entry["translation"] = deck_info["translation"]

        # dlexDB
        if word in words_needing_dlexdb and dlex:
            result = lookup_dlexdb(dlex, word, deck_info["pos"])
            if result:
                entry.setdefault("frequency", {})
                entry["frequency"]["dlexdb_abs"] = result["abs"]
                entry["frequency"]["dlexdb_per_million"] = result["per_million"]
                entry["frequency"]["dlexdb_rank"] = result["rank"]

        # Goethe
        if word in words_needing_goethe:
            level = lookup_goethe(cefr, word) if cefr else None
            entry["goethe_level"] = level

    # Count local results
    dlex_found = sum(1 for w in words_needing_dlexdb
                     if "frequency" in existing.get(w, {})
                     and "dlexdb_per_million" in existing[w]["frequency"])
    goethe_found = sum(1 for w in words_needing_goethe
                       if existing.get(w, {}).get("goethe_level"))
    print(f"\n  dlexDB matched:  {dlex_found}/{len(words_needing_dlexdb)}")
    print(f"  Goethe matched:  {goethe_found}/{len(words_needing_goethe)}")

    # 3. DWDS frequency (network)
    if words_needing_dwds:
        print(f"\n=== DWDS frequency API ({len(words_needing_dwds)} words) ===")
        dwds_results = fetch_dwds_frequency(words_needing_dwds)
        for word, freq_class in dwds_results.items():
            existing.setdefault(word, {})
            existing[word].setdefault("frequency", {})
            existing[word]["frequency"]["dwds_class"] = freq_class

    # 4. English Wiktionary senses (network)
    if words_needing_senses:
        print(f"\n=== English Wiktionary senses ({len(words_needing_senses)} words) ===")
        sense_results = fetch_senses_batch(words_needing_senses)
        for word, senses in sense_results.items():
            existing.setdefault(word, {})
            existing[word]["senses"] = senses

    # Remove words no longer in deck
    removed = [w for w in existing if w not in deck_words]
    for w in removed:
        del existing[w]
    if removed:
        print(f"\n  Removed {len(removed)} words no longer in deck")

    # Write output
    # Sort by word for stable diffs
    sorted_data = dict(sorted(existing.items(), key=lambda x: x[0].lower()))

    with open(OUTPUT_PATH, "w") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)
    print(f"\n=== Wrote {OUTPUT_PATH} ({len(sorted_data)} words) ===")

    # Summary
    has_freq = sum(1 for e in sorted_data.values() if e.get("frequency"))
    has_dwds = sum(1 for e in sorted_data.values()
                   if e.get("frequency", {}).get("dwds_class") is not None)
    has_cefr = sum(1 for e in sorted_data.values() if e.get("goethe_level"))
    has_senses = sum(1 for e in sorted_data.values() if e.get("senses"))
    print(f"  With dlexDB freq: {has_freq}")
    print(f"  With DWDS class:  {has_dwds}")
    print(f"  With Goethe CEFR: {has_cefr}")
    print(f"  With senses:      {has_senses}")


def run(args):
    """CLI entry point."""
    build(args)
