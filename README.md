# George's German Vocabulary

Pipeline-built Anki deck for learning German vocabulary relevant to conversations with children aged 4–6. The deck has 740 notes across 15 domains (play, food, animals, feelings, etc.), each generating three card types: production (EN→DE), recognition (DE→EN), and sentence cloze.

A separate **prefix** sub-deck teaches 21 German prefixes (separable, inseparable, and dual) with spatial/directional meanings.

## Prerequisites

- **Anki** (desktop) with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed and running
- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** for dependency management

Install dependencies:

```sh
uv sync
```

## Quick start

If you already have the deck imported in Anki, you only need the `tools/` scripts. The most common operations:

```sh
# Push latest CSS and templates to Anki (both note types)
uv run python tools/update_templates.py

# Enrich notes with IPA transcriptions from Wiktionary
uv run python tools/enrich_ipa_audio.py --ipa-only

# Unsuspend the next batch of cards for study
uv run python tools/unsuspend_candidates.py --apply
```

## Repository structure

```
pipeline/          Build a deck from scratch (numbered steps)
tools/             Maintain and enrich a live deck
data/              Curated data files
img/               Documentation images
```

## Building a deck from scratch

The pipeline scripts are numbered in execution order. Each reads the output of the previous step.

| Step | Script | What it does |
|------|--------|-------------|
| 1 | `pipeline/01_export_deck.py` | Exports an existing "German Vocabulary" deck via AnkiConnect to JSON + .apkg |
| 2 | `pipeline/02_select_vocab.py` | Scores exported notes for child-conversation relevance, selects 740, identifies gaps |
| 3 | `pipeline/03_build_deck.py` | Creates the "George's German Vocab" note type and imports all notes |
| 4 | `pipeline/04_build_prefixes.py` | Creates the "German Prefix" note type and imports 21 prefix cards |

After building, run `tools/update_templates.py` to push the latest CSS and templates.

To adapt for your own goals: edit the domain keywords and scoring in step 2, then rebuild from step 3.

## Tools reference

### `tools/update_templates.py`

**Live source of truth** for all CSS and HTML templates (both vocab and prefix note types). Pushes changes to Anki via AnkiConnect.

```sh
uv run python tools/update_templates.py
```

Always run this after modifying any template or CSS code. No flags — it pushes everything.

### `tools/enrich_ipa_audio.py`

Fetches IPA transcriptions and audio from German Wiktionary for notes missing them.

```sh
uv run python tools/enrich_ipa_audio.py --ipa-only       # IPA only (fast)
uv run python tools/enrich_ipa_audio.py --audio-only      # audio only (slow, rate-limited)
uv run python tools/enrich_ipa_audio.py --dry-run         # preview without changes
uv run python tools/enrich_ipa_audio.py --audio-delay 65  # seconds between audio downloads
```

### `tools/backfill_clozeword.py`

Populates the `ClozeWord` field — the exact text to blank in cloze sentences. Handles German morphology (inflected forms, separable verbs).

```sh
uv run python tools/backfill_clozeword.py --dry-run
uv run python tools/backfill_clozeword.py
uv run python tools/backfill_clozeword.py --verify
uv run python tools/backfill_clozeword.py --overrides data/clozeword_overrides.json
```

### `tools/fix_cloze_substrings.py`

Fixes cloze cards where the blanked word is a substring of another word in the sentence.

```sh
uv run python tools/fix_cloze_substrings.py --dry-run
uv run python tools/fix_cloze_substrings.py
```

### `tools/generate_sentences.py`

Generates alternative example sentences for notes using an LLM.

```sh
uv run python tools/generate_sentences.py --dry-run
uv run python tools/generate_sentences.py --batch-size 10 --limit 50
```

### `tools/fix_grammar.py`

Reviews and fixes grammar issues in sentence translations using an LLM.

```sh
uv run python tools/fix_grammar.py --dry-run
uv run python tools/fix_grammar.py --batch-size 20 --limit 100
```

### `tools/update_prefix_fields.py`

Syncs `CoreMeaning`, `SpatialSense`, and `Examples` from `data/prefix_data.json` to existing prefix notes in Anki.

```sh
uv run python tools/update_prefix_fields.py
```

### `tools/unsuspend_candidates.py`

Identifies cards ready to be unsuspended based on study progress and phase rules.

```sh
uv run python tools/unsuspend_candidates.py            # dry run (default)
uv run python tools/unsuspend_candidates.py --apply     # actually unsuspend
```

### `tools/query_note.py`

Quick lookup of a single note's fields and card state.

```sh
uv run python tools/query_note.py "der Saft"
```

## Card design

### Vocab note type — "George's German Vocab"

**13 fields:** Word, POS, Article, WordTranslation, WordTranslationDisambiguate, IPA, Audio, Sentence, ClozeWord, SentenceTranslation, Domains, Phase, Note

**3 card templates:**
- **EN → DE** — English prompt, produce the German word
- **DE → EN** — German word shown, recall the English
- **Sentence Cloze** — sentence with target word blanked (JS-rendered, not native Anki cloze)

### Prefix note type — "German Prefix"

**5 fields:** Prefix, PrefixType, CoreMeaning, SpatialSense, Examples

**2 card templates:**
- **Prefix → Meaning** — see the prefix, recall its meaning
- **Meaning → Prefix** — see the meaning, recall the prefix

### Visual design

- Dark/light mode via `prefers-color-scheme`
- Focal urgency timer: word colour shifts accent → amber → coral over 10 seconds (CSS-only, front cards only)
- Responsive font sizes via `clamp()`
- All CSS and templates live in `tools/update_templates.py`

## Review management

### Phased introduction

| Phase | Notes | Focus |
|-------|-------|-------|
| P1 | 80 | Greetings, core feelings, highest-frequency verbs |
| P2 | 87 | Numbers, animals, family, colours, common verbs |
| P3 | 573 | Remaining child-relevant vocabulary |

New cards start suspended. Use `tools/unsuspend_candidates.py` to introduce the next batch when ready.

### FSRS

The deck uses Anki's FSRS scheduler with default parameters.

## Further reading

See `NOTES.md` for detailed project history, design decisions, and template iteration notes. See `CLAUDE.md` for instructions that guide AI-assisted development on this project.
