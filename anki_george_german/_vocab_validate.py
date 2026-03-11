"""Validation and normalisation for generated vocabulary cards.

Extracted from generate_vocab.py so validation logic can be tested
and reused independently of the pipeline orchestration.
"""

import re

from rapidfuzz import fuzz

from ._anki import ARTICLES
from ._vocab_prompts import VALID_POS

_ARTICLES_RE = re.compile(
    r'^(' + '|'.join(ARTICLES) + r')\s+',
    re.IGNORECASE,
)

# spaCy model — lazily loaded via the same global as generate_vocab.py.
# Callers must set _nlp_model before calling functions that need spaCy
# (normalise_cloze, _find_noun_chunk).
_nlp_model = None


def _get_nlp():
    """Return the lazily-loaded spaCy model."""
    global _nlp_model
    if _nlp_model is None:
        import spacy
        _nlp_model = spacy.load("de_dep_news_trf")
    return _nlp_model


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
       (e.g. 'Kind' -> 'Jedes Kind')
    2. Case correction: 'Der Meister' -> 'den Meister' if case-insensitive
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
                        repairs.append(f"noun chunk: '{part}' -> '{chunk}'")
                        continue
                new_parts.append(part)
                continue

            # 2. Case-insensitive match
            idx = sentence.lower().find(part.lower())
            if idx >= 0:
                actual = sentence[idx:idx + len(part)]
                new_parts.append(actual)
                repairs.append(f"case fix: '{part}' -> '{actual}'")
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
                    repairs.append(f"noun phrase fix: '{part}' -> '{chunk}'")
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


def strip_orphan_disambiguations(cards):
    """Clear disambiguation on cards whose translation is unique in the batch.

    Disambiguation is only meaningful when two or more cards share the same
    English translation.  If a card's translation appears only once in the
    batch, any disambiguation text is noise (likely a definition or gloss
    the LLM generated) and is cleared.

    Mutates cards in place and returns them.
    """
    # Count translations
    trans_counts = {}
    for card in cards:
        t = card.get("translation", "").strip().lower()
        if t:
            trans_counts[t] = trans_counts.get(t, 0) + 1

    stripped = 0
    for card in cards:
        disambig = card.get("disambiguation", "")
        if not disambig:
            continue
        t = card.get("translation", "").strip().lower()
        if trans_counts.get(t, 0) < 2:
            word = card.get("word", "?")
            print(f"  STRIP disambig: {word} — no sibling in batch with "
                  f"translation \"{card.get('translation', '')}\"")
            card["disambiguation"] = ""
            stripped += 1

    if stripped:
        print(f"  Stripped {stripped} orphan disambiguation(s)")

    return cards


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
