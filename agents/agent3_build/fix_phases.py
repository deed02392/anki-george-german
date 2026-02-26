#!/usr/bin/env python3
"""Update phase assignments for notes that were incorrectly assigned to Phase 3."""
import json
import requests
import sys

ANKI_URL = "http://localhost:8765"
DECK_NAME = "George's German Vocabulary"

# Words that should be Phase 2 (not Phase 3)
# These are high-frequency actions, numbers, and location words
PHASE2_WORDS = {
    'hören', 'neun', 'eins', 'der Ball', 'machen', 'geben', 'kommen',
    'gehen', 'sehen', 'stehen', 'finden', 'liegen', 'nehmen', 'zeigen',
    'bringen', 'sitzen', 'suchen', 'helfen', 'schließen', 'öffnen',
    'schlafen', 'aufwachen', 'hier', 'zwei', 'oben', 'drei', 'dort',
    'vier', 'fünf', 'zehn', 'sechs', 'sieben', 'acht', 'unten',
    'draußen', 'drinnen',
}


def anki_request(action, **params):
    payload = {"action": action, "version": 6, "params": params}
    resp = requests.post(ANKI_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        return {"error": data["error"], "result": None}
    return {"error": None, "result": data.get("result")}


def main():
    print("Updating phase assignments ...")

    # Find all Phase 3 notes in the deck
    result = anki_request("findNotes", query=f'deck:"{DECK_NAME}" tag:phase::3')
    if result.get("error"):
        print(f"Error: {result['error']}")
        sys.exit(1)

    phase3_ids = result.get("result") or []
    print(f"Found {len(phase3_ids)} Phase 3 notes")

    # Get their info
    result2 = anki_request("notesInfo", notes=phase3_ids)
    note_infos = result2.get("result") or []

    # Find ones that should be Phase 2
    to_update = []
    for ni in note_infos:
        word = ni.get("fields", {}).get("Word", {}).get("value", "")
        if word in PHASE2_WORDS:
            to_update.append(ni)

    print(f"Found {len(to_update)} notes to move to Phase 2")

    updated = 0
    for ni in to_update:
        note_id = ni["noteId"]
        word = ni["fields"]["Word"]["value"]
        old_tags = ni.get("tags", [])

        # Remove phase::3 tag, add phase::2
        new_tags = [t for t in old_tags if t != "phase::3"] + ["phase::2"]

        # Update fields
        result3 = anki_request(
            "updateNote",
            note={
                "id": note_id,
                "fields": {"Phase": "2"},
                "tags": new_tags,
            }
        )
        if result3.get("error"):
            print(f"  [ERROR] {word}: {result3['error']}")
        else:
            print(f"  Updated: '{word}' -> Phase 2")
            updated += 1

    print(f"\nUpdated {updated} notes to Phase 2")

    # Verify final counts
    for p in ["1", "2", "3"]:
        r = anki_request("findNotes", query=f'deck:"{DECK_NAME}" tag:phase::{p}')
        print(f"Phase {p}: {len(r.get('result') or [])} notes")


if __name__ == "__main__":
    main()
