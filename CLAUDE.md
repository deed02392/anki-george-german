# Claude Session Context

## Project Overview
German vocabulary Anki deck for an adult learner. Vocabulary is generated from German texts (literature, articles) and domain briefs using an LLM-powered pipeline. See `NOTES.md` for full documentation.

## Repository Structure

```
anki_george_german/         Installable Python package (CLI: anki-german)
  __init__.py               PROJECT_ROOT, DATA_DIR constants
  cli.py                    Unified CLI dispatcher
  _anki.py                  Shared AnkiConnect helper (all modules import from here)
  _llm.py                   Shared Floodgate/LLM helper
  _vocab_prompts.py         LLM prompt templates for vocab generation
  _vocab_validate.py        Validation and normalisation for generated cards
  generate_vocab.py         Main vocab generation (text extraction + domain briefs)
  chapters.py               Chapter detection and text chunking for books
  enrich_ipa_audio.py       IPA + audio enrichment from Wiktionary + LLM fallback
  enrich_word_data.py        Word frequency + sense corpus builder
  enrich_hints.py           Backfill ClozeHint grammar annotations
  update_templates.py       LIVE SOURCE OF TRUTH for CSS and templates
  unsuspend_candidates.py   Weekly card unsuspension
  schedule.py               Manage launchd agent for auto-unsuspend
  update_prefix_fields.py   Sync prefix data to Anki
  update_grammar_fields.py  Sync grammar term data to Anki
  fix_disambiguations.py    Fix duplicate translations via LLM
  fix_noun_cloze_articles.py Fix article in cloze words
  deck_stats.py             Deck analysis and problem cards
  query_note.py             Quick note lookup
  templates/
    unsuspend_agent.swift   Swift source for launchd agent binary
    unsuspend.plist         Plist template for launchd agent
tests/                      pytest test suite
data/
  prefix_data.json          Prefix teaching data (21 entries)
  grammar_terms.json        Grammar term definitions
  word_data.json            Word frequency + sense corpus
  clozeword_overrides.json  Manual ClozeWord corrections (legacy)
  books/                    Source texts for vocab extraction
  external/                 Reference data (dlexDB, Goethe wordlists)
  generated/                JSON checkpoints from generation runs
pipeline/
  archive/                  Original deck build scripts (01-04, historical)
img/                        Documentation images
```

## CLI Command Reference

The project installs as `anki-german` via `uv sync`:

```sh
anki-german generate text       --file --source [--select] [--paragraphs] [--batch-size] [--sentences] [--dry-run] [--enrich]
anki-german generate domain     --brief --source [--count] [--sentences] [--dry-run]
anki-german generate scan       --file [--chunk-minutes] [--reading-speed]
anki-german enrich sentences    --source [--sentences] [--batch-size] [--dry-run]
anki-german enrich audio        [--ipa-only] [--audio-only] [--audio-delay] [--no-llm] [--dry-run]
anki-german enrich disambig     [--dry-run]
anki-german enrich noun-cloze   [--dry-run]
anki-german enrich hints        [--dry-run]
anki-german enrich worddata     [--dwds-only] [--senses-only] [--dry-run]
anki-german enrich transpos     [--dry-run]
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

## Vocabulary Generation

Two modes for generating new vocabulary cards:

### Text extraction mode
```sh
anki-german generate text \
    --file data/books/Schachenovelle.txt \
    --source schachnovelle --paragraphs 1-30 \
    --domain literature --dry-run
```

Pipeline stages:
1. **Ingest** — read paragraph range from text file
2. **spaCy extraction** — tokenize + lemmatize with `de_dep_news_trf`, filter function words
3. **Deck check** — skip existing words (tag them `source::{source}`), keep new ones
4. **Compound detection** — CharSplit filters transparent compounds (both parts known)
5. **Summarise** — LLM summarises the text chunk for thematic context
6. **LLM enrichment** — Claude Sonnet generates all card fields in batches of ~10
7. **Validation** — cloze substring check, verbatim quote rejection, field presence
8. **Import** — `addNotes` to Anki with source tags
9. **IPA enrichment** — automatic Wiktionary IPA lookup for new notes
10. **Checkpoint** — save JSON to `data/generated/`

### Domain brief mode
```sh
anki-german generate domain \
    --brief "IT security vocabulary" \
    --source it_security --count 30 \
    --domain security,technology --dry-run
```

Skips spaCy/compound stages; LLM generates words from the brief directly.

## Shared Modules

- **`anki_george_german/_anki.py`** — `anki(action, **params)`, `ANKI_URL`, `DECK`, `MODEL` constants. All modules import from here.
- **`anki_george_german/_llm.py`** — `get_floodgate_token()`, `call_llm(messages, token)` with JSON parsing and code fence stripping.
- **`anki_george_german/enrich_ipa_audio.py`** — importable `enrich_notes()` function + CLI. `generate_vocab.py` calls it directly after import.

## Critical Files

**`anki_george_german/update_templates.py`** is the LIVE SOURCE OF TRUTH for all card CSS and template HTML. Always run it after any template/CSS change.

## Timer Implementation

The timer uses **focal urgency** — the word you're looking at shifts colour over 10s:
- `.word-de.timed` / `.word-en.timed` on front templates animate via `@keyframes urgency-de` / `urgency-en`
- `.listen-prompt.timed` animates via `@keyframes urgency-listen` (slate blue to amber to coral)
- `.cloze-blank` animates automatically via `@keyframes urgency-blank` (border + subtle bg tint)
- Two discrete steps: accent holds 0–6s, snaps to amber 6–7s, holds 7–9s, snaps to coral 9–10s
- Back templates have no urgency animation

## Prefix Note Type ("German Prefix")

21 cards teaching the German prefix system. Sub-deck `George's German Vocabulary::Prefixes`.

### Note type fields (5)

| # | Field | Purpose |
|---|-------|---------|
| 0 | Prefix | The prefix (no hyphen — template adds it) |
| 1 | PrefixType | `separable` / `inseparable` / `both` |
| 2 | CoreMeaning | 2-4 word meaning cluster |
| 3 | SpatialSense | One-sentence spatial intuition |
| 4 | Examples | HTML with prefix highlighted via `<span class="pfx">` |

### CSS architecture

`anki_george_german/update_templates.py` splits CSS into shared base + per-note-type sections:
- `BASE_VARS` — `:root` design tokens, dark/light mode
- `BASE_LAYOUT` — `.card`, `.kard`, `.card-header`, `.card-type`, `hr.divider`
- `VOCAB_CLASSES` — vocab-specific (`.word-de`, `.word-en`, `.cloze-*`, source badges)
- `LISTEN_CLASSES` — listening-specific (accent colour `--accent-listen`, `.listen-prompt`, `.audio-center`)
- `PREFIX_CLASSES` — prefix-specific (accent colour, `.hero.pfx`, `.sub-hero.pfx`)
- `GRAMMAR_CLASSES` — grammar-specific (accent colour, `.hero.gram`, `.sub-hero.gram`)
- Shared components in `BASE_LAYOUT`: `.hero`, `.sub-hero`, `.type-tag`, `.hint-text`, `.examples`/`.hl`, `.callout`

## Tag Structure

- `source::schachnovelle`, `source::it_security` — origin of the card
- `source::schachnovelle::chunk::1` — chapter/chunk within a source

## Vocab Note Type Fields (13)

Word, POS, Article, WordTranslation, WordTranslationDisambiguate, TranslationPOS, IPA, Audio, Sentence, ClozeWord, ClozeHint, SentenceTranslation, Note

### ClozeWord convention

- Stores the exact text to blank in the cloze sentence
- `~` separates parts for separable verbs: `machte~auf`
- `|` separates sentence variants (multi-sentence cards)
- Set at generation time by the LLM — no backfill step needed

### WordTranslationDisambiguate — IMPORTANT

This field exists **only** to distinguish between cards that share the **exact same English translation**.

**Framing:** Prefer positive descriptions of the word's own sense (what the word IS), not negations. The field supports two modes via a prefix convention:
- `=everyday, warm, poetic` → rendered as-is: "everyday, warm, poetic"
- `animals eating` → rendered with label: "Not: animals eating"

The `=` prefix (positive framing) is preferred. The "Not:" fallback exists but is currently unused.

**When it's needed:** `essen` and `fressen` both translate to "to eat". The disambig on `essen` says `=humans eating, normal`, telling the learner what this specific word means.

**When it's NOT needed:**
- Cards with unique translations (no other card has the same English text)
- German homographs with different translations (der Tor = "fool" vs das Tor = "gate" — different English, no confusion possible)
- Definitions or glosses restating the word's own meaning

**Rules:**
- Never include German words — naming the sibling gives away the answer by elimination
- 3-8 words describing this word's sense, register, or usage
- Prefix with `=` for positive descriptions (preferred); omit prefix for "Not:" framing
- `fix_disambiguations.py` finds all duplicate-translation groups and generates/updates disambig via LLM
- `strip_orphan_disambiguations()` in `_vocab_validate.py` clears disambig on cards whose translation is unique within a generation batch
- Never clear a disambiguation without checking if siblings exist

## Card Layout — Key Decisions

### What's live (desktop + AnkiMobile)
```css
html, body, #qa { margin: 0; height: 100%; }
.card { min-height: 100%; display: grid; align-content: center; }
.kard { box-sizing: border-box; max-width: 560px; width: 100%; }
```

### Key rules
- Override Anki's `body { margin: 20px }` to `0`
- `#qa` height chain required for AnkiMobile
- `box-sizing: border-box` on `.kard` prevents horizontal overflow
- Font sizes use `clamp()` for responsive scaling
- Font stack: `"Noto Sans", sans-serif`

## Before Touching Templates or CSS

1. Read `NOTES.md`
2. The authoritative file is `anki_george_german/update_templates.py`
3. After editing, run `anki-german templates` to push to Anki via AnkiConnect
4. Test in **actual review mode** on mobile, not just Browse→Preview
5. Never manually edit templates in Anki's UI

## AnkiConnect Setup

- Requires Anki running with AnkiConnect add-on (2055492159)
- Default URL: `http://localhost:8765`
- All commands that call AnkiConnect must run in tmux session **anki** (`tmux new-session -s anki` or `tmux send-keys -t anki`)

## Wiktionary Enrichment

`anki_george_german/enrich_ipa_audio.py` fetches IPA + audio from de.wiktionary.org, with automatic LLM fallback for words Wiktionary doesn't have. Importable as a module (`from anki_george_german.enrich_ipa_audio import enrich_notes`) or run as CLI.

### Usage
```sh
anki-german enrich audio              # both IPA + audio
anki-german enrich audio --ipa-only   # fast
anki-german enrich audio --audio-only # slow (rate limits)
anki-german enrich audio --no-llm     # skip LLM fallback
anki-german enrich audio --dry-run
```

## Dependencies

```toml
dependencies = [
    "rapidfuzz>=3.14.3",
    "requests>=2.32.5",
    "spacy[transformers]>=3.7",
    "charsplit @ git+https://github.com/dtuggener/CharSplit.git",
    "torch>=2.0",
    "spacy-transformers>=1.3",
]
```

spaCy model (one-time): `uv run python -m spacy download de_dep_news_trf`

All commands use `uv run` — never bare `python` or `pip`.
