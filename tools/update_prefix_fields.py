#!/usr/bin/env python3
"""Push CoreMeaning, SpatialSense, and Examples from prefix_data.json to existing prefix notes in Anki.

Run this after editing prefix_data.json to sync changes to Anki without
recreating the notes. Complements build_prefixes.py (which creates notes
from scratch) and update_templates.py (which pushes CSS/templates).
"""

import json
import os
import sys
from pathlib import Path

# Ensure tools/ is on sys.path so sibling imports work regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki

DATA_PATH = Path(__file__).parent.parent / "data" / "prefix_data.json"


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
