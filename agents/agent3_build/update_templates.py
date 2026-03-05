#!/usr/bin/env python3
"""
Update "George's German Vocab" CSS and templates via AnkiConnect.

This is the LIVE SOURCE OF TRUTH for all card styling and template HTML.
Run this script after any template/CSS change to push to Anki.
"""

import requests

URL = "http://localhost:8765"


def anki(action, **params):
    r = requests.post(URL, json={"action": action, "version": 6, "params": params})
    r.raise_for_status()
    result = r.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect [{action}]: {result['error']}")
    return result["result"]


# ── CSS ───────────────────────────────────────────────────────────────────────
# @property registers --timer-pct as an animatable number (Houdini).
# Anki uses Qt WebEngine (Chromium 94+) so this is supported.
# Fallback: if @property is unsupported the ring simply doesn't animate,
# which is graceful — the badge still shows phase clearly.

CSS = """
/* George's German Vocab — shared styles
   Dark/light mode via prefers-color-scheme */

@property --timer-pct {
  syntax: "<number>";
  inherits: false;
  initial-value: 0;
}

:root {
  --bg:         #1a1a2e;
  --surface:    #16213e;
  --text:       #e0e0e0;
  --subtext:    #8892a4;
  --border:     rgba(255,255,255,0.08);
  --accent-de:  #7ec8e3;
  --accent-en:  #f5c842;
  --p1:         #4fa3e0;
  --p2:         #3dbb72;
  --p3:         #f08030;
  --disambig-fg:#f08080;
  --disambig-bg:rgba(240,128,128,0.08);
  --note-fg:    #90c0a0;
  --note-bg:    rgba(144,192,160,0.08);
  --chip-bg:    #2e3a5a;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg:         #f5f7fa;
    --surface:    #ffffff;
    --text:       #1a1a2e;
    --subtext:    #5a6478;
    --border:     rgba(0,0,0,0.10);
    --accent-de:  #1a6fa8;
    --accent-en:  #b07800;
    --p1:         #1a6fa8;
    --p2:         #217a44;
    --p3:         #c05a00;
    --disambig-fg:#c0302a;
    --disambig-bg:rgba(192,48,42,0.07);
    --note-fg:    #2a7a4a;
    --note-bg:    rgba(42,122,74,0.07);
    --chip-bg:    #dde3ef;
  }
}

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

.card-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-type {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--subtext);
}

/* ── Phase badge ── */
.phase-badge {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-radius: 4px;
  padding: 2px 8px;
  color: #fff;
}
.phase-1 { background: var(--p1); }
.phase-2 { background: var(--p2); }
.phase-3 { background: var(--p3); }

/* ── Timer ring ── */
/*
  A 22px circle drawn entirely with conic-gradient.
  --timer-pct animates from 0 → 100 over 16s total.
  3s invisible lead-in (--timer-pct starts at -23, clamped to 0),
  then 13s visible sweep.

  Colour: phase colour → amber at 80% → red at 93%.
  Animated via a separate @keyframes on --timer-ring-colour.
*/

@keyframes timer-sweep {
  /* 3s blank lead-in: --timer-pct starts at -23 (3/13 * 100 ≈ 23),
     conic-gradient clamps negative values to 0 so ring is invisible.
     Then sweeps to 100 over the remaining 13s (16s total). */
  from { --timer-pct: -23; }
  to   { --timer-pct: 100; }
}

@keyframes timer-colour {
  /* Phase colour holds through most of the comfortable retrieval window,
     shifting to amber only in the final third, red near the end. */
  0%   { --timer-ring-colour: var(--timer-phase-colour); }
  65%  { --timer-ring-colour: var(--timer-phase-colour); }
  80%  { --timer-ring-colour: #f08030; }
  93%  { --timer-ring-colour: #e04040; }
  100% { --timer-ring-colour: #e04040; }
}

@property --timer-ring-colour {
  syntax: "<color>";
  inherits: false;
  initial-value: #4fa3e0;
}

.timer-ring {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  flex-shrink: 0;
  animation:
    timer-sweep  16s linear forwards,
    timer-colour 16s linear forwards;
  background: conic-gradient(
    var(--timer-ring-colour) calc(var(--timer-pct) * 1%),
    transparent              calc(var(--timer-pct) * 1%)
  );
  /* Inner cutout: produces a ring rather than a filled pie slice.
     The outer track is now fully transparent so only the arc is visible. */
  -webkit-mask: radial-gradient(circle, transparent 55%, black 56%);
  mask:         radial-gradient(circle, transparent 55%, black 56%);
  opacity: 0.9;
}

/* Phase-specific ring start colours */
.timer-ring.phase-1 { --timer-phase-colour: var(--p1); }
.timer-ring.phase-2 { --timer-phase-colour: var(--p2); }
.timer-ring.phase-3 { --timer-phase-colour: var(--p3); }

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

/* ── Divider ── */
hr.divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 16px 0;
}

/* ── Sentences ── */
.sentence-de {
  font-size: 1.05rem;
  line-height: 1.55;
  color: var(--text);
  margin-bottom: 5px;
  overflow-wrap: break-word;
}
.sentence-en {
  font-size: 0.88rem;
  color: var(--subtext);
  font-style: italic;
  margin-bottom: 12px;
  overflow-wrap: break-word;
}

/* Cloze sentence — larger than normal sentences */
.cloze-sentence {
  font-size: clamp(1rem, 3.5vw, 1.2rem);
  margin-top: 8px;
}

/* ── Cloze ── */
.cloze-blank {
  display: inline-block;
  min-width: 72px;
  border-bottom: 2px solid var(--accent-de);
  color: transparent;
  user-select: none;
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

# ── Snippets ─────────────────────────────────────────────────────────────────

# The ring — only on front templates.
# Uses a Mustache conditional to pick the right phase class.
# No JS at all.
TIMER_RING = """\
{{#Phase}}<div class="timer-ring phase-{{Phase}}"></div>{{/Phase}}"""

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

# ── Templates ────────────────────────────────────────────────────────────────
# Back templates intentionally contain no timer element whatsoever.
# The ring's animation is tied to the card load, so even if {{FrontSide}}
# injects the ring HTML into the back, the animation restarts — undesirable.
# To be safe, backs are fully self-contained (no {{FrontSide}}).

EN_DE_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">EN&nbsp;&rarr;&nbsp;DE &middot; Production</div>
    <div class="card-header-right">
      """ + TIMER_RING + """
      {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
    </div>
  </div>

  <div class="word-en">{{WordTranslation}}</div>

  {{#SentenceTranslation}}
  <hr class="divider">
  <div class="sentence-en">&ldquo;{{SentenceTranslation}}&rdquo;</div>
  {{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}
</div>"""

EN_DE_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">EN&nbsp;&rarr;&nbsp;DE &middot; Production</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="word-en">{{WordTranslation}}</div>

  <hr class="divider">

  <div class="word-de">{{Word}}</div>
  {{#POS}}<div class="pos-hint">{{POS}}</div>{{/POS}}
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  {{#Audio}}{{Audio}}{{/Audio}}

  {{#Sentence}}<div class="sentence-de">{{Sentence}}</div>{{/Sentence}}
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-en-de") + "\n</div>"

DE_EN_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">DE&nbsp;&rarr;&nbsp;EN &middot; Recognition</div>
    <div class="card-header-right">
      """ + TIMER_RING + """
      {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
    </div>
  </div>

  <div class="word-de">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  {{#Audio}}{{Audio}}{{/Audio}}
</div>"""

DE_EN_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">DE&nbsp;&rarr;&nbsp;EN &middot; Recognition</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="word-de">{{Word}}</div>
  {{#POS}}<div class="pos-hint">{{POS}}</div>{{/POS}}
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}

  <hr class="divider">

  <div class="word-en">{{WordTranslation}}</div>

  {{#Sentence}}<div class="sentence-de">{{Sentence}}</div>{{/Sentence}}
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-de-en") + "\n</div>"

CLOZE_FRONT = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    <div class="card-header-right">
      """ + TIMER_RING + """
      {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
    </div>
  </div>

  <div class="sentence-de cloze-sentence" id="cloze-q"></div>
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}
  {{#Audio}}{{Audio}}{{/Audio}}
</div>
<script>
(function(){
  var sentence = "{{Sentence}}";
  var clozeWord = "{{ClozeWord}}".trim();
  var caseSensitive = true;
  if (!clozeWord) {
    clozeWord = "{{Word}}".replace(/^(der|die|das|ein|eine)\\s+/i, "").trim();
    caseSensitive = false;
  }
  var parts = clozeWord.split("|");
  var result = sentence;
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i].trim();
    if (!p) continue;
    var escaped = p.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
    result = result.replace(
      new RegExp(escaped, caseSensitive ? "" : "i"),
      '<span class="cloze-blank">$&</span>'
    );
  }
  var el = document.getElementById("cloze-q");
  if (el) el.innerHTML = result;
})();
</script>"""

CLOZE_BACK = """\
<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="sentence-de cloze-sentence" id="cloze-a"></div>
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}

  <hr class="divider">
  <div class="word-de">{{Word}}</div>
  {{#POS}}<div class="pos-hint">{{POS}}</div>{{/POS}}
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  <div class="word-en">{{WordTranslation}}</div>

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-cloze") + """
</div>
<script>
(function(){
  var sentence = "{{Sentence}}";
  var clozeWord = "{{ClozeWord}}".trim();
  var caseSensitive = true;
  if (!clozeWord) {
    clozeWord = "{{Word}}".replace(/^(der|die|das|ein|eine)\\s+/i, "").trim();
    caseSensitive = false;
  }
  var parts = clozeWord.split("|");
  var result = sentence;
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i].trim();
    if (!p) continue;
    var escaped = p.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
    result = result.replace(
      new RegExp(escaped, caseSensitive ? "" : "i"),
      '<span class="cloze-answer">$&</span>'
    );
  }
  var el = document.getElementById("cloze-a");
  if (el) el.innerHTML = result;
})();
</script>"""


# ── Push to Anki ──────────────────────────────────────────────────────────────

print("Updating CSS...")
anki("updateModelStyling", model={"name": "George's German Vocab", "css": CSS})
print("  Done.")

print("Updating templates...")
anki("updateModelTemplates", model={
    "name": "George's German Vocab",
    "templates": {
        "EN → DE":       {"Front": EN_DE_FRONT, "Back": EN_DE_BACK},
        "DE → EN":       {"Front": DE_EN_FRONT, "Back": DE_EN_BACK},
        "Sentence Cloze": {"Front": CLOZE_FRONT, "Back": CLOZE_BACK},
    }
})
print("  Done.")
print()
print("Templates and CSS pushed to Anki.")
