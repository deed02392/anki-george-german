#!/usr/bin/env python3
"""Backfill ClozeHint on existing vocab cards via LLM.

Finds cards with Sentence and ClozeWord but no ClozeHint, sends them
to the LLM in batches for grammatical annotation, and writes the
pipe-delimited hints back.

Usage:
    anki-german enrich hints [--dry-run] [--batch-size 10]
"""

import json
import sys

from ._anki import anki, DECK, MODEL
from ._llm import get_floodgate_token, call_llm_with_retry

BATCH_SIZE = 10

HINT_PROMPT = """\
You are a German grammar expert annotating flashcards for an adult learner.

For each card below, generate a SHORT (2-5 word) grammatical annotation for each \
cloze word, explaining the inflected form using German grammar terms. \
Use middle dot (·) as separator between components.

Examples of good annotations:
- Verb: "Präteritum · er/sie/es", "Konjunktiv II · ich", "Präsens · 3. Person Plural"
- Noun with article: "Akkusativ · maskulin", "Dativ · Plural"
- Adjective: "Komparativ · Dativ · Plural"
- If the cloze word is already the dictionary/base form, use "Grundform"
- For separable verbs (cloze_word contains ~), annotate the whole verb form

Return ONLY a JSON array (no markdown, no commentary). Each element:
{{
  "word": "<the word field exactly as given>",
  "hints": ["<hint for sentence 1>", "<hint for sentence 2>", ...]
}}

Cards:
{cards_block}"""


def build_cards_block(batch):
    """Format a batch of cards for the LLM prompt."""
    lines = []
    for i, card in enumerate(batch, 1):
        lines.append(f"{i}. Word: {card['word']}")
        for j, (sent, cloze) in enumerate(
            zip(card["sentences"], card["cloze_words"]), 1
        ):
            lines.append(f"   Sentence {j}: {sent}")
            lines.append(f"   ClozeWord {j}: {cloze}")
        lines.append("")
    return "\n".join(lines)


def run(args):
    dry_run = getattr(args, "dry_run", False)
    batch_size = getattr(args, "batch_size", BATCH_SIZE)

    # Find all vocab cards
    note_ids = anki("findNotes", query=f'"note:{MODEL}" "deck:{DECK}"')
    if not note_ids:
        print("No notes found.")
        return

    notes_info = anki("notesInfo", notes=note_ids)

    # Filter to cards with sentences but no hints
    candidates = []
    for note in notes_info:
        fields = note["fields"]
        sentence = fields.get("Sentence", {}).get("value", "")
        cloze_word = fields.get("ClozeWord", {}).get("value", "")
        cloze_hint = fields.get("ClozeHint", {}).get("value", "")

        if sentence and cloze_word and not cloze_hint:
            candidates.append({
                "note_id": note["noteId"],
                "word": fields["Word"]["value"],
                "sentences": sentence.split("|"),
                "cloze_words": cloze_word.split("|"),
            })

    if not candidates:
        print("All cards already have ClozeHint. Nothing to do.")
        return

    print(f"\n── Enriching {len(candidates)} cards with ClozeHint ──\n")

    if dry_run:
        for c in candidates[:20]:
            print(f"  {c['word']} ({len(c['sentences'])} sentences)")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")
        print(f"\n[DRY RUN] Would enrich {len(candidates)} cards.")
        return

    token = get_floodgate_token()
    enriched = 0
    failed = 0

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        cards_block = build_cards_block(batch)
        prompt = HINT_PROMPT.format(cards_block=cards_block)

        print(f"  Batch {i // batch_size + 1} "
              f"({len(batch)} cards: {batch[0]['word']} … {batch[-1]['word']})")

        result = call_llm_with_retry(
            [{"role": "user", "content": prompt}],
            token,
            max_tokens=4096,
            expect_len=len(batch),
        )

        if result is None:
            print(f"    FAILED: LLM returned no result")
            failed += len(batch)
            continue

        # Build lookup by word
        hint_map = {}
        for item in result:
            hint_map[item["word"]] = item["hints"]

        for card in batch:
            hints = hint_map.get(card["word"])
            if not hints:
                print(f"    MISS: {card['word']} not in LLM response")
                failed += 1
                continue

            # Ensure hint count matches sentence count
            n_sentences = len(card["sentences"])
            if len(hints) < n_sentences:
                hints.extend([""] * (n_sentences - len(hints)))
            elif len(hints) > n_sentences:
                hints = hints[:n_sentences]

            hint_value = "|".join(hints)
            anki("updateNoteFields", note={
                "id": card["note_id"],
                "fields": {"ClozeHint": hint_value},
            })
            enriched += 1

        # Print sample from this batch
        sample = batch[0]
        sample_hints = hint_map.get(sample["word"], [])
        if sample_hints:
            print(f"    e.g. {sample['word']}: {sample_hints[0]}")

    print(f"\nDone. {enriched} enriched, {failed} failed.")
