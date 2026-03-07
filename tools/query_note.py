#!/usr/bin/env python3
"""Quick query to show fields for a specific word."""
import requests, sys

def anki(action, **params):
    return requests.post("http://localhost:8765", json={"action": action, "params": params, "version": 6}).json()["result"]

word = sys.argv[1] if len(sys.argv) > 1 else "der Saft"
ids = anki("findNotes", query=f"deck:\"George's German Vocabulary\" Word:\"{word}\"")
notes = anki("notesInfo", notes=ids)
if not notes:
    print(f"No notes found for Word: {word}")
for n in notes:
    for f in ["Word", "Sentence", "SentenceTranslation", "ClozeWord"]:
        print(f"{f}: {n['fields'][f]['value']}")
    print(f"NoteID: {n['noteId']}")
