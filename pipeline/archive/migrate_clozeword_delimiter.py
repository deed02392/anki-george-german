#!/usr/bin/env python3
"""One-time migration: replace | with ~ in ClozeWord for separable verbs.

Existing cards use | to delimit separable verb parts (e.g. "läuft|ab").
Going forward, | is reserved for multi-sentence variant selection and ~ is
used for separable verb parts.  This script finds all ClozeWord values
containing | and replaces them with ~.

Usage:
    uv run python tools/migrate_clozeword_delimiter.py --dry-run
    uv run python tools/migrate_clozeword_delimiter.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki, DECK, MODEL, fetch_vocab_notes


def migrate(dry_run=False):
    all_notes = fetch_vocab_notes()
    if not all_notes:
        print("No notes found.")
        return
    to_update = []

    for note in all_notes:
        cloze = note["fields"].get("ClozeWord", {}).get("value", "")
        sentence = note["fields"].get("Sentence", {}).get("value", "")
        if "|" not in cloze:
            continue
        # Only migrate single-sentence cards.  Multi-sentence cards use |
        # as the variant delimiter — those pipes must be preserved.
        if "|" in sentence:
            continue
        new_cloze = cloze.replace("|", "~")
        word = note["fields"].get("Word", {}).get("value", "?")
        to_update.append((note["noteId"], word, cloze, new_cloze))

    if not to_update:
        print("No ClozeWord values contain |. Nothing to migrate.")
        return

    print(f"Found {len(to_update)} notes to migrate:\n")
    for nid, word, old, new in to_update:
        print(f"  {word:<35} {old:<25} → {new}")

    if dry_run:
        print(f"\n[dry-run] Would update {len(to_update)} notes.")
        return

    updated = 0
    for nid, word, old, new in to_update:
        anki("updateNoteFields", note={"id": nid, "fields": {"ClozeWord": new}})
        updated += 1

    print(f"\nUpdated {updated} notes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without updating")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
