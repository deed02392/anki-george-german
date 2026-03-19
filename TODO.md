# TODO — Remaining Critique Items

Unaddressed items from the [card design critique](critique/CARD_DESIGN_CRITIQUE.md) (2026-03-14).

## Card Design

- [ ] **W4 — No full sentence production card.** All three card types test word-level knowledge. Consider a 4th template that shows English + German keywords and requires producing the full German sentence. (R8)
- [x] **W6 — Deck options at unlimited defaults.** Already configured: new cards/day set to 10.
- [x] **W7 — No receptive listening card.** Added 4th template "Listening" — audio-only front with "Hor zu." prompt in slate blue (`--accent-listen`), POS hint. Back reveals word, IPA, translation, sentence context. Gated on Audio field; unsuspends when DE→EN interval >= 21 days.
- [ ] **W9 — Grammar cards don't connect to vocab context.** The grammar card for "Dativ" and a cloze hint "Dativ · maskulin" live in separate silos. Consider cross-referencing. (R9)

## Tooling

- [ ] **T7 — No automatic quality feedback loop.** Cards with ≥5 lapses aren't flagged for content review. `deck_stats.py` identifies them but doesn't feed back into the pipeline.
- [ ] **T8 — Checkpoint JSON files accumulate.** `data/generated/` has no cleanup or archival strategy.
- [ ] **T9 — Compound detection may be too aggressive.** CharSplit filters transparent compounds but German compounds often diverge from their parts (Handschuh ≠ hand + shoe).

## Data Quality

- [x] **37 duplicate-translation groups need disambiguation.** All 37 groups addressed: 16 resolved by splitting translations (genuinely different English words), 21 given positive-description disambiguations using `=` prefix convention.
- [ ] **Only 14 prepositions in the deck.** Preposition-case pairings are a major error source. Consider a targeted generation run.

## Addressed

Items from the critique that have been resolved:

- [x] **W1 — Audio coverage critically low (2.3%).** Pipeline overhauled: REST API audio discovery, Wiktionary batch indexing, checkpointing, rate-limit resilience, Gemini TTS fallback. Ready to run at scale.
- [x] **W2 — ClozeHint back-only.** Hint now available as optional tap on front card blanks (zero visual footprint, tap to reveal).
- [x] **W5 — Phase/Domains fields removed.** These fields were unused clutter — Phase was never rendered on cards, Domains was always empty. Removed from note model, CLI, and all code.
- [x] **W10 — Phase badge not displayed.** Moot — Phase field removed entirely.
- [x] **T6 — Audio enrichment under-utilised.** Pipeline is now robust and production-ready.
- [x] **T10 — `--sentences` defaults to 2.** Changed to 3 to match existing card consistency.
- [x] **W8 — Cloze blank width hints at word length.** Closed — blank length doesn't hint strongly enough to matter.
