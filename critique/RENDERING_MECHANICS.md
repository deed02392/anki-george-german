# Card Rendering Mechanics — Technical Deep Dive

How each card is constructed at render time by the JavaScript in `update_templates.py`.

---

## The Variant System

### Data Model

Each note stores multiple sentence variants in pipe-delimited fields:

```
Sentence:            "Die Polizei fängt den Einbrecher.|Wir fangen bunte Schmetterlinge.|Die Kinder spielen Fangen."
ClozeWord:           "fängt|fangen|Fangen"
ClozeHint:           "Präsens · er/sie/es|Präsens · 1. Person Plural|Substantivierter Infinitiv"
SentenceTranslation: "The police catch the burglar.|We catch colourful butterflies.|The children play catch."
POS:                 "verb|verb|verb"
```

### Variant Selection (Front)

On the front card, JavaScript picks a random index and stores it:

```javascript
var idx = Math.floor(Math.random() * sentences.length);
try { sessionStorage.setItem("v_" + "{{Word}}", idx); } catch(e) {}
```

All variant-indexed fields (Sentence, SentenceTranslation, POS, ClozeWord, ClozeHint) use this same index.

### Variant Consistency (Back)

On the back card, JavaScript reads the stored index:

```javascript
var idx;
try { idx = parseInt(sessionStorage.getItem("v_" + "{{Word}}")); } catch(e) {}
if (isNaN(idx) || idx < 0 || idx >= sentences.length)
    idx = Math.floor(Math.random() * sentences.length);
```

**Failure mode:** If sessionStorage fails (private browsing, AnkiMobile limitations), the back card picks a RANDOM variant that may differ from the front. The code handles this gracefully with a fallback, but the front-back inconsistency is a known limitation.

**AnkiMobile note:** sessionStorage persists within a review session on AnkiMobile but is cleared between sessions. Within a single review session, front-back consistency is maintained.

---

## Cloze Rendering

### Front Card (Blanking)

The cloze JS (`cloze_picker_js` with `span_class="cloze-blank"`):

1. Splits `{{Sentence}}` and `{{ClozeWord}}` by `|`
2. Selects variant `idx`
3. Splits the cloze word by `~` (separable verb delimiter)
4. For each part, builds a regex with word-boundary lookarounds:
   ```javascript
   var L = "[A-Za-z\\u00C0-\\u024F]";
   result = result.replace(
       new RegExp("(?<!" + L + ")" + escaped + "(?!" + L + ")", caseSensitive ? "" : "i"),
       '<span class="cloze-blank">$&</span>'
   );
   ```
5. The `cloze-blank` span has `color: transparent; user-select: none;` — the text is there but invisible
6. The blank has `min-width: 2.5em` and a bottom border that animates with urgency

**Key detail:** The word is NOT replaced with underscores — the actual text is rendered but made invisible. This means the blank width subtly hints at word length (longer words create wider blanks).

### Back Card (Revealing)

The back cloze JS uses `span_class="cloze-answer"`:
- Same regex replacement, but the span makes the word **bold and coloured** instead of invisible
- The `cloze-answer` class: `color: var(--accent-de); font-weight: 700; border-bottom: 2px solid;`

### Separable Verb Example

For `machte~auf` in sentence "Er machte die Tür auf":
- Part 1: "machte" → found and blanked/revealed
- Part 2: "auf" → found and blanked/revealed
- Result: "Er _____ die Tür _____" (two separate blanks)

### Fallback Behaviour

If `{{ClozeWord}}` is empty, the JS falls back to stripping the article from `{{Word}}`:
```javascript
if (!clozeWord) {
    clozeWord = "{{Word}}".replace(/^(der|die|das|ein|eine)\s+/i, "").trim();
    caseSensitive = false;
}
```
This case-insensitive fallback is less precise but ensures the card still works.

---

## ClozeHint Tooltip

### Where It Appears

**ONLY on the back card** (`CLOZE_BACK`). The front card does NOT render hints.

### Rendering Logic

After the cloze replacement, if `{{ClozeHint}}` has a value for the selected variant:

1. Finds the first `.cloze-answer` span in the sentence
2. Wraps it in a `cloze-hint-trigger` span
3. Appends a `cloze-hint-tooltip` element (positioned absolutely above the word)
4. Adds mouse hover + touch event handlers for show/hide

### Tooltip Styling

```css
.cloze-hint-tooltip {
    position: absolute;
    bottom: calc(100% + 8px);     /* floats above the word */
    font-size: 0.72rem;
    font-variant: small-caps;
    padding: 5px 12px;
    border-radius: 999px;         /* pill shape */
    background: var(--chip-bg);
    transition: opacity 200ms;    /* fade in */
}
```

With a CSS caret arrow pointing down to the word.

---

## Source Badge Rendering

The source badge uses JavaScript to extract the `source::X` tag:

```javascript
var tags = "{{Tags}}";
var m = tags.match(/source::([^\s]+)/);
if (m) {
    var s = m[1];
    el.textContent = s.replace(/_/g, " ");
    var h = 0;
    for (var i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    el.className = "source-badge source-" + ((Math.abs(h) % 4) + 1);
}
```

The colour class (`source-1` through `source-4`) is determined by a hash of the source name, mapping to `--p1` through `--p4` (blue, green, orange, purple).

---

## Grammar Example Card — Random Selection

The `GRAM_EXAMPLE_FRONT` template has inline JS that:

1. Finds all `.example-item` elements within the examples div
2. Picks one randomly: `var idx = Math.floor(Math.random() * items.length);`
3. Hides all others: `if (i !== idx) item.style.display = "none";`

This means you only see ONE example per review, forcing recall of the grammar term from a single contextual clue.

---

## FSRS Integration

The deck uses FSRS (Free Spaced Repetition Scheduler) instead of SM-2. FSRS is enabled at the Anki level, not in the card templates. Key implications:

- The `factor` field in card data is an SM-2 artifact; FSRS uses its own stability/difficulty model
- Interval scheduling is handled by FSRS's neural network, not the traditional ease factor
- The unsuspend thresholds (14d, 21d interval) still work because FSRS exposes `interval` through AnkiConnect
- "Easy" button in FSRS has a different effect than in SM-2 — it increases stability more aggressively

---

## Data Flow: From Generation to Review

```
Text file → spaCy tokenize → filter known words → compound check
    ↓
LLM enriches batch → validate cloze substrings → normalise articles
    ↓
Import via addNotes (all cards created suspended)
    ↓
IPA enrichment (Wiktionary + LLM fallback)
    ↓
ClozeHint enrichment (LLM batch)
    ↓
Manual unsuspend of EN→DE cards (or weekly auto-unsuspend)
    ↓
Review cycle begins:
  EN→DE active → after 14d interval → DE→EN unsuspended
                → after 21d on both → Cloze unsuspended
```

Each stage adds data to the note but never modifies the card templates. The templates are static HTML+JS that read fields at render time.
