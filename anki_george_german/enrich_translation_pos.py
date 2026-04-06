"""Backfill TranslationPOS field using spaCy English model.

Classifies the apparent POS of the English word *in each sentence variant*
so the EN→DE front template can show a hint when the German POS differs
(e.g. "dying" looks like a noun in "The dying of…" but a verb in "to die").

TranslationPOS is pipe-separated per variant, matching the pipe-separated
Sentence / SentenceTranslation / POS fields.

Usage:
    anki-german enrich transpos [--dry-run]
"""

from ._anki import anki, fetch_vocab_notes, MODEL

_nlp_en = None

SPACY_TO_POS = {
    "NOUN": "noun",
    "PROPN": "noun",
    "VERB": "verb",
    "ADJ": "adjective",
    "ADV": "adverb",
    "PRON": "pronoun",
    "ADP": "preposition",
    "NUM": "numeral",
    "CCONJ": "conjunction",
    "SCONJ": "conjunction",
    "INTJ": "interjection",
}


def _get_nlp():
    """Lazy-load the English spaCy transformer model."""
    global _nlp_en
    if _nlp_en is None:
        import spacy
        _nlp_en = spacy.load("en_core_web_trf")
    return _nlp_en


def classify_sentence_pos(sentence_translation, word_translation, nlp=None):
    """Classify the POS of word_translation as used in sentence_translation.

    Runs spaCy on the full English sentence and finds the token(s) matching
    word_translation via lemma/substring matching. Returns the mapped POS
    of the matched token, or empty string if no match.
    """
    if not sentence_translation or not sentence_translation.strip():
        return ""
    if not word_translation or not word_translation.strip():
        return ""

    if nlp is None:
        nlp = _get_nlp()

    doc = nlp(sentence_translation.strip())
    if not doc:
        return ""

    target = word_translation.strip().lower()
    # Strip "to " prefix for matching (e.g. "to eat" → "eat")
    bare_target = target.removeprefix("to ").strip()

    # Lemmatize the target word for cross-form matching
    # (e.g. "dying" lemma → "die" matches sentence token "die")
    target_doc = nlp(bare_target)
    target_lemmas = {t.lemma_.lower() for t in target_doc
                     if not t.is_punct and not t.is_space}

    # Strategy 1: exact token text, lemma, or target-lemma match
    for token in doc:
        if (token.text.lower() == bare_target
                or token.lemma_.lower() == bare_target
                or token.lemma_.lower() in target_lemmas):
            pos = SPACY_TO_POS.get(token.pos_, "")
            if pos:
                return pos

    # Strategy 2: substring match — find a token whose text is contained
    # in the target or vice versa (handles "dying" matching "die")
    # Require min 3 chars to avoid "he" in "forehead", "a" in "apple", etc.
    for token in doc:
        tok_lower = token.text.lower()
        if len(tok_lower) < 3:
            continue
        if tok_lower in bare_target or bare_target in tok_lower:
            if token.is_punct or token.is_space:
                continue
            pos = SPACY_TO_POS.get(token.pos_, "")
            if pos:
                return pos

    # Strategy 3: shared stem — tokens that share a long common prefix
    # (e.g. "presentable" vs "presentably", "reasonable" vs "reasonably")
    for token in doc:
        if token.is_punct or token.is_space:
            continue
        tok_lower = token.text.lower()
        min_len = min(len(tok_lower), len(bare_target))
        if min_len < 4:
            continue
        # Find length of common prefix
        common = 0
        for a, b in zip(tok_lower, bare_target):
            if a != b:
                break
            common += 1
        if common >= min_len * 0.8:
            pos = SPACY_TO_POS.get(token.pos_, "")
            if pos:
                return pos

    # Strategy 4: multi-word — check if the full target phrase appears
    # as a span in the sentence and use the root of that span
    sent_lower = sentence_translation.strip().lower()
    idx = sent_lower.find(bare_target)
    if idx >= 0:
        # Find which token covers this character offset
        for token in doc:
            if token.idx >= idx and token.idx < idx + len(bare_target):
                pos = SPACY_TO_POS.get(token.pos_, "")
                if pos:
                    return pos

    return ""


def run(args):
    """Backfill TranslationPOS for all vocab notes (per-variant)."""
    dry_run = getattr(args, "dry_run", False)

    # Ensure field exists
    fields = anki("modelFieldNames", modelName=MODEL)
    if "TranslationPOS" not in fields:
        print("Adding TranslationPOS field to model...")
        anki("modelFieldAdd", modelName=MODEL,
             fieldName="TranslationPOS", index=5)
        print("  Done.")

    notes = fetch_vocab_notes()
    candidates = []
    for n in notes:
        trans = n["fields"].get("WordTranslation", {}).get("value", "")
        sent_trans = n["fields"].get("SentenceTranslation", {}).get("value", "")
        if trans.strip() and sent_trans.strip():
            candidates.append(n)

    print(f"Found {len(candidates)} notes with sentences "
          f"(of {len(notes)} total)")

    if not candidates:
        return

    print("Loading English spaCy model...")
    nlp = _get_nlp()
    print("  Done.")

    updated = 0
    mismatches = 0

    for n in candidates:
        word_trans = n["fields"]["WordTranslation"]["value"].strip()
        sent_trans_raw = n["fields"]["SentenceTranslation"]["value"]
        pos_raw = n["fields"].get("POS", {}).get("value", "")
        old_tpos = n["fields"].get("TranslationPOS", {}).get("value", "")

        sent_variants = sent_trans_raw.split("|")
        pos_variants = pos_raw.split("|") if pos_raw else []

        tpos_parts = []
        variant_mismatches = 0
        for i, sent_tr in enumerate(sent_variants):
            tpos = classify_sentence_pos(sent_tr.strip(), word_trans, nlp)
            tpos_parts.append(tpos)
            de_pos = (pos_variants[i].strip()
                      if i < len(pos_variants) else
                      pos_variants[0].strip() if pos_variants else "")
            if de_pos and tpos and tpos != de_pos:
                variant_mismatches += 1

        new_tpos = "|".join(tpos_parts)

        # Skip if nothing changed
        if new_tpos == old_tpos:
            continue

        word = n["fields"].get("Word", {}).get("value", "?")
        if variant_mismatches:
            mismatches += 1
            marker = f" ← {variant_mismatches} MISMATCH(es)"
        else:
            marker = ""

        if dry_run:
            print(f"  {word}: {word_trans} → {new_tpos} "
                  f"(DE: {pos_raw}){marker}")
        else:
            anki("updateNoteFields", note={
                "id": n["noteId"],
                "fields": {"TranslationPOS": new_tpos},
            })

        updated += 1

    action = "Would update" if dry_run else "Updated"
    print(f"\n{action} {updated} notes. "
          f"POS mismatches found: {mismatches}")
