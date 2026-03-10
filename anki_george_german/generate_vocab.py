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
import re
import sys
import time
from pathlib import Path

from . import DATA_DIR
from ._anki import anki, DECK, MODEL, strip_article, fetch_vocab_notes
from ._llm import get_floodgate_token, call_llm, call_llm_text, call_llm_with_retry
from ._vocab_prompts import (
    VALID_POS, VALID_POS_STR,
    build_enrichment_prompt, build_domain_prompt, build_enrich_prompt,
)
from ._vocab_validate import (
    normalise_cloze, validate_card, validate_batch, validate_new_sentences,
    _find_noun_chunk,
)
from . import _vocab_validate
from .enrich_ipa_audio import enrich_notes

_nlp_model = None

def _get_nlp():
    """Lazy-load the spaCy model (expensive, only load once).

    Also shares the model with _vocab_validate so normalise_cloze
    and _find_noun_chunk use the same instance.
    """
    global _nlp_model
    if _nlp_model is None:
        import spacy
        _nlp_model = spacy.load("de_dep_news_trf")
        _vocab_validate._nlp_model = _nlp_model
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
    all_notes = fetch_vocab_notes()
    if not all_notes:
        print("No existing notes found in deck.")
        return lemmas

    # Build lookup: lowercase bare word -> note_id
    known = {}
    for note in all_notes:
        if "Word" not in note["fields"]:
            continue
        word = note["fields"]["Word"]["value"]
        bare = strip_article(word)
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
    from charsplit import Splitter
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
        summary = call_llm_text(messages, token, max_tokens=300)
        print(f"  Summary: {summary[:120]}...")
        return summary
    except Exception as e:
        print(f"  Warning: summarisation failed ({e}), proceeding without context")
        return ""


# ── Stage 6: LLM enrichment ─────────────────────────────────────────────────

def enrich_batch(batch, token, context_summary, source_text=None,
                 num_sentences=2):
    """Send a batch of words to the LLM for enrichment.

    Returns list of enriched word dicts, or None on failure.
    """
    prompt = build_enrichment_prompt(batch, context_summary, source_text,
                                     num_sentences)
    messages = [{"role": "user", "content": prompt}]
    return call_llm_with_retry(messages, token, expect_len=len(batch))


def check_duplicate_translations(cards):
    """Warn about cards whose translation already exists in the deck.

    For any match, prints a warning so the user can add disambiguation.
    Does not block import — just informational.
    """
    # Fetch existing translations from deck
    existing_notes = fetch_vocab_notes()
    if not existing_notes:
        return
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
        bare = strip_article(word)

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
        output_dir = DATA_DIR / "generated"
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
    prompt = build_domain_prompt(brief, count, num_sentences)
    messages = [{"role": "user", "content": prompt}]
    return call_llm_with_retry(messages, token)


# ── Enrich existing cards with additional sentences ─────────────────────────

def enrich_existing_batch(batch, token, num_new):
    """Call LLM to generate additional sentences for a batch of existing cards.

    Returns list of dicts with word + new_sentences, or None on failure.
    """
    prompt = build_enrich_prompt(batch, num_new)
    messages = [{"role": "user", "content": prompt}]
    return call_llm_with_retry(messages, token, expect_len=len(batch))



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
        nlp = _get_nlp()
        print("  Using de_dep_news_trf (transformer)")
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
    known_words = set()
    for note in fetch_vocab_notes():
        if "Word" not in note["fields"]:
            continue
        word = note["fields"]["Word"]["value"]
        bare = strip_article(word)
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
    all_notes = fetch_vocab_notes(f'"tag:source::{args.source}"')
    if not all_notes:
        print("No notes found with that source tag.")
        return
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
    known_words = set()
    for note in fetch_vocab_notes():
        if "Word" not in note["fields"]:
            continue
        word = note["fields"]["Word"]["value"]
        bare = strip_article(word)
        known_words.add(bare)

    new_cards = []
    existing_count = 0
    gendered_count = 0
    for card in result:
        word = card.get("word", "")
        bare = strip_article(word)
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
