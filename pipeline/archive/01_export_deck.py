#!/usr/bin/env python3
"""
Agent 1: Comprehensive export of the "German Vocabulary" Anki deck.

Outputs:
  deck_export.json     - Full note+scheduling data as a JSON array
  german_vocabulary.apkg - Full .apkg archive (with scheduling)
  apkg_crosscheck.json - Cross-check note/media counts from the .apkg SQLite DB
  report.md            - Human-readable summary report
"""

import json
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANKI_CONNECT_URL = "http://localhost:8765"
DECK_NAME = "German Vocabulary"

SCRIPT_DIR = Path(__file__).parent
EXPORT_FILE = SCRIPT_DIR / "deck_export.json"
APKG_FILE = SCRIPT_DIR / "german_vocabulary.apkg"
CROSSCHECK_FILE = SCRIPT_DIR / "apkg_crosscheck.json"
REPORT_FILE = SCRIPT_DIR / "report.md"

# Fields to include in the JSON export (all the meaningful content fields)
FIELDS_OF_INTEREST = [
    "Word",
    "WordTranslation",
    "WordTranslationDisambiguate",
    "Sentence",
    "SentenceTranslation",
    "IPA",
    "Level",
    "Note/Mnemonic",
    "WordSecondTranslation",
    "Word-Symbol",
]

# Chunk size when calling cardsInfo (keeps HTTP payloads reasonable)
CARDS_CHUNK_SIZE = 500

# ---------------------------------------------------------------------------
# AnkiConnect helpers
# ---------------------------------------------------------------------------


def anki_request(action: str, **params) -> object:
    """Send a single request to AnkiConnect and return the result value."""
    payload = {"action": action, "version": 6, "params": params}
    response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(
            f"AnkiConnect error for action '{action}': {data['error']}"
        )
    return data["result"]


def get_field_value(fields_dict: dict, field_name: str) -> str:
    """Extract the plain-text value from a field dict returned by notesInfo."""
    field = fields_dict.get(field_name)
    if field is None:
        return ""
    # notesInfo returns {"value": "...", "order": N}
    if isinstance(field, dict):
        return field.get("value", "")
    return str(field)


# ---------------------------------------------------------------------------
# Approach A – AnkiConnect structured export
# ---------------------------------------------------------------------------


def approach_a_export() -> list[dict]:
    """
    Pull all notes and cards via AnkiConnect, join them, and return a list of
    export records (one per note, using the best / most mature card for
    scheduling data).
    """

    # Step 1: note IDs
    print(f'[A] Finding notes in deck "{DECK_NAME}" ...')
    note_ids: list[int] = anki_request(
        "findNotes", query=f'deck:"{DECK_NAME}"'
    )
    print(f"    {len(note_ids):,} notes found.")

    if not note_ids:
        print("    No notes found – aborting.")
        sys.exit(1)

    # Step 2: note info (fields + tags)
    print("[A] Fetching note info (fields + tags) ...")
    notes_info: list[dict] = anki_request("notesInfo", notes=note_ids)
    print(f"    Received info for {len(notes_info):,} notes.")

    # Step 3: card IDs
    print("[A] Finding card IDs ...")
    card_ids: list[int] = anki_request(
        "findCards", query=f'deck:"{DECK_NAME}"'
    )
    print(f"    {len(card_ids):,} cards found.")

    # Step 4: card scheduling info (chunked to avoid oversized requests)
    print("[A] Fetching card scheduling info ...")
    all_cards: list[dict] = []
    for i in range(0, len(card_ids), CARDS_CHUNK_SIZE):
        chunk = card_ids[i : i + CARDS_CHUNK_SIZE]
        all_cards.extend(anki_request("cardsInfo", cards=chunk))
        print(
            f"    ... {min(i + CARDS_CHUNK_SIZE, len(card_ids)):,} / {len(card_ids):,} cards",
            end="\r",
        )
    print(f"\n    Received scheduling info for {len(all_cards):,} cards.")

    # Step 5: map note_id -> list of cards
    note_to_cards: dict[int, list[dict]] = {}
    for card in all_cards:
        nid = card.get("note")
        if nid is not None:
            note_to_cards.setdefault(nid, []).append(card)

    # Step 6: assemble one export record per note
    print("[A] Assembling export records ...")
    export_records: list[dict] = []

    for note in notes_info:
        note_id = note["noteId"]
        fields_raw = note.get("fields", {})

        fields = {f: get_field_value(fields_raw, f) for f in FIELDS_OF_INTEREST}

        # Pick the card with the highest interval as the "best" card
        cards_for_note = note_to_cards.get(note_id, [])

        best_card: dict | None = None
        for card in cards_for_note:
            if best_card is None or card.get("interval", 0) > best_card.get(
                "interval", 0
            ):
                best_card = card

        if best_card:
            scheduling = {
                "best_interval_days": best_card.get("interval", 0),
                "reps": best_card.get("reps", 0),
                "ease_factor": best_card.get("factor", 0),
                "lapses": best_card.get("lapses", 0),
                "card_type": best_card.get("type", 0),
                "queue": best_card.get("queue", 0),
            }
        else:
            scheduling = {
                "best_interval_days": 0,
                "reps": 0,
                "ease_factor": 0,
                "lapses": 0,
                "card_type": 0,
                "queue": 0,
            }

        export_records.append(
            {
                "noteId": note_id,
                "tags": note.get("tags", []),
                "fields": fields,
                "scheduling": scheduling,
            }
        )

    # Step 7: write JSON
    print(f"[A] Writing {len(export_records):,} records to {EXPORT_FILE} ...")
    with open(EXPORT_FILE, "w", encoding="utf-8") as fh:
        json.dump(export_records, fh, ensure_ascii=False, indent=2)
    size_mb = EXPORT_FILE.stat().st_size / 1024 / 1024
    print(f"    Done ({size_mb:.2f} MB).")

    return export_records


# ---------------------------------------------------------------------------
# Approach B – .apkg export + cross-check
# ---------------------------------------------------------------------------


def approach_b_apkg() -> dict:
    """
    Export the full deck as a .apkg file via AnkiConnect's exportPackage
    action, then open the archive and query the embedded SQLite DB for a
    cross-check of note count and media file count.
    """

    # Export the package
    print(f"[B] Exporting .apkg to {APKG_FILE} ...")
    anki_request(
        "exportPackage",
        deck=DECK_NAME,
        path=str(APKG_FILE),
        includeSched=True,
    )
    size_mb = APKG_FILE.stat().st_size / 1024 / 1024
    print(f"    Export complete ({size_mb:.1f} MB).")

    # Open the apkg (it is a zip file) and cross-check via SQLite
    print("[B] Cross-checking note count and media files in .apkg ...")
    note_count = 0
    media_files_count = 0

    with zipfile.ZipFile(APKG_FILE, "r") as zf:
        names = zf.namelist()

        # Count media files (everything except collection.anki2 and media
        # manifest files)
        non_db_files = [
            n
            for n in names
            if n not in ("collection.anki2", "collection.anki21", "media")
            and not n.endswith(".anki2")
        ]
        # The "media" entry is a JSON mapping; actual media have numeric names
        media_files_count = len(non_db_files)

        # Extract collection.anki2 to a temporary file and query it
        db_name = (
            "collection.anki21" if "collection.anki21" in names else "collection.anki2"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "collection.db"
            with zf.open(db_name) as src, open(db_path, "wb") as dst:
                # Stream copy to avoid loading the whole DB into memory
                while True:
                    chunk = src.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    dst.write(chunk)

            con = sqlite3.connect(db_path)
            try:
                # notes table exists in both anki2 and anki21 formats
                (note_count,) = con.execute("SELECT COUNT(*) FROM notes").fetchone()

                # Also count media from the media manifest if present
                if "media" in names:
                    media_json_bytes = zf.read("media")
                    media_manifest = json.loads(media_json_bytes.decode("utf-8"))
                    # manifest maps numeric string keys -> filename
                    media_files_count = len(media_manifest)

            finally:
                con.close()

    crosscheck = {"note_count": note_count, "media_files_count": media_files_count}
    print(
        f"    Cross-check: {note_count:,} notes, {media_files_count:,} media files."
    )

    print(f"[B] Writing cross-check to {CROSSCHECK_FILE} ...")
    with open(CROSSCHECK_FILE, "w", encoding="utf-8") as fh:
        json.dump(crosscheck, fh, indent=2)

    return crosscheck


# ---------------------------------------------------------------------------
# Approach C – Summary report
# ---------------------------------------------------------------------------


def approach_c_report(records: list[dict], crosscheck: dict) -> None:
    """Generate a human-readable Markdown report from the export records."""

    print(f"[C] Generating report ...")
    total = len(records)
    if total == 0:
        print("    No records – skipping report.")
        return

    # --- Field fill rates ---
    def filled(field: str) -> int:
        return sum(1 for r in records if r["fields"].get(field, "").strip())

    sentence_filled = filled("Sentence")
    ipa_filled = filled("IPA")
    level_filled = filled("Level")
    mnemonic_filled = filled("Note/Mnemonic")

    # --- Level distribution ---
    level_counter: Counter = Counter()
    for r in records:
        level = r["fields"].get("Level", "").strip() or "(empty)"
        level_counter[level] += 1

    # --- Tags ---
    tag_counter: Counter = Counter()
    for r in records:
        tag_counter.update(r["tags"])
    top_20_tags = tag_counter.most_common(20)
    unique_tag_count = len(tag_counter)

    # --- Scheduling buckets ---
    mature = sum(1 for r in records if r["scheduling"]["best_interval_days"] > 21)
    medium = sum(
        1 for r in records if 7 <= r["scheduling"]["best_interval_days"] <= 21
    )
    young = sum(
        1 for r in records if 1 <= r["scheduling"]["best_interval_days"] <= 6
    )
    new_cards = sum(
        1 for r in records if r["scheduling"]["best_interval_days"] == 0
    )

    # --- Ease factor distribution ---
    ease_struggling = sum(
        1
        for r in records
        if 0 < r["scheduling"]["ease_factor"] < 2000
    )
    ease_mid = sum(
        1
        for r in records
        if 2000 <= r["scheduling"]["ease_factor"] < 2500
    )
    ease_strong = sum(
        1 for r in records if r["scheduling"]["ease_factor"] >= 2500
    )
    ease_unseen = sum(
        1 for r in records if r["scheduling"]["ease_factor"] == 0
    )

    # --- Sample of 10 notes spread evenly across the list ---
    sample_count = 10
    step = max(1, total // sample_count)
    sample_indices = [i * step for i in range(sample_count) if i * step < total]
    # If deck has fewer than 10 notes, just take them all
    if total <= sample_count:
        sample_indices = list(range(total))
    sample_notes = [records[i] for i in sample_indices]

    # -----------------------------------------------------------------------
    # Build the Markdown
    # -----------------------------------------------------------------------

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%"

    lines: list[str] = []

    lines += [
        "# German Vocabulary Deck — Export Report",
        "",
        "**Export date:** 2026-02-25",
        f"**Deck:** {DECK_NAME}",
        f"**AnkiConnect notes:** {total:,}",
        f"**apkg cross-check notes:** {crosscheck.get('note_count', 'N/A'):,}",
        f"**apkg media files:** {crosscheck.get('media_files_count', 'N/A'):,}",
        "",
    ]

    # Overview table
    lines += [
        "## Overview",
        "",
        "| Metric | Count | % of total |",
        "|--------|------:|----------:|",
        f"| Total notes | {total:,} | 100% |",
        f"| Notes with `Sentence` filled | {sentence_filled:,} | {pct(sentence_filled)} |",
        f"| Notes with `Sentence` empty | {total - sentence_filled:,} | {pct(total - sentence_filled)} |",
        f"| Notes with `IPA` filled | {ipa_filled:,} | {pct(ipa_filled)} |",
        f"| Notes with `IPA` empty | {total - ipa_filled:,} | {pct(total - ipa_filled)} |",
        f"| Notes with `Level` filled | {level_filled:,} | {pct(level_filled)} |",
        f"| Notes with `Note/Mnemonic` filled | {mnemonic_filled:,} | {pct(mnemonic_filled)} |",
        "",
    ]

    # Level distribution
    lines += [
        "## Level Distribution",
        "",
        "| Level | Count | % of total |",
        "|-------|------:|----------:|",
    ]
    for level, count in sorted(level_counter.items()):
        lines.append(f"| {level} | {count:,} | {pct(count)} |")
    lines.append("")

    # Tags
    lines += [
        "## Tags",
        "",
        f"**Total unique tags:** {unique_tag_count:,}",
        "",
        "### Top 20 Most Common Tags",
        "",
    ]
    if top_20_tags:
        lines += [
            "| Tag | Count |",
            "|-----|------:|",
        ]
        for tag, count in top_20_tags:
            lines.append(f"| `{tag}` | {count:,} |")
    else:
        lines.append("_No tags found._")
    lines.append("")

    # Scheduling summary
    lines += [
        "## Scheduling Summary",
        "",
        "Interval buckets are based on the **best card interval** per note",
        "(the card with the longest interval, i.e. the most mature card).",
        "",
        "| Bucket | Count | % of total |",
        "|--------|------:|----------:|",
        f"| Mature (interval > 21 days) | {mature:,} | {pct(mature)} |",
        f"| Medium (7–21 days) | {medium:,} | {pct(medium)} |",
        f"| Young (1–6 days) | {young:,} | {pct(young)} |",
        f"| New / unseen (0 days) | {new_cards:,} | {pct(new_cards)} |",
        "",
    ]

    # Ease factor distribution
    lines += [
        "## Ease Factor Distribution",
        "",
        "| Bucket | Count | % of total |",
        "|--------|------:|----------:|",
        f"| Strong (ease ≥ 2500) | {ease_strong:,} | {pct(ease_strong)} |",
        f"| Average (2000–2499) | {ease_mid:,} | {pct(ease_mid)} |",
        f"| Struggling (ease < 2000, > 0) | {ease_struggling:,} | {pct(ease_struggling)} |",
        f"| Unseen (ease = 0) | {ease_unseen:,} | {pct(ease_unseen)} |",
        "",
    ]

    # Sample notes
    lines += [
        f"## Sample Notes ({len(sample_notes)})",
        "",
        "A representative sample spread evenly across the deck.",
        "",
    ]
    for i, note in enumerate(sample_notes, 1):
        sched = note["scheduling"]
        lines += [
            f"### Sample {i} — Note ID `{note['noteId']}`",
            "",
            f"**Tags:** {', '.join(f'`{t}`' for t in note['tags']) if note['tags'] else '_(none)_'}",
            "",
            "| Field | Value |",
            "|-------|-------|",
        ]
        for field_name, value in note["fields"].items():
            display = value.replace("|", "\\|").replace("\n", " ").strip()
            if len(display) > 120:
                display = display[:117] + "..."
            lines.append(f"| {field_name} | {display} |")
        lines += [
            f"| _(best interval days)_ | {sched['best_interval_days']} |",
            f"| _(reps)_ | {sched['reps']} |",
            f"| _(ease factor)_ | {sched['ease_factor']} |",
            f"| _(lapses)_ | {sched['lapses']} |",
            f"| _(card type)_ | {sched['card_type']} |",
            f"| _(queue)_ | {sched['queue']} |",
            "",
        ]

    report_text = "\n".join(lines) + "\n"
    with open(REPORT_FILE, "w", encoding="utf-8") as fh:
        fh.write(report_text)

    size_kb = REPORT_FILE.stat().st_size / 1024
    print(f"    Report written to {REPORT_FILE} ({size_kb:.1f} KB).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("Agent 1 — German Vocabulary Deck Export")
    print("=" * 60)

    # Approach A: AnkiConnect structured JSON export
    export_records = approach_a_export()

    # Approach B: .apkg export + cross-check
    crosscheck = approach_b_apkg()

    # Approach C: summary report
    approach_c_report(export_records, crosscheck)

    print()
    print("=" * 60)
    print("All done. Output files:")
    for f in (EXPORT_FILE, APKG_FILE, CROSSCHECK_FILE, REPORT_FILE):
        if f.exists():
            size = f.stat().st_size
            unit = "MB" if size > 1024 * 1024 else "KB"
            size_display = size / (1024 * 1024 if unit == "MB" else 1024)
            print(f"  {f}  ({size_display:.1f} {unit})")
    print("=" * 60)


if __name__ == "__main__":
    main()
