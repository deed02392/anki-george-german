#!/usr/bin/env python3
"""Generate German vocabulary cards from text or domain briefs.

Two subcommands:

  text   — Extract vocabulary from a German text file, enrich via LLM,
           and import to Anki.
  domain — Generate vocabulary from a topic brief via LLM.

Both output 13-field notes compatible with "George's German Vocab" and
import directly via AnkiConnect.

Usage:
    uv run python tools/generate_vocab.py text \\
        --file data/books/Schachenovelle.txt \\
        --source schachnovelle --paragraphs 1-30 \\
        --domain literature --phase 4 --dry-run

    uv run python tools/generate_vocab.py domain \\
        --brief "IT security vocabulary" \\
        --source it_security --count 30 \\
        --domain security,technology --phase 4 --dry-run

Requires:
    - Anki running with AnkiConnect
    - appleconnect CLI for Floodgate OIDC
    - spaCy model: uv run python -m spacy download de_dep_news_trf
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Ensure tools/ is on sys.path so sibling imports work regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import spacy
from charsplit import Splitter
from rapidfuzz import fuzz

from _anki import anki, DECK, MODEL
from _llm import get_floodgate_token, call_llm
from enrich_ipa_audio import enrich_notes

VALID_POS = (
    "noun", "verb", "adjective", "adverb",
    "pronoun", "preposition", "numeral",
    "conjunction", "interjection", "phrase",
)
VALID_POS_STR = "|".join(VALID_POS)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_nlp_model = None

def _get_nlp():
    """Lazy-load the spaCy model (expensive, only load once)."""
    global _nlp_model
    if _nlp_model is None:
        _nlp_model = spacy.load("de_dep_news_trf")
    return _nlp_model

# German function-word POS tags to filter out
FILTER_POS = {"DET", "ADP", "CONJ", "CCONJ", "SCONJ", "PRON", "AUX",
              "PUNCT", "SPACE", "SYM", "X", "PART"}

# Ultra-common words to skip even if they're NOUN/VERB/ADJ/ADV
STOP_WORDS = {
    # sein/haben/werden
    "sein", "haben", "werden", "ist", "sind", "war", "waren", "hat", "hatte",
    "wird", "wurde", "worden", "gewesen", "gehabt",
    # Modal verbs
    "können", "müssen", "sollen", "wollen", "dürfen", "mögen",
    "kann", "muss", "soll", "will", "darf", "mag",
    "konnte", "musste", "sollte", "wollte", "durfte", "mochte",
    # Common conjunctions/adverbs that spaCy sometimes tags as ADV
    "und", "oder", "aber", "denn", "sondern", "weil", "dass", "wenn",
    "als", "ob", "da", "doch", "noch", "schon", "auch", "nur", "sehr",
    "nicht", "kein", "keine", "keinen", "keiner", "keinem",
    # Pronouns that slip through
    "ich", "du", "er", "sie", "es", "wir", "ihr", "man",
    "mich", "dich", "sich", "uns", "euch",
    "mir", "dir", "ihm", "ihnen",
    "mein", "dein", "sein", "ihr", "unser", "euer",
    # Common prepositions tagged as ADV
    "hier", "dort", "dann", "nun", "so", "wie", "wo",
    # Other ultra-common
    "machen", "tun", "gehen", "kommen", "geben", "nehmen", "lassen",
    "sagen", "sehen", "wissen", "stehen", "finden",
    "gut", "groß", "klein", "neu", "alt", "lang", "kurz",
    "viel", "wenig", "mehr", "ganz", "recht",
    "ja", "nein", "bitte", "danke",
    "etwas", "nichts", "alles", "alle",
}


# ── Stage 1: Ingest text ─────────────────────────────────────────────────────

def ingest_text(filepath, paragraphs=None):
    """Read a text file and return the specified paragraph range.

    Paragraphs are non-blank lines. --paragraphs "1-30" returns lines 1–30.
    """
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    if paragraphs:
        m = re.match(r"(\d+)-(\d+)", paragraphs)
        if m:
            start, end = int(m.group(1)) - 1, int(m.group(2))
            lines = lines[start:end]
        else:
            # Single number
            idx = int(paragraphs) - 1
            lines = [lines[idx]] if idx < len(lines) else []

    text = "\n".join(lines)
    print(f"Ingested {len(lines)} paragraphs ({len(text)} chars)")
    return text


# ── Stage 2: spaCy tokenization + lemmatization ──────────────────────────────

def extract_lemmas(text, nlp):
    """Extract content-word lemmas with frequency counts.

    Returns:
        List of (lemma, pos, count) sorted by frequency descending.
    """
    doc = nlp(text)
    freq = {}
    for token in doc:
        if token.pos_ in FILTER_POS:
            continue
        if not token.is_alpha:
            continue
        lemma = token.lemma_
        if lemma.lower() in STOP_WORDS:
            continue
        if token.pos_ not in ("NOUN", "VERB", "ADJ", "ADV"):
            continue
        key = (lemma, token.pos_)
        freq[key] = freq.get(key, 0) + 1

    results = [(lemma, pos, count) for (lemma, pos), count in freq.items()]
    results.sort(key=lambda x: -x[2])
    print(f"Extracted {len(results)} unique lemmas")
    return results


# ── Stage 3: Check existing deck ─────────────────────────────────────────────

def _gendered_counterpart(bare):
    """Return the bare counterpart of a gendered noun, if any.

    Given 'lehrerin', returns 'lehrer' (masculine of feminine -in form).
    Given 'lehrer', returns 'lehrerin' (feminine of masculine form).
    Works on bare words (no article).
    """
    low = bare.lower()
    # Feminine -> masculine: Lehrerin -> Lehrer, Freundin -> Freund
    if low.endswith("erin") and len(low) > 5:
        return low[:-2]  # drop "in" from "erin" -> "er"
    if low.endswith("in") and len(low) > 3 and not low.endswith("stein"):
        return low[:-2]  # Freundin -> Freund
    # Masculine -> feminine
    if low.endswith("er") and len(low) > 3:
        return low + "in"  # Lehrer -> Lehrerin
    return None


def check_existing_deck(lemmas, source):
    """Check which lemmas already exist in the deck.

    For existing notes: tags them with source::{source}.
    Returns: list of new lemmas (not in deck).
    """
    note_ids = anki("findNotes", query=f'"deck:{DECK}" "note:{MODEL}"')
    if not note_ids:
        print("No existing notes found in deck.")
        return lemmas

    all_notes = anki("notesInfo", notes=note_ids)

    # Build lookup: lowercase bare word -> note_id
    known = {}
    for note in all_notes:
        if "Word" not in note["fields"]:
            continue
        word = note["fields"]["Word"]["value"]
        bare = re.sub(r"^(der|die|das|ein|eine|sich)\s+", "", word, flags=re.IGNORECASE).strip().lower()
        known[bare] = note["noteId"]

    existing = []
    gendered_skipped = []
    new = []
    for lemma, pos, count in lemmas:
        if lemma.lower() in known:
            existing.append((lemma, known[lemma.lower()]))
        else:
            # Skip feminine/masculine forms whose counterpart already exists
            counterpart = _gendered_counterpart(lemma.lower())
            if counterpart and counterpart in known:
                gendered_skipped.append((lemma, counterpart))
            else:
                new.append((lemma, pos, count))

    # Tag existing notes with source
    if existing and source:
        tag = f"source::{source}"
        existing_ids = [nid for _, nid in existing]
        # Tag in batches of 50
        for i in range(0, len(existing_ids), 50):
            batch = existing_ids[i:i + 50]
            notes_str = " ".join(str(nid) for nid in batch)
            anki("addTags", notes=batch, tags=tag)
        print(f"  Tagged {len(existing)} existing notes with '{tag}'")

    if gendered_skipped:
        print(f"  Skipped {len(gendered_skipped)} gendered duplicates:")
        for fem, masc in gendered_skipped:
            print(f"    {fem} (counterpart '{masc}' already in deck)")

    print(f"  Existing: {len(existing)}, Gendered skips: {len(gendered_skipped)}, New: {len(new)}")
    return new


# ── Stage 4: Compound word detection ─────────────────────────────────────────

def _is_known_or_transparent(word, known_words, splitter, depth=0):
    """Check if a word is known or recursively splits into known components."""
    if word.lower() in known_words:
        return True, [word]
    if depth >= 3:
        return False, []

    splits = splitter.split_compound(word)
    if not splits:
        return False, []

    best_score, left, right = splits[0]
    if best_score <= 0.5:
        return False, []

    left_clean = left.strip("-")
    right_clean = right.strip("-")

    left_ok, left_parts = _is_known_or_transparent(
        left_clean, known_words, splitter, depth + 1)
    if not left_ok:
        return False, []

    right_ok, right_parts = _is_known_or_transparent(
        right_clean, known_words, splitter, depth + 1)
    if not right_ok:
        return False, []

    return True, left_parts + right_parts


def filter_transparent_compounds(lemmas, known_words):
    """Filter out compound nouns whose components are all known.

    Uses CharSplit for character n-gram compound splitting.
    Recursively splits components that aren't directly known.
    """
    splitter = Splitter()
    kept = []
    filtered = 0

    for lemma, pos, count in lemmas:
        if pos != "NOUN":
            kept.append((lemma, pos, count))
            continue

        is_transparent, parts = _is_known_or_transparent(
            lemma, known_words, splitter)

        if is_transparent and len(parts) >= 2:
            parts_str = " + ".join(parts)
            print(f"  SKIP compound: {lemma} = {parts_str}")
            filtered += 1
        else:
            kept.append((lemma, pos, count))

    print(f"  Filtered {filtered} transparent compounds, {len(kept)} remaining")
    return kept


# ── Stage 5: Summarise text chunk ────────────────────────────────────────────

def summarise_text(text, token):
    """Get a 2-3 sentence summary of the source text for context."""
    messages = [{
        "role": "user",
        "content": (
            "Summarise this German text in 2-3 sentences in English. "
            "Describe the scene, themes, and emotional tone. "
            "This summary will be used as context for generating example sentences.\n\n"
            f"{text[:3000]}"
        ),
    }]
    try:
        # call_llm returns parsed JSON, but here we want plain text
        resp = requests.post(
            "https://floodgate.g.apple.com/api/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "anki-george-german/1.0",
            },
            json={
                "model": "aws:anthropic.claude-sonnet-4-20250514-v1:0",
                "max_tokens": 300,
                "messages": messages,
            },
            timeout=60,
        )
        resp.raise_for_status()
        summary = resp.json()["choices"][0]["message"]["content"].strip()
        print(f"  Summary: {summary[:120]}...")
        return summary
    except Exception as e:
        print(f"  Warning: summarisation failed ({e}), proceeding without context")
        return ""


# ── Stage 6: LLM enrichment ─────────────────────────────────────────────────

def build_enrichment_prompt(batch, context_summary, source_text=None,
                            num_sentences=2):
    """Build the prompt to enrich a batch of words."""
    words_block = ""
    for i, (lemma, pos, count) in enumerate(batch, 1):
        words_block += f"{i}. {lemma} [{pos}] (freq: {count})\n"

    context_section = ""
    if context_summary:
        context_section = (
            f"\nContext: These words come from a German text. "
            f"Summary: {context_summary}\n"
            f"Generate example sentences that fit this literary/thematic world "
            f"without quoting the source verbatim.\n"
        )

    return f"""\
You are generating German vocabulary flashcards for an adult learner.
{context_section}
For each word below, provide all fields for an Anki flashcard. Return ONLY a JSON \
array (no markdown, no commentary).

Rules:
- For nouns: include the article (der/die/das) in the "word" field
- For reflexive verbs: use "sich" + infinitive (e.g. "sich bemühen", not "bemühen (sich)")
- "article" is "der", "die", or "das" for nouns, empty string for others
- "translation" is a concise English translation (British English: colour, mum, favourite)
- "disambiguation" clarifies meaning if the word has multiple common translations (else empty)
- Generate exactly {num_sentences} example sentence(s) per word in the "sentences" array
- Each sentence should show the word in a DIFFERENT grammatical context \
(different tenses, cases, nominalised forms, etc.)
- Each sentence entry has its own "pos" ({VALID_POS_STR}) and "cloze_word"
- "cloze_word" is the EXACT form of the word as it appears in the sentence (case-sensitive). \
Copy-paste from the sentence — if the sentence has "den Apfel", cloze_word must be "den Apfel" not "Der Apfel". \
For separable verbs where the prefix separates, use ~ (tilde) between parts (e.g. "machte~auf")
- For separable verbs: at least one sentence MUST show the prefix separating from the stem \
(e.g. "Er machte die Tür auf" not only "Er wollte die Tür aufmachen")
- For nouns: include the article in "cloze_word" if one precedes the noun in the sentence \
(e.g. if sentence is "Ich esse den Apfel", cloze_word is "den Apfel" not just "Apfel")
- For reflexive verbs: include the reflexive pronoun in "cloze_word" using ~ \
(e.g. if sentence is "Er bemühte sich", cloze_word is "bemühte~sich")
- "sentence_translation" is the English translation (British English)
- Sentences should be 5-15 words, NOT verbatim quotes from the source
- "domains" is a comma-separated list of relevant topic domains
- "note" is an optional usage note (empty if not needed)


Words:
{words_block}
Each element in the JSON array:
{{
  "word": "<word with article for nouns, sich + infinitive for reflexive verbs>",
  "article": "<der|die|das or empty>",
  "translation": "<English translation>",
  "disambiguation": "<disambiguation or empty>",
  "sentences": [
    {{
      "sentence": "<German example sentence>",
      "cloze_word": "<exact form in sentence, ~ for separable verbs>",
      "sentence_translation": "<English translation of sentence>",
      "pos": "<{VALID_POS_STR}>"
    }}
  ],
  "domains": "<comma-separated domains>",
  "note": "<usage note or empty>"
}}"""


def enrich_batch(batch, token, context_summary, source_text=None,
                 num_sentences=2):
    """Send a batch of words to the LLM for enrichment.

    Returns list of enriched word dicts, or None on failure.
    """
    prompt = build_enrichment_prompt(batch, context_summary, source_text,
                                     num_sentences)
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(2):
        try:
            result = call_llm(messages, token, max_tokens=8192)
            if not isinstance(result, list):
                print(f"  Bad response shape (attempt {attempt + 1}): not a list")
                if attempt == 0:
                    continue
                return None

            if len(result) != len(batch):
                print(f"  Bad response length (attempt {attempt + 1}): "
                      f"expected {len(batch)}, got {len(result)}")
                if attempt == 0:
                    continue
                return None

            return result

        except json.JSONDecodeError as e:
            print(f"  JSON parse error (attempt {attempt + 1}): {e}")
            if attempt == 0:
                continue
            return None
        except requests.HTTPError as e:
            print(f"  HTTP error (attempt {attempt + 1}): {e}")
            if hasattr(e, "response") and e.response.status_code == 401:
                print("  Refreshing OIDC token...")
                token = get_floodgate_token()
            if attempt == 0:
                time.sleep(2)
                continue
            return None

    return None


# ── Stage 7: Quality validation ──────────────────────────────────────────────

_ARTICLES_RE = re.compile(
    r'^(der|die|das|den|dem|des|ein|eine|einen|einem|eines|einer|'
    r'kein|keine|keinen|keinem|keines|keiner|'
    r'dieser|diese|dieses|diesen|diesem|jeder|jede|jedes|jeden|jedem)\s+',
    re.IGNORECASE,
)


def _find_noun_chunk(sentence, bare):
    """Find the spaCy noun chunk containing `bare` in `sentence`.

    Returns the chunk text if a valid noun phrase is found (starts with
    DET/PRON, contains only one noun), else None.
    """
    nlp = _get_nlp()
    doc = nlp(sentence)
    best = None
    for chunk in doc.noun_chunks:
        if bare not in chunk.text:
            continue
        # Only accept chunks headed by a determiner or pronoun
        if chunk[0].pos_ not in ("DET", "PRON"):
            continue
        # Reject chunks containing multiple nouns
        if sum(1 for t in chunk if t.pos_ in ("NOUN", "PROPN")) > 1:
            continue
        if best is None or len(chunk.text) < len(best.text):
            best = chunk
    return best.text if best else None


def normalise_cloze(card):
    """Fix common cloze_word issues using spaCy noun chunks.

    Fixes applied:
    1. Bare noun expansion: if cloze_word is a single bare noun and the
       sentence has a determiner before it, expand to the full noun phrase
       (e.g. 'Kind' → 'Jedes Kind')
    2. Case correction: 'Der Meister' → 'den Meister' if case-insensitive
       match exists in sentence
    3. Article form mismatch: if cloze_word has a different article than
       the sentence, find the correct noun phrase via spaCy
    4. Strip leading 'NOT:' from disambiguation
    """
    sentences = card.get("sentences")
    if not sentences:
        return card

    repairs = []

    for sent in sentences:
        sentence = sent.get("sentence", "")
        cloze = sent.get("cloze_word", "")
        if not sentence or not cloze:
            continue

        parts = [p.strip() for p in cloze.split("~") if p.strip()]
        new_parts = []
        for part in parts:
            # 1. Exact match — but check if bare noun needs expansion
            if part in sentence:
                if sent.get("pos") == "noun" and " " not in part:
                    chunk = _find_noun_chunk(sentence, part)
                    if chunk and chunk != part and chunk in sentence:
                        new_parts.append(chunk)
                        repairs.append(f"noun chunk: '{part}' → '{chunk}'")
                        continue
                new_parts.append(part)
                continue

            # 2. Case-insensitive match
            idx = sentence.lower().find(part.lower())
            if idx >= 0:
                actual = sentence[idx:idx + len(part)]
                new_parts.append(actual)
                repairs.append(f"case fix: '{part}' → '{actual}'")
                continue

            # 3. Article form mismatch — strip article, find bare noun,
            #    use spaCy to rebuild noun phrase
            m = _ARTICLES_RE.match(part)
            if m:
                bare = part[m.end():]
                bare_idx = sentence.find(bare)
                if bare_idx < 0:
                    bare_idx_ci = sentence.lower().find(bare.lower())
                    if bare_idx_ci >= 0:
                        bare = sentence[bare_idx_ci:bare_idx_ci + len(bare)]

                chunk = _find_noun_chunk(sentence, bare)
                if chunk and chunk in sentence:
                    new_parts.append(chunk)
                    repairs.append(f"noun phrase fix: '{part}' → '{chunk}'")
                    continue

            # Fallback: keep original
            new_parts.append(part)

        sent["cloze_word"] = "~".join(new_parts)

    # Strip 'NOT: ' from disambiguation
    disambig = card.get("disambiguation", "")
    if disambig.startswith("NOT: ") or disambig.startswith("NOT:"):
        cleaned = disambig.removeprefix("NOT: ").removeprefix("NOT:")
        repairs.append("stripped 'NOT:' from disambiguation")
        card["disambiguation"] = cleaned

    if repairs:
        print(f"  REPAIR {card.get('word', '?')}: {'; '.join(repairs)}")

    return card


def validate_card(card, source_text=None):
    """Validate a single enriched card. Returns (is_valid, errors)."""
    errors = []

    # Required top-level fields
    for field in ("word", "translation"):
        if not card.get(field):
            errors.append(f"missing '{field}'")

    # Must have sentences array
    sentences = card.get("sentences")
    if not sentences or not isinstance(sentences, list):
        errors.append("missing or empty 'sentences' array")
        return False, errors

    if errors:
        return False, errors

    # Validate each sentence entry
    has_noun = False
    for i, sent in enumerate(sentences):
        prefix = f"sentences[{i}]"
        for field in ("sentence", "cloze_word", "sentence_translation", "pos"):
            if not sent.get(field):
                errors.append(f"{prefix}: missing '{field}'")

        if not sent.get("pos"):
            continue

        # POS validation
        if sent["pos"] not in VALID_POS:
            errors.append(f"{prefix}: invalid pos '{sent['pos']}'")

        if sent["pos"] == "noun":
            has_noun = True

        if not sent.get("sentence") or not sent.get("cloze_word"):
            continue

        # ClozeWord parts must be substrings of sentence (case-sensitive)
        # Use ~ as separable verb delimiter
        parts = [p.strip() for p in sent["cloze_word"].split("~") if p.strip()]
        for part in parts:
            if part not in sent["sentence"]:
                errors.append(f"{prefix}: cloze_word '{part}' not in sentence")

        # Check for verbatim quotes from source (>80% similarity)
        if source_text:
            source_sentences = re.split(r'[.!?]+', source_text)
            for src_sent in source_sentences:
                src_sent = src_sent.strip()
                if len(src_sent) < 10:
                    continue
                similarity = fuzz.ratio(sent["sentence"], src_sent)
                if similarity > 80:
                    errors.append(f"{prefix}: too similar to source ({similarity}%)")
                    break

    # Article check: require article only when the word is primarily a noun
    # (all sentences are nouns). Mixed POS (e.g. verb with one nominalised
    # sentence) doesn't need a top-level article.
    all_noun = has_noun and all(
        s.get("pos") == "noun" for s in sentences if s.get("pos")
    )
    if all_noun and not card.get("article"):
        errors.append("noun missing article")
    if not has_noun and card.get("article"):
        errors.append(f"non-noun has article '{card['article']}'")

    return len(errors) == 0, errors


def validate_batch(cards, source_text=None):
    """Validate all cards in a batch. Returns (valid_cards, error_count)."""
    valid = []
    error_count = 0
    for card in cards:
        card = normalise_cloze(card)
        is_valid, errors = validate_card(card, source_text)
        if is_valid:
            valid.append(card)
        else:
            word = card.get("word", "?")
            print(f"  INVALID: {word} — {'; '.join(errors)}")
            error_count += 1
    return valid, error_count


def check_duplicate_translations(cards):
    """Warn about cards whose translation already exists in the deck.

    For any match, prints a warning so the user can add disambiguation.
    Does not block import — just informational.
    """
    # Fetch existing translations from deck
    note_ids = anki("findNotes", query=f'deck:"{DECK}" "note:{MODEL}"')
    if not note_ids:
        return

    existing_notes = anki("notesInfo", notes=note_ids)
    existing_trans = {}  # lower translation -> list of words
    for note in existing_notes:
        word = note["fields"]["Word"]["value"]
        trans = note["fields"]["WordTranslation"]["value"].strip().lower()
        if trans:
            existing_trans.setdefault(trans, []).append(word)

    # Check new cards
    warnings = []
    for card in cards:
        trans = card.get("translation", "").strip().lower()
        if trans in existing_trans:
            existing_words = existing_trans[trans]
            if not card.get("disambiguation"):
                warnings.append((card["word"], card["translation"], existing_words))

    if warnings:
        print(f"\n  WARNING: {len(warnings)} cards share a translation with "
              f"existing deck words (consider adding disambiguation):")
        for word, trans, existing in warnings:
            print(f"    {word} → \"{trans}\" — also used by: "
                  f"{', '.join(existing)}")
        print()


def dedup_gendered_pairs(cards):
    """Remove gendered duplicates from a batch of cards.

    If a batch contains both 'der Lehrer' and 'die Lehrerin', keep whichever
    appears first. The -in/-erin suffix is regular and doesn't need a
    separate card.
    """
    seen_bare = {}  # bare stem -> card word
    keep = []
    dropped = []

    for card in cards:
        word = card.get("word", "")
        bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", word,
                      flags=re.IGNORECASE).strip().lower()

        # Compute the stem that both gendered forms share
        stem = bare
        if bare.endswith("erin") and len(bare) > 5:
            stem = bare[:-2]  # lehrerin -> lehrer
        elif bare.endswith("in") and len(bare) > 3 and not bare.endswith("stein"):
            stem = bare[:-2]  # freundin -> freund

        counterpart = _gendered_counterpart(bare)
        counterpart_stem = counterpart if counterpart else None

        # Check if we've already seen this word's gendered counterpart
        if counterpart_stem and counterpart_stem in seen_bare:
            dropped.append((word, seen_bare[counterpart_stem]))
        elif stem in seen_bare and stem != bare:
            dropped.append((word, seen_bare[stem]))
        else:
            seen_bare[bare] = word
            keep.append(card)

    if dropped:
        print(f"  Dropped {len(dropped)} gendered duplicate(s):")
        for word, kept in dropped:
            print(f"    {word} (keeping {kept})")

    return keep


# ── Stage 8: Import to Anki ──────────────────────────────────────────────────

def import_to_anki(cards, source, domains_override, phase, dry_run=False):
    """Import validated cards to Anki via addNotes.

    Returns list of (note_id, word) for successfully imported notes.
    """
    anki_notes = []
    for card in cards:
        domains = domains_override or card.get("domains", "")
        tags = [f"source::{source}", f"phase::{phase}"]
        domain_list = [d.strip() for d in domains.split(",") if d.strip()]
        for d in domain_list:
            tags.append(f"domain::{d}")

        sentences = card["sentences"]

        anki_notes.append({
            "deckName": DECK,
            "modelName": MODEL,
            "fields": {
                "Word": card["word"],
                "POS": "|".join(s["pos"] for s in sentences),
                "Article": card.get("article", ""),
                "WordTranslation": card["translation"],
                "WordTranslationDisambiguate": card.get("disambiguation", ""),
                "IPA": "",
                "Audio": "",
                "Sentence": "|".join(s["sentence"] for s in sentences),
                "ClozeWord": "|".join(s["cloze_word"] for s in sentences),
                "SentenceTranslation": "|".join(
                    s["sentence_translation"] for s in sentences
                ),
                "Domains": ",".join(domain_list),
                "Phase": str(phase),
                "Note": card.get("note", ""),
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
            },
            "tags": tags,
        })

    if dry_run:
        print(f"\n[dry-run] Would import {len(anki_notes)} notes:\n")
        for n in anki_notes:
            f = n["fields"]
            article_str = f" ({f['Article']})" if f["Article"] else ""
            disambig_str = f"  NOT: {f['WordTranslationDisambiguate']}" if f["WordTranslationDisambiguate"] else ""
            print(f"  {f['Word']}{article_str:<6} → {f['WordTranslation']}{disambig_str}")
            # Show each sentence variant with POS
            sents = f["Sentence"].split("|")
            clozes = f["ClozeWord"].split("|")
            trans = f["SentenceTranslation"].split("|")
            poses = f["POS"].split("|")
            for i, (s, c, t, p) in enumerate(
                zip(sents, clozes, trans, poses)
            ):
                print(f"    [{i+1}] [{p}] {s}")
                print(f"        cloze: {c}")
                print(f"        EN: {t}")
            if f.get("Note"):
                print(f"    note: {f['Note']}")
            print()
        return []

    # Import in batches of 50
    imported = []
    for i in range(0, len(anki_notes), 50):
        batch = anki_notes[i:i + 50]
        result = anki("addNotes", notes=batch)
        for j, note_id in enumerate(result):
            word = batch[j]["fields"]["Word"]
            if note_id is None:
                print(f"  SKIP (duplicate): {word}")
            else:
                imported.append((note_id, word))
        time.sleep(0.1)

    print(f"Imported {len(imported)}/{len(anki_notes)} notes")
    return imported


# ── Stage 10: Write checkpoint ────────────────────────────────────────────────

def write_checkpoint(cards, source, paragraphs, output_dir=None):
    """Save generated cards as a JSON checkpoint for auditability."""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "data" / "generated"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    para_suffix = f"_p{paragraphs}" if paragraphs else ""
    filename = f"{source}{para_suffix}.json"
    path = output_dir / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2, ensure_ascii=False)
    print(f"Checkpoint saved: {path}")


# ── Domain brief mode ────────────────────────────────────────────────────────

def generate_domain_vocab(brief, count, token, num_sentences=2):
    """Generate vocabulary from a domain brief via LLM."""
    prompt = f"""\
You are generating German vocabulary flashcards for an adult learner.

Generate exactly {count} German words relevant to this domain:
"{brief}"

Return ONLY a JSON array (no markdown, no commentary). Each element:
{{
  "word": "<word with article for nouns>",
  "article": "<der|die|das or empty>",
  "translation": "<English translation (British English)>",
  "disambiguation": "<disambiguation or empty>",
  "sentences": [
    {{
      "sentence": "<German example sentence, 5-15 words>",
      "cloze_word": "<exact form in sentence, ~ for separable verbs>",
      "sentence_translation": "<English translation of sentence (British English)>",
      "pos": "<{VALID_POS_STR}>"
    }}
  ],
  "domains": "<comma-separated domains>",
  "note": "<usage note or empty>"
}}

Rules:
- For nouns: include the article (der/die/das) in "word"
- For reflexive verbs: use "sich" + infinitive (e.g. "sich bemühen", not "bemühen (sich)")
- Generate exactly {num_sentences} sentence(s) per word in the "sentences" array
- Each sentence should show the word in a DIFFERENT grammatical context \
(different tenses, cases, nominalised forms, etc.)
- Each sentence entry has its own "pos" and "cloze_word"
- "cloze_word" must be an exact substring of "sentence" (case-sensitive)
- For separable verbs, use ~ (tilde) between separated parts (e.g. "machte~auf")
- For separable verbs: at least one sentence MUST show the prefix separating from the stem
- For nouns: include the article in "cloze_word" if one precedes the noun in the sentence \
(e.g. if sentence is "Ich esse den Apfel", cloze_word is "den Apfel" not just "Apfel")
- For reflexive verbs: include the reflexive pronoun in "cloze_word" using ~ \
(e.g. if sentence is "Er bemühte sich", cloze_word is "bemühte~sich")
- Use British English (colour, mum, favourite)
- Mix word types: nouns, verbs, adjectives, adverbs, and other parts of speech where relevant
- Choose words that are practical and commonly used in the domain
"""
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(2):
        try:
            result = call_llm(messages, token, max_tokens=8192)
            if isinstance(result, list):
                return result
            print(f"  Bad response shape (attempt {attempt + 1})")
        except (json.JSONDecodeError, requests.HTTPError) as e:
            print(f"  Error (attempt {attempt + 1}): {e}")
            if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 401:
                token = get_floodgate_token()
            time.sleep(2)

    return None


# ── Enrich existing cards with additional sentences ─────────────────────────

def build_enrich_prompt(batch, num_new):
    """Build prompt to generate additional sentences for existing cards.

    batch: list of dicts with word, translation, article, existing_sentences.
    num_new: number of NEW sentences to generate per word.
    """
    words_block = ""
    for i, card in enumerate(batch, 1):
        existing = "; ".join(
            f'"{s["sentence"]}" (cloze: {s["cloze_word"]}, pos: {s["pos"]})'
            for s in card["existing_sentences"]
        )
        words_block += (
            f'{i}. {card["word"]} — "{card["translation"]}"\n'
            f'   Existing: {existing}\n'
        )

    return f"""\
You are generating additional German example sentences for vocabulary flashcards.

For each word below, generate exactly {num_new} NEW example sentence(s) that are \
DIFFERENT from the existing ones. Return ONLY a JSON array (no markdown, no commentary).

Rules:
- Each new sentence should show the word in a different grammatical context \
(different tenses, cases, nominalised forms) from the existing sentences
- Each sentence entry has its own "pos" ({VALID_POS_STR}) and "cloze_word"
- "cloze_word" is the EXACT form of the word as it appears in the sentence (case-sensitive)
- For separable verbs where the prefix separates, use ~ (tilde) between parts (e.g. "machte~auf")
- For separable verbs: at least one sentence MUST show the prefix separating from the stem
- For nouns: include the article in "cloze_word" if one precedes the noun in the sentence \
(e.g. if sentence is "Ich esse den Apfel", cloze_word is "den Apfel" not just "Apfel")
- For reflexive verbs: include the reflexive pronoun in "cloze_word" using ~ \
(e.g. if sentence is "Er bemühte sich", cloze_word is "bemühte~sich")
- Sentences should be 5-15 words
- Use British English for translations (colour, mum, favourite)

Words:
{words_block}
Each element in the JSON array:
{{
  "word": "<the word exactly as given above>",
  "new_sentences": [
    {{
      "sentence": "<German example sentence>",
      "cloze_word": "<exact form in sentence, ~ for separable verbs>",
      "sentence_translation": "<English translation>",
      "pos": "<{VALID_POS_STR}>"
    }}
  ]
}}"""


def enrich_existing_batch(batch, token, num_new):
    """Call LLM to generate additional sentences for a batch of existing cards.

    Returns list of dicts with word + new_sentences, or None on failure.
    """
    prompt = build_enrich_prompt(batch, num_new)
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(2):
        try:
            result = call_llm(messages, token, max_tokens=8192)
            if not isinstance(result, list):
                print(f"  Bad response shape (attempt {attempt + 1}): not a list")
                if attempt == 0:
                    continue
                return None

            if len(result) != len(batch):
                print(f"  Bad response length (attempt {attempt + 1}): "
                      f"expected {len(batch)}, got {len(result)}")
                if attempt == 0:
                    continue
                return None

            return result

        except json.JSONDecodeError as e:
            print(f"  JSON parse error (attempt {attempt + 1}): {e}")
            if attempt == 0:
                continue
            return None
        except requests.HTTPError as e:
            print(f"  HTTP error (attempt {attempt + 1}): {e}")
            if hasattr(e, "response") and e.response.status_code == 401:
                print("  Refreshing OIDC token...")
                token = get_floodgate_token()
            if attempt == 0:
                time.sleep(2)
                continue
            return None

    return None


def validate_new_sentences(new_sentences):
    """Validate a list of new sentence entries. Returns (valid, errors)."""
    errors = []
    valid = []
    for i, sent in enumerate(new_sentences):
        prefix = f"new_sentences[{i}]"
        for field in ("sentence", "cloze_word", "sentence_translation", "pos"):
            if not sent.get(field):
                errors.append(f"{prefix}: missing '{field}'")
                continue

        if not sent.get("pos") or not sent.get("sentence") or not sent.get("cloze_word"):
            continue

        if sent["pos"] not in VALID_POS:
            errors.append(f"{prefix}: invalid pos '{sent['pos']}'")
            continue

        # ClozeWord parts must be substrings of sentence
        parts = [p.strip() for p in sent["cloze_word"].split("~") if p.strip()]
        cloze_ok = True
        for part in parts:
            if part not in sent["sentence"]:
                errors.append(f"{prefix}: cloze_word '{part}' not in sentence")
                cloze_ok = False

        if cloze_ok:
            valid.append(sent)

    return valid, errors


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_text(args):
    """Handle the 'text' subcommand."""
    # Stage 1: Ingest
    print("\n── Stage 1: Ingest text ──")
    text = ingest_text(args.file, args.paragraphs)

    # Stage 2: spaCy extraction
    print("\n── Stage 2: spaCy extraction ──")
    print("Loading spaCy model...")
    try:
        nlp = spacy.load("de_dep_news_trf")
        print("  Using de_dep_news_trf (transformer)")
    except OSError:
        try:
            nlp = spacy.load("de_core_news_sm")
            print("  Using de_core_news_sm (fallback)")
        except OSError:
            print("ERROR: No German spaCy model found. Install with:")
            print("  uv run python -m spacy download de_dep_news_trf")
            sys.exit(1)
    lemmas = extract_lemmas(text, nlp)

    if not lemmas:
        print("No content words extracted. Check your text/paragraph range.")
        return

    # Stage 3: Check existing deck
    print("\n── Stage 3: Check existing deck ──")
    new_lemmas = check_existing_deck(lemmas, args.source)

    if not new_lemmas:
        print("All extracted words already in deck. Nothing to generate.")
        return

    # Stage 4: Compound detection
    print("\n── Stage 4: Compound word detection ──")
    # Build known-words set from deck
    note_ids = anki("findNotes", query=f'"deck:{DECK}" "note:{MODEL}"')
    known_words = set()
    if note_ids:
        all_notes = anki("notesInfo", notes=note_ids)
        for note in all_notes:
            if "Word" not in note["fields"]:
                continue
            word = note["fields"]["Word"]["value"]
            bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", word,
                          flags=re.IGNORECASE).strip().lower()
            known_words.add(bare)
    new_lemmas = filter_transparent_compounds(new_lemmas, known_words)

    if not new_lemmas:
        print("All remaining words are transparent compounds. Nothing to generate.")
        return

    if args.dry_run and not args.enrich:
        print(f"\n[dry-run] {len(new_lemmas)} words to generate")

    # Authenticate for LLM
    print("\n── Authenticating ──")
    token = get_floodgate_token()
    print("OK")

    # Stage 5: Summarise text
    print("\n── Stage 5: Summarise text ──")
    summary = summarise_text(text, token)

    # Stage 6 + 7: LLM enrichment + validation
    print("\n── Stage 6-7: LLM enrichment + validation ──")
    batch_size = args.batch_size
    all_cards = []
    total_errors = 0

    for i in range(0, len(new_lemmas), batch_size):
        batch = new_lemmas[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(new_lemmas) + batch_size - 1) // batch_size
        words_str = ", ".join(l for l, _, _ in batch)
        print(f"\n  Batch {batch_num}/{total_batches}: {words_str}")

        result = enrich_batch(batch, token, summary, text, args.sentences)
        if result is None:
            print(f"  FAILED batch {batch_num}")
            total_errors += len(batch)
            continue

        valid, errs = validate_batch(result, text)
        total_errors += errs
        all_cards.extend(valid)

        if i + batch_size < len(new_lemmas):
            time.sleep(1)

    print(f"\n  Generated {len(all_cards)} valid cards, {total_errors} errors")

    if not all_cards:
        print("No valid cards generated.")
        return

    # Check for duplicate translations against existing deck
    check_duplicate_translations(all_cards)

    # Dedup gendered pairs within batch
    all_cards = dedup_gendered_pairs(all_cards)

    # Stage 8: Import to Anki
    print("\n── Stage 8: Import to Anki ──")
    imported = import_to_anki(
        all_cards, args.source, args.domain, args.phase, dry_run=args.dry_run
    )

    # Stage 9: IPA enrichment
    if imported and not args.dry_run:
        print("\n── Stage 9: IPA enrichment ──")
        note_ids_to_enrich = [nid for nid, _ in imported]
        enrich_notes(note_ids_to_enrich, ipa_only=True)

    # Stage 10: Checkpoint
    print("\n── Stage 10: Checkpoint ──")
    write_checkpoint(all_cards, args.source, args.paragraphs)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Source:     {args.source}")
    print(f"  Paragraphs: {args.paragraphs or 'all'}")
    print(f"  Extracted:  {len(lemmas)} lemmas")
    print(f"  New:        {len(new_lemmas)} after filtering")
    print(f"  Generated:  {len(all_cards)} cards")
    print(f"  Imported:   {len(imported)}")
    print(f"  Errors:     {total_errors}")


def cmd_enrich(args):
    """Handle the 'enrich' subcommand — add sentences to existing cards."""
    target = args.sentences

    # Find notes by source tag
    print(f"\n── Finding notes with source::{args.source} ──")
    note_ids = anki("findNotes",
                    query=f'"deck:{DECK}" "note:{MODEL}" "tag:source::{args.source}"')
    if not note_ids:
        print("No notes found with that source tag.")
        return

    all_notes = anki("notesInfo", notes=note_ids)
    print(f"  Found {len(all_notes)} notes")

    # Filter to notes that need more sentences
    to_enrich = []
    already_ok = 0
    for note in all_notes:
        fields = note["fields"]
        word = fields.get("Word", {}).get("value", "")
        sentence = fields.get("Sentence", {}).get("value", "")
        cloze = fields.get("ClozeWord", {}).get("value", "")
        pos = fields.get("POS", {}).get("value", "")
        trans = fields.get("SentenceTranslation", {}).get("value", "")
        translation = fields.get("WordTranslation", {}).get("value", "")
        article = fields.get("Article", {}).get("value", "")

        current_sentences = sentence.split("|") if sentence else []
        current_count = len(current_sentences)

        if current_count >= target:
            already_ok += 1
            continue

        # Build existing sentences list for the prompt
        clozes = cloze.split("|") if cloze else []
        poses = pos.split("|") if pos else []
        translations_list = trans.split("|") if trans else []

        existing = []
        for i in range(current_count):
            existing.append({
                "sentence": current_sentences[i] if i < len(current_sentences) else "",
                "cloze_word": clozes[i] if i < len(clozes) else "",
                "pos": poses[i] if i < len(poses) else "",
                "sentence_translation": translations_list[i] if i < len(translations_list) else "",
            })

        to_enrich.append({
            "note_id": note["noteId"],
            "word": word,
            "translation": translation,
            "article": article,
            "existing_sentences": existing,
            "current_count": current_count,
            "need": target - current_count,
        })

    print(f"  Already at {target}+ sentences: {already_ok}")
    print(f"  Need enrichment: {len(to_enrich)}")

    if not to_enrich:
        print("Nothing to enrich.")
        return

    # Authenticate
    print("\n── Authenticating ──")
    token = get_floodgate_token()
    print("OK")

    # Process in batches
    print(f"\n── Generating additional sentences ──")
    batch_size = args.batch_size
    updated = 0
    errors = 0

    for i in range(0, len(to_enrich), batch_size):
        batch = to_enrich[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(to_enrich) + batch_size - 1) // batch_size
        words_str = ", ".join(c["word"] for c in batch)
        num_new = batch[0]["need"]  # All cards in this run need the same count
        print(f"\n  Batch {batch_num}/{total_batches} (+{num_new} sentences): "
              f"{words_str}")

        result = enrich_existing_batch(batch, token, num_new)
        if result is None:
            print(f"  FAILED batch {batch_num}")
            errors += len(batch)
            continue

        # Match results to cards and update
        for card, enrichment in zip(batch, result):
            new_sents = enrichment.get("new_sentences", [])
            valid_sents, errs = validate_new_sentences(new_sents)

            if errs:
                word = card["word"]
                for e in errs:
                    print(f"    INVALID {word}: {e}")
                errors += 1

            if not valid_sents:
                print(f"    SKIP {card['word']}: no valid new sentences")
                continue

            # Build updated pipe-delimited fields
            existing = card["existing_sentences"]
            all_sents = existing + valid_sents

            new_sentence = "|".join(s["sentence"] for s in all_sents)
            new_cloze = "|".join(s["cloze_word"] for s in all_sents)
            new_trans = "|".join(s["sentence_translation"] for s in all_sents)
            new_pos = "|".join(s["pos"] for s in all_sents)

            if args.dry_run:
                print(f"  {card['word']:<25} {card['current_count']} → "
                      f"{len(all_sents)} sentences")
                for j, s in enumerate(all_sents):
                    marker = "  " if j < card["current_count"] else " +"
                    print(f"  {marker}[{j+1}] {s['sentence'][:70]}")
                    print(f"        ClozeWord: {s['cloze_word']}  "
                          f"POS: {s['pos']}")
            else:
                anki("updateNoteFields", note={
                    "id": card["note_id"],
                    "fields": {
                        "Sentence": new_sentence,
                        "ClozeWord": new_cloze,
                        "SentenceTranslation": new_trans,
                        "POS": new_pos,
                    },
                })
                updated += 1

        if i + batch_size < len(to_enrich):
            time.sleep(1)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Source:    {args.source}")
    print(f"  Target:   {target} sentences per card")
    print(f"  Found:    {len(to_enrich)} cards needing enrichment")
    if args.dry_run:
        print(f"  [dry-run] Would update {len(to_enrich)} cards")
    else:
        print(f"  Updated:  {updated}")
    print(f"  Errors:   {errors}")


def cmd_domain(args):
    """Handle the 'domain' subcommand."""
    print("\n── Authenticating ──")
    token = get_floodgate_token()
    print("OK")

    # Generate vocab from brief
    print(f"\n── Generating {args.count} words for: {args.brief} ──")
    result = generate_domain_vocab(args.brief, args.count, token, args.sentences)

    if not result:
        print("Failed to generate vocabulary.")
        return

    # Stage 3: Check existing deck
    print("\n── Check existing deck ──")
    # Filter out words already in deck
    note_ids = anki("findNotes", query=f'"deck:{DECK}" "note:{MODEL}"')
    known_words = set()
    if note_ids:
        all_notes = anki("notesInfo", notes=note_ids)
        for note in all_notes:
            if "Word" not in note["fields"]:
                continue
            word = note["fields"]["Word"]["value"]
            bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", word,
                          flags=re.IGNORECASE).strip().lower()
            known_words.add(bare)

    new_cards = []
    existing_count = 0
    gendered_count = 0
    for card in result:
        word = card.get("word", "")
        bare = re.sub(r"^(der|die|das|ein|eine)\s+", "", word,
                      flags=re.IGNORECASE).strip().lower()
        if bare in known_words:
            existing_count += 1
            # Tag existing
            matching = anki("findNotes",
                            query=f'"deck:{DECK}" "Word:*{bare}*"')
            if matching:
                anki("addTags", notes=matching, tags=f"source::{args.source}")
        else:
            # Skip gendered duplicates
            counterpart = _gendered_counterpart(bare)
            if counterpart and counterpart in known_words:
                gendered_count += 1
                print(f"    Skipped gendered duplicate: {word} "
                      f"(counterpart '{counterpart}' in deck)")
            else:
                new_cards.append(card)

    print(f"  Existing: {existing_count}, Gendered skips: {gendered_count}, "
          f"New: {len(new_cards)}")

    if not new_cards:
        print("All generated words already in deck.")
        return

    # Stage 7: Validate
    print("\n── Validate ──")
    valid, errs = validate_batch(new_cards)
    print(f"  Valid: {len(valid)}, Errors: {errs}")

    if not valid:
        print("No valid cards after validation.")
        return

    # Check for duplicate translations against existing deck
    check_duplicate_translations(valid)

    # Dedup gendered pairs within batch
    valid = dedup_gendered_pairs(valid)

    # Stage 8: Import
    print("\n── Import to Anki ──")
    imported = import_to_anki(
        valid, args.source, args.domain, args.phase, dry_run=args.dry_run
    )

    # Stage 9: IPA enrichment
    if imported and not args.dry_run:
        print("\n── IPA enrichment ──")
        note_ids_to_enrich = [nid for nid, _ in imported]
        enrich_notes(note_ids_to_enrich, ipa_only=True)

    # Stage 10: Checkpoint
    print("\n── Checkpoint ──")
    write_checkpoint(valid, args.source, None)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Source:    {args.source}")
    print(f"  Brief:     {args.brief}")
    print(f"  Generated: {len(result)} words")
    print(f"  New:       {len(new_cards)}")
    print(f"  Valid:     {len(valid)}")
    print(f"  Imported:  {len(imported)}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── text subcommand ──
    text_p = sub.add_parser("text", help="Extract vocab from a German text")
    text_p.add_argument("--file", required=True,
                        help="Path to German text file")
    text_p.add_argument("--source", required=True,
                        help="Source tag (e.g. 'schachnovelle')")
    text_p.add_argument("--paragraphs",
                        help="Paragraph range (e.g. '1-30')")
    text_p.add_argument("--domain", default="",
                        help="Override domain tags (comma-separated)")
    text_p.add_argument("--phase", type=int, default=4,
                        help="Phase number (default: 4)")
    text_p.add_argument("--batch-size", type=int, default=10,
                        help="Words per LLM call (default: 10)")
    text_p.add_argument("--sentences", type=int, default=2,
                        help="Example sentences per word (default: 2)")
    text_p.add_argument("--dry-run", action="store_true",
                        help="Preview without importing")
    text_p.add_argument("--enrich", action="store_true",
                        help="In dry-run mode, still call LLM for enrichment")

    # ── domain subcommand ──
    domain_p = sub.add_parser("domain", help="Generate vocab from a topic brief")
    domain_p.add_argument("--brief", required=True,
                          help="Description of the domain")
    domain_p.add_argument("--source", required=True,
                          help="Source tag (e.g. 'it_security')")
    domain_p.add_argument("--count", type=int, default=30,
                          help="Number of words to generate (default: 30)")
    domain_p.add_argument("--domain", default="",
                          help="Override domain tags (comma-separated)")
    domain_p.add_argument("--phase", type=int, default=4,
                          help="Phase number (default: 4)")
    domain_p.add_argument("--sentences", type=int, default=2,
                          help="Example sentences per word (default: 2)")
    domain_p.add_argument("--dry-run", action="store_true",
                          help="Preview without importing")

    # ── enrich subcommand ──
    enrich_p = sub.add_parser("enrich",
                              help="Add sentences to existing cards")
    enrich_p.add_argument("--source", required=True,
                          help="Source tag to find cards (e.g. 'schachnovelle')")
    enrich_p.add_argument("--sentences", type=int, default=3,
                          help="Target sentence count per card (default: 3)")
    enrich_p.add_argument("--batch-size", type=int, default=10,
                          help="Words per LLM call (default: 10)")
    enrich_p.add_argument("--dry-run", action="store_true",
                          help="Preview without updating")

    args = parser.parse_args()

    if args.command == "text":
        cmd_text(args)
    elif args.command == "domain":
        cmd_domain(args)
    elif args.command == "enrich":
        cmd_enrich(args)


if __name__ == "__main__":
    main()
