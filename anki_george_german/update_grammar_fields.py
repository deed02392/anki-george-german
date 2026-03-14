#!/usr/bin/env python3
"""Sync grammar term data from grammar_terms.json to Anki.

Creates missing notes and updates existing ones in place (preserving
review history). Mirrors the prefix workflow in update_prefix_fields.py.

Usage:
    anki-german grammar [--dry-run]
"""

import json

from . import DATA_DIR
from ._anki import anki

DATA_PATH = DATA_DIR / "grammar_terms.json"
DECK = "George's German Vocabulary::Grammar Terms"
MODEL = "German Grammar Term"
TAG = "grammar::term"


def main(args=None):
    dry_run = getattr(args, "dry_run", False) if args else False

    with open(DATA_PATH) as f:
        terms = json.load(f)

    print(f"\n── Syncing {len(terms)} grammar terms ──")

    # Ensure deck exists
    if not dry_run:
        anki("createDeck", deck=DECK)

    # Fetch existing notes, build lookup by Term field value
    note_ids = anki("findNotes", query=f'"note:{MODEL}"')
    existing = {}
    if note_ids:
        notes_info = anki("notesInfo", notes=note_ids)
        for note in notes_info:
            term = note["fields"]["Term"]["value"]
            existing[term] = note

    created = 0
    updated = 0
    unchanged = 0

    for entry in terms:
        term = entry["term"]
        fields = {
            "Term": entry["term"],
            "Category": entry["category"],
            "Definition": entry["definition"],
            "Formation": entry["formation"],
            "Example": entry["example"],
            "Note": entry["note"],
        }

        if term in existing:
            # Check if any field actually changed
            note = existing[term]
            changed = []
            for key, new_val in fields.items():
                old_val = note["fields"].get(key, {}).get("value", "")
                if old_val != new_val:
                    changed.append(key)

            if not changed:
                unchanged += 1
                continue

            if dry_run:
                print(f"  [update] {term}: {', '.join(changed)}")
            else:
                anki("updateNoteFields", note={
                    "id": note["noteId"],
                    "fields": fields,
                })
                print(f"  Updated: {term} ({', '.join(changed)})")
            updated += 1
        else:
            if dry_run:
                print(f"  [create] {term}")
            else:
                result = anki("addNotes", notes=[{
                    "deckName": DECK,
                    "modelName": MODEL,
                    "fields": fields,
                    "tags": [TAG],
                    "options": {"allowDuplicate": False},
                }])
                if result[0] is None:
                    print(f"  FAILED to create: {term}")
                    continue
                print(f"  Created: {term}")
            created += 1

    # Check for notes in Anki that are no longer in the JSON
    json_terms = {e["term"] for e in terms}
    orphans = [t for t in existing if t not in json_terms]
    if orphans:
        print(f"\n  WARNING: {len(orphans)} notes in Anki not in JSON:")
        for t in orphans:
            print(f"    - {t}")

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Done. {created} created, {updated} updated, "
          f"{unchanged} unchanged.")


if __name__ == "__main__":
    main()
