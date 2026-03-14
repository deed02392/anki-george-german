#!/usr/bin/env python3
"""Fix noun cloze cards to include articles and contractions in ClozeWord.

For noun sentences, if an article (der/die/das/den/dem/des/ein/eine/etc.)
or a contracted preposition+article (beim, im, zum, zur, etc.) immediately
precedes the cloze word in the sentence, update ClozeWord to include it.
This ensures the learner must produce the full noun phrase including case.

Usage:
    anki-german enrich noun-cloze --dry-run
    anki-german enrich noun-cloze
"""
import argparse
import re

from ._anki import anki, DECK, MODEL, ARTICLE_SET, fetch_vocab_notes

# Contracted preposition+article forms.
# The cloze should include these so the learner produces the full phrase.
CONTRACTIONS = {
    "am", "ans", "aufs", "beim", "durchs", "fürs",
    "im", "ins", "vom", "zum", "zur", "ums", "hinterm",
    "hintern", "hinters", "überm", "übern", "übers",
    "unterm", "untern", "unters", "vors", "vorm",
}


def find_preceding_article_or_contraction(sentence, cloze_word):
    """If an article or contraction immediately precedes cloze_word, return it."""
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

    if clean.lower() in ARTICLE_SET or clean.lower() in CONTRACTIONS:
        # Return as it appears in the sentence (preserving case)
        return clean

    return None


def fix_notes(dry_run=False):
    all_notes = fetch_vocab_notes()
    if not all_notes:
        print("No notes found.")
        return
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

            # Skip if cloze already starts with an article or contraction
            first_word = cloze.split()[0] if cloze else ""
            if first_word.lower() in ARTICLE_SET or first_word.lower() in CONTRACTIONS:
                new_clozes.append(cloze)
                continue

            preceding = find_preceding_article_or_contraction(sent, cloze)
            if preceding:
                new_cloze = f"{preceding} {cloze}"
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


def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    fix_notes(dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without updating")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
