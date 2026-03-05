#!/usr/bin/env python3
"""
Build "George's German Vocabulary" Anki deck via AnkiConnect.

Steps:
1. Create the "George's German Vocab" note type with 3 card templates
2. Read and deduplicate selected_cards.json + new_vocab.json
3. Assign phases (1/2/3) based on priority and domain
4. Build cloze sentences for each note
5. Import all notes into Anki via AnkiConnect
6. Generate verification report
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

ANKI_URL = "http://localhost:8765"
MODEL_NAME = "George's German Vocab"
DECK_NAME = "George's German Vocabulary"

PROJECT_ROOT = Path(__file__).parent.parent.parent
AGENT2_DIR = PROJECT_ROOT / "agents" / "agent2_vocab"
AGENT3_DIR = PROJECT_ROOT / "agents" / "agent3_build"

SELECTED_CARDS_PATH = AGENT2_DIR / "selected_cards.json"
NEW_VOCAB_PATH = AGENT2_DIR / "new_vocab.json"

# ---------------------------------------------------------------------------
# AnkiConnect helpers
# ---------------------------------------------------------------------------

def anki_request(action: str, **params) -> dict:
    """Send a request to AnkiConnect and return the result."""
    payload = {"action": action, "version": 6, "params": params}
    try:
        resp = requests.post(ANKI_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"[ERROR] AnkiConnect request failed ({action}): {exc}", file=sys.stderr)
        sys.exit(1)
    if data.get("error"):
        return {"error": data["error"], "result": None}
    return {"error": None, "result": data.get("result")}


# ---------------------------------------------------------------------------
# Card templates HTML/CSS
# ---------------------------------------------------------------------------

CARD_CSS = """
/* ============================================================
   George's German Vocab — shared card styles
   ============================================================ */

:root {
  --bg:         #1a1a2e;
  --surface:    #16213e;
  --text:       #e0e0e0;
  --subtext:    #a0a8b8;
  --accent-de:  #7ec8e3;
  --accent-en:  #f5c842;

  /* Phase colours */
  --p1: #4fa3e0;   /* blue  */
  --p2: #3dbb72;   /* green */
  --p3: #f08030;   /* orange */
}

.card {
  font-family: "Noto Sans", "Segoe UI", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wrapper {
  max-width: 560px;
  width: 100%;
  margin: 0 auto;
  padding: 28px 24px 32px;
}

/* Phase badge */
.phase-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border-radius: 4px;
  padding: 2px 8px;
  margin-bottom: 12px;
}
.phase-badge.p1 { background: var(--p1); color: #fff; }
.phase-badge.p2 { background: var(--p2); color: #fff; }
.phase-badge.p3 { background: var(--p3); color: #fff; }

/* Card type label */
.card-type {
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--subtext);
  margin-bottom: 8px;
}

/* Main word */
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

/* IPA */
.ipa {
  font-size: 1rem;
  color: var(--subtext);
  margin-bottom: 16px;
}

/* POS hint */
.pos-hint {
  font-size: 0.8rem;
  color: var(--subtext);
  font-style: italic;
  margin-bottom: 6px;
}

/* Divider */
hr.divider {
  border: none;
  border-top: 1px solid #2e3a5a;
  margin: 18px 0;
}

/* Example sentence */
.sentence-de {
  font-size: 1.05rem;
  color: var(--text);
  line-height: 1.55;
  margin-bottom: 6px;
}

.sentence-en {
  font-size: 0.9rem;
  color: var(--subtext);
  font-style: italic;
  margin-bottom: 14px;
}

/* Answer highlight in cloze */
.answer {
  color: var(--accent-de);
  font-weight: 700;
  border-bottom: 2px solid var(--accent-de);
}

/* Blank in cloze front */
.blank {
  display: inline-block;
  min-width: 80px;
  border-bottom: 2px solid var(--accent-de);
  color: transparent;
  user-select: none;
}

/* Disambiguation note */
.disambig {
  font-size: 0.85rem;
  color: #f08080;
  margin-top: 10px;
  padding: 6px 10px;
  border-left: 3px solid #f08080;
  background: rgba(240,128,128,0.08);
  border-radius: 0 4px 4px 0;
}

/* Usage note */
.usage-note {
  font-size: 0.82rem;
  color: #90c0a0;
  margin-top: 8px;
  padding: 6px 10px;
  border-left: 3px solid #90c0a0;
  background: rgba(144,192,160,0.08);
  border-radius: 0 4px 4px 0;
}

/* Domain chips */
.domains {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.domain-chip {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: #2e3a5a;
  color: var(--subtext);
  border-radius: 12px;
  padding: 3px 10px;
}

/* Context sentence (prompt on EN→DE) */
.context-sentence {
  font-size: 0.9rem;
  color: var(--subtext);
  font-style: italic;
  margin-top: 8px;
  margin-bottom: 4px;
}
"""

# ------------------------------------------------------------------
# Template 1: EN → DE  (Production)
# ------------------------------------------------------------------

TMPL_EN_DE_FRONT = """
<div class="wrapper">
  <div class="card-type">EN → DE &nbsp;&middot;&nbsp; Production</div>

  {{#Phase}}
  <script>
    (function(){
      var p = "{{Phase}}".trim();
      var label = p === "1" ? "Phase 1" : p === "2" ? "Phase 2" : "Phase 3";
      var cls   = p === "1" ? "p1"      : p === "2" ? "p2"      : "p3";
      document.write('<span class="phase-badge ' + cls + '">' + label + '</span>');
    })();
  </script>
  {{/Phase}}

  <div class="word-en">{{WordTranslation}}</div>

  {{#POS}}<div class="pos-hint">{{POS}}</div>{{/POS}}

  {{#SentenceTranslation}}
  <hr class="divider">
  <div class="context-sentence">e.g. &ldquo;{{SentenceTranslation}}&rdquo;</div>
  {{/SentenceTranslation}}
</div>
"""

TMPL_EN_DE_BACK = """
{{FrontSide}}
<hr class="divider">
<div class="wrapper" style="padding-top:0">
  <div class="word-de">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}

  {{#Sentence}}
  <div class="sentence-de">{{Sentence}}</div>
  {{/Sentence}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}
  <div class="usage-note">{{Note}}</div>
  {{/Note}}

  {{#Domains}}
  <div class="domains" id="domains-en-de"></div>
  <script>
  (function(){
    var raw = "{{Domains}}";
    var el = document.getElementById("domains-en-de");
    if (!el || !raw.trim()) return;
    raw.split(",").forEach(function(d){
      var chip = document.createElement("span");
      chip.className = "domain-chip";
      chip.textContent = d.trim();
      el.appendChild(chip);
    });
  })();
  </script>
  {{/Domains}}
</div>
"""

# ------------------------------------------------------------------
# Template 2: DE → EN  (Recognition)
# ------------------------------------------------------------------

TMPL_DE_EN_FRONT = """
<div class="wrapper">
  <div class="card-type">DE → EN &nbsp;&middot;&nbsp; Recognition</div>

  {{#Phase}}
  <script>
    (function(){
      var p = "{{Phase}}".trim();
      var label = p === "1" ? "Phase 1" : p === "2" ? "Phase 2" : "Phase 3";
      var cls   = p === "1" ? "p1"      : p === "2" ? "p2"      : "p3";
      document.write('<span class="phase-badge ' + cls + '">' + label + '</span>');
    })();
  </script>
  {{/Phase}}

  <div class="word-de">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
</div>
"""

TMPL_DE_EN_BACK = """
{{FrontSide}}
<hr class="divider">
<div class="wrapper" style="padding-top:0">
  <div class="word-en">{{WordTranslation}}</div>

  {{#Sentence}}
  <div class="sentence-de">{{Sentence}}</div>
  {{/Sentence}}
  {{#SentenceTranslation}}
  <div class="sentence-en">{{SentenceTranslation}}</div>
  {{/SentenceTranslation}}

  {{#WordTranslationDisambiguate}}
  <div class="disambig">NOT: {{WordTranslationDisambiguate}}</div>
  {{/WordTranslationDisambiguate}}

  {{#Note}}
  <div class="usage-note">{{Note}}</div>
  {{/Note}}

  {{#Domains}}
  <div class="domains" id="domains-de-en"></div>
  <script>
  (function(){
    var raw = "{{Domains}}";
    var el = document.getElementById("domains-de-en");
    if (!el || !raw.trim()) return;
    raw.split(",").forEach(function(d){
      var chip = document.createElement("span");
      chip.className = "domain-chip";
      chip.textContent = d.trim();
      el.appendChild(chip);
    });
  })();
  </script>
  {{/Domains}}
</div>
"""

# ------------------------------------------------------------------
# Template 3: Sentence Cloze  (Context)
# ------------------------------------------------------------------

TMPL_CLOZE_FRONT = """
<div class="wrapper">
  <div class="card-type">Sentence Cloze &nbsp;&middot;&nbsp; Context</div>

  {{#Phase}}
  <script>
    (function(){
      var p = "{{Phase}}".trim();
      var label = p === "1" ? "Phase 1" : p === "2" ? "Phase 2" : "Phase 3";
      var cls   = p === "1" ? "p1"      : p === "2" ? "p2"      : "p3";
      document.write('<span class="phase-badge ' + cls + '">' + label + '</span>');
    })();
  </script>
  {{/Phase}}

  <div class="sentence-de" id="cloze-front-sentence" style="font-size:1.3rem; margin-top:12px;"></div>
  <div class="sentence-en" style="margin-top:8px;">{{SentenceTranslation}}</div>

  <script>
  (function(){
    var raw = "{{Sentence}}";
    var rendered = raw.replace(/[{][{]c1::([^}]*)[}][}]/g, '<span class="blank">[___]</span>');
    var el = document.getElementById("cloze-front-sentence");
    if (el) el.innerHTML = rendered;
  })();
  </script>
</div>
"""

TMPL_CLOZE_BACK = """
<div class="wrapper">
  <div class="card-type">Sentence Cloze &nbsp;&middot;&nbsp; Context</div>

  {{#Phase}}
  <script>
    (function(){
      var p = "{{Phase}}".trim();
      var label = p === "1" ? "Phase 1" : p === "2" ? "Phase 2" : "Phase 3";
      var cls   = p === "1" ? "p1"      : p === "2" ? "p2"      : "p3";
      document.write('<span class="phase-badge ' + cls + '">' + label + '</span>');
    })();
  </script>
  {{/Phase}}

  <div class="sentence-de" id="cloze-back-sentence" style="font-size:1.3rem; margin-top:12px;"></div>
  <div class="sentence-en" style="margin-top:8px;">{{SentenceTranslation}}</div>

  <hr class="divider">
  <div class="word-de" style="font-size:1.8rem;">{{Word}}</div>
  {{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
  <div class="word-en" style="font-size:1.2rem;">{{WordTranslation}}</div>

  {{#Domains}}
  <div class="domains" id="domains-cloze"></div>
  <script>
  (function(){
    var raw = "{{Domains}}";
    var el = document.getElementById("domains-cloze");
    if (!el || !raw.trim()) return;
    raw.split(",").forEach(function(d){
      var chip = document.createElement("span");
      chip.className = "domain-chip";
      chip.textContent = d.trim();
      el.appendChild(chip);
    });
  })();
  </script>
  {{/Domains}}

  <script>
  (function(){
    var raw = "{{Sentence}}";
    var rendered = raw.replace(/[{][{]c1::([^}]*)[}][}]/g, '<span class="answer">$1</span>');
    var el = document.getElementById("cloze-back-sentence");
    if (el) el.innerHTML = rendered;
  })();
  </script>
</div>
"""


# ---------------------------------------------------------------------------
# Step 1: Create the note type
# ---------------------------------------------------------------------------

def create_note_type():
    """Create the George's German Vocab note type if it doesn't already exist."""
    print("\n[1] Checking / creating note type ...")
    result = anki_request("modelNames")
    existing = result.get("result") or []
    if MODEL_NAME in existing:
        print(f"    Note type '{MODEL_NAME}' already exists — skipping creation.")
        return

    fields = [
        {"name": "Word"},
        {"name": "POS"},
        {"name": "Article"},
        {"name": "WordTranslation"},
        {"name": "WordTranslationDisambiguate"},
        {"name": "IPA"},
        {"name": "Audio"},
        {"name": "Sentence"},
        {"name": "ClozeWord"},
        {"name": "SentenceTranslation"},
        {"name": "Domains"},
        {"name": "Phase"},
        {"name": "Note"},
    ]

    templates = [
        {
            "Name": "EN → DE",
            "Front": TMPL_EN_DE_FRONT,
            "Back": TMPL_EN_DE_BACK,
        },
        {
            "Name": "DE → EN",
            "Front": TMPL_DE_EN_FRONT,
            "Back": TMPL_DE_EN_BACK,
        },
        {
            "Name": "Sentence Cloze",
            "Front": TMPL_CLOZE_FRONT,
            "Back": TMPL_CLOZE_BACK,
        },
    ]

    result = anki_request(
        "createModel",
        modelName=MODEL_NAME,
        inOrderFields=[f["name"] for f in fields],
        css=CARD_CSS,
        isCloze=False,
        cardTemplates=templates,
    )
    if result.get("error"):
        print(f"    [ERROR] Could not create note type: {result['error']}")
        sys.exit(1)
    print(f"    Created note type '{MODEL_NAME}'.")


# ---------------------------------------------------------------------------
# Step 2: Create the deck
# ---------------------------------------------------------------------------

def create_deck():
    """Create the deck (idempotent)."""
    print("\n[2] Creating deck ...")
    result = anki_request("createDeck", deck=DECK_NAME)
    if result.get("error"):
        print(f"    [WARN] createDeck error: {result['error']}")
    else:
        print(f"    Deck '{DECK_NAME}' ready (id={result['result']}).")


# ---------------------------------------------------------------------------
# Step 3: Load and deduplicate data
# ---------------------------------------------------------------------------

def infer_pos_from_word(word: str) -> str:
    """Infer POS from the word text (best-effort)."""
    lower = word.lower()
    articles = {"der ", "die ", "das ", "ein ", "eine "}
    if any(word.startswith(a) for a in {"der ", "die ", "das "}):
        return "noun"
    if lower.endswith("en") and not any(word.startswith(a) for a in articles):
        return "verb"
    return "phrase"


def make_cloze(sentence: str, word: str) -> str:
    """
    Wrap the first occurrence of `word` (or its base form) in the sentence
    with {{c1::...}} Anki cloze syntax.

    If the sentence already contains {{c1::...}}, return it unchanged.
    If the word cannot be found in the sentence, return the sentence unchanged.
    """
    if "{{c1::" in sentence:
        return sentence

    # Strip article prefix for lookup
    bare_word = word
    for article in ("der ", "die ", "das ", "ein ", "eine "):
        if word.startswith(article):
            bare_word = word[len(article):]
            break

    # Try a case-insensitive whole-word match
    pattern = re.compile(r'\b(' + re.escape(bare_word) + r')\b', re.IGNORECASE)
    new_sentence, n = pattern.subn(r'{{c1::\1}}', sentence, count=1)
    if n > 0:
        return new_sentence

    # Fallback: substring match (for compound words etc.)
    idx = sentence.lower().find(bare_word.lower())
    if idx >= 0:
        matched = sentence[idx:idx + len(bare_word)]
        return sentence[:idx] + "{{c1::" + matched + "}}" + sentence[idx + len(bare_word):]

    return sentence  # Can't find — leave as-is


def assign_phase(priority: float, domains: list, scheduling_status: str) -> str:
    """
    Phase 1: priority >= 8 OR (domains include key social/communication domains AND new status); ~80 items
    Phase 2: priority 5-7.5 AND core domains; ~120 items
    Phase 3: everything else
    """
    phase1_domains = {"greetings", "social", "questions", "feelings"}
    # Expanded core domains: actions and numbers are critical for child conversation
    core_domains = {
        "play", "food", "family", "animals", "body", "colours",
        "actions", "numbers", "toys", "location",
    }

    if priority >= 8:
        return "1"
    if (priority >= 7 and bool(phase1_domains.intersection(set(domains)))
            and scheduling_status == "new"):
        return "1"
    if 5 <= priority < 8 and bool(core_domains.union(phase1_domains).intersection(set(domains))):
        return "2"
    return "3"


def load_and_deduplicate():
    """
    Load both input files, deduplicate by German word (case-insensitive),
    and return a unified list of note dicts.

    new_vocab.json takes precedence for words that appear in both files
    (it has richer structured data). However, selected_cards.json items
    carry existing scheduling data and rich sentences, so we merge them:
    prefer new_vocab data for fields it provides, keep existing sentence
    if new_vocab sentence is missing.
    """
    print("\n[3] Loading and deduplicating vocabulary ...")

    with open(SELECTED_CARDS_PATH) as f:
        selected = json.load(f)

    with open(NEW_VOCAB_PATH) as f:
        new_vocab = json.load(f)

    # ---- Build lookup of new_vocab by bare word (no article) ----
    def bare(w: str) -> str:
        for a in ("der ", "die ", "das ", "ein ", "eine "):
            if w.lower().startswith(a):
                return w[len(a):].strip().lower()
        return w.strip().lower()

    new_vocab_by_bare = {}
    for nv in new_vocab:
        new_vocab_by_bare[bare(nv["word"])] = nv

    # ---- Process selected_cards ----
    notes = []
    merged_count = 0
    kept_from_existing = 0

    for card in selected:
        fields = card["fields"]
        word = fields["Word"].strip()
        bw = bare(word)

        # Determine POS
        nv = new_vocab_by_bare.get(bw)
        if nv:
            pos = nv.get("pos") or infer_pos_from_word(word)
            article = nv.get("article") or ""
            domains = nv.get("domains") or card.get("child_domains") or []
            priority = nv.get("priority") or card.get("priority_score") or 0
            word_display = nv["word"]  # use new_vocab word form (has article)
            translation = nv.get("translation") or fields.get("WordTranslation", "")
            sentence_de = nv.get("example_sentence_de") or fields.get("Sentence", "")
            sentence_en = nv.get("example_sentence_en") or fields.get("SentenceTranslation", "")
            notes_text = nv.get("notes") or fields.get("Note/Mnemonic", "")
            merged_count += 1
        else:
            pos = infer_pos_from_word(word)
            article = ""
            if word.startswith("der "):
                article = "der"
            elif word.startswith("die "):
                article = "die"
            elif word.startswith("das "):
                article = "das"
            domains = card.get("child_domains") or []
            priority = card.get("priority_score") or 0
            word_display = word
            translation = fields.get("WordTranslation", "")
            sentence_de = fields.get("Sentence", "")
            sentence_en = fields.get("SentenceTranslation", "")
            notes_text = fields.get("Note/Mnemonic", "")
            kept_from_existing += 1

        phase = assign_phase(priority, domains, card.get("scheduling_status", "new"))

        # Build cloze sentence
        cloze_sentence = make_cloze(sentence_de, word_display) if sentence_de else ""

        notes.append({
            "word": word_display,
            "pos": pos,
            "article": article,
            "translation": translation,
            "disambiguate": fields.get("WordTranslationDisambiguate", ""),
            "ipa": fields.get("IPA", ""),
            "sentence": cloze_sentence,
            "sentence_translation": sentence_en,
            "domains": domains,
            "phase": phase,
            "note": notes_text,
            "source": "existing",
            "priority": priority,
        })

    # ---- Process new_vocab items that are NOT already in selected_cards ----
    existing_bare_words = {bare(card["fields"]["Word"]) for card in selected}
    added_new = 0

    for nv in new_vocab:
        bw = bare(nv["word"])
        if bw in existing_bare_words:
            continue  # already handled above

        pos = nv.get("pos") or infer_pos_from_word(nv["word"])
        domains = nv.get("domains") or []
        priority = nv.get("priority") or 0
        sentence_de = nv.get("example_sentence_de", "")
        sentence_en = nv.get("example_sentence_en", "")
        cloze_sentence = make_cloze(sentence_de, nv["word"]) if sentence_de else ""
        phase = assign_phase(priority, domains, "new")

        notes.append({
            "word": nv["word"],
            "pos": pos,
            "article": nv.get("article") or "",
            "translation": nv.get("translation", ""),
            "disambiguate": "",
            "ipa": "",
            "sentence": cloze_sentence,
            "sentence_translation": sentence_en,
            "domains": domains,
            "phase": phase,
            "note": nv.get("notes", ""),
            "source": "new",
            "priority": priority,
        })
        added_new += 1

    # Deduplicate within the final list by exact word (case-insensitive)
    seen = {}
    deduped = []
    dup_count = 0
    for n in notes:
        key = n["word"].strip().lower()
        if key in seen:
            dup_count += 1
            # Keep the one with higher priority
            if n["priority"] > seen[key]["priority"]:
                idx = next(i for i, x in enumerate(deduped) if x["word"].strip().lower() == key)
                deduped[idx] = n
        else:
            seen[key] = n
            deduped.append(n)

    print(f"    Selected cards loaded:       {len(selected)}")
    print(f"    New vocab items loaded:       {len(new_vocab)}")
    print(f"    Merged (overlap):             {merged_count}")
    print(f"    Kept from existing only:      {kept_from_existing}")
    print(f"    Added net-new:                {added_new}")
    print(f"    Duplicates removed:           {dup_count}")
    print(f"    Total notes after dedup:      {len(deduped)}")

    # Phase distribution
    from collections import Counter
    phase_counts = Counter(n["phase"] for n in deduped)
    print(f"    Phase 1: {phase_counts['1']}  Phase 2: {phase_counts['2']}  Phase 3: {phase_counts['3']}")

    return deduped, {
        "selected_count": len(selected),
        "new_vocab_count": len(new_vocab),
        "merged": merged_count,
        "kept_existing": kept_from_existing,
        "added_new": added_new,
        "duplicates_removed": dup_count,
        "total": len(deduped),
        "phase_counts": dict(phase_counts),
    }


# ---------------------------------------------------------------------------
# Step 4: Build Anki notes and import
# ---------------------------------------------------------------------------

def build_anki_note(note: dict) -> dict:
    """Convert our internal note dict to an AnkiConnect note object."""
    domains_str = ",".join(note.get("domains") or [])
    tags = ["child_vocab", f"phase::{note['phase']}"]
    for d in (note.get("domains") or []):
        tags.append(f"domain::{d}")

    return {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {
            "Word": note["word"],
            "POS": note.get("pos") or "",
            "Article": note.get("article") or "",
            "WordTranslation": note.get("translation") or "",
            "WordTranslationDisambiguate": note.get("disambiguate") or "",
            "IPA": note.get("ipa") or "",
            "Audio": "",
            "Sentence": note.get("sentence") or "",
            "ClozeWord": "",
            "SentenceTranslation": note.get("sentence_translation") or "",
            "Domains": domains_str,
            "Phase": note["phase"],
            "Note": note.get("note") or "",
        },
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
        },
        "tags": tags,
    }


def import_notes(notes: list) -> dict:
    """
    Import notes into Anki in batches of 50.
    Returns a summary dict with counts of successes and failures.
    """
    print(f"\n[4] Importing {len(notes)} notes into Anki ...")
    batch_size = 50
    total = len(notes)
    success_count = 0
    fail_count = 0
    fail_log = []

    for batch_start in range(0, total, batch_size):
        batch = notes[batch_start: batch_start + batch_size]
        anki_notes = [build_anki_note(n) for n in batch]

        result = anki_request("addNotes", notes=anki_notes)
        if result.get("error"):
            print(f"    [ERROR] Batch {batch_start}-{batch_start + len(batch)}: {result['error']}")
            fail_count += len(batch)
            for n in batch:
                fail_log.append({"word": n["word"], "error": result["error"]})
            continue

        ids = result.get("result") or []
        for i, note_id in enumerate(ids):
            word = batch[i]["word"]
            if note_id is None:
                fail_count += 1
                fail_log.append({"word": word, "error": "duplicate or rejected"})
                print(f"    [SKIP] '{word}' — duplicate or rejected")
            else:
                success_count += 1

        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"    Batch {batch_num}/{total_batches}: added {sum(1 for x in ids if x is not None)}/{len(batch)}")
        time.sleep(0.1)  # brief pause to avoid overwhelming AnkiConnect

    print(f"\n    Import complete: {success_count} added, {fail_count} failed/skipped.")
    return {
        "success": success_count,
        "failed": fail_count,
        "fail_log": fail_log,
    }


# ---------------------------------------------------------------------------
# Step 5: Verification
# ---------------------------------------------------------------------------

def verify_import(notes: list, import_stats: dict) -> dict:
    """
    Query AnkiConnect to verify the deck was populated correctly.
    Sample a few notes and check their fields.
    """
    print("\n[5] Verifying import ...")

    # Find all notes in the deck
    result = anki_request("findNotes", query=f'deck:"{DECK_NAME}"')
    if result.get("error"):
        print(f"    [ERROR] findNotes: {result['error']}")
        return {}

    found_ids = result.get("result") or []
    print(f"    Notes found in deck: {len(found_ids)}")

    # Phase breakdown via tags
    phase_results = {}
    for p in ["1", "2", "3"]:
        r = anki_request("findNotes", query=f'deck:"{DECK_NAME}" tag:phase::{p}')
        phase_results[p] = len(r.get("result") or [])

    print(f"    Phase 1: {phase_results.get('1',0)}  Phase 2: {phase_results.get('2',0)}  Phase 3: {phase_results.get('3',0)}")

    # Sample 10 notes and check their info
    sample_ids = found_ids[:10]
    if sample_ids:
        result2 = anki_request("notesInfo", notes=sample_ids)
        sample_notes = result2.get("result") or []
        print(f"    Sample note check ({len(sample_notes)} notes):")
        for sn in sample_notes[:5]:
            word = sn.get("fields", {}).get("Word", {}).get("value", "?")
            phase = sn.get("fields", {}).get("Phase", {}).get("value", "?")
            domains = sn.get("fields", {}).get("Domains", {}).get("value", "?")
            print(f"      Word='{word}' Phase={phase} Domains={domains}")

    return {
        "total_in_deck": len(found_ids),
        "phase_breakdown": phase_results,
        "sample_note_ids": sample_ids,
    }


# ---------------------------------------------------------------------------
# Step 6: Generate report data
# ---------------------------------------------------------------------------

def collect_domain_counts(notes: list) -> dict:
    from collections import Counter
    counts = Counter()
    for n in notes:
        for d in (n.get("domains") or []):
            counts[d] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def format_sample_cards(notes: list) -> list:
    """Pick 3 representative notes (one per phase) and describe front/back."""
    samples = []
    for phase in ["1", "2", "3"]:
        candidates = [n for n in notes if n["phase"] == phase]
        if candidates:
            n = candidates[0]
            samples.append(n)
    return samples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("George's German Vocabulary — Anki Deck Builder")
    print("=" * 60)

    # 1. Create note type
    create_note_type()

    # 2. Create deck
    create_deck()

    # 3. Load and deduplicate
    notes, dedup_stats = load_and_deduplicate()

    # 4. Import
    import_stats = import_notes(notes)

    # 5. Verify
    verify_stats = verify_import(notes, import_stats)

    # 6. Save data for report
    report_data = {
        "dedup_stats": dedup_stats,
        "import_stats": {
            "success": import_stats["success"],
            "failed": import_stats["failed"],
            "fail_log": import_stats["fail_log"][:20],  # truncate
        },
        "verify_stats": verify_stats,
        "domain_counts": collect_domain_counts(notes),
        "sample_cards": format_sample_cards(notes),
        "notes_preview": [
            {
                "word": n["word"],
                "phase": n["phase"],
                "domains": n["domains"],
                "sentence": n["sentence"],
                "translation": n["translation"],
                "ipa": n["ipa"],
            }
            for n in notes[:30]
        ],
    }

    report_data_path = AGENT3_DIR / "build_data.json"
    with open(report_data_path, "w") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"\n[6] Report data saved to {report_data_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total notes prepared:  {dedup_stats['total']}")
    print(f"  Successfully imported: {import_stats['success']}")
    print(f"  Failed/skipped:        {import_stats['failed']}")
    print(f"  Deck: '{DECK_NAME}'")
    print(f"  Note type: '{MODEL_NAME}'")
    print("=" * 60)


if __name__ == "__main__":
    main()
