#!/usr/bin/env python3
"""Fix noun cloze cards to include the article in ClozeWord.

For noun sentences, if an article (der/die/das/den/dem/des/ein/eine/etc.)
immediately precedes the cloze word in the sentence, update ClozeWord to
include the article.  This prevents the visible article from giving away
the gender on the cloze card.

Usage:
    uv run python tools/fix_noun_cloze_articles.py --dry-run
    uv run python tools/fix_noun_cloze_articles.py
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki, DECK, MODEL

# German articles — definite, indefinite, negative, demonstrative
ARTICLES = (
    # definite
    "der", "die", "das", "den", "dem", "des",
    # indefinite
    "ein", "eine", "einen", "einem", "eines", "einer",
    # negative
    "kein", "keine", "keinen", "keinem", "keines", "keiner",
)
ARTICLE_SET = set(ARTICLES)


def find_preceding_article(sentence, cloze_word):
    """If an article immediately precedes cloze_word in sentence, return it."""
    # Handle separable verb ~ delimiter — only look at the first part
    first_part = cloze_word.split("~")[0].strip()
    idx = sentence.find(first_part)
    if idx <= 0:
        return None

    # Get the word immediately before
    before = sentence[:idx].rstrip()
    if not before:
        return None

    preceding_word = before.split()[-1]

    # Strip punctuation from the preceding word
    clean = preceding_word.strip(".,;:!?\"'()[]{}–—")

    if clean.lower() in {a.lower() for a in ARTICLES}:
        # Return the article as it appears in the sentence (preserving case)
        return clean

    return None


def fix_notes(dry_run=False):
    note_ids = anki("findNotes", query=f'deck:"{DECK}" "note:{MODEL}"')
    if not note_ids:
        print("No notes found.")
        return

    all_notes = anki("notesInfo", notes=note_ids)
    to_update = []

    for note in all_notes:
        fields = note["fields"]
        sentences_raw = fields.get("Sentence", {}).get("value", "")
        cloze_raw = fields.get("ClozeWord", {}).get("value", "")
        pos_raw = fields.get("POS", {}).get("value", "")
        word = fields.get("Word", {}).get("value", "?")

        if not sentences_raw or not cloze_raw:
            continue

        sentences = sentences_raw.split("|")
        clozes = cloze_raw.split("|")
        poses = pos_raw.split("|") if pos_raw else []

        # Pad to same length
        while len(clozes) < len(sentences):
            clozes.append("")
        while len(poses) < len(sentences):
            poses.append("")

        changed = False
        new_clozes = []

        for i, (sent, cloze, pos) in enumerate(zip(sentences, clozes, poses)):
            sent = sent.strip()
            cloze = cloze.strip()
            pos = pos.strip().lower()

            if pos != "noun" or not cloze:
                new_clozes.append(cloze)
                continue

            # Skip if cloze already starts with an article
            first_word = cloze.split()[0] if cloze else ""
            if first_word.lower() in {a.lower() for a in ARTICLES}:
                new_clozes.append(cloze)
                continue

            article = find_preceding_article(sent, cloze)
            if article:
                new_cloze = f"{article} {cloze}"
                # Verify the combined string is in the sentence
                if new_cloze in sent:
                    new_clozes.append(new_cloze)
                    changed = True
                else:
                    new_clozes.append(cloze)
            else:
                new_clozes.append(cloze)

        if changed:
            new_cloze_field = "|".join(new_clozes)
            to_update.append((note["noteId"], word, cloze_raw, new_cloze_field))

    if not to_update:
        print("No noun cloze cards need article fixes.")
        return

    print(f"Found {len(to_update)} notes to update:\n")
    for nid, word, old, new in to_update:
        old_parts = old.split("|")
        new_parts = new.split("|")
        changes = []
        for j, (o, n) in enumerate(zip(old_parts, new_parts)):
            if o != n:
                changes.append(f"    [{j}] {o} → {n}")
        print(f"  {word}")
        print("\n".join(changes))

    if dry_run:
        print(f"\n[dry-run] Would update {len(to_update)} notes.")
        return

    updated = 0
    for nid, word, old, new in to_update:
        anki("updateNoteFields", note={"id": nid, "fields": {"ClozeWord": new}})
        updated += 1

    print(f"\nUpdated {updated} notes.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without updating")
    args = parser.parse_args()
    fix_notes(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
