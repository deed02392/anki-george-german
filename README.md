# George's German Vocabulary

LLM-powered Anki deck for learning German vocabulary. Vocabulary is extracted from German texts (literature, articles) using spaCy NLP, enriched by Claude, and pushed to Anki via AnkiConnect. New cards can also be generated from domain briefs (e.g. "IT security vocabulary").

The deck currently has ~1,141 vocab notes across four card types: production (EN→DE), recognition (DE→EN), sentence cloze, and listening. A separate **prefix** sub-deck teaches 21 German prefixes, and a **grammar** sub-deck covers grammar terms.

## Prerequisites

- **Anki** (desktop) with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed and running
- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** for dependency management

Install dependencies:

```sh
uv sync
```

## Quick start

The project installs as an `anki-german` CLI:

```sh
# Push latest CSS and templates to Anki (all note types)
anki-german templates

# Generate vocabulary from a German text
anki-german generate text \
    --file data/books/Schachnovelle.txt \
    --source schachnovelle --paragraphs 1-30

# Generate vocabulary from a domain brief
anki-german generate domain \
    --brief "IT security vocabulary" \
    --source it_security --count 30

# Enrich notes with IPA transcriptions and audio from Wiktionary
anki-german enrich audio --ipa-only

# Unsuspend the next batch of cards for study
anki-german unsuspend --apply
```

## Repository structure

```
anki_george_german/         Installable Python package (CLI: anki-german)
  cli.py                    Unified CLI dispatcher
  _anki.py                  Shared AnkiConnect helper
  _llm.py                   Shared Floodgate/LLM helper
  generate_vocab.py         Main vocab generation (text + domain modes)
  chapters.py               Chapter detection and text chunking
  enrich_ipa_audio.py       IPA + audio enrichment from Wiktionary
  enrich_word_data.py       Word frequency + sense corpus builder
  enrich_hints.py           ClozeHint grammar annotations
  update_templates.py       LIVE SOURCE OF TRUTH for CSS and templates
  unsuspend_candidates.py   Progressive card unsuspension
  schedule.py               Manage launchd agent for auto-unsuspend
  fix_disambiguations.py    Fix duplicate translations via LLM
  fix_noun_cloze_articles.py Fix article in cloze words
  deck_stats.py             Deck analysis and problem cards
  query_note.py             Quick note lookup
  update_prefix_fields.py   Sync prefix data to Anki
  update_grammar_fields.py  Sync grammar term data to Anki
tests/                      pytest test suite
data/
  prefix_data.json          Prefix teaching data (21 entries)
  grammar_terms.json        Grammar term definitions
  word_data.json            Word frequency + sense corpus
  books/                    Source texts for vocab extraction
  external/                 Reference data (dlexDB, Goethe wordlists)
  generated/                JSON checkpoints from generation runs
pipeline/
  archive/                  Original deck build scripts (historical)
img/                        Documentation images
```

## CLI command reference

```sh
# ── Generate ──
anki-german generate text       --file --source [--select] [--paragraphs] [--batch-size] [--sentences] [--dry-run] [--enrich]
anki-german generate domain     --brief --source [--count] [--sentences] [--dry-run]
anki-german generate scan       --file [--chunk-minutes] [--reading-speed]

# ── Enrich ──
anki-german enrich sentences    --source [--sentences] [--batch-size] [--dry-run]
anki-german enrich audio        [--ipa-only] [--audio-only] [--audio-delay] [--no-llm] [--dry-run]
anki-german enrich disambig     [--dry-run]
anki-german enrich noun-cloze   [--dry-run]
anki-german enrich hints        [--dry-run]
anki-german enrich worddata     [--dwds-only] [--senses-only] [--dry-run]

# ── Manage ──
anki-german unsuspend           [--apply] [--max N]
anki-german stats
anki-german templates
anki-german prefixes
anki-german grammar
anki-german query               [WORD]
anki-german schedule install    [--day MON] [--hour 9] [--max 5]
anki-german schedule uninstall
anki-german schedule status
```

## Card design

### Vocab note type — "George's German Vocab"

**12 fields:** Word, POS, Article, WordTranslation, WordTranslationDisambiguate, IPA, Audio, Sentence, ClozeWord, ClozeHint, SentenceTranslation, Note

**4 card templates:**
- **EN → DE** — English prompt, produce the German word
- **DE → EN** — German word shown, recall the English
- **Sentence Cloze** — sentence with target word blanked (JS-rendered, not native Anki cloze)
- **Listening** — audio-only front, POS hint. Only generated when Audio field is populated.

### Prefix note type — "German Prefix"

**5 fields:** Prefix, PrefixType, CoreMeaning, SpatialSense, Examples

**2 card templates:** Prefix → Meaning, Meaning → Prefix

### Grammar note type — "German Grammar Term"

**2 card templates:** Term → Definition, Example → Term

### Visual design

- Dark/light mode via `prefers-color-scheme`
- Focal urgency timer: word colour shifts accent → amber → coral over 10 seconds (CSS-only, front cards only)
- Responsive font sizes via `clamp()`
- All CSS and templates live in `anki_george_german/update_templates.py`

## Progressive unsuspension

Cards are introduced gradually based on review maturity:
- **DE→EN**: unsuspended when EN→DE interval ≥ 14 days
- **Sentence Cloze**: unsuspended when both EN→DE and DE→EN interval ≥ 21 days
- **Listening**: unsuspended when DE→EN interval ≥ 21 days

EN→DE cards are unsuspended on creation.

## FSRS

The deck uses Anki's FSRS scheduler. Set Desired Retention to **0.85** in deck options.

## Further reading

See `NOTES.md` for detailed project history, design decisions, and template iteration notes. See `CLAUDE.md` for instructions that guide AI-assisted development on this project. See `STYLE_GUIDE.md` for the card CSS design system.
