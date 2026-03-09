#!/usr/bin/env python3
"""Fix noun cloze words missing their article/determiner.

Uses spaCy noun chunks to expand bare noun clozes to include the
preceding determiner and any adjectives, e.g. "Kind" → "Jedes Kind".

Only expands when the noun chunk starts with a DET or PRON token
(articles, possessives, demonstratives) and contains a single noun.

Usage:
    uv run python tools/fix_noun_cloze.py --dry-run
    uv run python tools/fix_noun_cloze.py
"""
import argparse
import os
import sys

import spacy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki, DECK, MODEL


def fix_noun_clozes(dry_run=False):
    print("Loading spaCy model...")
    nlp = spacy.load("de_dep_news_trf")

    note_ids = anki("findNotes", query=f'deck:"{DECK}" "note:{MODEL}"')
    notes = anki("notesInfo", notes=note_ids)

    updates = []

    for note in notes:
        fields = note["fields"]
        pos_raw = fields.get("POS", {}).get("value", "")
        poses = pos_raw.split("|")
        if "noun" not in poses:
            continue

        word = fields["Word"]["value"]
        sentences = fields["Sentence"]["value"].split("|")
        clozes = fields["ClozeWord"]["value"].split("|")

        new_clozes = list(clozes)
        changed = False

        for i, (sent, cloze) in enumerate(zip(sentences, clozes)):
            if i >= len(poses):
                continue
            if poses[i] != "noun":
                continue
            if "~" in cloze:
                continue

            bare = cloze.strip()

            # Already has multiple words (likely already has determiner)
            if " " in bare:
                continue

            # Bare noun must appear in the sentence
            if bare not in sent:
                continue

            # Parse with spaCy and find the noun chunk containing our word
            doc = nlp(sent)
            best_chunk = None
            for chunk in doc.noun_chunks:
                if bare in chunk.text:
                    # Only use chunk if it starts with a DET or PRON token
                    first_tok = chunk[0]
                    if first_tok.pos_ not in ("DET", "PRON"):
                        continue
                    # Reject chunks that include extra nouns beyond target
                    nouns_in_chunk = [
                        t for t in chunk if t.pos_ in ("NOUN", "PROPN")
                    ]
                    if len(nouns_in_chunk) > 1:
                        continue
                    # Prefer the tightest chunk
                    if best_chunk is None or len(chunk.text) < len(best_chunk.text):
                        best_chunk = chunk

            if best_chunk and best_chunk.text != bare and best_chunk.text in sent:
                new_clozes[i] = best_chunk.text
                changed = True

        if changed:
            updates.append({
                "noteId": note["noteId"],
                "word": word,
                "sentences": sentences,
                "old_clozes": clozes,
                "new_clozes": new_clozes,
            })

    prefix = "[dry-run] " if dry_run else ""
    print(f"\n{prefix}Noun cloze fixes ({len(updates)} cards):\n")
    for u in updates:
        print(f"  {u['word']}")
        for i, (sent, old_c, new_c) in enumerate(
            zip(u["sentences"], u["old_clozes"], u["new_clozes"])
        ):
            if old_c != new_c:
                print(f"    [{i+1}] {sent}")
                print(f"        {old_c} → {new_c}")
        print()

    if dry_run:
        print(f"[dry-run] Would update {len(updates)} cards.")
        return

    for u in updates:
        anki("updateNoteFields", note={
            "id": u["noteId"],
            "fields": {"ClozeWord": "|".join(u["new_clozes"])}
        })

    print(f"Updated {len(updates)} cards.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    fix_noun_clozes(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
