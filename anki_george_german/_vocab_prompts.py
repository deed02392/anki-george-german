"""Shared prompt-building helpers for German vocabulary generation.

Extracted from generate_vocab.py to centralise the card-generation rules
that appear in text-mode, domain-mode, and enrich-mode prompts.
"""

VALID_POS = (
    "noun", "verb", "adjective", "adverb",
    "pronoun", "preposition", "numeral",
    "conjunction", "interjection", "phrase",
)
VALID_POS_STR = "|".join(VALID_POS)

# Rules shared across all card-generation prompts (text, domain, enrich).
# Use {num_sentences}, {VALID_POS_STR} as format placeholders.
SENTENCE_RULES = """\
- Each sentence should show the word in a DIFFERENT grammatical context \
(different tenses, cases, nominalised forms, etc.)
- Each sentence entry has its own "pos" ({valid_pos}) and "cloze_word"
- "cloze_word" is the EXACT form of the word as it appears in the sentence (case-sensitive). \
Copy-paste from the sentence — if the sentence has "den Apfel", cloze_word must be "den Apfel" not "Der Apfel". \
For separable verbs where the prefix separates, use ~ (tilde) between parts (e.g. "machte~auf")
- For separable verbs: at least one sentence MUST show the prefix separating from the stem \
(e.g. "Er machte die Tür auf" not only "Er wollte die Tür aufmachen")
- For nouns: include the article in "cloze_word" if one precedes the noun in the sentence \
(e.g. if sentence is "Ich esse den Apfel", cloze_word is "den Apfel" not just "Apfel")
- For reflexive verbs: include the reflexive pronoun in "cloze_word" using ~ \
(e.g. if sentence is "Er bemühte sich", cloze_word is "bemühte~sich")
- Sentences should be 5-15 words
- Use British English for translations (colour, mum, favourite)"""

SENTENCE_SCHEMA = """\
    {{
      "sentence": "<German example sentence>",
      "cloze_word": "<exact form in sentence, ~ for separable verbs>",
      "sentence_translation": "<English translation of sentence>",
      "pos": "<{valid_pos}>"
    }}"""


def _format_rules(extra_rules=""):
    """Return the shared sentence rules with POS placeholder filled in."""
    base = SENTENCE_RULES.format(valid_pos=VALID_POS_STR)
    if extra_rules:
        return base + "\n" + extra_rules
    return base


def build_enrichment_prompt(batch, context_summary, source_text=None,
                            num_sentences=2):
    """Build the prompt to enrich a batch of words (text mode)."""
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

    extra = (
        '- For nouns: include the article (der/die/das) in the "word" field\n'
        '- For reflexive verbs: use "sich" + infinitive '
        '(e.g. "sich bemühen", not "bemühen (sich)")\n'
        '- "article" is "der", "die", or "das" for nouns, empty string for others\n'
        '- "translation" is a concise English translation '
        "(British English: colour, mum, favourite)\n"
        '- "disambiguation" clarifies meaning if the word has multiple '
        "common translations (else empty)\n"
        f"- Generate exactly {num_sentences} example sentence(s) per word "
        'in the "sentences" array\n'
        "- NOT verbatim quotes from the source\n"
        '- "domains" is a comma-separated list of relevant topic domains\n'
        '- "note" is an optional usage note (empty if not needed)'
    )
    rules = _format_rules(extra)
    schema = SENTENCE_SCHEMA.format(valid_pos=VALID_POS_STR)

    return f"""\
You are generating German vocabulary flashcards for an adult learner.
{context_section}
For each word below, provide all fields for an Anki flashcard. Return ONLY a JSON \
array (no markdown, no commentary).

Rules:
{rules}


Words:
{words_block}
Each element in the JSON array:
{{
  "word": "<word with article for nouns, sich + infinitive for reflexive verbs>",
  "article": "<der|die|das or empty>",
  "translation": "<English translation>",
  "disambiguation": "<disambiguation or empty>",
  "sentences": [
{schema}
  ],
  "domains": "<comma-separated domains>",
  "note": "<usage note or empty>"
}}"""


def build_domain_prompt(brief, count, num_sentences=2):
    """Build the prompt for domain-brief vocabulary generation."""
    extra = (
        '- For nouns: include the article (der/die/das) in "word"\n'
        '- For reflexive verbs: use "sich" + infinitive '
        '(e.g. "sich bemühen", not "bemühen (sich)")\n'
        f"- Generate exactly {num_sentences} sentence(s) per word "
        'in the "sentences" array\n'
        "- Mix word types: nouns, verbs, adjectives, adverbs, "
        "and other parts of speech where relevant\n"
        "- Choose words that are practical and commonly used in the domain"
    )
    rules = _format_rules(extra)
    schema = SENTENCE_SCHEMA.format(valid_pos=VALID_POS_STR)

    return f"""\
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
{schema}
  ],
  "domains": "<comma-separated domains>",
  "note": "<usage note or empty>"
}}

Rules:
{rules}"""


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

    extra = (
        "- Each new sentence should show the word in a different grammatical "
        "context from the existing sentences"
    )
    rules = _format_rules(extra)
    schema = SENTENCE_SCHEMA.format(valid_pos=VALID_POS_STR)

    return f"""\
You are generating additional German example sentences for vocabulary flashcards.

For each word below, generate exactly {num_new} NEW example sentence(s) that are \
DIFFERENT from the existing ones. Return ONLY a JSON array (no markdown, no commentary).

Rules:
{rules}

Words:
{words_block}
Each element in the JSON array:
{{
  "word": "<the word exactly as given above>",
  "new_sentences": [
{schema}
  ]
}}"""
