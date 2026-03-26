#!/usr/bin/env python3
"""
Weekly script: identify cards in "George's German Vocabulary" that are ready
to have their DE→EN, Sentence Cloze, Listening, or Grammar templates unsuspended.

Thresholds:
  DE→EN unsuspend:      EN→DE card interval >= 14 days
  Cloze unsuspend:      EN→DE interval >= 21 days AND DE→EN interval >= 21 days
  Listening unsuspend:  DE→EN interval >= 21 days
  Grammar unsuspend:    >=3 vocab cards reference the grammar term in ClozeHint

Usage:
  uv run unsuspend_candidates.py                # dry run — print candidates only
  uv run unsuspend_candidates.py --apply        # unsuspend the candidates in Anki
  uv run unsuspend_candidates.py --apply --max 10  # unsuspend at most 10 per type
"""

import argparse
import json

from . import DATA_DIR
from ._anki import anki, DECK, MODEL

EN_DE_MIN_INTERVAL  = 14   # days — gate for unsuspending DE→EN
DE_EN_MIN_INTERVAL  = 21   # days — gate for unsuspending Cloze (alongside EN→DE)
LISTEN_MIN_INTERVAL = 21   # days — gate for unsuspending Listening (DE→EN must be mature)
GRAMMAR_HINT_THRESHOLD = 3  # distinct vocab notes referencing the grammar term in ClozeHint

GRAMMAR_MODEL = "German Grammar Term"


def fetch_cards(ids):
    """Return dict of cardId -> card info, fetched in chunks."""
    out = {}
    for i in range(0, len(ids), 500):
        for c in anki("cardsInfo", cards=ids[i:i+500]):
            out[c["cardId"]] = c
    return out


def by_note(cards):
    return {c["note"]: c for c in cards.values()}


def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    DRY_RUN = not args.apply
    MAX_PER_TYPE = args.max

    # ── Fetch all three card templates for the deck ──────────────────────────

    print("Fetching card data from Anki...")

    en_de_ids  = anki("findCards", query='deck:"George\'s German Vocabulary" card:"EN → DE"')
    de_en_ids  = anki("findCards", query='deck:"George\'s German Vocabulary" card:"DE → EN"')
    cloze_ids  = anki("findCards", query='deck:"George\'s German Vocabulary" card:"Sentence Cloze"')
    listen_ids = anki("findCards", query='deck:"George\'s German Vocabulary" card:"Listening"')

    en_de_cards  = fetch_cards(en_de_ids)
    de_en_cards  = fetch_cards(de_en_ids)
    cloze_cards  = fetch_cards(cloze_ids)
    listen_cards = fetch_cards(listen_ids)

    print(f"  EN→DE:     {len(en_de_cards)} cards")
    print(f"  DE→EN:     {len(de_en_cards)} cards")
    print(f"  Cloze:     {len(cloze_cards)} cards")
    print(f"  Listening: {len(listen_cards)} cards")

    # ── Index by note ID ─────────────────────────────────────────────────────

    en_de_by_note  = by_note(en_de_cards)
    de_en_by_note  = by_note(de_en_cards)
    cloze_by_note  = by_note(cloze_cards)
    listen_by_note = by_note(listen_cards)

    # ── Evaluate candidates ──────────────────────────────────────────────────

    de_en_candidates  = []   # (cardId, word, en_de_interval)
    cloze_candidates  = []   # (cardId, word, en_de_interval, de_en_interval)
    listen_candidates = []   # (cardId, word, de_en_interval)

    for note_id, en_de in en_de_by_note.items():
        word      = en_de["fields"]["Word"]["value"]
        en_de_ivl = en_de["interval"]

        # ── DE→EN candidate ──────────────────────────────────────────────────
        de_en = de_en_by_note.get(note_id)
        if de_en and de_en["queue"] == -1:   # -1 = suspended
            if en_de_ivl >= EN_DE_MIN_INTERVAL:
                de_en_candidates.append((de_en["cardId"], word, en_de_ivl))

        # ── Cloze candidate ──────────────────────────────────────────────────
        cloze = cloze_by_note.get(note_id)
        if cloze and cloze["queue"] == -1:   # suspended
            de_en_ivl = de_en["interval"] if de_en else 0
            if en_de_ivl >= DE_EN_MIN_INTERVAL and de_en_ivl >= DE_EN_MIN_INTERVAL:
                cloze_candidates.append((cloze["cardId"], word, en_de_ivl, de_en_ivl))

        # ── Listening candidate ──────────────────────────────────────────────
        listen = listen_by_note.get(note_id)
        if listen and listen["queue"] == -1:   # suspended
            de_en_ivl = de_en["interval"] if de_en else 0
            if de_en_ivl >= LISTEN_MIN_INTERVAL:
                listen_candidates.append((listen["cardId"], word, de_en_ivl))

    # ── Grammar candidates ─────────────────────────────────────────────────

    grammar_candidates = []   # (cardId, term, hint_count)

    # Load grammar terms from JSON to know which terms exist
    grammar_terms_path = DATA_DIR / "grammar_terms.json"
    with open(grammar_terms_path) as f:
        grammar_terms = {entry["term"] for entry in json.load(f)}

    # Find suspended grammar cards
    grammar_card_ids = anki("findCards",
        query=f'"note:{GRAMMAR_MODEL}" is:suspended')
    if grammar_card_ids:
        grammar_cards_info = fetch_cards(grammar_card_ids)

        # Collect ClozeHint values from all vocab notes
        vocab_note_ids = anki("findNotes", query=f'"note:{MODEL}" "deck:{DECK}"')
        vocab_notes = anki("notesInfo", notes=vocab_note_ids) if vocab_note_ids else []

        # Build: term -> set of note IDs that reference it
        # Use case-insensitive matching (terms like "maskulin" appear
        # capitalised in ClozeHint: "Akkusativ · Maskulin")
        term_lower_map = {t.lower(): t for t in grammar_terms}
        term_note_counts = {t: set() for t in grammar_terms}
        for note in vocab_notes:
            hint = note["fields"].get("ClozeHint", {}).get("value", "")
            if not hint:
                continue
            # Split on | (sentence variants), then · (components), strip whitespace
            for variant in hint.split("|"):
                for part in variant.split("·"):
                    key = part.strip().lower()
                    if key in term_lower_map:
                        term_note_counts[term_lower_map[key]].add(note["noteId"])

        # Track which terms already qualify (so both templates get unsuspended)
        qualifying_terms = {
            term for term, notes in term_note_counts.items()
            if len(notes) >= GRAMMAR_HINT_THRESHOLD
        }

        # Collect suspended grammar cards whose term qualifies
        for card in grammar_cards_info.values():
            term = card["fields"]["Term"]["value"]
            if term in qualifying_terms:
                grammar_candidates.append(
                    (card["cardId"], term, len(term_note_counts[term])))

        # Sort by hint count descending, then by term name
        grammar_candidates.sort(key=lambda x: (-x[2], x[1]))

    # ── Report ───────────────────────────────────────────────────────────────

    print()
    if DRY_RUN:
        print("DRY RUN — pass --apply to unsuspend these cards in Anki")
    else:
        print("APPLYING — unsuspending candidates now")
    print()

    print(f"── DE→EN candidates ({len(de_en_candidates)}) ─────────────────────────")
    print(f"   Threshold: EN→DE interval ≥ {EN_DE_MIN_INTERVAL}d")
    print()
    if de_en_candidates:
        de_en_candidates.sort(key=lambda x: -x[2])
        for card_id, word, ivl in de_en_candidates:
            print(f"  {word:<30}  EN→DE interval: {ivl:>4}d")
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

    print()
    print(f"── Listening candidates ({len(listen_candidates)}) ─────────────────────────")
    print(f"   Threshold: DE→EN interval ≥ {LISTEN_MIN_INTERVAL}d")
    print()
    if listen_candidates:
        listen_candidates.sort(key=lambda x: -x[2])
        for card_id, word, de_ivl in listen_candidates:
            print(f"  {word:<30}  DE→EN: {de_ivl:>4}d")
    else:
        print("  None ready yet.")

    # Deduplicate grammar candidates for display (group both templates per term)
    grammar_display = {}
    for card_id, term, count in grammar_candidates:
        if term not in grammar_display:
            grammar_display[term] = count
    grammar_display_list = sorted(grammar_display.items(), key=lambda x: (-x[1], x[0]))

    print()
    print(f"── Grammar candidates ({len(grammar_display_list)}) ─────────────────────────")
    print(f"   Threshold: ≥{GRAMMAR_HINT_THRESHOLD} vocab cards with matching ClozeHint")
    print()
    if grammar_display_list:
        for term, count in grammar_display_list:
            print(f"  {term:<30} {count:>3} vocab hints")
    else:
        print("  None ready yet.")

    # ── Apply ────────────────────────────────────────────────────────────────

    # Apply --max cap (sorted by longest interval first, so strongest cards win)
    if MAX_PER_TYPE:
        de_en_candidates = de_en_candidates[:MAX_PER_TYPE]
        cloze_candidates = cloze_candidates[:MAX_PER_TYPE]
        listen_candidates = listen_candidates[:MAX_PER_TYPE]
        # For grammar, cap by distinct terms (each term has up to 2 cards)
        capped_terms = set()
        capped_grammar = []
        for card_id, term, count in grammar_candidates:
            if term not in capped_terms:
                if len(capped_terms) >= MAX_PER_TYPE:
                    break
                capped_terms.add(term)
            capped_grammar.append((card_id, term, count))
        grammar_candidates = capped_grammar

    if not DRY_RUN:
        all_to_unsuspend = (
            [c[0] for c in de_en_candidates] +
            [c[0] for c in cloze_candidates] +
            [c[0] for c in listen_candidates] +
            [c[0] for c in grammar_candidates]
        )
        if all_to_unsuspend:
            anki("unsuspend", cards=all_to_unsuspend)
            print()
            n_grammar_terms = len({t for _, t, _ in grammar_candidates})
            print(f"Unsuspended {len(de_en_candidates)} DE→EN, "
                  f"{len(cloze_candidates)} Cloze, "
                  f"{len(listen_candidates)} Listening, "
                  f"and {len(grammar_candidates)} Grammar card(s) "
                  f"({n_grammar_terms} terms).")
        else:
            print()
            print("Nothing to unsuspend.")
    else:
        print()
        total = (len(de_en_candidates) + len(cloze_candidates)
                 + len(listen_candidates) + len(grammar_candidates))
        if total:
            cap_note = f" (capped to {MAX_PER_TYPE} per type)" if MAX_PER_TYPE else ""
            print(f"{total} card(s) would be unsuspended{cap_note}. Re-run with --apply to action.")
        else:
            print("Nothing to unsuspend yet — keep reviewing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Actually unsuspend (default is dry run)")
    parser.add_argument("--max", type=int, default=None,
                        help="Max cards to unsuspend per type (DE→EN / Cloze)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
