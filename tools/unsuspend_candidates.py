#!/usr/bin/env python3
"""
Weekly script: identify cards in "George's German Vocabulary" that are ready
to have their DE→EN or Sentence Cloze templates unsuspended.

Thresholds:
  DE→EN unsuspend:    EN→DE card interval >= 14 days AND ease >= 2200
  Cloze unsuspend:    EN→DE interval >= 21 days AND DE→EN interval >= 21 days

Usage:
  uv run unsuspend_candidates.py           # dry run — print candidates only
  uv run unsuspend_candidates.py --apply   # unsuspend the candidates in Anki
"""

import os
import sys

# Ensure tools/ is on sys.path so sibling imports work regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki

DRY_RUN = "--apply" not in sys.argv

EN_DE_MIN_INTERVAL  = 14   # days — gate for unsuspending DE→EN
DE_EN_MIN_INTERVAL  = 21   # days — gate for unsuspending Cloze (alongside EN→DE)
MIN_EASE            = 2200 # ease factor gate for DE→EN unsuspend


# ── Fetch all three card templates for the deck ───────────────────────────────

print("Fetching card data from Anki...")

en_de_ids  = anki("findCards", query='deck:"George\'s German Vocabulary" card:"EN → DE"')
de_en_ids  = anki("findCards", query='deck:"George\'s German Vocabulary" card:"DE → EN"')
cloze_ids  = anki("findCards", query='deck:"George\'s German Vocabulary" card:"Sentence Cloze"')

def fetch_cards(ids):
    """Return dict of cardId -> card info, fetched in chunks."""
    out = {}
    for i in range(0, len(ids), 500):
        for c in anki("cardsInfo", cards=ids[i:i+500]):
            out[c["cardId"]] = c
    return out

en_de_cards  = fetch_cards(en_de_ids)
de_en_cards  = fetch_cards(de_en_ids)
cloze_cards  = fetch_cards(cloze_ids)

print(f"  EN→DE:  {len(en_de_cards)} cards")
print(f"  DE→EN:  {len(de_en_cards)} cards")
print(f"  Cloze:  {len(cloze_cards)} cards")

# ── Index by note ID ──────────────────────────────────────────────────────────

def by_note(cards):
    return {c["note"]: c for c in cards.values()}

en_de_by_note  = by_note(en_de_cards)
de_en_by_note  = by_note(de_en_cards)
cloze_by_note  = by_note(cloze_cards)

# ── Evaluate candidates ───────────────────────────────────────────────────────

de_en_candidates  = []   # (cardId, word, en_de_interval, ease)
cloze_candidates  = []   # (cardId, word, en_de_interval, de_en_interval)

for note_id, en_de in en_de_by_note.items():
    word      = en_de["fields"]["Word"]["value"]
    en_de_ivl = en_de["interval"]
    en_de_ease = en_de["factor"]

    # ── DE→EN candidate ──────────────────────────────────────────────────────
    de_en = de_en_by_note.get(note_id)
    if de_en and de_en["queue"] == -1:   # -1 = suspended
        if en_de_ivl >= EN_DE_MIN_INTERVAL and en_de_ease >= MIN_EASE:
            de_en_candidates.append((de_en["cardId"], word, en_de_ivl, en_de_ease))

    # ── Cloze candidate ───────────────────────────────────────────────────────
    cloze = cloze_by_note.get(note_id)
    if cloze and cloze["queue"] == -1:   # suspended
        de_en_ivl = de_en["interval"] if de_en else 0
        if en_de_ivl >= DE_EN_MIN_INTERVAL and de_en_ivl >= DE_EN_MIN_INTERVAL:
            cloze_candidates.append((cloze["cardId"], word, en_de_ivl, de_en_ivl))

# ── Report ────────────────────────────────────────────────────────────────────

print()
if DRY_RUN:
    print("DRY RUN — pass --apply to unsuspend these cards in Anki")
else:
    print("APPLYING — unsuspending candidates now")
print()

print(f"── DE→EN candidates ({len(de_en_candidates)}) ─────────────────────────")
print(f"   Threshold: EN→DE interval ≥ {EN_DE_MIN_INTERVAL}d, ease ≥ {MIN_EASE}")
print()
if de_en_candidates:
    de_en_candidates.sort(key=lambda x: -x[2])
    for card_id, word, ivl, ease in de_en_candidates:
        print(f"  {word:<30}  EN→DE interval: {ivl:>4}d   ease: {ease}")
else:
    print("  None ready yet.")

print()
print(f"── Sentence Cloze candidates ({len(cloze_candidates)}) ──────────────────")
print(f"   Threshold: both EN→DE and DE→EN interval ≥ {DE_EN_MIN_INTERVAL}d")
print()
if cloze_candidates:
    cloze_candidates.sort(key=lambda x: -x[2])
    for card_id, word, en_ivl, de_ivl in cloze_candidates:
        print(f"  {word:<30}  EN→DE: {en_ivl:>4}d   DE→EN: {de_ivl:>4}d")
else:
    print("  None ready yet.")

# ── Apply ─────────────────────────────────────────────────────────────────────

if not DRY_RUN:
    all_to_unsuspend = (
        [c[0] for c in de_en_candidates] +
        [c[0] for c in cloze_candidates]
    )
    if all_to_unsuspend:
        anki("unsuspendCards", cards=all_to_unsuspend)
        print()
        print(f"Unsuspended {len(de_en_candidates)} DE→EN card(s) "
              f"and {len(cloze_candidates)} Cloze card(s).")
    else:
        print()
        print("Nothing to unsuspend.")
else:
    print()
    total = len(de_en_candidates) + len(cloze_candidates)
    if total:
        print(f"{total} card(s) would be unsuspended. Re-run with --apply to action.")
    else:
        print("Nothing to unsuspend yet — keep reviewing.")
