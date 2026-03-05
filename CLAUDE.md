# Claude Session Context

## Project Overview
Three-agent pipeline building a German vocabulary Anki deck for children (ages 4–6). See `NOTES.md` for full documentation.

## Critical Files & Execution Order

**DO NOT edit these files directly unless you know the execution order:**

1. `agents/agent3_build/build.py` — Creates note type and imports notes
2. `agents/agent3_build/fix_templates.py` — Fixes applied after build (cloze cleanup, dark/light mode)
3. `agents/agent3_build/update_templates.py` — **LIVE SOURCE OF TRUTH** for CSS and templates

Each script supersedes the previous one. **Always run `update_templates.py` last** if you modify templates or CSS, or your changes will be overwritten.

## Timer Implementation

The timer uses **focal urgency** — the word you're looking at shifts colour over 10s:
- `.word-de.timed` / `.word-en.timed` on front templates animate via `@keyframes urgency-de` / `urgency-en`
- `.cloze-blank` animates automatically via `@keyframes urgency-blank` (border + subtle bg tint)
- Two discrete steps: accent holds 0–6s, snaps to amber 6–7s, holds 7–9s, snaps to coral 9–10s, then `forwards` holds coral
- No JavaScript, no timer ring — purely CSS `@keyframes` on `color` / `border-bottom-color`
- Back templates have no urgency animation

See `update_templates.py` lines 119–142 for the urgency CSS.

## Card Layout — Key Decisions and Lessons Learned

The layout went through extensive iteration. Here's what works and why:

### What's live (working on both desktop and mobile)

```css
body { margin: 0; }                          /* override Anki's 20px body margin */
html, body, #qa { margin: 0; height: 100%; } /* propagate height for centering */
.card { min-height: 100%; display: grid; align-content: center; }
.kard { box-sizing: border-box; max-width: 560px; width: 100%; }
```

### Anki's rendering environment

- **Anki's reviewer injects `body { margin: 20px }`** via `reviewer.scss`. This must be overridden to `0` in our card CSS, otherwise it creates asymmetric-looking margins and eats into content width.
- **AnkiMobile wraps card content in a `#qa` div.** Setting `height: 100%` on `html`, `body`, AND `#qa` is required for `min-height: 100%` to resolve on `.card`.
- **`position: fixed` is broken on AnkiMobile** — fixed elements are relative to `#qa`, not the viewport.
- **`env(safe-area-inset-*)` returns 0** on AnkiMobile because the webview doesn't set `viewport-fit=cover`.

### Viewport units — what was tried and why they failed

| Unit | Desktop | Mobile (review) | Mobile (Browse→Preview) |
|------|---------|-----------------|-------------------------|
| `100vh` | Works | Too tall (includes space behind OS chrome) | Way too tall |
| `100dvh` | Works | Same as vh in Anki's webview | Way too tall |
| `100svh` | Works | Works | Way too tall |
| `100%` (without height chain) | No centering (resolves to 0) | No centering | No centering |
| `100%` (with `html,body,#qa { height:100% }`) | **Works** | **Works** | Too tall but acceptable |

**`min-height: 100%` with the full height chain is the correct solution.** It resolves to the actual container height on both platforms. Browse→Preview will show extra space because the preview pane is smaller than the viewport, but actual review sessions are correct — and that's what matters.

### Vertical centering

- **`display: grid; align-content: center`** on `.card` — works correctly.
- **`align-items: center` (flex)** was tried first but clips the top of tall cards (content pushed above viewport with no way to scroll up).
- **`margin: auto` on `.kard`** doesn't work with `align-items: stretch` (flex stretches the child, leaving no space for auto margins).
- **`place-content: center` (grid)** centres both axes but shrinks the grid column to content width, breaking horizontal layout.
- **Block-level `align-content: center`** (no grid/flex) is too new for Anki's embedded Chromium.

### Horizontal sizing

- **`box-sizing: border-box` on `.kard` is essential.** Without it, `width: 100%` is the content width, and padding is added on top — causing horizontal overflow (the `<hr>` divider made this especially visible).
- **`overflow-wrap: break-word`** on sentence elements prevents long German compounds from causing horizontal scroll.
- **Font sizes use `clamp()`** for responsive scaling: e.g. `.word-de` is `clamp(1.6rem, 6vw, 2.4rem)`.
- **Cloze sentence** font size is a CSS class `.cloze-sentence` (not an inline style) using `clamp(1rem, 3.5vw, 1.2rem)`.
- **Font stack** is `"Noto Sans", sans-serif` — no backward-compat fallbacks needed.

### What NOT to do

- **Don't use `margin: -20px`** to counteract body margin — it expands `.card` beyond the viewport.
- **Don't use `@media (min-width: ...)` to conditionally apply `min-height`** — fragile, device-dependent.
- **Don't remove `min-height` after confirming it works** — the `html,body,#qa { height:100% }` chain is not a "hack", it's required for `100%` to resolve.
- **Don't use inline `style="font-size:..."` on template elements** when a CSS class can handle it responsively.

## Before Touching Templates or CSS

1. Read `NOTES.md` (especially sections on timer, template fixes, and phase structure)
2. The authoritative file for all CSS and templates is `update_templates.py`
3. After editing, run the script to push changes to Anki via AnkiConnect
4. Test in **actual review mode** on mobile, not just Browse→Preview (viewport units behave differently in the preview pane)
5. Never manually edit templates in Anki's UI — they'll be overwritten on next script run

## AnkiWeb

AnkiWeb (browser-based review at ankiweb.net) has known rendering differences:
- The card is a `<div>` inside a full webpage, not its own webview — so `html`/`body` selectors affect the whole page
- `background: var(--bg)` on `.card` colours only the card box, not the surrounding AnkiWeb UI
- `min-height: 100%` doesn't behave the same — the container height model differs
- The parent container likely grows with content (not fixed-height), so a `height`-based approach may work if this is ever worth fixing
- George doesn't review on AnkiWeb so this is low priority

## AnkiConnect Setup

- Requires Anki running with AnkiConnect add-on (2055492159)
- Default URL: `http://localhost:8765`
- `setSpecificValueOfCard` is allowlisted in config for future use

## Wiktionary Enrichment (`enrich_from_wiktionary.py`)

Script that fetches IPA transcriptions and audio from German Wiktionary for notes missing them. Based on the earlier `add_ipa_legacy.py` but adapted for the new deck's field names and extended with audio support.

### Note type changes

An `Audio` field was added after `IPA` (13 fields total, including ClozeWord). Both `build.py` and `update_templates.py` have been updated to include it.

### Template audio placement

Audio auto-plays via Anki's `[sound:...]` syntax using `{{#Audio}}{{Audio}}{{/Audio}}`:
- **EN→DE Back** — hear the word after answering (production reinforcement)
- **DE→EN Front** — hear the word as a prompt (recognition)
- **Cloze Front** — hear the word as a prompt
- DE→EN Back and Cloze Back have no audio (already heard on front)

### Current state (as of 2026-03-05)

- **IPA**: 713/740 notes have IPA. The 27 missing are phrases (greetings, questions like "Wie heißt du?") that have no Wiktionary page. Only `Lego` (brand name) was a single word without a German Wiktionary entry.
- **Audio**: 16/740 notes have audio (mp3 format). Remaining ~700 still need downloads — blocked by `upload.wikimedia.org` rate limiting (429 with `Retry-After: 60`).
- **Format**: All audio stored as `.mp3` (converted from Wiktionary's `.ogg` via ffmpeg) for iOS/AnkiMobile compatibility. The enrichment script handles ogg→mp3 conversion automatically.

### How the script works

1. Queries AnkiConnect for notes with empty IPA or Audio
2. Strips articles (der/die/das) from the Word field to get the lookup word
3. Skips phrases (words containing spaces, `?`, `!`, `...`)
4. Fetches wikitext from `de.wiktionary.org` (falls back to lowercase if needed, e.g. Tschüss → tschüss)
5. Extracts the German section (`{{Sprache|Deutsch}}`), then the `{{Aussprache}}` block to avoid matching IPA/audio from other languages (e.g. Danish on the "orange" page) or prose
6. Extracts IPA via `{{Lautschrift|...}}` regex
7. Extracts audio filename via `{{Audio|...ogg}}` regex
8. Downloads audio from Wikimedia Commons using MD5-based URL (no API call needed)
9. Converts ogg to mp3 via ffmpeg (required for iOS/AnkiMobile compatibility)
10. Stores mp3 in Anki via `storeMediaFile` and updates fields

### Usage

```sh
python3 enrich_from_wiktionary.py --ipa-only     # fast, no rate limit issues
python3 enrich_from_wiktionary.py --audio-only    # slow due to Wikimedia rate limits
python3 enrich_from_wiktionary.py --dry-run       # preview without changes
python3 enrich_from_wiktionary.py --audio-delay 65 # customise delay between downloads
```

### Rate limiting problem

`upload.wikimedia.org` aggressively rate-limits audio downloads — returns 429 after 2–3 requests regardless of delay. The `Retry-After` header says 60s. The Wiktionary parse API (`de.wiktionary.org/w/api.php`) has no such issue. Requires a `User-Agent` header (Wikimedia policy).

### Wiktionary wikitext edge cases handled

- **Multi-language pages** (e.g. "orange" has German, Danish, English): extract `{{Sprache|Deutsch}}` section only
- **Prose Lautschrift** (e.g. "orange" has `{{Lautschrift|…ʃ}}` in an annotation paragraph): restrict search to `{{Aussprache}}` block
- **Case sensitivity** (e.g. "Tschüss" exists as "tschüss"): automatic lowercase fallback
- **Non-German-only pages** (e.g. "lego" is only Italian/Latin/Spanish): require `{{Sprache|Deutsch}}` in wikitext

## ClozeWord Field & Cloze Matching (`backfill_clozeword.py`)

The cloze card JS originally matched the dictionary form (e.g. "rennen") against the sentence, but German morphology changes forms (e.g. "rannte") and separable verbs split ("aufspringen" → "sprang...auf"). This broke 235/740 cloze cards.

### Solution

A `ClozeWord` field (index 8, after Sentence) stores the exact text to blank in the sentence. The `|` separator handles separable verbs: `sprang|auf` blanks both parts independently.

**Field position in note type** (13 fields total): Word, POS, Article, WordTranslation, WordTranslationDisambiguate, IPA, Audio, Sentence, **ClozeWord**, SentenceTranslation, Domains, Phase, Note

### Cloze JS logic (in `update_templates.py`)

1. Read `{{ClozeWord}}`; if non-empty, use it (case-sensitive match)
2. If empty, fall back to `{{Word}}` with article stripping (case-insensitive match)
3. Split on `|`, blank each part independently in the sentence

### Backfill matching cascade

1. **Exact match** — bare word found verbatim in sentence
2. **Annotation stripping** — remove `(sich)`, `(r, s)`, `OR ...`, `...`
3. **Phrase template** — `Wo ist ...?` → strip `...` and punctuation, match core words
4. **Umlaut/plural** — try a→ä, o→ö, u→ü + common plural suffixes
5. **Separable verb** — detect prefix (ab/an/auf/aus/etc.), fuzzy-match stem, verify prefix at clause end
6. **Fuzzy match** — rapidfuzz.fuzz.ratio ≥65 threshold against sentence tokens

### Usage

```sh
python3 backfill_clozeword.py --dry-run          # preview matches
python3 backfill_clozeword.py                     # apply
python3 backfill_clozeword.py --verify            # check ClozeWord parts exist in sentences
python3 backfill_clozeword.py --overrides fix.json # apply manual corrections
```
