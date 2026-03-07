#!/usr/bin/env python3
"""
Build "German Prefix" note type and import 21 prefix cards via AnkiConnect.

Creates a sub-deck "George's German Vocabulary::Prefixes" with cards that teach
the German prefix system — what each prefix means spatially/directionally, and
how that meaning shows up in verbs George already studies.
"""

import json
import sys
from pathlib import Path

import requests

ANKI_URL = "http://localhost:8765"
MODEL_NAME = "German Prefix"
DECK_NAME = "George's German Vocabulary::Prefixes"
DATA_PATH = Path(__file__).parent / "prefix_data.json"


def anki(action, **params):
    r = requests.post(ANKI_URL, json={"action": action, "version": 6, "params": params})
    r.raise_for_status()
    result = r.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect [{action}]: {result['error']}")
    return result["result"]


def create_note_type():
    """Create the German Prefix note type if it doesn't exist."""
    existing = anki("modelNames")
    if MODEL_NAME in existing:
        print(f"Note type '{MODEL_NAME}' already exists — skipping creation.")
        return

    # Placeholder templates — update_templates.py is the source of truth
    fields = ["Prefix", "PrefixType", "CoreMeaning", "SpatialSense", "Examples"]
    templates = [
        {
            "Name": "Prefix → Meaning",
            "Front": "<div>{{Prefix}}-</div>",
            "Back": "<div>{{CoreMeaning}}</div><div>{{Examples}}</div>",
        },
        {
            "Name": "Meaning → Prefix",
            "Front": "<div>{{CoreMeaning}}</div>",
            "Back": "<div>{{Prefix}}-</div><div>{{Examples}}</div>",
        },
    ]

    anki(
        "createModel",
        modelName=MODEL_NAME,
        inOrderFields=fields,
        css="",  # update_templates.py pushes the real CSS
        isCloze=False,
        cardTemplates=templates,
    )
    print(f"Created note type '{MODEL_NAME}'.")


def format_examples_html(prefix, examples):
    """Format example verbs as HTML with the prefix highlighted."""
    lines = []
    for ex in examples:
        verb = ex["verb"]
        translation = ex["translation"]
        # Highlight the prefix in the verb
        pfx_lower = prefix.lower()
        verb_lower = verb.lower()
        if verb_lower.startswith(pfx_lower):
            highlighted = f'<span class="pfx">{verb[:len(prefix)]}</span>{verb[len(prefix):]}'
        else:
            highlighted = verb
        lines.append(f"{highlighted} — {translation}")
    return "<br>".join(lines)


def main():
    print("=" * 50)
    print("German Prefix Cards — Builder")
    print("=" * 50)

    # Load data
    with open(DATA_PATH) as f:
        prefixes = json.load(f)
    print(f"Loaded {len(prefixes)} prefixes from {DATA_PATH.name}")

    # Create note type
    create_note_type()

    # Create sub-deck
    anki("createDeck", deck=DECK_NAME)
    print(f"Deck '{DECK_NAME}' ready.")

    # Build notes
    notes = []
    for entry in prefixes:
        examples_html = format_examples_html(entry["prefix"], entry["examples"])
        notes.append({
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {
                "Prefix": entry["prefix"],
                "PrefixType": entry["type"],
                "CoreMeaning": entry["core_meaning"],
                "SpatialSense": entry["spatial_sense"],
                "Examples": examples_html,
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
            "tags": ["prefix"],
        })

    # Import
    print(f"Importing {len(notes)} prefix notes...")
    result = anki("addNotes", notes=notes)

    added = sum(1 for r in result if r is not None)
    skipped = sum(1 for r in result if r is None)
    print(f"  Added: {added}")
    if skipped:
        print(f"  Skipped (duplicates): {skipped}")

    # Verify
    found = anki("findNotes", query=f'deck:"{DECK_NAME}"')
    print(f"  Notes in deck: {len(found)}")

    print()
    print(f"Done. {added} prefix cards created in '{DECK_NAME}'.")


if __name__ == "__main__":
    main()
