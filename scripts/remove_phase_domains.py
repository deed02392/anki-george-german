#!/usr/bin/env python3
"""Remove Phase and Domains fields from the George's German Vocab note model.

Run in tmux pane 4 (needs AnkiConnect):
    uv run python scripts/remove_phase_domains.py
"""
import json
import urllib.request


def anki(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params})
    req = urllib.request.Request(
        "http://localhost:8765",
        data=payload.encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("error"):
        raise RuntimeError(resp["error"])
    return resp.get("result")


MODEL = "George's German Vocab"

# 1. Verify current fields
fields = anki("modelFieldNames", modelName=MODEL)
print(f"Current fields ({len(fields)}):")
for i, f in enumerate(fields):
    print(f"  {i:2d}  {f}")

assert "Domains" in fields, "Domains field not found!"
assert "Phase" in fields, "Phase field not found!"

# 2. Check that Phase and Domains data is expendable
# Phase: all values are 1-4 (historical, no longer used)
# Domains: all empty
print("\nSampling Phase/Domains values to confirm they're safe to delete...")
note_ids = anki("findNotes", query=f'note:"{MODEL}"')
sample = note_ids[:20]
notes = anki("notesInfo", notes=sample)
for n in notes:
    phase = n["fields"].get("Phase", {}).get("value", "")
    domains = n["fields"].get("Domains", {}).get("value", "")
    word = n["fields"].get("Word", {}).get("value", "")
    if domains:
        print(f"  WARNING: {word} has Domains={domains!r}")
    if phase:
        print(f"  {word}: Phase={phase}")

# 3. Remove fields
print("\nRemoving 'Domains' field...")
anki("modelFieldRemove", modelName=MODEL, fieldName="Domains")
print("Removing 'Phase' field...")
anki("modelFieldRemove", modelName=MODEL, fieldName="Phase")

# 4. Verify
fields_after = anki("modelFieldNames", modelName=MODEL)
print(f"\nFields after removal ({len(fields_after)}):")
for i, f in enumerate(fields_after):
    print(f"  {i:2d}  {f}")

assert "Domains" not in fields_after
assert "Phase" not in fields_after
print("\nDone! Phase and Domains fields removed successfully.")
