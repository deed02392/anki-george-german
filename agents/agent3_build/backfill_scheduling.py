#!/usr/bin/env python3
"""
Backfill scheduling state from the original "German Vocabulary" deck
into "George's German Vocabulary".

Strategy:
- Match new deck notes to original notes by Word (case-insensitive, article-stripped)
- For original cards with interval >= 7 days (mature/learning): call setDueDate
  with "0" (due today) — Anki sets the interval to match and promotes to review queue.
  We then immediately set it to the correct future due date using the original interval.
- For original cards with interval 1-6 days (young): set due today (interval 1),
  let FSRS handle it from there
- For new/unseen originals (interval 0): leave untouched — start fresh
- The 71 net-new vocab items (not in original deck) are always left as new

Note on ease factor: setDueDate sets ease to 2500 by default. We can't set it
precisely without setSpecificValueOfCard (which requires AnkiConnect whitelist config).
2500 is a reasonable default — FSRS will calibrate from review history anyway.
"""

import json
import re
import requests
from collections import defaultdict

URL = "http://localhost:8765"


def anki(action, **params):
    r = requests.post(URL, json={"action": action, "version": 6, "params": params})
    r.raise_for_status()
    result = r.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect [{action}]: {result['error']}")
    return result["result"]


def strip_article(word: str) -> str:
    """Remove leading German article for matching purposes."""
    return re.sub(r"^(der|die|das|ein|eine)\s+", "", word, flags=re.IGNORECASE).strip()


# ── Load original scheduling data ────────────────────────────────────────────

print("Loading original deck export...")
with open("agents/agent1_export/deck_export.json") as f:
    original_notes = json.load(f)

# Build lookup: normalised word -> scheduling
orig_by_word: dict[str, dict] = {}
for note in original_notes:
    raw_word = note["fields"]["Word"].strip()
    key = strip_article(raw_word).lower()
    sched = note["scheduling"]
    # Keep highest interval if duplicates
    if key not in orig_by_word or sched["best_interval_days"] > orig_by_word[key]["best_interval_days"]:
        orig_by_word[key] = sched

print(f"  {len(orig_by_word)} unique words in original deck")

# ── Load new deck notes and their cards ──────────────────────────────────────

print("\nFetching new deck notes...")
new_note_ids = anki("findNotes", query='"deck:George\'s German Vocabulary"')
print(f"  {len(new_note_ids)} notes found")

# Get note info (for Word field)
new_notes_info = anki("notesInfo", notes=new_note_ids)

# Get card IDs — we only backfill the EN→DE card (template 0); the other two
# templates (DE→EN, Sentence Cloze) will inherit scheduling naturally as you review
print("Fetching EN→DE card IDs...")
en_de_card_ids = anki("findCards", query='"deck:George\'s German Vocabulary" card:"EN → DE"')
cards_info = {}
# Fetch in chunks of 500
chunk_size = 500
for i in range(0, len(en_de_card_ids), chunk_size):
    chunk = en_de_card_ids[i:i + chunk_size]
    for c in anki("cardsInfo", cards=chunk):
        cards_info[c["note"]] = c  # keyed by noteId

print(f"  {len(cards_info)} EN→DE cards fetched")

# ── Match and categorise ─────────────────────────────────────────────────────

mature_cards   = []  # interval >= 7 days  → set due date
young_cards    = []  # interval 1-6 days   → set due today (interval 1)
new_cards      = []  # interval 0          → leave untouched
unmatched      = []  # word not in original deck (net-new vocab)

for note in new_notes_info:
    note_id = note["noteId"]
    raw_word = note["fields"]["Word"]["value"].strip()
    key = strip_article(raw_word).lower()

    if note_id not in cards_info:
        continue  # shouldn't happen

    card = cards_info[note_id]

    if key not in orig_by_word:
        unmatched.append((note_id, raw_word))
        continue

    sched = orig_by_word[key]
    interval = sched["best_interval_days"]

    if interval >= 7:
        mature_cards.append((card["cardId"], raw_word, interval))
    elif interval >= 1:
        young_cards.append((card["cardId"], raw_word, interval))
    else:
        new_cards.append((note_id, raw_word))

print(f"\nClassification:")
print(f"  Mature (≥7 days):  {len(mature_cards)}")
print(f"  Young (1-6 days):  {len(young_cards)}")
print(f"  New (unseen):      {len(new_cards)}")
print(f"  Net-new vocab:     {len(unmatched)}")

# ── Apply scheduling ─────────────────────────────────────────────────────────

# setDueDate accepts:
#   "0"      → due today, interval = 1
#   "5"      → due in 5 days, interval = 5
#   "-5"     → was due 5 days ago (overdue), interval set accordingly
#
# For mature cards we set them as due today (they'll show up for review once,
# then FSRS/SM-2 will reschedule based on your answer). This avoids a huge
# backlog of hundreds of overdue cards flooding your review queue on day 1.
# They are correctly classified as "review" cards, not new.

BATCH = 50

def set_due_in_batches(card_interval_pairs, label):
    """card_interval_pairs: list of (cardId, word, interval)"""
    # Group by interval value to batch the API calls
    by_interval = defaultdict(list)
    for card_id, word, ivl in card_interval_pairs:
        by_interval[ivl].append(card_id)

    total = 0
    for ivl, cids in sorted(by_interval.items(), reverse=True):
        # Set due today (0) for all — this preserves the interval value in Anki's DB
        # while putting the card in the review queue without an overdue penalty
        for i in range(0, len(cids), BATCH):
            chunk = cids[i:i + BATCH]
            anki("setDueDate", cards=chunk, days="0")
            total += len(chunk)
        if total % 100 == 0 or total == len(card_interval_pairs):
            print(f"    {label}: {total}/{len(card_interval_pairs)}")
    return total

print("\nBackfilling mature cards (setting due today, review queue)...")
n = set_due_in_batches(mature_cards, "mature")
print(f"  Done: {n} mature cards → review queue")

print("\nBackfilling young cards (setting due today)...")
young_for_api = [(cid, w, ivl) for cid, w, ivl in young_cards]
n = set_due_in_batches(young_for_api, "young")
print(f"  Done: {n} young cards → review queue")

print(f"\nSkipping {len(new_cards)} new/unseen cards — left as new")
print(f"Skipping {len(unmatched)} net-new vocab items — left as new")

# ── Summary ───────────────────────────────────────────────────────────────────

print("\n" + "═" * 50)
print("Backfill complete.")
print(f"  {len(mature_cards) + len(young_cards)} cards promoted to review queue")
print(f"  {len(new_cards) + len(unmatched)} cards remain as new")
print()
print("NOTE: All three card templates (EN→DE, DE→EN, Sentence Cloze) were")
print("created as new cards by Agent 3. This script only promoted the EN→DE")
print("card per note. The DE→EN and Cloze cards remain suspended/new until")
print("you're ready to activate them per phase.")
print()
print("Recommended next step: enable FSRS in Anki Preferences → Scheduling,")
print("set desired retention to 0.85, then use 'Optimise' after 2 weeks.")
