#!/usr/bin/env python3
"""Backfill the ClozeWord field for George's German Vocabulary notes.

ClozeWord stores the exact text to blank in cloze cards, with | separators
for separable verbs (e.g. "sprang|auf" for aufspringen).

Matching cascade:
  1. Exact match: bare word found verbatim in sentence
  2. Annotation stripping: remove (sich), (r, s), OR ..., etc.
  3. Phrase template: "Wo ist ...?" → check if core text is in sentence
  4. Fuzzy match: score each sentence token against bare word (≥65 threshold)
  5. Separable verb decomposition: detect prefix, fuzzy-match stem, verify prefix
  6. Umlaut noun matching: try a→ä, o→ö, u→ü substitutions + plural suffixes
  7. Manual fallback: flag for review

Usage:
    python3 backfill_clozeword.py              # apply changes
    python3 backfill_clozeword.py --dry-run     # preview without changes
    python3 backfill_clozeword.py --verify      # check existing ClozeWord values
    python3 backfill_clozeword.py --overrides manual.json  # apply manual corrections
"""
import argparse
import json
import re
import sys

import requests

try:
    from rapidfuzz import fuzz
except ImportError:
    print("ERROR: rapidfuzz is required. Install with: pip install rapidfuzz", file=sys.stderr)
    sys.exit(1)

DECK = "George's German Vocabulary"
MODEL = "George's German Vocab"
ANKI_URL = "http://localhost:8765"

SEPARABLE_PREFIXES = [
    "zusammen", "zurück", "weiter", "heraus", "herunter", "herein", "hinaus",
    "hinein", "fest", "statt",
    "ab", "an", "auf", "aus", "bei", "ein", "her", "hin", "los", "mit",
    "nach", "vor", "weg", "zu",
]

INSEPARABLE_PREFIXES = {"be", "emp", "ent", "er", "ge", "miss", "ver", "zer"}


# ── AnkiConnect ──────────────────────────────────────────────────────────────

def anki(action, **params):
    resp = requests.post(ANKI_URL, json={"action": action, "params": params, "version": 6}).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {resp['error']}")
    return resp["result"]


def ensure_clozeword_field():
    """Add the ClozeWord field to the note type if it doesn't already exist."""
    fields = anki("modelFieldNames", modelName=MODEL)
    if "ClozeWord" in fields:
        return False
    # Insert after Sentence (index 8)
    sentence_idx = fields.index("Sentence") if "Sentence" in fields else 7
    anki("modelFieldAdd", modelName=MODEL,
         fieldName="ClozeWord", index=sentence_idx + 1)
    print("Added 'ClozeWord' field to note type (after Sentence).")
    return True


# ── Word extraction ──────────────────────────────────────────────────────────

def strip_article(word):
    """Remove leading German article."""
    return re.sub(r"^(der|die|das|ein|eine)\s+", "", word, flags=re.IGNORECASE).strip()


def is_phrase(word):
    """Check if the word is a multi-word phrase."""
    clean = strip_article(word)
    return any(c in clean for c in [" ", "?", "!", "…"]) or "..." in clean


def strip_annotations(word):
    """Remove parenthetical annotations like (sich), (r, s), (etw.), etc."""
    # Remove parenthetical content
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", word)
    # Remove "OR ..." alternatives
    cleaned = re.sub(r"\s+OR\s+.*", "", cleaned, flags=re.IGNORECASE)
    # Remove trailing ellipsis
    cleaned = re.sub(r"\s*\.\.\.+\s*", " ", cleaned)
    return cleaned.strip()


def tokenise_sentence(sentence):
    """Split a sentence into word tokens, preserving original case."""
    return re.findall(r"[A-Za-zÀ-ÿ\u00c0-\u024f]+", sentence)


# ── Matching strategies ──────────────────────────────────────────────────────

def try_exact_match(bare, sentence):
    """Strategy 1: exact substring match (case-sensitive)."""
    if bare in sentence:
        return bare, 100, "exact"
    return None, 0, None


def try_case_insensitive_match(bare, sentence):
    """Strategy 1b: case-insensitive substring match."""
    m = re.search(re.escape(bare), sentence, re.IGNORECASE)
    if m:
        return m.group(0), 99, "exact-ci"
    return None, 0, None


def try_annotation_stripped(word, sentence):
    """Strategy 2: strip annotations and try matching."""
    cleaned = strip_annotations(strip_article(word))
    if not cleaned or cleaned == strip_article(word):
        return None, 0, None

    # Try each comma-separated variant
    variants = [v.strip() for v in cleaned.split(",")]
    for v in variants:
        if not v:
            continue
        if v in sentence:
            return v, 95, "annotation-stripped"
        m = re.search(re.escape(v), sentence, re.IGNORECASE)
        if m:
            return m.group(0), 94, "annotation-stripped-ci"
    return None, 0, None


def try_phrase_template(word, sentence):
    """Strategy 3: handle phrase templates like 'Wo ist ...?'."""
    bare = strip_article(word)
    if "..." not in bare and "…" not in bare:
        return None, 0, None

    # Strip ellipsis and punctuation to get core text
    core = re.sub(r"[.…?!]+", " ", bare).strip()
    words_in_core = core.split()
    if not words_in_core:
        return None, 0, None

    # Check if all core words appear in the sentence
    matched_parts = []
    for w in words_in_core:
        m = re.search(re.escape(w), sentence, re.IGNORECASE)
        if m:
            matched_parts.append(m.group(0))
        else:
            return None, 0, None

    return "|".join(matched_parts), 85, "phrase-template"


def try_fuzzy_match(bare, sentence, threshold=65):
    """Strategy 4: fuzzy match each token against the bare word."""
    tokens = tokenise_sentence(sentence)
    if not tokens:
        return None, 0, None

    best_token = None
    best_score = 0
    for token in tokens:
        score = fuzz.ratio(bare.lower(), token.lower())
        if score > best_score:
            best_score = score
            best_token = token

    if best_score >= threshold:
        return best_token, best_score, "fuzzy"
    return None, 0, None


def try_separable_verb(word, sentence, threshold=60):
    """Strategy 5: decompose separable verb into stem + prefix."""
    bare = strip_article(word).lower()

    # Check for separable prefix
    prefix = None
    stem = None
    for p in SEPARABLE_PREFIXES:
        if bare.startswith(p) and len(bare) > len(p) + 1:
            candidate_stem = bare[len(p):]
            # Skip if the remaining stem starts with an inseparable prefix
            # (e.g. "verstehen" — "ver" is inseparable, not "ver" + "stehen" separated)
            if any(candidate_stem.startswith(ip) for ip in INSEPARABLE_PREFIXES):
                continue
            prefix = p
            stem = candidate_stem
            break

    if not prefix or not stem:
        return None, 0, None

    tokens = tokenise_sentence(sentence)
    if not tokens:
        return None, 0, None

    # Fuzzy-match stem against tokens
    best_token = None
    best_score = 0
    for token in tokens:
        score = fuzz.ratio(stem, token.lower())
        if score > best_score:
            best_score = score
            best_token = token

    if best_score < threshold:
        return None, 0, None

    # Verify prefix appears at or near clause end (last 3 tokens)
    prefix_token = None
    for token in reversed(tokens):
        if token.lower() == prefix:
            prefix_token = token
            break

    if not prefix_token:
        # Also check a relaxed match — prefix might be capitalised or have suffix
        for token in reversed(tokens):
            if token.lower().startswith(prefix):
                score = fuzz.ratio(prefix, token.lower())
                if score >= 80:
                    prefix_token = token
                    break

    if prefix_token:
        return f"{best_token}|{prefix_token}", best_score, "separable-verb"
    return None, 0, None


def try_umlaut_match(bare, sentence):
    """Strategy 6: try umlaut substitutions + plural suffixes."""
    umlaut_map = {"a": "ä", "o": "ö", "u": "ü", "au": "äu"}

    candidates = set()
    bare_lower = bare.lower()

    # Try each umlaut substitution
    for plain, umlauted in umlaut_map.items():
        if plain in bare_lower:
            # Replace first occurrence
            variant = bare_lower.replace(plain, umlauted, 1)
            candidates.add(variant)
            # Also try with common plural suffixes
            for suffix in ["e", "er", "en", "n"]:
                candidates.add(variant + suffix)

    # Also try just adding plural suffixes without umlaut
    for suffix in ["e", "er", "en", "n", "s"]:
        candidates.add(bare_lower + suffix)

    for candidate in candidates:
        m = re.search(re.escape(candidate), sentence, re.IGNORECASE)
        if m:
            return m.group(0), 90, "umlaut-plural"

    return None, 0, None


def find_cloze_word(word, sentence):
    """Run the full matching cascade and return (cloze_word, confidence, method)."""
    bare = strip_article(word)

    # Strategy 1: exact match
    result, conf, method = try_exact_match(bare, sentence)
    if result:
        return result, conf, method

    # Strategy 1b: case-insensitive exact
    result, conf, method = try_case_insensitive_match(bare, sentence)
    if result:
        return result, conf, method

    # Strategy 2: annotation stripping
    result, conf, method = try_annotation_stripped(word, sentence)
    if result:
        return result, conf, method

    # Strategy 3: phrase template
    result, conf, method = try_phrase_template(word, sentence)
    if result:
        return result, conf, method

    # Strategy 6: umlaut/plural before fuzzy (higher confidence)
    result, conf, method = try_umlaut_match(bare, sentence)
    if result:
        return result, conf, method

    # Strategy 5: separable verb (before fuzzy — more specific)
    result, conf, method = try_separable_verb(word, sentence)
    if result:
        return result, conf, method

    # Strategy 4: fuzzy match (last resort)
    result, conf, method = try_fuzzy_match(bare, sentence)
    if result:
        return result, conf, method

    return None, 0, "none"


# ── Verification ─────────────────────────────────────────────────────────────

def verify_cloze_words(notes):
    """Check that each |‐separated part of ClozeWord appears in Sentence."""
    errors = []
    checked = 0
    for note in notes:
        cw = note["fields"].get("ClozeWord", {}).get("value", "")
        sentence = note["fields"]["Sentence"]["value"]
        word = note["fields"]["Word"]["value"]
        if not cw:
            continue
        checked += 1
        parts = [p.strip() for p in cw.split("|") if p.strip()]
        for part in parts:
            if part not in sentence:
                errors.append({
                    "word": word,
                    "cloze_word": cw,
                    "missing_part": part,
                    "sentence": sentence,
                })
    return checked, errors


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without applying them")
    parser.add_argument("--verify", action="store_true",
                        help="Verify existing ClozeWord values match sentences")
    parser.add_argument("--overrides", type=str,
                        help="JSON file with manual overrides: {word: cloze_word}")
    args = parser.parse_args()

    # Load overrides
    overrides = {}
    if args.overrides:
        with open(args.overrides) as f:
            overrides = json.load(f)
        print(f"Loaded {len(overrides)} manual overrides.")

    # Ensure field exists
    if not args.verify:
        if not args.dry_run:
            ensure_clozeword_field()
        else:
            fields = anki("modelFieldNames", modelName=MODEL)
            if "ClozeWord" not in fields:
                print("[dry-run] Would add 'ClozeWord' field to note type.\n")

    # Fetch all notes
    note_ids = anki("findNotes", query=f'"deck:{DECK}"')
    notes = anki("notesInfo", notes=note_ids)
    print(f"Fetched {len(notes)} notes.\n")

    # Verify mode
    if args.verify:
        checked, errors = verify_cloze_words(notes)
        print(f"Verified {checked} notes with ClozeWord values.")
        if errors:
            print(f"\n{len(errors)} ERRORS found:")
            for e in errors:
                print(f"  {e['word']}: ClozeWord='{e['cloze_word']}' "
                      f"missing '{e['missing_part']}' in sentence")
        else:
            print("All ClozeWord values verified OK.")
        return

    # Backfill
    stats = {
        "exact": 0, "exact-ci": 0, "annotation-stripped": 0,
        "annotation-stripped-ci": 0, "phrase-template": 0,
        "umlaut-plural": 0, "separable-verb": 0, "fuzzy": 0,
        "override": 0, "no-sentence": 0, "already-set": 0, "failed": 0,
    }
    low_confidence = []
    updated = 0

    for note in notes:
        nid = note["noteId"]
        word = note["fields"]["Word"]["value"]
        sentence = note["fields"]["Sentence"]["value"]
        existing_cw = note["fields"].get("ClozeWord", {}).get("value", "")

        # Skip if already has a ClozeWord (unless override exists)
        bare_for_override = strip_article(word).lower()
        has_override = bare_for_override in overrides or word in overrides

        if existing_cw and not has_override:
            stats["already-set"] += 1
            continue

        # No sentence → nothing to blank
        if not sentence:
            stats["no-sentence"] += 1
            continue

        # Check overrides first
        if has_override:
            cloze_word = overrides.get(word) or overrides.get(bare_for_override, "")
            if cloze_word:
                conf, method = 100, "override"
            else:
                # Empty override means "skip"
                continue
        else:
            cloze_word, conf, method = find_cloze_word(word, sentence)

        if cloze_word:
            stats[method] = stats.get(method, 0) + 1

            # Report
            prefix = "[dry-run] " if args.dry_run else ""
            confidence_marker = ""
            if conf < 80:
                confidence_marker = " ⚠"
                low_confidence.append({
                    "word": word,
                    "cloze_word": cloze_word,
                    "confidence": conf,
                    "method": method,
                    "sentence": sentence,
                })

            print(f"{prefix}{word:<30} → {cloze_word:<25} ({method}, {conf}%){confidence_marker}")

            if not args.dry_run:
                anki("updateNoteFields", note={"id": nid, "fields": {"ClozeWord": cloze_word}})
            updated += 1
        else:
            stats["failed"] += 1
            print(f"{'[dry-run] ' if args.dry_run else ''}MISS: {word:<30} "
                  f"sentence: {sentence[:60]}...")
            low_confidence.append({
                "word": word,
                "cloze_word": None,
                "confidence": 0,
                "method": "none",
                "sentence": sentence,
            })

    # Summary
    print(f"\n{'[dry-run] ' if args.dry_run else ''}Summary:")
    print(f"  Updated:           {updated}")
    print(f"  Already set:       {stats['already-set']}")
    print(f"  No sentence:       {stats['no-sentence']}")
    print(f"  Failed (no match): {stats['failed']}")
    print(f"\n  By method:")
    for method in ["exact", "exact-ci", "annotation-stripped", "annotation-stripped-ci",
                    "phrase-template", "umlaut-plural", "separable-verb", "fuzzy", "override"]:
        count = stats.get(method, 0)
        if count:
            print(f"    {method:<25} {count}")

    if low_confidence:
        print(f"\n  Low-confidence / failed ({len(low_confidence)} notes):")
        for lc in low_confidence:
            marker = f"→ {lc['cloze_word']}" if lc["cloze_word"] else "→ NO MATCH"
            print(f"    {lc['word']:<30} {marker:<30} "
                  f"({lc['method']}, {lc['confidence']}%)")
            print(f"      sentence: {lc['sentence'][:80]}")
        print(f"\n  To fix these, create a JSON overrides file and re-run with --overrides.")
        print(f"  Format: {'{'}\"word\": \"cloze_word\", ...{'}'}")


if __name__ == "__main__":
    main()
