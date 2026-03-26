# Data Quality Report

Summary statistics from the live Anki deck as of 2026-03-14.

---

## Deck Inventory

| Sub-deck | Note Type | Notes | Cards |
|----------|-----------|-------|-------|
| George's German Vocabulary | George's German Vocab | 1,141 | 3,423 |
| ::Prefixes | German Prefix | 21 | 42 |
| ::Grammar Terms | German Grammar Term | 29 | 58 |
| **Total** | | **1,191** | **3,523** |

Also in the collection (hibernated): German Vocabulary (original, 4,028 notes) and German Sentences.

---

## Scheduling Health

### EN→DE (Production) — 212 active cards

| Metric | Value |
|--------|-------|
| Avg interval | 18.5 days |
| Avg ease factor | 243% |
| Total lapses | 35 |
| Problem cards | 1 |
| Interval <1 week | 52 |
| Interval 1-4 weeks | 122 |
| Interval 1-3 months | 31 |
| Interval 3-12 months | 4 |

### DE→EN (Recognition) — 281 active cards

| Metric | Value |
|--------|-------|
| Avg interval | 15.4 days |
| Avg ease factor | 242% |
| Total lapses | 9 |
| Problem cards | 0 |
| Interval <1 week | 107 |
| Interval 1-4 weeks | 122 |
| Interval 1-3 months | 43 |

### Sentence Cloze (Context) — 159 active cards

| Metric | Value |
|--------|-------|
| Avg interval | 16.9 days |
| Avg ease factor | 224% |
| Total lapses | 11 |
| Problem cards | 3 |
| Interval <1 week | 42 |
| Interval 1-4 weeks | 67 |
| Interval 1-3 months | 35 |

**Key observation:** Cloze cards have the lowest ease factor (224% vs 242-243%) and the most problem cards (3 vs 0-1). This is expected — cloze is the hardest card type, requiring inflected production rather than recognition or base-form recall.

---

## Tag Health

| Tag Category | Status |
|-------------|--------|
| `source::schachnovelle` | 430 notes (working) |
| `source::schachnovelle::chunk::1` | 422 notes (working) |
| `child_vocab` | **0 notes** (broken) |
| `phase::1` through `phase::4` | **0 notes each** (broken) |
| `domain::*` (all 15 domains) | **0 notes each** (broken) |

**711 notes (62.3%) have no tags at all.** The original phase/domain/child_vocab tags appear to have been lost. The Phase and Domains fields are populated on the notes, but the corresponding Anki tags are empty.

---

## Duplicate Translation Groups (37)

These word pairs share the same English translation and need disambiguation:

| Translation | German Words | Has Disambig? |
|-------------|-------------|---------------|
| there | dort, dahin, hin, dorthin, da | Partial |
| to wake up | aufwachen, wecken, erwachen | Partial |
| outside | draußen, außen, außerhalb | Check needed |
| number | die Anzahl, die Zahl, die Nummer | Check needed |
| to play | spielen, abspielen | Yes |
| to catch | fangen, erwischen | Yes |
| to eat | essen, fressen | Yes |
| body | der Leib, der Körper | Check needed |
| ... | (29 more groups) | |

**63 notes currently have disambiguation text.** With 37 duplicate groups containing 2-5 words each, likely 50-80 more notes need disambiguation.

---

## Sentence Quality

- **3 variants:** 1,101 notes (96.5%)
- **2 variants:** 40 notes (3.5%)
- **Cloze substring failures:** 0 (all cloze words found in their sentences)
- **ClozeHint coverage:** 100% (all 1,141 notes)
- **Hint/sentence count alignment:** 100% (all hints match sentence count)

Sentence and cloze quality is excellent — the validation pipeline is working.

---

## Audio Coverage (Critical Gap)

| Metric | Count | Percentage |
|--------|-------|-----------|
| Notes with audio | 26 | 2.3% |
| Notes without audio | 1,115 | 97.7% |
| Notes with IPA | 1,141 | 100% |

All 26 audio files are Wiktionary-sourced `.mp3` files. Zero TTS-generated audio files exist, suggesting the Gemini TTS fallback has never been run at scale.

---

## POS Balance

| POS | Count | % | Assessment |
|-----|-------|---|-----------|
| noun | 415 | 36.4% | Good — nouns are the largest category in any language |
| verb | 376 | 33.0% | Good — verbs are essential for production |
| adverb | 175 | 15.3% | Slightly high — many German adverbs overlap with adjectives |
| adjective | 165 | 14.5% | Good |
| numeral | 27 | 2.4% | Fine — numbers are a closed class |
| phrase | 25 | 2.2% | Good for idiomatic expressions |
| preposition | 14 | 1.2% | Low — prepositions are critical for case governance |
| pronoun | 8 | 0.7% | Low but pronouns are a closed class |
| conjunction | 5 | 0.4% | Fine |
| interjection | 6 | 0.5% | Fine |

**Notable gap:** Only 14 prepositions. German preposition-case pairings (an + Dativ/Akkusativ, auf + Dativ/Akkusativ, etc.) are a major source of errors for learners. Consider a targeted preposition generation run.

---

## Deck Options Assessment

| Setting | Current | Recommended |
|---------|---------|-------------|
| New cards/day | 9999 | 10-15 |
| Max reviews/day | 9999 | 200 |
| Learn steps (min) | [1, 10] | [1, 10, 60] |
| Relearn steps (min) | [15] | [10, 60] |

The unlimited settings suggest George relies on self-discipline to manage load. This works until a vacation or busy period creates a review backlog, at which point unlimited reviews become overwhelming.
