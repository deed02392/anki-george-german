# Anki Card Design Critique — George's German Vocabulary

**Date:** 2026-03-14
**Analyst perspective:** Expert in spaced-repetition flashcard design for adult L2 acquisition

---

## Table of Contents

1. [Deck Architecture Overview](#1-deck-architecture-overview)
2. [Card-by-Card Walkthrough](#2-card-by-card-walkthrough)
3. [What Your Brain Experiences During Review](#3-what-your-brain-experiences-during-review)
4. [Strengths — What Will Help You Improve](#4-strengths)
5. [Weaknesses — What Will Cause Stagnation or Regression](#5-weaknesses)
6. [Actionable Recommendations](#6-actionable-recommendations)
7. [Tooling Critique (Secondary)](#7-tooling-critique)
8. [Beyond Anki (Tertiary)](#8-beyond-anki)

---

## 1. Deck Architecture Overview

### Note Types (3)

| Note Type | Fields | Templates | Cards |
|-----------|--------|-----------|-------|
| George's German Vocab | 14 fields | EN→DE, DE→EN, Sentence Cloze | 3,423 (1,141 notes × 3) |
| German Prefix | 5 fields | Prefix→Meaning, Meaning→Prefix | 42 (21 notes × 2) |
| German Grammar Term | 6 fields | Term→Definition, Example→Term | 58 (29 notes × 2) |

### Current Card Queue State

| Template | Total | Suspended | New | Review | Learning |
|----------|-------|-----------|-----|--------|----------|
| EN→DE | 1,141 | 567 | 297 | 203 | 9 |
| DE→EN | 1,141 | 567 | 228 | 271 | 10 |
| Cloze | 1,141 | 571 | 346 | 143 | 16 |
| Prefix | 42 | — | — | — | — |
| Grammar | 58 | — | — | — | — |

### Field Completeness

| Field | Coverage | Notes |
|-------|----------|-------|
| Word, POS, Translation, IPA, Sentence, ClozeWord, ClozeHint, SentenceTranslation | 100% | Excellent |
| Article | 35.3% | Expected — only nouns (36.4% of notes) need articles |
| Audio | **2.3%** | Critical gap — only 26 of 1,141 notes have audio |
| Disambiguation | 5.5% | 63 notes; 37 duplicate-translation groups identified |
| Note | 8.5% | Usage notes on 97 notes — appropriate for special cases |

### POS Distribution

Nouns (415), Verbs (376), Adverbs (175), Adjectives (165), Numerals (27), Phrases (25), Prepositions (14), Pronouns (8), Interjections (6), Conjunctions (5).

### Sentence Variant Distribution

- 3 sentences per note: 1,101 notes (96.5%)
- 2 sentences per note: 40 notes (3.5%)

---

## 2. Card-by-Card Walkthrough

### 2a. EN→DE (Production Card)

**Front:**
```
[EN → DE · Production]               [source badge]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

              to catch                    ← accent-en, timed (10s urgency)

─────────────────────────────────────
"The police catch the burglar."       ← random variant from pipe-delimited sentences
                                        (English translation, quoted)

NOT: catching someone in wrongdoing   ← disambiguation callout (if present)
```

**What you must do:** See English, produce the German word.

**Back (after flip):**
```
[EN → DE · Production]               [source badge]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

              to catch

─────────────────────────────────────

              fangen                   ← German word (accent-de, NO animation)
              verb                     ← POS hint (from variant-matched POS)
              [ˈfaŋən]                 ← IPA
              🔊                       ← Audio (if present)

"Die Polizei fängt den Einbrecher."   ← German sentence (same variant as front)
"The police catch the burglar."       ← English translation

NOT: catching someone in wrongdoing

📝 usage note                         ← Note field (if present)
```

**Cognitive analysis:**
- Front stimulus: English meaning + English sentence context + disambiguation
- Required recall: The German word (any valid form)
- The English sentence on the front is a *significant hint* — it shows context that narrows the answer
- The disambiguation "NOT: X" is shown on both front AND back, which is appropriate since it's needed for production

**Grading guidance (what SHOULD happen):**
- **Again:** Cannot produce any German word, or produces wrong word
- **Hard:** Produces the word but takes >6 seconds (urgency timer reaches amber/coral)
- **Good:** Produces the word within 6 seconds
- **Easy:** Instant recall, no hesitation

### 2b. DE→EN (Recognition Card)

**Front:**
```
[DE → EN · Recognition]              [source badge]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

              fangen                   ← German word (timed urgency)
              [ˈfaŋən]                 ← IPA
              🔊                       ← Audio
```

**What you must do:** See German word + hear pronunciation, produce English meaning.

**Back:**
```
[DE → EN · Recognition]              [source badge]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

              fangen
              verb                     ← POS hint
              [ˈfaŋən]

─────────────────────────────────────

              to catch                 ← English translation

"Die Polizei fängt den Einbrecher."  ← German sentence
"The police catch the burglar."      ← English translation

NOT: catching someone in wrongdoing

📝 usage note
```

**Cognitive analysis:**
- Front stimulus: German word only (+ IPA + audio)
- Required recall: English meaning
- This is the easiest of the three cards — recognition is faster than production
- The front is appropriately minimal

### 2c. Sentence Cloze (Context Card)

**Front:**
```
[Sentence Cloze · Context]           [source badge]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Die Polizei _____ den Einbrecher.    ← Cloze sentence (blank animates with urgency)
"The police catch the burglar."      ← English translation
🔊                                   ← Audio
```

The blank (`_____`) replaces the cloze word. For "fängt", the blank covers that exact substring. For separable verbs like "machte~auf", TWO blanks appear at separate positions.

**Tooltip hint (on hover/tap of blank):**
A small floating tooltip appears: `präsens · er/sie/es` — the ClozeHint field tells you the grammatical form expected.

**What you must do:** Read the sentence with the blank + the English translation, and produce the missing German word in the correct inflected form.

**Back:**
```
[Sentence Cloze · Context]           [source badge]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Die Polizei fängt den Einbrecher.    ← Word shown in bold accent colour
"The police catch the burglar."

─────────────────────────────────────
              fangen
              verb                     ← POS hint (variant-matched)
              [ˈfaŋən]
              to catch

📝 usage note
```

**Critical design feature — the ClozeHint tooltip on the BACK:**
The cloze hint tooltip appears on the **back** card, NOT the front. Looking at the code in `update_templates.py:701`:
```python
CLOZE_BACK = ... + cloze_picker_js("cloze-a", "cloze-tr-back", "cloze-answer", pos_id="cloze-pos", hint=True)
```
The `hint=True` parameter is only on the back card's JS. The front card at line 681 uses:
```python
CLOZE_FRONT = ... + cloze_picker_js("cloze-q", "cloze-tr", "cloze-blank", is_front=True)
```
No `hint=True` on the front.

**This means the ClozeHint is NOT available as a study aid during the question phase.** It only appears on the answer side as a grammar annotation. This is a significant finding — more on this in the critique.

**Grading guidance:**
- **Again:** Cannot produce the word, or wrong word entirely
- **Hard:** Correct word but wrong inflection (e.g. "fang" instead of "fängt")
- **Good:** Correct word in correct form
- **Easy:** Instant, no hesitation

### 2d. Prefix → Meaning

**Front:**
```
[Prefix]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                auf-                   ← Large, accent-pfx, timed
              SEPARABLE                ← PrefixType tag
```

**Back:**
```
[Prefix]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

              up, open                 ← CoreMeaning
   rising to an exposed state —       ← SpatialSense (hint-text)
   opening is going up

─────────────────────────────────────
   aufmachen — to open                ← Examples with prefix highlighted
   aufwachen — to wake up
   ...
```

### 2e. Meaning → Prefix

**Front:**
```
[Prefix]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

              up, open                 ← CoreMeaning, timed
   rising to an exposed state         ← SpatialSense
```

**Back:** Shows the prefix with type tag and examples.

### 2f. Grammar Term → Definition

**Front:** Shows the German grammar term (e.g. "Konjunktiv II") with category tag.
**Back:** Shows definition, formation pattern, and examples.

### 2g. Grammar Example → Term

**Front:** Shows ONE randomly selected example (from potentially multiple examples).
**Back:** Shows the grammar term, definition, and formation.

---

## 3. What Your Brain Experiences During Review

### The Variant System — A Novel Approach

Each note stores 2-3 sentence variants separated by `|`. JavaScript randomly selects one variant per review and uses `sessionStorage` to keep front/back consistent. This means:

- **You see different sentences for the same word across reviews** — this is genuinely excellent for preventing rote sentence memorisation
- The variant is chosen randomly, so you cannot predict which sentence you'll get
- ClozeWord, SentenceTranslation, POS, and ClozeHint are all pipe-delimited and variant-indexed

**Impact on learning:** This is one of the strongest design decisions in the deck. It forces contextual flexibility rather than "I remember the sentence about the cat" pattern matching. Over time, this trains genuine word knowledge rather than sentence-level recognition.

### The Focal Urgency Timer

The 10-second CSS animation shifts the focal word's colour:
- 0-6s: Accent colour (calm, reading)
- 6-7s: Snap to amber (mild pressure)
- 9-10s: Snap to coral (strong pressure)
- Stays coral permanently after 10s

**Impact on learning:** This is a subtle but effective self-assessment aid. Research on retrieval practice shows that retrieval speed correlates with strength of encoding. The colour shift gives you an implicit cue about whether to press Hard vs Good without requiring you to consciously track time. The 6-second threshold is reasonable — most fluent retrievals happen within 3-5 seconds.

### The Progressive Unsuspension Model

Cards are introduced in a specific order:
1. EN→DE first (production)
2. DE→EN after EN→DE interval ≥ 14 days
3. Cloze after both EN→DE and DE→EN interval ≥ 21 days

**Impact on learning:** This is a well-designed difficulty ladder. Production before recognition is the correct order (harder first, establishes deeper encoding). The cloze card as the final stage tests morphological precision. The interval thresholds (14d, 21d) are conservative but safe — they ensure base knowledge is solid before adding complexity.

### The Three-Card Structure

For each vocabulary note, you ultimately review:
1. English → German (production)
2. German → English (recognition)
3. German sentence → fill the blank (contextual production)

**Impact on learning:** This hits three distinct cognitive pathways:
- (1) tests L1→L2 lexical access (the hardest direction)
- (2) tests L2→L1 recognition (solidifies orthographic form)
- (3) tests morphological/syntactic integration (case, verb form, word order)

This is textbook-quality multi-faceted testing. Most commercial language decks only test (1) and (2).

---

## 4. Strengths — What Will Help You Improve

### S1. Three-card architecture hits distinct cognitive pathways
Every word is tested in three fundamentally different ways. This creates "desirable difficulty" — each card type forces different neural processing, leading to more robust and flexible word knowledge.

### S2. Sentence variant randomisation prevents rote pattern-matching
The pipe-delimited variant system with random selection is genuinely innovative. Most Anki language decks suffer from "I remember the sentence, not the word" — your design actively fights this.

### S3. Grammatically diverse sentences per word
Each word's 2-3 sentences are explicitly required to show *different* grammatical contexts (different tenses, cases, nominalised forms). This means the cloze card tests different inflections across reviews, which is exactly how you build morphological competence.

### S4. ClozeHint grammar annotations
The `Präteritum · er/sie/es` style annotations, even though they only appear on the back, serve as a post-retrieval confirmation of grammatical understanding. Over time, seeing these repeatedly builds grammatical metalanguage fluency.

### S5. Article-inclusive cloze words for nouns
The system (and the fix_noun_cloze_articles.py fixer) ensures that noun clozes include the article: "den Einbrecher" not just "Einbrecher". This forces case-awareness during cloze review — you must know both the word AND its case in context.

### S6. Separable verb handling
The `~` delimiter for separable verbs (e.g. `machte~auf`) creates two separate blanks in the sentence. This tests a notoriously difficult aspect of German — knowing that the prefix detaches and where it lands.

### S7. Progressive unsuspension with conservative thresholds
The difficulty ladder (EN→DE → DE→EN → Cloze) with maturity gates prevents cognitive overload and ensures foundational knowledge before adding complexity.

### S8. Disambiguation system is well-designed
The "NOT: X" callouts for duplicate translations (essen/fressen, öffnen/aufmachen) are a clean solution to the synonym problem. The rule of never including German in disambiguation text prevents answer leakage.

### S9. Prefix and Grammar sub-decks provide structural scaffolding
The 21 prefix cards and 29 grammar term cards give you a metalinguistic framework. Understanding "ab- means detachment" helps you decode unknown words — this is transfer learning, not just memorisation.

### S10. Dark/light mode with responsive sizing
Reviewing in different lighting conditions with appropriate contrast reduces eye strain and maintains readability across devices.

---

## 5. Weaknesses — What Will Cause Stagnation or Regression

### W1. CRITICAL: Only 2.3% audio coverage

**Current state:** 26 out of 1,141 notes have audio.

**Impact:** Without audio, your brain has no phonological anchor for these words. You are learning to READ German, not to SPEAK or UNDERSTAND German. When you encounter these words in conversation, there will be a disconnect between the visual form you memorised and the spoken form.

**Specific risks:**
- You won't recognise words you "know" when they're spoken to you
- Your pronunciation will calcify around incorrect internal guesses
- The DE→EN card shows IPA, but most learners can't fluently read IPA in real-time — audio is essential

**Severity: HIGH** — This is the single biggest gap in the deck.

### W2. ClozeHint is back-only — missed learning opportunity

**Current state:** The ClozeHint tooltip (e.g. "Dativ · Plural") only renders on the back card. The front card has no hint access.

**Impact:** This means the ClozeHint cannot serve as a progressive scaffolding tool during the question phase. A learner who sees `Den _____` and knows the root word "Einbrecher" but can't produce the correct case form has NO way to get a nudge. They must either:
- Get it right (no help needed → hint is wasted)
- Get it wrong (hint shows on back but the learning moment has passed)

**What it SHOULD do:** The hint should be available as an optional tap/hover on the FRONT, allowing the learner to self-scaffold. This creates a "hint penalty" model — if you need the hint, press Hard instead of Good.

### ~~W3.~~ *(Retracted)* English sentence on EN→DE front

Originally flagged as "too generous" — but on reflection, the English sentence doesn't help you produce the German word. You either know "weinen" or you don't; seeing "Animals cannot cry" gives no L2 lexical hint. The sentence provides context for the back-side German sentence, primes you for which variant you'll see, and helps disambiguate polysemous words — all legitimate functions.

### W4. No production of full German sentences anywhere

**Current state:** All three card types test word-level knowledge:
- EN→DE: produce the word
- DE→EN: recognise the word
- Cloze: produce one word in a sentence

**Missing:** There is no card type that requires you to produce a complete German sentence. You never practise word order, clause construction, or natural phrasing.

**Impact:** You will build a large passive vocabulary but struggle to construct sentences in conversation. Vocabulary without syntax is like having bricks without mortar.

### W5. 711 notes (62.3%) have no tags at all

**Current state:** Only 430 notes have source tags (all from schachnovelle). The original 711 notes from the initial deck build have NO tags — their `child_vocab`, `phase::*`, and `domain::*` tags returned 0 results in the query.

**Impact:** Without tags, you cannot:
- Filter reviews by domain or phase
- Track which source contributed which words
- Use Anki's filtered decks for targeted study
- Measure progress by domain

This is a data quality issue that compounds over time as the deck grows.

### W6. Deck options are at default values

**Current state:**
- New cards/day: 9999 (unlimited)
- Max reviews/day: 9999 (unlimited)
- Learn steps: [1, 10] minutes
- Relearn steps: [15] minutes

**Impact:** With no limits, you risk:
- Introducing too many new cards and creating an overwhelming review burden
- The learn steps [1, 10] are standard but short — for an adult language learner, [1, 10, 60] or [1, 10, 1440] (next day) would provide better initial spacing
- Single relearn step of 15 minutes is too aggressive for lapsed cards — you'll see them once 15 minutes later and then not again for the card's interval, which may cause re-lapsing

### W7. No receptive listening card

**Current state:** No card plays audio and asks you to identify/write the word from hearing alone.

**Impact:** Your listening comprehension will lag behind your reading comprehension. For conversational German, you need to recognise words by ear, not just by text.

### W8. Cloze blanks use fixed-width, not variable-width

**Current state:** `.cloze-blank { min-width: 2.5em; }` — all blanks are at least 2.5em wide regardless of word length.

**Impact:** The blank length is a clue. A 2.5em blank for "der" vs "den" looks the same (good), but a 2.5em blank for "Kindergarten" is suspiciously short. The blank should either:
- Always be the same width (current approach, mostly fine)
- OR match the actual word width (would be a dead giveaway)

The current approach is acceptable but the `min-width` means short words get appropriately-sized blanks while long words get blanks that are narrower than the word, which is a mild hint. This is minor.

### W9. No spaced exposure to grammar in context

**Current state:** Grammar cards test metalinguistic terminology (Konjunktiv II → definition). But there's no connection between the grammar card "Dativ" and the vocab cloze hint "Dativ · maskulin" on a noun card.

**Impact:** Grammar knowledge and vocabulary knowledge develop in parallel silos. You might know what "Dativ" means from the grammar card and correctly fill in "dem Hund" in a cloze card, but the connection between the two won't be explicitly strengthened.

### W10. Phase badge is stored but not displayed

**Current state:** The Phase field is populated (values: "1", "2", "3", "4") but looking at the templates, there is no `{{Phase}}` rendering in any current template. The old `source-badge` JS renders source tags, not phase tags.

**Impact:** You have no visual indicator of a card's difficulty tier during review. This is a missed opportunity for metacognitive awareness.

---

## 6. Actionable Recommendations

### Priority 1 — Fix Critical Gaps

**R1. Audio coverage must reach >80%**
The Gemini TTS fallback and Wiktionary pipeline exist but coverage is at 2.3%. Run `anki-german enrich ipa --audio-only` aggressively. For the ~98% of words without audio, the TTS fallback should be the primary path. Consider making audio enrichment automatic after every import.

**R2. Move ClozeHint to the front card (optional tap/hover)**
Change `CLOZE_FRONT` to include `hint=True` in the cloze_picker_js call. This turns the hint into a scaffolding tool: learners who need it tap for a clue and self-assess as Hard; learners who don't need it ignore it and self-assess as Good.

### Priority 2 — Improve Encoding Depth

**R3.** *(Retracted — see W3)*

**R4. Add a listening card (4th template)**
Create a card type that plays audio and shows no text. The learner must type or speak the word. This is the "audio → German word" direction, filling the gap between visual recognition and auditory recognition.

Implementation sketch: A 4th template `Audio → Word` with front showing only `{{Audio}}` and a "What word is this?" label. Back shows the word, IPA, translation.

### Priority 3 — Improve Metadata and Workflow

**R5. Backfill tags on the 711 untagged notes**
The original child-vocab notes lost their tags (or never had them applied correctly — the `child_vocab`, `phase::1-3`, and `domain::*` tags all show 0 notes). Run a script to re-tag based on the Domains and Phase fields, which ARE populated.

**R6. Set reasonable deck limits**
- New cards/day: 10-15 (as recommended in NOTES.md, but not enforced in deck options)
- Max reviews/day: 200 (prevents marathon sessions)
- Learn steps: [1, 10, 60] (adds a 1-hour spacing before graduation)
- Relearn steps: [10, 60] (two chances before re-entering review queue)

**R7. Display Phase badge on cards**
Add `{{#Phase}}<span class="source-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}` to the card-header alongside the source badge.

### Priority 4 — Long-term Improvements

**R8. Consider sentence production cards**
A card that shows English sentence + a few German keywords and asks you to produce the full German sentence. This is the hardest card type and should only be activated after all three current cards are mature. It tests syntax, not just vocabulary.

**R9. Link grammar cards to vocab context**
When a cloze hint mentions "Dativ", it would be powerful to have a mechanism (even just a Note field annotation) that references the grammar card. This builds cross-referential knowledge.

**R10. Track and visualise learning velocity per source**
Your tags distinguish schachnovelle words from other sources. A dashboard showing retention rate per source would help you calibrate difficulty when choosing your next text.

---

## 7. Tooling Critique (Secondary)

### Strengths of the Tooling

**T1. The generation pipeline is sophisticated and well-validated**
The 10-stage pipeline (ingest → spaCy → deck check → compounds → summarise → LLM → validate → import → IPA → checkpoint) is production-quality. The validation step (cloze substring checking, verbatim quote rejection, field presence) catches LLM hallucinations.

**T2. The normalise_cloze system is clever**
Using spaCy noun chunks to fix article mismatches (LLM says "Der Meister" but sentence has "den Meister") is a robust solution to a common LLM failure mode.

**T3. The chapter/chunk system enables systematic text processing**
Auto-detecting chapter markers and falling back to word-count chunking means you can process any German text without manual preparation.

**T4. The unsuspend scheduler is well-engineered**
A launchd agent that launches Anki, waits for AnkiConnect, runs unsuspend logic, and logs results — this is proper automation, not a cron hack.

**T5. Gendered pair deduplication**
Automatically dropping Lehrerin when Lehrer exists prevents card bloat from regular morphological derivations.

### Weaknesses of the Tooling

**T6. Audio enrichment is under-utilised**
The Wiktionary + Gemini TTS pipeline exists but only 26 notes have audio. The GEMINI_API_KEY environment variable dependency and rate limiting (10 requests/day on free tier) suggest this pipeline hasn't been run at scale.

**T7. No automatic quality feedback loop**
When you fail a card repeatedly (lapses ≥ 5), there's no mechanism to automatically review or improve that card's content. The `deck_stats.py` identifies problem cards but doesn't feed back into the generation pipeline.

**T8. Checkpoint JSON files accumulate without cleanup**
`data/generated/` stores JSON checkpoints from every generation run. There's no garbage collection or archival strategy.

**T9. The compound detection filter may be too aggressive**
CharSplit filters "transparent compounds" where both parts are known. But German compounds often have meanings that diverge from their parts (Handschuh = glove, not "hand shoe"). Filtering these out means you miss important vocabulary.

**T10. The `--sentences` parameter defaults to 2 but best practice is 3**
Most notes have 3 sentences. The default of 2 means new cards generated with default settings get fewer variants than existing cards, creating inconsistency.

---

## 8. Beyond Anki (Tertiary)

Anki is excellent for vocabulary acquisition but has fundamental limitations for language learning. Here's what to add:

### 8.1. Immersive Reading (with lookup)

Use a reader app (Readlang, LingQ, or even Kindle's built-in dictionary) to read German texts. This provides:
- Incidental vocabulary acquisition (words you don't study but absorb)
- Syntactic intuition from extended exposure
- Contextual disambiguation that flashcards can't provide

**Integration with your pipeline:** Your `generate text` command already extracts vocab from books. The missing piece is actually READING those books, not just extracting words from them. Read each chapter BEFORE or AFTER generating cards from it.

### 8.2. Listening Practice

- **Podcasts:** Slow German, Coffee Break German, or authentic content at your level
- **Audiobooks:** Listen to the books you're generating cards from (Schachnovelle has excellent audiobook versions)
- **Paired reading:** Read a chapter while listening to the audiobook simultaneously

This directly addresses the audio gap (W1/W7).

### 8.3. Active Production Practice

- **Journaling in German:** Write 3-5 sentences daily using recently-learned vocabulary
- **Shadowing:** Listen to German audio and repeat immediately, matching prosody
- **Conversation practice:** Even 15 minutes/week with a tutor or language partner provides production practice that Anki cannot

### 8.4. Grammar-in-Context Study

Your grammar cards teach metalanguage, but you also need to build procedural grammar knowledge:
- Work through a structured grammar textbook (Hammer's German Grammar, or the more approachable Deutsche Grammatik by Hering/Matussek/Perlmann-Balme)
- Do grammar exercises that require producing correct forms (not just recognising terms)
- Your cloze cards partially serve this purpose, but they only test ONE word per sentence

### 8.5. Spaced Repetition for Sentences (not just words)

Consider a separate deck or sub-deck of full German sentences (bilingual sentence pairs) where you see the English and must produce the German. This is distinct from your cloze cards because:
- Cloze tests one word in context
- Sentence production tests the entire sentence construction
- This is what Glossika and Clozemaster focus on

### 8.6. Cultural and Pragmatic Knowledge

Your deck is semantically rich but pragmatically thin. Consider adding:
- Register awareness (formal/informal, written/spoken)
- Common collocations (e.g. "eine Entscheidung treffen" not "eine Entscheidung machen")
- Idiomatic expressions that don't decompose into individual words

---

## Summary Verdict

**Will your brain improve, maintain, or regress?**

**Improve — significantly, for reading comprehension and vocabulary breadth.** The three-card architecture, sentence variants, and progressive unsuspension are genuinely well-designed. You are building a broad, contextually flexible vocabulary with morphological awareness.

**Maintain — for grammatical metalanguage.** The grammar cards provide a reference framework but don't deeply integrate with vocabulary practice.

**Risk of stagnation — for listening, speaking, and sentence production.** The near-zero audio coverage and absence of production-beyond-word-level cards means your receptive visual skills will far outpace your other language skills. You'll be a strong reader who struggles in conversation.

**The single highest-impact change:** Get audio onto >80% of cards. Everything else is refinement; this is foundational.
