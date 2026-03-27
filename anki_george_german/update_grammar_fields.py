#!/usr/bin/env python3
"""Sync grammar term data from grammar_terms.json to Anki.

Creates missing notes and updates existing ones in place (preserving
review history). Mirrors the prefix workflow in update_prefix_fields.py.

Also populates VocabExamples — real sentences from the vocab deck that
demonstrate each grammar concept, drawn from ClozeHint annotations.

Usage:
    anki-german grammar [--dry-run]
"""

import html
import json
import re
from collections import defaultdict

from . import DATA_DIR
from ._anki import anki, DECK as VOCAB_DECK, MODEL as VOCAB_MODEL

DATA_PATH = DATA_DIR / "grammar_terms.json"
DECK = "George's German Vocabulary::Grammar Terms"
MODEL = "German Grammar Term"
TAG = "grammar::term"

MAX_VOCAB_EXAMPLES = 5


def _collect_vocab_examples(vocab_notes, grammar_term_names):
    """Build term → list of vocab example dicts from ClozeHint annotations.

    Returns {term: [{word, translation, sentence, cloze_word, hint}, ...]}.
    """
    # Case-insensitive lookup: lower → canonical term name
    term_lower_map = {t.lower(): t for t in grammar_term_names}

    # term → {sub_pattern → [example_dict]}
    term_examples = defaultdict(lambda: defaultdict(list))

    for note in vocab_notes:
        fields = note["fields"]
        word = fields.get("Word", {}).get("value", "")
        translation = fields.get("WordTranslation", {}).get("value", "")
        sentence_raw = fields.get("Sentence", {}).get("value", "")
        cloze_word_raw = fields.get("ClozeWord", {}).get("value", "")
        hint_raw = fields.get("ClozeHint", {}).get("value", "")

        if not hint_raw or not sentence_raw:
            continue

        # Use first variant only (split on |)
        sentence = sentence_raw.split("|")[0].strip()
        cloze_word = cloze_word_raw.split("|")[0].strip()
        hint = hint_raw.split("|")[0].strip()

        # Split hint on · to find which terms this note references
        parts = [p.strip() for p in hint.split("·")]
        matched_terms = set()
        for part in parts:
            key = part.lower()
            if key in term_lower_map:
                matched_terms.add(term_lower_map[key])

        example = {
            "word": word,
            "translation": translation,
            "sentence": sentence,
            "cloze_word": cloze_word,
            "hint": hint,
        }

        for term in matched_terms:
            # Use full hint as sub-pattern key for variety
            term_examples[term][hint].append(example)

    return term_examples


def _select_examples(term_examples_by_pattern, max_n=MAX_VOCAB_EXAMPLES):
    """Select up to max_n examples with variety across sub-patterns.

    Picks one from each sub-pattern in round-robin fashion, sorted by word
    for stability.
    """
    if not term_examples_by_pattern:
        return []

    # Sort sub-patterns for determinism, sort examples within each by word
    sorted_patterns = sorted(term_examples_by_pattern.keys())
    pattern_lists = []
    for pat in sorted_patterns:
        examples = sorted(term_examples_by_pattern[pat], key=lambda e: e["word"])
        pattern_lists.append(examples)

    selected = []
    seen_words = set()
    idx = 0
    while len(selected) < max_n and pattern_lists:
        bucket = pattern_lists[idx % len(pattern_lists)]
        # Find next unseen word in this bucket
        picked = False
        for ex in bucket:
            if ex["word"] not in seen_words:
                selected.append(ex)
                seen_words.add(ex["word"])
                picked = True
                break
        if not picked:
            # This bucket is exhausted of unique words — remove it
            pattern_lists.pop(idx % len(pattern_lists))
            if not pattern_lists:
                break
            continue
        idx += 1

    return selected


def _highlight_cloze_in_sentence(sentence, cloze_word):
    """Wrap the cloze word in the sentence with <span class="hl gram">.

    Handles ~ separator for separable verbs. Returns HTML string.
    """
    result = html.escape(sentence)
    if not cloze_word:
        return result

    parts = cloze_word.split("~")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        escaped_part = re.escape(html.escape(part))
        # Word-boundary aware replacement (unicode letters)
        letter = r"[A-Za-z\u00C0-\u024F]"
        pattern = f"(?<!{letter}){escaped_part}(?!{letter})"
        replacement = f'<span class="hl gram">{html.escape(part)}</span>'
        result = re.sub(pattern, replacement, result, count=1)

    return result


def format_vocab_examples(examples):
    """Format a list of example dicts as HTML for the VocabExamples field."""
    if not examples:
        return ""

    items = []
    for ex in examples:
        word_html = html.escape(ex["word"])
        trans_html = html.escape(ex["translation"])
        sentence_html = _highlight_cloze_in_sentence(
            ex["sentence"], ex["cloze_word"]
        )
        items.append(
            f'<div class="example-item">'
            f'<span class="vocab-ex-word">{word_html}</span> '
            f'<span class="vocab-ex-trans">{trans_html}</span><br>'
            f'{sentence_html}'
            f'</div>'
        )

    return "".join(items)


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

    # ── Collect vocab examples from ClozeHint annotations ──
    grammar_term_names = {e["term"] for e in terms}
    vocab_note_ids = anki("findNotes",
                          query=f'"note:{VOCAB_MODEL}" "deck:{VOCAB_DECK}"')
    vocab_notes = anki("notesInfo", notes=vocab_note_ids) if vocab_note_ids else []

    term_examples_raw = _collect_vocab_examples(vocab_notes, grammar_term_names)

    # Select and format examples per term
    vocab_examples_html = {}
    for term_name in grammar_term_names:
        examples = _select_examples(term_examples_raw.get(term_name, {}))
        vocab_examples_html[term_name] = format_vocab_examples(examples)

    n_with_examples = sum(1 for v in vocab_examples_html.values() if v)
    print(f"  Vocab examples: {n_with_examples}/{len(grammar_term_names)} terms "
          f"have matching vocabulary")

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
            "VocabExamples": vocab_examples_html.get(term, ""),
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
