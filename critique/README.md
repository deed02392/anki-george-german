# Critique — George's German Vocabulary Anki Deck

Full analysis of the Anki card design, tooling, and learning approach.

## Documents

| File | Focus | Description |
|------|-------|-------------|
| [CARD_DESIGN_CRITIQUE.md](CARD_DESIGN_CRITIQUE.md) | **Primary** | Complete card-by-card walkthrough, cognitive analysis, 10 strengths, 10 weaknesses, 10 recommendations, and beyond-Anki guidance |
| [RENDERING_MECHANICS.md](RENDERING_MECHANICS.md) | Technical | How the JavaScript variant system, cloze blanking, tooltips, and source badges render at review time |
| [DATA_QUALITY_REPORT.md](DATA_QUALITY_REPORT.md) | Quantitative | Field completeness, scheduling health, tag issues, POS balance, duplicate translations |

## Supporting Data

| File | Description |
|------|-------------|
| `deck_data.json` | Full export of all 1,141 vocab notes + 3,423 cards + prefix/grammar notes (pulled from Anki via AnkiConnect) |
| `analysis_output.txt` | Raw output from the statistical analysis script |
| `scripts/pull_deck_data.py` | Script used to export deck data from Anki |
| `scripts/analyse_deck.py` | Script used to compute statistics from exported data |

## Key Findings

1. **The three-card architecture and sentence variant system are genuinely excellent** — this is better than most commercial language decks
2. **Audio coverage is critically low (2.3%)** — this is the single highest-impact improvement available
3. **ClozeHint appears only on the back card** — moving it to the front (as optional scaffold) would improve morphological learning
4. **711 notes (62%) have no tags** — tag backfill needed
5. **Deck options are at unlimited defaults** — should be constrained

## Status

This analysis was created on the `anki-card-critique` branch (2026-03-14) and merged to main. Since then, a 4th card template (Listening) was added, audio coverage was dramatically improved, ClozeHint was moved to the front card (tap-to-reveal), and Phase/Domains fields were removed. See [TODO.md](../TODO.md) for remaining unaddressed items.
