# Style Guide — George's German Vocabulary

Reference for all card design work. The authoritative source is `anki_george_german/update_templates.py`.

## Design Tokens

All colours use CSS variables defined in `BASE_VARS`. Dark mode is the default; light mode overrides via `@media (prefers-color-scheme: light)`.

**Never hardcode colours.** Always use `var(--token-name)`. If no token fits, add a new one to `BASE_VARS` with both dark and light values.

| Token | Dark | Light | Purpose |
|-------|------|-------|---------|
| `--bg` | `#1a1a2e` | `#f5f7fa` | Page background |
| `--surface` | `#16213e` | `#ffffff` | Card/panel surface |
| `--text` | `#e0e0e0` | `#1a1a2e` | Primary body text |
| `--text-de` | `#a8d4e8` | `#2a5a7a` | German text (sentences, examples) |
| `--subtext` | `#8892a4` | `#5a6478` | Muted/secondary text (IPA, hints, metadata) |
| `--border` | `rgba(255,255,255,0.08)` | `rgba(0,0,0,0.10)` | Dividers, borders |
| `--accent-de` | `#7ec8e3` | `#1a6fa8` | German word accent (headwords, cloze answers) |
| `--accent-en` | `#f5c842` | `#b07800` | English word accent |
| `--chip-bg` | `#2e3a5a` | `#dde3ef` | Chip/badge/tooltip backgrounds |
| `--cloze-text` | `#b0d0e4` | `#1a3a5e` | Cloze sentence text |
| `--p1`–`--p4` | blue/green/orange/purple | darker variants | Source badge colour hashing |
| `--disambig-fg/bg` | `#f08080` / `rgba(…0.08)` | `#c0302a` / `rgba(…0.07)` | Disambiguation "NOT:" callout |
| `--note-fg/bg` | `#90c0a0` / `rgba(…0.08)` | `#2a7a4a` / `rgba(…0.07)` | Note callout |
| `--accent-pfx` | `#c0a0e0` | `#7b5ea7` | Prefix card accent |
| `--accent-gram` | `#5bbfb5` | `#2a8a7e` | Grammar card accent |

### Adding new note-type accents

Define `--accent-xxx` in the note-type's own CSS section with a `@media` light override. Then bind shared classes to it: `.hero.xxx { color: var(--accent-xxx); }` etc.

## Typography

- **Font family:** `"Noto Sans", sans-serif` — set on `.card`
- **Responsive sizing:** Always use `clamp(min, preferred, max)` for hero/heading text
- **Scale reference:**

| Element | Size | Weight |
|---------|------|--------|
| Hero (`.hero`) | `clamp(2.2rem, 8vw, 3.2rem)` | 800 |
| Vocab word DE (`.word-de`) | `clamp(1.6rem, 6vw, 2.4rem)` | 700 |
| Sub-hero (`.sub-hero`) | varies by note type | 600 |
| Vocab word EN (`.word-en`) | `clamp(1.4rem, 5vw, 2rem)` | 600 |
| Cloze sentence | `clamp(1rem, 3.5vw, 1.2rem)` | 500 |
| Examples (`.examples`) | `0.92rem` | normal |
| Sentence DE | `1.05rem` | normal |
| Sentence EN | `0.88rem` | normal, italic |
| Hint text (`.hint-text`) | `0.88rem` | normal, italic |
| IPA | `0.95rem` | normal |
| Callout (`.callout`) | `0.80rem` | normal |
| Badges (`.card-type`, `.type-tag`, `.source-badge`) | `0.62rem` | 700, uppercase, tracked |
| POS hint | `0.78rem` | normal, italic |
| Tooltip (`.cloze-hint-tooltip`) | `0.72rem` | 500, small-caps |

## Layout

```css
html, body, #qa { margin: 0; height: 100%; }    /* Reset Anki's margin */
.card  { min-height: 100%; display: grid; align-content: center; }
.kard  { box-sizing: border-box; max-width: 560px; width: 100%; margin: 0 auto; padding: 24px clamp(16px, 5vw, 32px) 28px; }
```

- `.card` = full-viewport grid container (centering)
- `.kard` = content container (max-width, padding)
- `#qa` height chain is required for AnkiMobile

## Shared Component Classes

These live in `BASE_LAYOUT` and are available to all note types.

### `.hero` — Large centred display
Used for the primary element on front cards (prefix, grammar term). Note-type modifier sets colour:
```html
<div class="hero pfx timed">{{Prefix}}-</div>
<div class="hero gram">{{Term}}</div>
```

### `.sub-hero` — Medium centred display
Used for secondary hero content (meaning, definition). Note-type modifier sets colour and font-size override:
```html
<div class="sub-hero pfx">{{CoreMeaning}}</div>
<div class="sub-hero gram">{{Definition}}</div>
```

### `.type-tag` — Uppercase label
Used for category/type labels below or above hero content:
```html
<div class="type-tag">{{PrefixType}}</div>
<div class="type-tag">{{Category}}</div>
```

### `.hint-text` — Muted italic hint
Used for supplementary text (spatial sense, formation pattern):
```html
<div class="hint-text">{{SpatialSense}}</div>
<div class="hint-text">{{Formation}}</div>
```

### `.examples` + `.hl` — Example block with highlights
Used for example lists. The `.hl` span highlights the relevant part in the note-type accent colour:
```html
<div class="examples">
  <span class="hl pfx">auf</span>machen — to open
</div>
```
For multiple examples, wrap each in `.example-item`:
```html
<div class="examples">
  <div class="example-item">Er <span class="hl gram">öffnete</span> die Tür.</div>
  <div class="example-item">Sie <span class="hl gram">spielte</span> Klavier.</div>
</div>
```

### `.callout` — Bordered callout box
Base class with modifiers for colour:
```html
<div class="callout callout-disambig">NOT: {{WordTranslationDisambiguate}}</div>
<div class="callout callout-note">{{Note}}</div>
```

### Card header + divider
```html
<div class="card-header">
  <div class="card-type">Grammar</div>
</div>
<hr class="divider">
```

## Animations

### Focal urgency (10s timer)
- Two-step discrete colour shift: accent → amber (6–7s) → coral (9–10s)
- Applied via `.timed` class on the front card only
- Back cards have no urgency animation
- Keyframes in BASE_LAYOUT: `urgency-de`, `urgency-en`, `urgency-blank`
- Note-type keyframes: `urgency-pfx`, `urgency-gram` (start from their accent colour)

### Tooltip entrance
- `opacity: 0 → 1`, `translateY(4px) → 0` over `200ms ease-out`
- No bounce, no overshoot

## Rules for New Card Types

1. **Use the shared base.** Compose CSS as `BASE_VARS + BASE_LAYOUT + YOUR_CLASSES`. Never duplicate base styles.
2. **Use shared component classes.** `.hero`, `.sub-hero`, `.type-tag`, `.hint-text`, `.examples`, `.callout` — add a note-type modifier class for colour only.
3. **Define a note-type accent.** Add `--accent-xxx` with dark/light values. Bind via `.hero.xxx`, `.sub-hero.xxx`, `.examples .hl.xxx`.
4. **Add a urgency keyframe** starting from your accent colour, bind via `.hero.xxx.timed`.
5. **Never style in isolation.** Always reference this guide and the existing token values.
6. **Test in review mode** on both Anki desktop and AnkiMobile, not just Browse → Preview.
7. **Mobile-first.** Use `clamp()` for text sizing. Test on narrow viewports.
8. **Push via `anki-german templates`.** Never edit templates in Anki's UI.
