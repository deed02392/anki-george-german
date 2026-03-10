#!/usr/bin/env python3
"""Quick query to show fields for a specific word."""
import sys

from ._anki import anki


def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    word = args.word
    ids = anki("findNotes", query=f"deck:\"George's German Vocabulary\" Word:\"{word}\"")
    notes = anki("notesInfo", notes=ids)
    if not notes:
        print(f"No notes found for Word: {word}")
    for n in notes:
        for f in ["Word", "Sentence", "SentenceTranslation", "ClozeWord"]:
            print(f"{f}: {n['fields'][f]['value']}")
        print(f"NoteID: {n['noteId']}")


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "der Saft"

    class Args:
        pass

    args = Args()
    args.word = word
    run(args)


if __name__ == "__main__":
    main()
