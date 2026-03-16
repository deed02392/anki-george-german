#!/usr/bin/env python3
"""
Update card CSS and templates for ALL note types via AnkiConnect.

This is the LIVE SOURCE OF TRUTH for all card styling and template HTML.
Run this script after any template/CSS change to push to Anki.

Note types managed:
  1. "George's German Vocab"    — vocabulary cards (EN→DE, DE→EN, Cloze)
  2. "German Prefix"            — prefix teaching cards (Prefix→Meaning, Meaning→Prefix)
  3. "German Grammar Term"      — grammar term cards (Term→Definition, Example→Term)
"""

from ._anki import anki


# ══════════════════════════════════════════════════════════════════════════════
# CSS — shared base
# ══════════════════════════════════════════════════════════════════════════════

BASE_VARS = """
/* ── Design tokens (dark default, light override) ── */

:root {
  --bg:         #1a1a2e;
  --surface:    #16213e;
  --text:       #e0e0e0;
  --text-de:    #a8d4e8;
  --subtext:    #8892a4;
  --border:     rgba(255,255,255,0.08);
  --accent-de:  #7ec8e3;
  --accent-en:  #f5c842;
  --p1:         #4fa3e0;
  --p2:         #3dbb72;
  --p3:         #f08030;
  --p4:         #9b59b6;
  --disambig-fg:#f08080;
  --disambig-bg:rgba(240,128,128,0.08);
  --note-fg:    #90c0a0;
  --note-bg:    rgba(144,192,160,0.08);
  --chip-bg:    #2e3a5a;
  --cloze-text: #b0d0e4;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg:         #f5f7fa;
    --surface:    #ffffff;
    --text:       #1a1a2e;
    --text-de:    #2a5a7a;
    --subtext:    #5a6478;
    --border:     rgba(0,0,0,0.10);
    --accent-de:  #1a6fa8;
    --accent-en:  #b07800;
    --p1:         #1a6fa8;
    --p2:         #217a44;
    --p3:         #c05a00;
    --p4:         #6c3483;
    --disambig-fg:#c0302a;
    --disambig-bg:rgba(192,48,42,0.07);
    --note-fg:    #2a7a4a;
    --note-bg:    rgba(42,122,74,0.07);
    --chip-bg:    #dde3ef;
    --cloze-text: #1a3a5e;
  }
}
"""

BASE_LAYOUT = """
/* ── Reset & grid centering ── */

/* Override Anki's reviewer body { margin: 20px } so we control all spacing */
html, body, #qa { margin: 0; height: 100%; }

.card {
  font-family: "Noto Sans", sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100%;
  margin: 0; padding: 0;
  display: grid;
  align-content: center;
}

.kard {
  box-sizing: border-box;
  max-width: 560px;
  width: 100%;
  margin: 0 auto;
  padding: 24px clamp(16px, 5vw, 32px) 28px;
}

/* ── Header row ── */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.card-type {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--subtext);
}

/* ── Divider ── */
hr.divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 16px 0;
}

/* ── Shared hero display ── */
.hero {
  font-size: clamp(2.2rem, 8vw, 3.2rem);
  font-weight: 800;
  text-align: center;
  line-height: 1.1;
  margin-bottom: 2px;
}

/* ── Shared sub-hero (meaning / definition) ── */
.sub-hero {
  font-weight: 600;
  text-align: center;
  line-height: 1.2;
  margin-bottom: 6px;
}

/* ── Shared type tag (separability / category) ── */
.type-tag {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--subtext);
  text-align: center;
  margin-bottom: 4px;
}

/* ── Shared hint text (spatial sense / formation) ── */
.hint-text {
  font-size: 0.88rem;
  color: var(--subtext);
  font-style: italic;
  text-align: center;
  margin-bottom: 8px;
}

/* ── Shared examples block ── */
.examples {
  font-size: 0.92rem;
  line-height: 1.8;
  color: var(--text-de);
}
.examples .hl {
  font-weight: 700;
}
.example-item {
  margin-bottom: 6px;
}
.example-item:last-child {
  margin-bottom: 0;
}

/* ── Shared callout (disambig / note) ── */
.callout {
  font-size: 0.80rem;
  margin-top: 8px;
  padding: 5px 10px;
  border-left: 3px solid;
  border-radius: 0 4px 4px 0;
}
.callout-disambig {
  font-size: 0.83rem;
  margin-top: 10px;
  color: var(--disambig-fg);
  border-left-color: var(--disambig-fg);
  background: var(--disambig-bg);
}
.callout-note {
  color: var(--note-fg);
  border-left-color: var(--note-fg);
  background: var(--note-bg);
}

/* ── Focal urgency keyframes ── */
@keyframes urgency-de {
  0%   { color: var(--accent-de); }
  60%  { color: var(--accent-de); }
  70%  { color: #d4a040; }
  90%  { color: #d4a040; }
  100% { color: #c06040; }
}

@keyframes urgency-en {
  0%   { color: var(--accent-en); }
  60%  { color: var(--accent-en); }
  70%  { color: #e07830; }
  90%  { color: #e07830; }
  100% { color: #c05040; }
}

@keyframes urgency-cloze {
  0%   { border-bottom-color: var(--accent-de); background-color: transparent; }
  60%  { border-bottom-color: var(--accent-de); background-color: transparent; }
  70%  { border-bottom-color: #d4a040; background-color: rgba(212, 160, 64, 0.06); }
  90%  { border-bottom-color: #d4a040; background-color: rgba(212, 160, 64, 0.06); }
  100% { border-bottom-color: #c06040; background-color: rgba(192, 96, 64, 0.10); }
}
"""

# ══════════════════════════════════════════════════════════════════════════════
# CSS — vocab-specific classes
# ══════════════════════════════════════════════════════════════════════════════

VOCAB_CLASSES = """
/* ── Source badge ── */
.source-badge {
  display: inline-block;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border-radius: 4px;
  padding: 2px 8px;
  color: #fff;
}
.source-1 { background: var(--p1); }
.source-2 { background: var(--p2); }
.source-3 { background: var(--p3); }
.source-4 { background: var(--p4); }

.word-de.timed { animation: urgency-de 10s linear forwards; }
.word-en.timed { animation: urgency-en 10s linear forwards; }

/* ── Main words ── */
.word-de {
  font-size: clamp(1.6rem, 6vw, 2.4rem);
  font-weight: 700;
  color: var(--accent-de);
  line-height: 1.15;
  margin-bottom: 4px;
}
.word-en {
  font-size: clamp(1.4rem, 5vw, 2rem);
  font-weight: 600;
  color: var(--accent-en);
  line-height: 1.2;
  margin-bottom: 6px;
}
.ipa {
  font-size: 0.95rem;
  color: var(--subtext);
  margin-bottom: 14px;
}
.pos-hint {
  font-size: 0.78rem;
  color: var(--subtext);
  font-style: italic;
  margin-bottom: 8px;
}

/* ── Sentences ── */
.sentence-de {
  font-size: 1.05rem;
  line-height: 1.55;
  color: var(--text-de);
  margin-bottom: 5px;
  overflow-wrap: break-word;
}
.sentence-en {
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--subtext);
  font-style: italic;
  margin-bottom: 12px;
  overflow-wrap: break-word;
}
.sentence-en.quoted::before { content: "\\201C"; }
.sentence-en.quoted::after  { content: "\\201D"; }

/* Cloze sentence — larger than normal sentences */
.cloze-sentence {
  font-size: clamp(1rem, 3.5vw, 1.2rem);
  font-weight: 500;
  line-height: 1.55;
  color: var(--cloze-text);
  margin-top: 8px;
  overflow-wrap: break-word;
}

/* ── Cloze ── */
.cloze-blank {
  display: inline-block;
  min-width: 2.5em;
  border-bottom: 2px solid var(--accent-de);
  border-radius: 4px 4px 0 0;
  padding: 1px 4px;
  margin: 0 2px;
  color: transparent;
  user-select: none;
  animation: urgency-cloze 10s linear forwards;
}
.cloze-answer {
  color: var(--accent-de);
  font-weight: 700;
  border-bottom: 2px solid var(--accent-de);
}

/* ── Cloze hint tooltip ── */
.cloze-hint-trigger {
  position: relative;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.cloze-hint-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) translateY(4px);
  opacity: 0;
  pointer-events: none;
  z-index: 100;
  white-space: nowrap;
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--chip-bg);
  color: var(--subtext) !important;
  font-variant: small-caps;
  text-transform: lowercase;
  transition: opacity 200ms ease-out, transform 200ms ease-out;
}
.cloze-hint-tooltip.visible {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
  pointer-events: auto;
}
/* Caret arrow */
.cloze-hint-tooltip::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--chip-bg);
}

/* ── Audio replay button (Anki default restyle) ── */
.replay-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin: 4px 0;
  opacity: 0.4;
  transform: scale(0.7);
  transform-origin: center;
  transition: opacity 200ms;
}
.replay-button:hover { opacity: 0.85; }
.replay-button svg circle { fill: var(--surface); stroke: var(--subtext); }
.replay-button svg path { fill: var(--subtext); }
"""

# ══════════════════════════════════════════════════════════════════════════════
# CSS — prefix-specific classes
# ══════════════════════════════════════════════════════════════════════════════

PREFIX_CLASSES = """
/* ── Prefix accent ── */
:root {
  --accent-pfx: #c0a0e0;
}
@media (prefers-color-scheme: light) {
  :root {
    --accent-pfx: #7b5ea7;
  }
}

.hero.pfx       { color: var(--accent-pfx); }
.sub-hero.pfx   { color: var(--accent-pfx); font-size: clamp(1.4rem, 5vw, 2rem); }
.examples .hl.pfx { color: var(--accent-pfx); }

/* ── Urgency animation for prefix ── */
@keyframes urgency-pfx {
  0%   { color: var(--accent-pfx); }
  60%  { color: var(--accent-pfx); }
  70%  { color: #d4a040; }
  90%  { color: #d4a040; }
  100% { color: #c06040; }
}
.hero.pfx.timed     { animation: urgency-pfx 10s linear forwards; }
.sub-hero.pfx.timed { animation: urgency-pfx 10s linear forwards; }
"""

# ══════════════════════════════════════════════════════════════════════════════
# CSS — grammar-specific classes
# ══════════════════════════════════════════════════════════════════════════════

GRAMMAR_CLASSES = """
/* ── Grammar accent ── */
:root {
  --accent-gram: #5bbfb5;
}
@media (prefers-color-scheme: light) {
  :root {
    --accent-gram: #2a8a7e;
  }
}

.hero.gram       { color: var(--accent-gram); }
.sub-hero.gram   { color: var(--accent-gram); font-size: clamp(1.2rem, 4.5vw, 1.7rem); }
.examples .hl.gram { color: var(--accent-gram); }

/* ── Urgency animation for grammar ── */
@keyframes urgency-gram {
  0%   { color: var(--accent-gram); }
  60%  { color: var(--accent-gram); }
  70%  { color: #d4a040; }
  90%  { color: #d4a040; }
  100% { color: #c06040; }
}
.hero.gram.timed     { animation: urgency-gram 10s linear forwards; }
.examples.gram.timed { animation: urgency-gram 10s linear forwards; }
"""

# ── Composed CSS for each note type ──────────────────────────────────────────

VOCAB_CSS = BASE_VARS + BASE_LAYOUT + VOCAB_CLASSES
PREFIX_CSS = BASE_VARS + BASE_LAYOUT + PREFIX_CLASSES
GRAMMAR_CSS = BASE_VARS + BASE_LAYOUT + GRAMMAR_CLASSES

# ══════════════════════════════════════════════════════════════════════════════
# Vocab template snippets
# ══════════════════════════════════════════════════════════════════════════════


def source_badge_js(elem_id):
    """JS that extracts source::X from tags and displays as a colour-hashed badge."""
    return f"""
<span class="source-badge" id="{elem_id}"></span>
<script>
(function(){{
  var tags = "{{{{Tags}}}}";
  var el = document.getElementById("{elem_id}");
  if (!el) return;
  var m = tags.match(/source::([^\\s]+)/);
  if (m) {{
    var s = m[1];
    el.textContent = s.replace(/_/g, " ");
    var h = 0;
    for (var i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    el.className = "source-badge source-" + ((Math.abs(h) % 4) + 1);
  }} else {{
    el.style.display = "none";
  }}
}})();
</script>"""


def variant_picker_js(sentence_id, translation_id=None, is_front=False, pos_id=None):
    """JS that picks a random variant from pipe-separated Sentence/SentenceTranslation/POS.

    is_front=True:  pick random index, store in sessionStorage for back to read.
    is_front=False: load index from sessionStorage (fallback to random).
    pos_id:         element id to fill with the variant-matched POS value.
    """
    tr_line = ""
    if translation_id:
        tr_line = f"""
  var tel = document.getElementById("{translation_id}");
  if (tel) tel.textContent = (translations[idx] || "").trim();"""
    pos_line = ""
    if pos_id:
        pos_line = f"""
  var posVals = "{{{{POS}}}}".split("|");
  var pel = document.getElementById("{pos_id}");
  if (pel) pel.textContent = (posVals[idx] || posVals[0] || "").trim();"""
    if is_front:
        idx_logic = """\
  var idx = Math.floor(Math.random() * sentences.length);
  try { sessionStorage.setItem("v_" + "{{{{Word}}}}", idx); } catch(e) {}"""
    else:
        idx_logic = """\
  var idx;
  try { idx = parseInt(sessionStorage.getItem("v_" + "{{{{Word}}}}")); } catch(e) {}
  if (isNaN(idx) || idx < 0 || idx >= sentences.length) idx = Math.floor(Math.random() * sentences.length);"""
    return f"""
<script>
(function(){{
  var sentences = "{{{{Sentence}}}}".split("|");
  var translations = "{{{{SentenceTranslation}}}}".split("|");
  {idx_logic}
  var el = document.getElementById("{sentence_id}");
  if (el) el.textContent = sentences[idx].trim();{tr_line}{pos_line}
}})();
</script>"""


def cloze_picker_js(sentence_id, translation_id, span_class, is_front=False, pos_id=None, hint=False, hint_front=False):
    """JS that picks a random variant and applies cloze blanking.

    is_front=True:  pick random index, store in sessionStorage.
    is_front=False: load index from sessionStorage (fallback to random).
    pos_id:         element id to fill with the variant-matched POS value.
    hint:           if True, render ClozeHint tooltip on hover/tap (back card).
    hint_front:     if True, render ClozeHint tooltip on tap only (front card).
                    The blank itself is the trigger — zero visual footprint.
    """
    if is_front:
        idx_logic = """\
  var idx = Math.floor(Math.random() * sentences.length);
  try { sessionStorage.setItem("v_" + "{{{{Word}}}}", idx); } catch(e) {}"""
    else:
        idx_logic = """\
  var idx;
  try { idx = parseInt(sessionStorage.getItem("v_" + "{{{{Word}}}}")); } catch(e) {}
  if (isNaN(idx) || idx < 0 || idx >= sentences.length) idx = Math.floor(Math.random() * sentences.length);"""
    pos_line = ""
    if pos_id:
        pos_line = f"""
  var posVals = "{{{{POS}}}}".split("|");
  var pel = document.getElementById("{pos_id}");
  if (pel) pel.textContent = (posVals[idx] || posVals[0] || "").trim();"""
    hint_block = ""
    if hint or hint_front:
        # Back card: hover + tap reveal on the answer span (wrapped)
        # Front card: tap-only on the blank itself — zero visual footprint
        if hint and not hint_front:
            hint_block = f"""
  /* ── Hint tooltip (back — hover + tap) ── */
  var hints = "{{{{ClozeHint}}}}".split("|");
  var hint = (hints[idx] || "").trim();
  if (hint) {{
    var spans = document.querySelectorAll("#{sentence_id} .{span_class}");
    if (spans.length) {{
      var span = spans[0];
      var wrapper = document.createElement("span");
      wrapper.className = "cloze-hint-trigger";
      span.parentNode.insertBefore(wrapper, span);
      wrapper.appendChild(span);
      var tip = document.createElement("span");
      tip.className = "cloze-hint-tooltip";
      tip.textContent = hint;
      wrapper.appendChild(tip);
      wrapper.addEventListener("mouseenter", function(){{ tip.classList.add("visible"); }});
      wrapper.addEventListener("mouseleave", function(){{ tip.classList.remove("visible"); }});
      var isTouch = false;
      wrapper.addEventListener("touchstart", function(e){{
        isTouch = true;
        e.preventDefault();
        var show = !tip.classList.contains("visible");
        document.querySelectorAll(".cloze-hint-tooltip.visible").forEach(function(t){{ t.classList.remove("visible"); }});
        if (show) tip.classList.add("visible");
      }});
      document.addEventListener("touchstart", function(e){{
        if (!wrapper.contains(e.target)) tip.classList.remove("visible");
      }});
      wrapper.addEventListener("click", function(e){{ if (isTouch) e.preventDefault(); }});
    }}
  }}"""
        else:
            hint_block = f"""
  /* ── Hint tooltip (front — tap only, blank is trigger) ── */
  var hints = "{{{{ClozeHint}}}}".split("|");
  var hint = (hints[idx] || "").trim();
  if (hint) {{
    var spans = document.querySelectorAll("#{sentence_id} .{span_class}");
    if (spans.length) {{
      var span = spans[0];
      span.classList.add("cloze-hint-trigger");
      span.style.position = "relative";
      var tip = document.createElement("span");
      tip.className = "cloze-hint-tooltip";
      tip.textContent = hint;
      span.appendChild(tip);
      span.addEventListener("touchstart", function(e){{
        e.preventDefault();
        e.stopPropagation();
        var show = !tip.classList.contains("visible");
        document.querySelectorAll(".cloze-hint-tooltip.visible").forEach(function(t){{ t.classList.remove("visible"); }});
        if (show) tip.classList.add("visible");
      }});
      span.addEventListener("click", function(e){{
        e.stopPropagation();
        var show = !tip.classList.contains("visible");
        document.querySelectorAll(".cloze-hint-tooltip.visible").forEach(function(t){{ t.classList.remove("visible"); }});
        if (show) tip.classList.add("visible");
      }});
      document.addEventListener("touchstart", function(e){{
        if (!span.contains(e.target)) tip.classList.remove("visible");
      }});
      document.addEventListener("click", function(e){{
        if (!span.contains(e.target)) tip.classList.remove("visible");
      }});
    }}
  }}"""
    return f"""
<script>
(function(){{
  var sentences = "{{{{Sentence}}}}".split("|");
  var translations = "{{{{SentenceTranslation}}}}".split("|");
  var clozeWords = "{{{{ClozeWord}}}}".split("|");
  {idx_logic}
  var sentence = sentences[idx].trim();
  var clozeWord = (clozeWords[idx] || "").trim();
  var caseSensitive = true;
  if (!clozeWord) {{
    clozeWord = "{{{{Word}}}}".replace(/^(der|die|das|ein|eine)\\s+/i, "").trim();
    caseSensitive = false;
  }}
  var parts = clozeWord.split("~");
  var result = sentence;
  for (var i = 0; i < parts.length; i++) {{
    var p = parts[i].trim();
    if (!p) continue;
    var escaped = p.replace(/[.*+?^${{}}()|[\\]\\\\]/g, "\\\\$&");
    var L = "[A-Za-z\\\\u00C0-\\\\u024F]";
    result = result.replace(
      new RegExp("(?<!" + L + ")" + escaped + "(?!" + L + ")", caseSensitive ? "" : "i"),
      '<span class="{span_class}">$&</span>'
    );
  }}
  var el = document.getElementById("{sentence_id}");
  if (el) el.innerHTML = result;
  var tel = document.getElementById("{translation_id}");
  if (tel) tel.textContent = (translations[idx] || "").trim();{pos_line}{hint_block}
}})();
</script>"""

# ══════════════════════════════════════════════════════════════════════════════
# Vocab templates
# ══════════════════════════════════════════════════════════════════════════════
# Front templates add class="timed" to the focal word element so the urgency
# animation shifts its colour over 10s. Cloze blanks animate automatically
# via the .cloze-blank rule.  Back templates have no urgency animation.

EN_DE_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">EN&nbsp;&rarr;&nbsp;DE &middot; Production</div>
    """ + source_badge_js("src-ende-f") + """
  </div>

  <div class="word-en timed">{{WordTranslation}}</div>

  {{#SentenceTranslation}}
  <hr class="divider">
  <div class="sentence-en quoted" id="ende-tr-front"></div>
  {{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="callout callout-disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}
</div>""" + variant_picker_js("ende-s-front", "ende-tr-front", is_front=True)

EN_DE_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">EN&nbsp;&rarr;&nbsp;DE &middot; Production</div>
    """ + source_badge_js("src-ende-b") + """
  </div>

  <div class="word-en">{{WordTranslation}}</div>

  <hr class="divider">

  <div class="word-de">{{Word}}</div>
  {{#POS}}<div class="pos-hint" id="ende-pos"></div>{{/POS}}
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  {{#Audio}}{{Audio}}{{/Audio}}

  {{#Sentence}}<div class="sentence-de" id="ende-s-back"></div>{{/Sentence}}
  {{#SentenceTranslation}}<div class="sentence-en quoted" id="ende-tr-back"></div>{{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="callout callout-disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="callout callout-note">{{Note}}</div>{{/Note}}
""" + "\n</div>" + variant_picker_js("ende-s-back", "ende-tr-back", pos_id="ende-pos")

DE_EN_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">DE&nbsp;&rarr;&nbsp;EN &middot; Recognition</div>
    """ + source_badge_js("src-deen-f") + """
  </div>

  <div class="word-de timed">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  {{#Audio}}{{Audio}}{{/Audio}}
</div>"""

DE_EN_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">DE&nbsp;&rarr;&nbsp;EN &middot; Recognition</div>
    """ + source_badge_js("src-deen-b") + """
  </div>

  <div class="word-de">{{Word}}</div>
  {{#POS}}<div class="pos-hint" id="deen-pos"></div>{{/POS}}
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  {{#Audio}}{{Audio}}{{/Audio}}

  <hr class="divider">

  <div class="word-en">{{WordTranslation}}</div>

  {{#Sentence}}<div class="sentence-de" id="deen-s-back"></div>{{/Sentence}}
  {{#SentenceTranslation}}<div class="sentence-en quoted" id="deen-tr-back"></div>{{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="callout callout-disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="callout callout-note">{{Note}}</div>{{/Note}}
""" + "\n</div>" + variant_picker_js("deen-s-back", "deen-tr-back", pos_id="deen-pos")

CLOZE_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    """ + source_badge_js("src-cloze-f") + """
  </div>

  <div class="sentence-de cloze-sentence" id="cloze-q"></div>
  {{#SentenceTranslation}}<div class="sentence-en quoted" id="cloze-tr"></div>{{/SentenceTranslation}}
  {{#Audio}}{{Audio}}{{/Audio}}
</div>""" + cloze_picker_js("cloze-q", "cloze-tr", "cloze-blank", is_front=True, hint_front=True)

CLOZE_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    """ + source_badge_js("src-cloze-b") + """
  </div>

  <div class="sentence-de cloze-sentence" id="cloze-a"></div>
  {{#SentenceTranslation}}<div class="sentence-en quoted" id="cloze-tr-back"></div>{{/SentenceTranslation}}

  <hr class="divider">
  <div class="word-de">{{Word}}</div>
  {{#POS}}<div class="pos-hint" id="cloze-pos"></div>{{/POS}}
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  {{#Audio}}{{Audio}}{{/Audio}}
  <div class="word-en">{{WordTranslation}}</div>

  {{#Note}}<div class="callout callout-note">{{Note}}</div>{{/Note}}
""" + """
</div>""" + cloze_picker_js("cloze-a", "cloze-tr-back", "cloze-answer", pos_id="cloze-pos", hint=True)

# ══════════════════════════════════════════════════════════════════════════════
# Prefix templates
# ══════════════════════════════════════════════════════════════════════════════

PFX_MEANING_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="hero pfx timed">{{Prefix}}-</div>
  <div class="type-tag">{{PrefixType}}</div>
</div>"""

PFX_MEANING_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="sub-hero pfx">{{CoreMeaning}}</div>
  <div class="hint-text">{{SpatialSense}}</div>
  <hr class="divider">
  <div class="examples">{{Examples}}</div>
</div>"""

MEANING_PFX_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="sub-hero pfx timed">{{CoreMeaning}}</div>
  <div class="hint-text">{{SpatialSense}}</div>
</div>"""

MEANING_PFX_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="hero pfx">{{Prefix}}-</div>
  <div class="type-tag">{{PrefixType}}</div>
  <hr class="divider">
  <div class="examples">{{Examples}}</div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# Grammar templates
# ══════════════════════════════════════════════════════════════════════════════

GRAM_TERM_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Grammar</div>
  </div>
  <div class="type-tag">{{Category}}</div>
  <div class="hero gram timed">{{Term}}</div>
</div>"""

GRAM_TERM_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Grammar</div>
  </div>
  <div class="type-tag">{{Category}}</div>
  <div class="hero gram">{{Term}}</div>
  <hr class="divider">
  <div class="sub-hero gram">{{Definition}}</div>
  {{#Formation}}
  <div class="hint-text">{{Formation}}</div>
  {{/Formation}}
  {{#Example}}
  <hr class="divider">
  <div class="examples">{{Example}}</div>
  {{/Example}}
  {{#Note}}<div class="callout callout-note">{{Note}}</div>{{/Note}}
</div>"""

GRAM_EXAMPLE_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Grammar &middot; Example</div>
  </div>
  <div class="examples gram timed" id="gram-ex-front">{{Example}}</div>
</div>
<script>
(function(){
  var el = document.getElementById("gram-ex-front");
  if (!el) return;
  var items = el.querySelectorAll(".example-item");
  if (items.length < 2) return;
  var idx = Math.floor(Math.random() * items.length);
  items.forEach(function(item, i){ if (i !== idx) item.style.display = "none"; });
})();
</script>"""

GRAM_EXAMPLE_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Grammar &middot; Example</div>
  </div>
  <div class="hero gram">{{Term}}</div>
  <div class="type-tag">{{Category}}</div>
  <hr class="divider">
  <div class="sub-hero gram">{{Definition}}</div>
  {{#Formation}}
  <div class="hint-text">{{Formation}}</div>
  {{/Formation}}
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# Push to Anki
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Vocab note type ──
    print("Updating George's German Vocab CSS...")
    anki("updateModelStyling", model={"name": "George's German Vocab", "css": VOCAB_CSS})
    print("  Done.")

    print("Updating George's German Vocab templates...")
    anki("updateModelTemplates", model={
        "name": "George's German Vocab",
        "templates": {
            "EN → DE":       {"Front": EN_DE_FRONT, "Back": EN_DE_BACK},
            "DE → EN":       {"Front": DE_EN_FRONT, "Back": DE_EN_BACK},
            "Sentence Cloze": {"Front": CLOZE_FRONT, "Back": CLOZE_BACK},
        }
    })
    print("  Done.")

    # ── Prefix note type ──
    print("Updating German Prefix CSS...")
    anki("updateModelStyling", model={"name": "German Prefix", "css": PREFIX_CSS})
    print("  Done.")

    print("Updating German Prefix templates...")
    anki("updateModelTemplates", model={
        "name": "German Prefix",
        "templates": {
            "Prefix → Meaning": {"Front": PFX_MEANING_FRONT, "Back": PFX_MEANING_BACK},
            "Meaning → Prefix": {"Front": MEANING_PFX_FRONT, "Back": MEANING_PFX_BACK},
        }
    })
    print("  Done.")

    # ── Grammar note type ──
    print("Updating German Grammar Term CSS...")
    anki("updateModelStyling", model={"name": "German Grammar Term", "css": GRAMMAR_CSS})
    print("  Done.")

    print("Updating German Grammar Term templates...")
    anki("updateModelTemplates", model={
        "name": "German Grammar Term",
        "templates": {
            "Term → Definition":  {"Front": GRAM_TERM_FRONT, "Back": GRAM_TERM_BACK},
            "Example → Term":     {"Front": GRAM_EXAMPLE_FRONT, "Back": GRAM_EXAMPLE_BACK},
        }
    })
    print("  Done.")

    print()
    print("Templates and CSS pushed to Anki (all note types).")


if __name__ == "__main__":
    main()
