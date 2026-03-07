#!/usr/bin/env python3
"""Push CoreMeaning, SpatialSense, and Examples from prefix_data.json to existing prefix notes in Anki.

Run this after editing prefix_data.json to sync changes to Anki without
recreating the notes. Complements build_prefixes.py (which creates notes
from scratch) and update_templates.py (which pushes CSS/templates).
"""

import json
from pathlib import Path

import requests

ANKI_URL = "http://localhost:8765"
DATA_PATH = Path(__file__).parent / "prefix_data.json"


def anki(action, **params):
    r = requests.post(ANKI_URL, json={"action": action, "version": 6, "params": params})
    r.raise_for_status()
    result = r.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect [{action}]: {result['error']}")
    return result["result"]


def format_examples_html(prefix, examples):
    """Format example verbs as HTML with the prefix highlighted."""
    lines = []
    for ex in examples:
        verb = ex["verb"]
        translation = ex["translation"]
        pfx_lower = prefix.lower()
        if verb.lower().startswith(pfx_lower):
            highlighted = f'<span class="pfx">{verb[:len(prefix)]}</span>{verb[len(prefix):]}'
        else:
            highlighted = verb
        lines.append(f"{highlighted} — {translation}")
    return "<br>".join(lines)


def main():
    with open(DATA_PATH) as f:
        prefixes = json.load(f)

    # Find all prefix notes
    note_ids = anki("findNotes", query='deck:"George\'s German Vocabulary::Prefixes"')
    notes_info = anki("notesInfo", notes=note_ids)

    # Build lookup: prefix value -> note ID
    prefix_to_note = {}
    for note in notes_info:
        pfx = note["fields"]["Prefix"]["value"]
        prefix_to_note[pfx] = note["noteId"]

    updated = 0
    for entry in prefixes:
        pfx = entry["prefix"]
        note_id = prefix_to_note.get(pfx)
        if not note_id:
            print(f"  SKIP: '{pfx}' not found in Anki")
            continue
        examples_html = format_examples_html(pfx, entry["examples"])
        anki("updateNoteFields", note={
            "id": note_id,
            "fields": {
                "CoreMeaning": entry["core_meaning"],
                "SpatialSense": entry["spatial_sense"],
                "Examples": examples_html,
            }
        })
        updated += 1
        print(f"  Updated: {pfx} -> \"{entry['core_meaning']}\" / \"{entry['spatial_sense']}\"")

    print(f"\nDone. {updated} notes updated.")


if __name__ == "__main__":
    main()
