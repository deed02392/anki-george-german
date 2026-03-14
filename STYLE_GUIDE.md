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
| `--p1` | `#4fa3e0` | `#1a6fa8` | Phase 1 blue |
| `--p2` | `#3dbb72` | `#217a44` | Phase 2 green |
| `--p3` | `#f08030` | `#c05a00` | Phase 3 orange |
| `--p4` | `#9b59b6` | `#6c3483` | Phase 4 purple |
| `--disambig-fg/bg` | `#f08080` / `rgba(…0.08)` | `#c0302a` / `rgba(…0.07)` | Disambiguation "NOT:" text |
| `--note-fg/bg` | `#90c0a0` / `rgba(…0.08)` | `#2a7a4a` / `rgba(…0.07)` | Note/mnemonic text |
| `--accent-pfx` | `#c0a0e0` | `#7b5ea7` | Prefix card accent (defined in PREFIX_CLASSES) |

### Adding new note-type accents

Follow the prefix pattern: define `--accent-xxx` in the note-type's own CSS section with a `@media` light override. Choose a colour that doesn't clash with P1–P4 or `--accent-pfx`.

## Typography

- **Font family:** `"Noto Sans", sans-serif` — set on `.card`
- **Responsive sizing:** Always use `clamp(min, preferred, max)` for hero/heading text
- **Scale reference:**

| Element | Size | Weight |
|---------|------|--------|
| Hero word (`.word-de`) | `clamp(1.6rem, 6vw, 2.4rem)` | 700 |
| Secondary word (`.word-en`) | `clamp(1.4rem, 5vw, 2rem)` | 600 |
| Cloze sentence | `clamp(1rem, 3.5vw, 1.2rem)` | 500 |
| Sentence DE | `1.05rem` | normal |
| Sentence EN | `0.88rem` | normal, italic |
| IPA | `0.95rem` | normal |
| Badges/labels (`.card-type`, `.source-badge`) | `0.62rem` | 700, uppercase, tracked |
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
- Always set `box-sizing: border-box` on content containers
- `#qa` height chain is required for AnkiMobile

## Component Patterns

### Card header
```html
<div class="card-header">
  <div class="card-type">EN → DE</div>
  <\!-- optional: source badge, phase badge on right -->
</div>
```
- `0.62rem`, `font-weight: 700`, `letter-spacing: 0.10em`, `text-transform: uppercase`, `color: var(--subtext)`

### Divider
```html
<hr class="divider">
```
- `border-top: 1px solid var(--border)`, `margin: 16px 0`

### Badges (source/phase)
- Pill shape: `border-radius: 4px`, `padding: 2px 8px`
- `0.62rem`, `font-weight: 700`, `text-transform: uppercase`
- Background: phase colour variable, text: `#fff`

### Chip/tooltip backgrounds
- Use `var(--chip-bg)` for floating UI elements (tooltips, info chips)
- Text in chips: `var(--subtext)`

## Animations

### Focal urgency (10s timer)
- Two-step discrete colour shift: accent → amber (6–7s) → coral (9–10s)
- Applied via `.timed` class on the front card only
- Back cards have no urgency animation
- Keyframes: `urgency-de`, `urgency-en`, `urgency-blank`, `urgency-pfx`

### Tooltip entrance
- `opacity: 0 → 1`, `translateY(4px) → 0` over `200ms ease-out`
- No bounce, no overshoot

## Rules for New Card Types

1. **Use the shared base.** Compose CSS as `BASE_VARS + BASE_LAYOUT + YOUR_CLASSES`. Never duplicate base styles.
2. **Define a note-type accent.** Add `--accent-xxx` with dark/light values in your CSS section.
3. **Reuse component patterns.** Card header, dividers, badges should look identical across note types.
4. **Never style in isolation.** Always reference this guide and the existing token values.
5. **Test in review mode** on both Anki desktop and AnkiMobile, not just Browse → Preview.
6. **Mobile-first.** Use `clamp()` for text sizing. Test on narrow viewports.
7. **Push via `anki-german templates`.** Never edit templates in Anki's UI.
