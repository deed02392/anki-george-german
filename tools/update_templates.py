#!/usr/bin/env python3
"""
Update card CSS and templates for BOTH note types via AnkiConnect.

This is the LIVE SOURCE OF TRUTH for all card styling and template HTML.
Run this script after any template/CSS change to push to Anki.

Note types managed:
  1. "George's German Vocab"  — vocabulary cards (EN→DE, DE→EN, Cloze)
  2. "German Prefix"          — prefix teaching cards (Prefix→Meaning, Meaning→Prefix)
"""

import os
import sys

# Ensure tools/ is on sys.path so sibling imports work regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _anki import anki


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

/* ── Focal urgency ── */
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

@keyframes urgency-blank {
  0%   { border-bottom-color: var(--accent-de); background-color: transparent; }
  60%  { border-bottom-color: var(--accent-de); background-color: transparent; }
  70%  { border-bottom-color: #d4a040; background-color: rgba(212, 160, 64, 0.06); }
  90%  { border-bottom-color: #d4a040; background-color: rgba(212, 160, 64, 0.06); }
  100% { border-bottom-color: #c06040; background-color: rgba(192, 96, 64, 0.10); }
}

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
  animation: urgency-blank 10s linear forwards;
}
.cloze-answer {
  color: var(--accent-de);
  font-weight: 700;
  border-bottom: 2px solid var(--accent-de);
}

/* ── Notes / disambig ── */
.disambig {
  font-size: 0.83rem;
  color: var(--disambig-fg);
  margin-top: 10px;
  padding: 5px 10px;
  border-left: 3px solid var(--disambig-fg);
  background: var(--disambig-bg);
  border-radius: 0 4px 4px 0;
}
.usage-note {
  font-size: 0.80rem;
  color: var(--note-fg);
  margin-top: 8px;
  padding: 5px 10px;
  border-left: 3px solid var(--note-fg);
  background: var(--note-bg);
  border-radius: 0 4px 4px 0;
}

/* ── Domain chips ── */
.domains {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.domain-chip {
  font-size: 0.67rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: var(--chip-bg);
  color: var(--subtext);
  border-radius: 10px;
  padding: 2px 9px;
}
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

/* ── Prefix hero display ── */
.prefix-hero {
  font-size: clamp(2.2rem, 8vw, 3.2rem);
  font-weight: 800;
  color: var(--accent-pfx);
  text-align: center;
  line-height: 1.1;
  margin-bottom: 2px;
}

/* ── Core meaning ── */
.core-meaning {
  font-size: clamp(1.4rem, 5vw, 2rem);
  font-weight: 600;
  color: var(--accent-pfx);
  text-align: center;
  line-height: 1.2;
  margin-bottom: 6px;
}

/* ── Spatial sense ── */
.spatial-sense {
  font-size: 0.88rem;
  color: var(--subtext);
  font-style: italic;
  text-align: center;
  margin-bottom: 8px;
}

/* ── Separability tag ── */
.pfx-type-tag {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--subtext);
  text-align: center;
  margin-bottom: 4px;
}

/* ── Example verbs ── */
.pfx-examples {
  font-size: 0.92rem;
  line-height: 1.8;
  color: var(--text-de);
}
.pfx-examples .pfx {
  color: var(--accent-pfx);
  font-weight: 700;
}

/* ── Urgency animation for prefix ── */
@keyframes urgency-pfx {
  0%   { color: var(--accent-pfx); }
  60%  { color: var(--accent-pfx); }
  70%  { color: #d4a040; }
  90%  { color: #d4a040; }
  100% { color: #c06040; }
}
.prefix-hero.timed { animation: urgency-pfx 10s linear forwards; }
.core-meaning.timed { animation: urgency-pfx 10s linear forwards; }
"""

# ── Composed CSS for each note type ──────────────────────────────────────────

VOCAB_CSS = BASE_VARS + BASE_LAYOUT + VOCAB_CLASSES
PREFIX_CSS = BASE_VARS + BASE_LAYOUT + PREFIX_CLASSES

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


def domains_js(elem_id):
    return f"""
<div class="domains" id="{elem_id}"></div>
<script>
(function(){{
  var raw = "{{{{Domains}}}}";
  var el = document.getElementById("{elem_id}");
  if (!el || !raw.trim()) return;
  raw.split(",").forEach(function(d){{
    var chip = document.createElement("span");
    chip.className = "domain-chip";
    chip.textContent = d.trim();
    el.appendChild(chip);
  }});
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


def cloze_picker_js(sentence_id, translation_id, span_class, is_front=False, pos_id=None):
    """JS that picks a random variant and applies cloze blanking.

    is_front=True:  pick random index, store in sessionStorage.
    is_front=False: load index from sessionStorage (fallback to random).
    pos_id:         element id to fill with the variant-matched POS value.
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
  if (tel) tel.textContent = (translations[idx] || "").trim();{pos_line}
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
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
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
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-en-de") + "\n</div>" + variant_picker_js("ende-s-back", "ende-tr-back", pos_id="ende-pos")

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

  <hr class="divider">

  <div class="word-en">{{WordTranslation}}</div>

  {{#Sentence}}<div class="sentence-de" id="deen-s-back"></div>{{/Sentence}}
  {{#SentenceTranslation}}<div class="sentence-en quoted" id="deen-tr-back"></div>{{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-de-en") + "\n</div>" + variant_picker_js("deen-s-back", "deen-tr-back", pos_id="deen-pos")

CLOZE_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    """ + source_badge_js("src-cloze-f") + """
  </div>

  <div class="sentence-de cloze-sentence" id="cloze-q"></div>
  {{#SentenceTranslation}}<div class="sentence-en quoted" id="cloze-tr"></div>{{/SentenceTranslation}}
  {{#Audio}}{{Audio}}{{/Audio}}
</div>""" + cloze_picker_js("cloze-q", "cloze-tr", "cloze-blank", is_front=True)

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
  <div class="word-en">{{WordTranslation}}</div>

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-cloze") + """
</div>""" + cloze_picker_js("cloze-a", "cloze-tr-back", "cloze-answer", pos_id="cloze-pos")

# ══════════════════════════════════════════════════════════════════════════════
# Prefix templates
# ══════════════════════════════════════════════════════════════════════════════

PFX_MEANING_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="prefix-hero timed">{{Prefix}}-</div>
  <div class="pfx-type-tag">{{PrefixType}}</div>
</div>"""

PFX_MEANING_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="core-meaning">{{CoreMeaning}}</div>
  <div class="spatial-sense">{{SpatialSense}}</div>
  <hr class="divider">
  <div class="pfx-examples">{{Examples}}</div>
</div>"""

MEANING_PFX_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="core-meaning timed">{{CoreMeaning}}</div>
  <div class="spatial-sense">{{SpatialSense}}</div>
</div>"""

MEANING_PFX_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Prefix</div>
  </div>
  <div class="prefix-hero">{{Prefix}}-</div>
  <div class="pfx-type-tag">{{PrefixType}}</div>
  <hr class="divider">
  <div class="pfx-examples">{{Examples}}</div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# Push to Anki
# ══════════════════════════════════════════════════════════════════════════════

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

print()
print("Templates and CSS pushed to Anki (both note types).")
