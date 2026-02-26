#!/usr/bin/env python3
"""
Fix the "George's German Vocab" note type:
  1. Strip {{c1::...}} from Sentence fields on all 740 notes
  2. Rewrite all three card templates (fix phase badge, add timer, dark/light mode)
"""

import json
import re
import requests

URL = "http://localhost:8765"


def anki(action, **params):
    r = requests.post(URL, json={"action": action, "version": 6, "params": params})
    r.raise_for_status()
    result = r.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect error in {action}: {result['error']}")
    return result["result"]


# ── 1. Strip cloze syntax from Sentence fields ────────────────────────────────

print("Finding notes with cloze syntax in Sentence...")
note_ids = anki("findNotes", query='deck:"George\'s German Vocabulary" Sentence:*c1*')
print(f"  {len(note_ids)} notes to fix")

notes_info = anki("notesInfo", notes=note_ids)

updates = []
for note in notes_info:
    sentence = note["fields"]["Sentence"]["value"]
    # {{c1::word}} → word
    cleaned = re.sub(r"\{\{c\d+::([^}]*)\}\}", r"\1", sentence)
    if cleaned != sentence:
        updates.append({
            "id": note["noteId"],
            "fields": {"Sentence": cleaned},
        })

print(f"  Updating {len(updates)} notes...")
# updateNoteFields only takes one note at a time
for i, u in enumerate(updates):
    anki("updateNoteFields", note=u)
    if (i + 1) % 50 == 0:
        print(f"    {i + 1}/{len(updates)}")

print(f"  Done. Cloze syntax stripped from {len(updates)} notes.")


# ── 2. Shared CSS ─────────────────────────────────────────────────────────────

CSS = """
/* George's German Vocab — shared styles
   Supports automatic dark / light mode via prefers-color-scheme */

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

.card {
  font-family: "Noto Sans", sans-serif;
  background: var(--bg);
  color: var(--text);
  /* dvh = dynamic viewport height: shrinks when browser/OS chrome is visible.
     This is the correct unit for mobile — 100vh would be taller than the
     visible area when the address bar is shown, causing unwanted scroll. */
  min-height: 100dvh;
  margin: 0; padding: 0;
  display: flex;
  /* flex-start so content anchors to the top of the viewport.
     align-items:center would vertically centre the .kard inside a min-height
     container, which pushes the top of long cards above the visible area. */
  align-items: flex-start;
  justify-content: center;
}

.kard {
  max-width: 560px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 22px 28px;
  /* Keep content above the iPhone home-indicator safe area */
  padding-bottom: max(28px, env(safe-area-inset-bottom));
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

/* ── Main words ── */
.word-de {
  font-size: 2.4rem;
  font-weight: 700;
  color: var(--accent-de);
  line-height: 1.15;
  margin-bottom: 4px;
}
.word-en {
  font-size: 2rem;
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
}
.sentence-en {
  font-size: 0.88rem;
  color: var(--subtext);
  font-style: italic;
  margin-bottom: 12px;
}
.context-sentence {
  font-size: 0.88rem;
  color: var(--subtext);
  font-style: italic;
  margin-top: 6px;
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

/* ── Timer bar ── */
.timer-bar-wrap {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  height: 4px;
  background: transparent;
  z-index: 100;
  /* Must not intercept taps on Anki's answer buttons */
  pointer-events: none;
}
.timer-bar {
  height: 100%;
  width: 0%;
  transition: background 0.4s;
}
.timer-msg {
  position: fixed;
  bottom: 8px;
  right: 12px;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0;
  transition: opacity 0.3s;
  color: var(--subtext);
  pointer-events: none;
}
"""

# ── 3. Shared JS snippets ────────────────────────────────────────────────────

# Domain chips renderer — called with a unique element id
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

# Timer — same logic as the original deck (2s blank, 6s hard, 4s again)
TIMER_JS = """
<div class="timer-bar-wrap"><div class="timer-bar" id="timerBar"></div></div>
<div class="timer-msg" id="timerMsg"></div>
<script>
(function(){
  var bar = document.getElementById("timerBar");
  var msg = document.getElementById("timerMsg");
  if (!bar) return;
  var t0 = Date.now();
  var DELAY = 2000, HARD = 6000, AGAIN = 4000;
  function tick() {
    var el = Date.now() - t0;
    if (el < DELAY) {
      bar.style.width = "0%";
      bar.style.background = "";
      msg.style.opacity = "0";
    } else if (el < DELAY + HARD) {
      var pct = (el - DELAY) / HARD * 50;
      bar.style.width = pct + "%";
      bar.style.background = "#4fa3e0";
      msg.style.opacity = "0";
    } else if (el < DELAY + HARD + AGAIN) {
      var pct = 50 + (el - DELAY - HARD) / AGAIN * 50;
      bar.style.width = pct + "%";
      bar.style.background = "#f08030";
      msg.style.opacity = "1";
      msg.textContent = "taking a while\u2026";
    } else {
      bar.style.width = "100%";
      bar.style.background = "#e05050";
      msg.style.opacity = "1";
      msg.textContent = "time to move on";
      return;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
</script>"""

# ── 4. Template HTML ─────────────────────────────────────────────────────────

EN_DE_FRONT = """<div class="kard">
  <div class="card-header">
    <div class="card-type">EN&nbsp;&rarr;&nbsp;DE &middot; Production</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="word-en">{{WordTranslation}}</div>
  {{#POS}}<div class="pos-hint">{{POS}}</div>{{/POS}}

  {{#SentenceTranslation}}
  <hr class="divider">
  <div class="context-sentence">&ldquo;{{SentenceTranslation}}&rdquo;</div>
  {{/SentenceTranslation}}
</div>
""" + TIMER_JS

EN_DE_BACK = """{{FrontSide}}
<hr class="divider">
<div class="kard" style="padding-top:0">
  <div class="word-de">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}

  {{#Sentence}}<div class="sentence-de">{{Sentence}}</div>{{/Sentence}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-en-de") + "\n</div>"

DE_EN_FRONT = """<div class="kard">
  <div class="card-header">
    <div class="card-type">DE&nbsp;&rarr;&nbsp;EN &middot; Recognition</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="word-de">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
</div>
""" + TIMER_JS

DE_EN_BACK = """{{FrontSide}}
<hr class="divider">
<div class="kard" style="padding-top:0">
  <div class="word-en">{{WordTranslation}}</div>

  {{#Sentence}}<div class="sentence-de">{{Sentence}}</div>{{/Sentence}}
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-de-en") + "\n</div>"

# Cloze front: blank the target word in the sentence using JS
# (Word field holds "der Hund" or "spielen" — strip article for matching)
CLOZE_FRONT = """<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="sentence-de" id="cloze-q" style="font-size:1.2rem; margin-top:8px;"></div>
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}
</div>
<script>
(function(){
  var sentence = "{{Sentence}}";
  var word = "{{Word}}".replace(/^(der|die|das|ein|eine)\\s+/i, "").trim();
  var escaped = word.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
  var blanked = sentence.replace(
    new RegExp("(" + escaped + ")", "i"),
    '<span class="cloze-blank">$1</span>'
  );
  var el = document.getElementById("cloze-q");
  if (el) el.innerHTML = blanked;
})();
</script>
""" + TIMER_JS

CLOZE_BACK = """<div class="kard">
  <div class="card-header">
    <div class="card-type">Sentence Cloze &middot; Context</div>
    {{#Phase}}<span class="phase-badge phase-{{Phase}}">P{{Phase}}</span>{{/Phase}}
  </div>

  <div class="sentence-de" id="cloze-a" style="font-size:1.2rem; margin-top:8px;"></div>
  {{#SentenceTranslation}}<div class="sentence-en">{{SentenceTranslation}}</div>{{/SentenceTranslation}}

  <hr class="divider">
  <div class="word-de">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  <div class="word-en" style="font-size:1.2rem;">{{WordTranslation}}</div>

  {{#Note}}<div class="usage-note">{{Note}}</div>{{/Note}}
""" + domains_js("dom-cloze") + """
</div>
<script>
(function(){
  var sentence = "{{Sentence}}";
  var word = "{{Word}}".replace(/^(der|die|das|ein|eine)\\s+/i, "").trim();
  var escaped = word.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
  var revealed = sentence.replace(
    new RegExp("(" + escaped + ")", "i"),
    '<span class="cloze-answer">$1</span>'
  );
  var el = document.getElementById("cloze-a");
  if (el) el.innerHTML = revealed;
})();
</script>"""


# ── 5. Push updated templates and CSS to AnkiConnect ────────────────────────

print("\nUpdating CSS...")
anki("updateModelStyling", model={"name": "George's German Vocab", "css": CSS})
print("  Done.")

print("Updating templates...")
anki("updateModelTemplates", model={
    "name": "George's German Vocab",
    "templates": {
        "EN → DE": {"Front": EN_DE_FRONT, "Back": EN_DE_BACK},
        "DE → EN": {"Front": DE_EN_FRONT, "Back": DE_EN_BACK},
        "Sentence Cloze": {"Front": CLOZE_FRONT, "Back": CLOZE_BACK},
    }
})
print("  Done.")

print("\nAll fixes applied successfully.")
print(f"  - {len(updates)} notes had cloze syntax stripped from Sentence field")
print("  - Phase badge rewritten as pure Mustache (no document.write)")
print("  - Timer bar added to all front templates")
print("  - Dark/light mode via prefers-color-scheme added to CSS")
