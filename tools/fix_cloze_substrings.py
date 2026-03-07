#!/usr/bin/env python3
"""Find and fix ClozeWord values that are substrings of longer words in sentences.

When ClozeWord is "Ente" but the sentence has "Enten", the cloze blank only covers
"Ente" and the trailing "n" leaks morphological information. This script finds all
such cases and updates ClozeWord to the full inflected form from the sentence.

Usage:
    python3 fix_partial_cloze.py --dry-run    # preview
    python3 fix_partial_cloze.py              # apply fixes
"""
import argparse
import re

import requests

ANKI_URL = "http://localhost:8765"
DECK = "George's German Vocabulary"
MODEL = "George's German Vocab"


def anki(action, **params):
    resp = requests.post(ANKI_URL, json={"action": action, "params": params, "version": 6}).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {resp['error']}")
    return resp["result"]


def tokenise(sentence):
    """Extract word tokens from a sentence, preserving original case."""
    return re.findall(r"[A-Za-zÀ-ÿ\u00c0-\u024f]+", sentence)


def check_part(part, tokens):
    """Check whether a ClozeWord part matches a full token or only a substring.

    Returns:
        (None, False)          — part matches a standalone token exactly (no fix needed)
        (full_token, True)     — part only exists as a substring of full_token (needs fix)
        (None, False)          — part not found at all (leave alone)
    """
    # First: does part match any token exactly?
    for token in tokens:
        if token == part:
            return None, False
    # Case-insensitive exact check
    part_lower = part.lower()
    for token in tokens:
        if token.lower() == part_lower:
            return None, False

    # Part doesn't match any standalone token. Look for it as a substring.
    # Case-sensitive first
    for token in tokens:
        if part in token and len(token) > len(part):
            return token, True
    # Case-insensitive fallback
    for token in tokens:
        if part_lower in token.lower() and len(token) > len(part):
            return token, True

    return None, False


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without applying")
    args = parser.parse_args()

    note_ids = anki("findNotes", query=f'"deck:{DECK}"')
    notes = anki("notesInfo", notes=note_ids)
    print(f"Fetched {len(notes)} notes.\n")

    fixes = []

    for note in notes:
        nid = note["noteId"]
        word = note["fields"]["Word"]["value"]
        sentence = note["fields"]["Sentence"]["value"]
        cloze_word = note["fields"].get("ClozeWord", {}).get("value", "")

        if not sentence:
            continue

        # Determine what the cloze JS will actually use
        if cloze_word:
            active = cloze_word
        else:
            # JS fallback: strip article from Word
            active = re.sub(r"^(der|die|das|ein|eine)\s+", "", word, flags=re.IGNORECASE).strip()

        tokens = tokenise(sentence)

        # Check each tilde-separated part (~ separates separable verb parts)
        parts = [p.strip() for p in active.split("~") if p.strip()]
        new_parts = []
        any_partial = False

        for part in parts:
            full_token, is_partial = check_part(part, tokens)
            if is_partial and full_token:
                new_parts.append(full_token)
                any_partial = True
            else:
                new_parts.append(part)

        if any_partial:
            new_cloze = "~".join(new_parts)
            fixes.append({
                "nid": nid,
                "word": word,
                "old": active,
                "new": new_cloze,
                "sentence": sentence,
                "had_clozeword": bool(cloze_word),
            })

    # Report
    if not fixes:
        print("No partial matches found. All cloze words cover full tokens.")
        return

    print(f"Found {len(fixes)} partial matches:\n")
    for f in fixes:
        source = "ClozeWord" if f["had_clozeword"] else "Word (fallback)"
        print(f"  {f['word']:<28} {f['old']:<20} → {f['new']:<20} (from {source})")
        print(f"    {f['sentence'][:90]}")
        print()

    if args.dry_run:
        print(f"[dry-run] Would fix {len(fixes)} notes.")
        return

    # Apply fixes
    updated = 0
    for f in fixes:
        anki("updateNoteFields", note={"id": f["nid"], "fields": {"ClozeWord": f["new"]}})
        updated += 1

    print(f"Updated {updated} notes.")


if __name__ == "__main__":
    main()
