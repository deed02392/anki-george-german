#!/usr/bin/env python3
"""Quick query to show fields for a specific word."""
import os
import sys

# Ensure tools/ is on sys.path so sibling imports work regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki

word = sys.argv[1] if len(sys.argv) > 1 else "der Saft"
ids = anki("findNotes", query=f"deck:\"George's German Vocabulary\" Word:\"{word}\"")
notes = anki("notesInfo", notes=ids)
if not notes:
    print(f"No notes found for Word: {word}")
for n in notes:
    for f in ["Word", "Sentence", "SentenceTranslation", "ClozeWord"]:
        print(f"{f}: {n['fields'][f]['value']}")
    print(f"NoteID: {n['noteId']}")
