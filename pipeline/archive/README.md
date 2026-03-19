# Pipeline Archive

These scripts document how the original 740-card deck was created. They are
no longer part of the active workflow — vocabulary is now generated via
`tools/generate_vocab.py`.

## Original execution order

1. `01_export_deck.py` — Export existing Anki deck to JSON
2. `02_select_vocab.py` — Select relevant cards for the new deck
3. `03_build_deck.py` — Create the "George's German Vocab" note type and import notes
4. `04_build_prefixes.py` — Create the "German Prefix" note type and import 21 prefix notes

## Why archived

The pipeline was a one-time migration from an older deck format. The active
workflow uses the `anki-german` CLI (package `anki_george_german/`) to extract
vocabulary from German texts (spaCy + LLM enrichment) or generate cards from
domain briefs.
