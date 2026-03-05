# George's German Vocabulary — Project Notes

## What this repo now does

Originally this repo contained a single script (`disambiguate.py`) for identifying disambiguation gaps in the "German Vocabulary" deck. It has been extended with a three-agent pipeline that built a new deck, **"George's German Vocabulary"**, optimised for conversing with two native German-speaking children aged 4 and 6.

---

## Agent pipeline

Each agent owns its own directory under `agents/`. Scripts are rerunnable.

### Agent 1 — `agents/agent1_export/`
Exports the original "German Vocabulary" deck comprehensively:
- `export.py` — pulls all 4,028 notes and 8,055 cards via AnkiConnect, plus exports a full `.apkg` backup and cross-checks note count via the SQLite DB inside it
- `deck_export.json` — structured JSON of all notes with fields + scheduling data
- `german_vocabulary.apkg` — full deck backup including scheduling (203 MB, gitignored)
- `report.md` — summary statistics of the original deck

Key findings from the original deck: 4,028 notes, ~100% have sentences and IPA, Level field is entirely empty, only 3 unique tags used, 38.6% of cards were mature (>21 day interval).

### Agent 2 — `agents/agent2_vocab/`
Identifies which existing cards are relevant to child-conversation goals, and what's missing:
- `analyse.py` — keyword + regex matching across 15 domains, priority scoring 0–10
- `selected_cards.json` — 669 existing notes matched as child-relevant
- `new_vocab.json` — 72 net-new vocabulary items not in the original deck
- `report.md` — full analysis with phase recommendations

Domains covered: play, toys, food, family, school/kindergarten, animals, feelings, body, colours, numbers, greetings/social, questions, location, time, actions.

### Agent 3 — `agents/agent3_build/`
Designs the note type and builds the deck:
- `build.py` — creates the "George's German Vocab" note type and "George's German Vocabulary" deck via AnkiConnect, imports all 740 notes
- `fix_templates.py` — fixes applied after initial build (see Template fixes below)
- `backfill_scheduling.py` — ports scheduling state from original deck into new deck
- `build_data.json` — machine-readable build output
- `report.md` — card schema, sample cards, 4-milestone self-assessment framework

---

## The "George's German Vocab" note type

**Fields:** Word, POS, Article, WordTranslation, WordTranslationDisambiguate, IPA, Sentence, SentenceTranslation, Domains, Phase, Note

**Three card templates per note:**
1. **EN → DE** (Production) — English prompt, must produce German
2. **DE → EN** (Recognition) — German shown, must recall English
3. **Sentence Cloze** (Context) — sentence with target word blanked, JS-rendered from `Word` field

**Design decisions:**
- Dark/light mode via `prefers-color-scheme` CSS media query — switches automatically with macOS system appearance
- Phase badge (P1/P2/P3) rendered as a pure Mustache conditional `{{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}` — no JavaScript involved
- Timer ring (22px conic-gradient) in the card header, left of the phase badge — pure CSS, front templates only. See Timer ring section below.
- Cloze blanking done in JavaScript at render time by stripping the article from `Word` and regex-replacing the first match in `Sentence` — does NOT use Anki's native Cloze note type, which would preclude the other two templates

---

## Template fixes (applied after initial build)

The initial Agent 3 build had two bugs:

1. **`document.write()` destroyed card content.** The phase badge used `document.write()` inside a `{{#Phase}}` block. In Anki's WebKit renderer, `document.write()` called after page load truncates the document — everything after the script tag was wiped, leaving only the phase text visible. Fixed by replacing with a static Mustache span.

2. **`{{c1::word}}` syntax in Sentence fields caused validation errors.** Anki flags notes containing cloze syntax on non-Cloze note types. The 505 affected notes had `{{c1::word}}` stripped from their Sentence fields by `fix_templates.py`. The JS cloze rendering in the template reads the `Word` field directly, so no data was lost.

---

## Deck structure

| Phase | Notes | Focus |
|-------|-------|-------|
| P1    | 80    | Greetings, core feelings, highest-frequency play/food/action verbs |
| P2    | 87    | Numbers, animals, family, colours, common verbs, toys, location |
| P3    | 573   | Supplementary child-relevant vocabulary from the original deck |

Tags used: `child_vocab`, `phase::1` / `phase::2` / `phase::3`, `domain::play`, `domain::food`, etc.

---

## Scheduling backfill

`backfill_scheduling.py` matched new deck notes to the original deck by word (case-insensitive, article-stripped) and used AnkiConnect's `setDueDate` to promote previously-seen words to the review queue:

- **317 EN→DE cards** promoted to review queue (words seen in original deck with interval ≥1 day)
- **423 cards** left as new (unseen in original deck, or net-new vocab)

Only the EN→DE card per note was promoted. DE→EN and Sentence Cloze cards remain new/suspended to be activated per phase as proficiency builds.

**Important caveat — intervals were not restored:** `setDueDate "0"` promotes a card to the review queue due today but sets interval to 1 day regardless of the original value. All 317 backfilled cards therefore landed at interval <7 days rather than their original SM-2 intervals.

Attempting to correct this post-hoc via `setSpecificValueOfCard` (which can write `ivl`, `due`, `factor` directly) was ruled out because **FSRS had already been enabled** on the deck. FSRS uses its own internal state fields (`stability`, `difficulty`, `last_review`) that are decoupled from the SM-2 `ivl`/`factor` fields — overwriting those with stale SM-2 values would create inconsistent scheduler state. The correct approach is to leave the intervals as-is and let FSRS calibrate naturally from review responses. Words you know well will return to long intervals within 2–3 reviews; FSRS converges quickly.

**AnkiConnect allowList:** `setSpecificValueOfCard` was enabled in the AnkiConnect config for potential future use:
```json
"allowList": ["setSpecificValueOfCard"]
```
This is already applied to `addons21/2055492159/config.json`.

---

## Timer ring

The front of each card shows a small 22px conic-gradient ring in the header, left of the phase badge. Implemented in `agents/agent3_build/update_templates.py`.

- Pure CSS `@keyframes` — no JavaScript
- **3s** invisible lead-in (ring appears empty, giving time to read the card)
- **10s** sweep in phase colour (comfortable retrieval window)
- Colour shifts to amber at ~65% of the animation, red at ~93%
- Total duration: **16 seconds**
- Track is `transparent` so the ring is invisible when empty — no visible outline
- Not present on any back/reverse template; backs are fully self-contained HTML

---

## Mobile and responsive layout

The card CSS was reworked to fix several issues on AnkiMobile (iOS):

**Problems fixed:**
- Horizontal scrolling caused by `width: 100%` without `box-sizing: border-box` — padding was added on top of width, overflowing the viewport
- Asymmetric horizontal margins caused by Anki's hidden `body { margin: 20px }` in `reviewer.scss` conflicting with the card's own padding
- Vertical scrolling caused by `min-height: 100vh`/`100dvh`/`100svh` — all viewport units resolve to the full webview height, which extends behind Anki's UI chrome
- Tap targets near the screen bottom being intercepted by a `position: fixed` timer bar (since replaced by the in-flow timer ring)

**Current approach:**
- `html, body, #qa { margin: 0; height: 100%; }` — resets Anki's body margin and propagates the actual container height down the chain. `#qa` is the wrapper div AnkiMobile uses around card content.
- `min-height: 100%` on `.card` — resolves to the real usable height (not viewport height), enabling vertical centering without overflow
- `display: grid; align-content: center` on `.card` — vertically centres content. Grid was chosen over flexbox because `align-items: center` (flex) clips the top of tall cards. Block-level `align-content` (no grid) is too new for Anki's Chromium.
- `box-sizing: border-box` on `.kard` — ensures `width: 100%` includes padding
- `overflow-wrap: break-word` on sentence elements — prevents long German text from causing horizontal scroll
- Responsive font sizes via `clamp()` — e.g. `.word-de` uses `clamp(1.6rem, 6vw, 2.4rem)`
- Responsive padding via `clamp()` — `.kard` uses `padding-inline: clamp(16px, 5vw, 32px)`

**Note on Browse→Preview:** The preview pane is smaller than the full viewport, so `min-height: 100%` can produce extra space above content there. This only affects previewing — actual review sessions display correctly on both desktop and mobile.

## Progressive unsuspending

`unsuspend_candidates.py` at the repo root identifies suspended DE→EN and Sentence Cloze cards that are ready to activate based on EN→DE review maturity.

Thresholds:
- **DE→EN**: EN→DE interval ≥ 14 days and ease ≥ 2200
- **Sentence Cloze**: both EN→DE and DE→EN interval ≥ 21 days

Run weekly in dry-run mode (default), apply with `--apply`:
```
uv run unsuspend_candidates.py           # see candidates
uv run unsuspend_candidates.py --apply   # unsuspend them
```

Due to the interval backfill issue (all 317 backfilled cards landed at interval <7 days — see Scheduling backfill above), no candidates will appear until those cards have been reviewed and FSRS has pushed their intervals out. Expect DE→EN candidates to start appearing after 2–3 weeks of regular review.

---

## Recommended study workflow

### Phase approach
Start with only Phase 1 EN→DE cards active. In Anki Browser:
```
deck:"George's German Vocabulary" card:"EN → DE" tag:phase::1
```
Unsuspend only these. Keep DE→EN and Sentence Cloze suspended until Phase 1 EN→DE retention is consistently >85%.

### Daily limits
- New cards: 10–15/day
- Always clear reviews before introducing new cards
- Cap sessions at 20–30 minutes

### Phase progression (approximate)

| Weeks | Active cards | Goal |
|-------|-------------|------|
| 1–2   | P1 EN→DE (~80) | Greetings, feelings, core verbs |
| 3–4   | + P2 EN→DE (~87) | Animals, food, family, numbers |
| 5–6   | Unsuspend DE→EN for P1+P2 | Add recognition direction |
| 7–8   | Unsuspend Cloze for P1 | Context and sentence fluency |

### FSRS
FSRS is enabled. Set Desired Retention to **0.85** in deck options. Run "Optimise" after ~2 weeks of review data has accumulated.

FSRS is meaningfully better than SM-2 for language learning because it models retrievability per card rather than applying a uniform ease factor. Due to the backfill limitation, FSRS has no prior history to work from — it will calibrate from scratch based on your responses, which typically converges within a few weeks.

### Self-assessment milestones
See `agents/agent3_build/report.md` for the full 4-milestone framework (weeks 2, 4, 6, 8). The headline test: can you sustain a 5-minute back-and-forth with the children about one of the target domains without pausing to think?
