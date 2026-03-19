# George's German Vocabulary — Project Notes

## What this repo does

An installable Python package (`anki-german` CLI) that generates, enriches, and manages a German vocabulary Anki deck for an adult learner. Vocabulary is extracted from German texts (literature, articles) and domain briefs using an LLM-powered pipeline with spaCy NLP, then pushed to Anki via AnkiConnect.

The deck currently has ~1,141 vocab notes (4 card templates each), 21 prefix notes, and grammar term notes.

---

## Historical context

The repo originally contained a single script (`disambiguate.py`). It was extended with a three-agent pipeline (`agents/agent1_export/`, `agent2_vocab/`, `agent3_build/`) that built an initial 740-note deck from an older "German Vocabulary" deck, selecting child-conversation-relevant cards and creating a new note type. That agent code has since been archived to `pipeline/archive/` and the project restructured as an installable Python package under `anki_george_german/`.

Key facts from the original build:
- 4,028 notes in the original deck, ~100% had sentences and IPA
- 669 existing notes matched as relevant, 72 net-new items generated
- Scheduling state was backfilled via `setDueDate` (intervals not fully preserved due to FSRS)

---

## The "George's German Vocab" note type

**12 fields:** Word, POS, Article, WordTranslation, WordTranslationDisambiguate, IPA, Audio, Sentence, ClozeWord, ClozeHint, SentenceTranslation, Note

**Four card templates per note:**
1. **EN → DE** (Production) — English prompt, produce the German word
2. **DE → EN** (Recognition) — German word shown, recall the English
3. **Sentence Cloze** (Context) — sentence with target word blanked (JS-rendered from `ClozeWord` field)
4. **Listening** (Auditory) — audio-only front with "Hör zu." prompt, POS hint. Only generates when Audio field is populated. Gated on DE→EN interval ≥ 21 days.

**Design decisions:**
- Dark/light mode via `prefers-color-scheme` CSS media query
- Focal urgency animation — the word shifts colour over 10s (accent → amber → coral) via pure CSS `@keyframes`. Front templates only.
- Cloze blanking reads the `ClozeWord` field and blanks matching text in the `Sentence` field at render time via JavaScript. Does NOT use Anki's native Cloze note type (which would preclude the other templates).
- `ClozeWord` stores the exact inflected text to blank. `~` separates parts for separable verbs (`machte~auf`), `|` separates sentence variants.
- Source badges on back cards show the origin of each card (e.g. `schachnovelle`, `it_security`).

---

## Prefix note type ("German Prefix")

21 cards in sub-deck `George's German Vocabulary::Prefixes`. 5 fields: Prefix, PrefixType, CoreMeaning, SpatialSense, Examples.

2 card templates: Prefix → Meaning, Meaning → Prefix.

---

## Grammar note type ("German Grammar Term")

Grammar term cards in sub-deck `George's German Vocabulary::Grammar`. 2 card templates: Term → Definition, Example → Term.

---

## Focal urgency

Instead of a separate timer widget, the focal element itself (the word or cloze blank) shifts colour over time to hint at retrieval difficulty. Implemented in `anki_george_german/update_templates.py`.

- Pure CSS `@keyframes` — no JavaScript
- **10 seconds** total animation, two discrete colour steps:
  - **0–6s** (0–60%): accent colour holds (reading and initial recall)
  - **6–7s** (60–70%): rapid snap to amber/orange
  - **7–9s** (70–90%): amber holds (retrieval effort zone)
  - **9–10s** (90–100%): rapid snap to coral — `animation-fill-mode: forwards` holds it permanently
- `.word-de.timed` and `.word-en.timed` classes on front templates trigger the animation
- `.listen-prompt.timed` animates via `@keyframes urgency-listen` (slate blue → amber → coral)
- `.cloze-blank` animates automatically (border colour + subtle background tint)
- Not present on any back template
- Dark/light mode handled automatically since `--accent-de`/`--accent-en` resolve differently per scheme

---

## Mobile and responsive layout

The card CSS was reworked to fix several issues on AnkiMobile (iOS):

**Problems fixed:**
- Horizontal scrolling caused by `width: 100%` without `box-sizing: border-box`
- Asymmetric horizontal margins caused by Anki's hidden `body { margin: 20px }`
- Vertical scrolling caused by `min-height: 100vh`/`100dvh`/`100svh` — all viewport units resolve to the full webview height, which extends behind Anki's UI chrome

**Current approach:**
- `html, body, #qa { margin: 0; height: 100%; }` — resets Anki's body margin and propagates the actual container height. `#qa` is the wrapper div AnkiMobile uses.
- `min-height: 100%` on `.card` — resolves to the real usable height, enabling vertical centering without overflow
- `display: grid; align-content: center` on `.card` — vertically centres content. Grid was chosen over flexbox because `align-items: center` (flex) clips the top of tall cards.
- `box-sizing: border-box` on `.kard` — ensures `width: 100%` includes padding
- `overflow-wrap: break-word` on sentence elements
- Responsive font sizes via `clamp()` — e.g. `.word-de` uses `clamp(1.6rem, 6vw, 2.4rem)`
- Responsive padding via `clamp()` — `.kard` uses `padding-inline: clamp(16px, 5vw, 32px)`

**Note on Browse→Preview:** The preview pane is smaller than the full viewport, so `min-height: 100%` can produce extra space above content there. This only affects previewing — actual review sessions display correctly on both desktop and mobile.

---

## Progressive unsuspending

`anki_george_german/unsuspend_candidates.py` identifies suspended cards ready to activate based on review maturity.

**Thresholds (interval-based only):**
- **DE→EN**: EN→DE interval ≥ 14 days
- **Sentence Cloze**: both EN→DE and DE→EN interval ≥ 21 days
- **Listening**: DE→EN interval ≥ 21 days

Run via CLI:
```sh
anki-german unsuspend           # dry run (default)
anki-german unsuspend --apply   # actually unsuspend
anki-german unsuspend --max 10  # cap unsuspensions per batch
```

A launchd agent can automate weekly unsuspension:
```sh
anki-german schedule install --day MON --hour 9 --max 5
anki-german schedule status
anki-german schedule uninstall
```

---

## FSRS

FSRS is enabled on the deck. Set Desired Retention to **0.85** in deck options. Run "Optimise" periodically as review data accumulates. FSRS models retrievability per card rather than applying a uniform ease factor, and converges quickly from review responses.

---

## Template fixes (historical)

The initial build had two bugs, both long since fixed:

1. **`document.write()` destroyed card content.** The phase badge used `document.write()` inside a `{{#Phase}}` block, which truncated the document in Anki's WebKit renderer. Fixed by replacing with static HTML.

2. **`{{c1::word}}` syntax in Sentence fields caused validation errors.** Anki flags cloze syntax on non-Cloze note types. The affected notes had the syntax stripped. The JS cloze rendering reads the `ClozeWord` field directly, so no data was lost.

The Phase and Domains fields were later removed entirely as unused clutter.
