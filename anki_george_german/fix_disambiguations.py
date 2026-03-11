#!/usr/bin/env python3
"""Fix duplicate translations by adding disambiguation via LLM.

Finds all words that share the same English translation and uses the LLM
to generate WordTranslationDisambiguate text for each, so the EN→DE card
shows "NOT: ..." to help the learner pick the right synonym.

Usage:
    uv run python tools/fix_disambiguations.py --dry-run
    uv run python tools/fix_disambiguations.py
"""
import argparse

from ._anki import anki, DECK, MODEL, fetch_vocab_notes
from ._llm import get_floodgate_token, call_llm_with_retry


def find_duplicate_translations():
    """Find groups of notes sharing the same translation."""
    notes = fetch_vocab_notes()

    trans_groups = {}
    for note in notes:
        word = note["fields"]["Word"]["value"]
        trans = note["fields"]["WordTranslation"]["value"].strip().lower()
        disambig = note["fields"]["WordTranslationDisambiguate"]["value"].strip()
        if trans:
            trans_groups.setdefault(trans, []).append({
                "noteId": note["noteId"],
                "word": word,
                "translation": note["fields"]["WordTranslation"]["value"].strip(),
                "disambiguation": disambig,
            })

    # Keep groups with 2+ words
    dupes = {}
    for trans, group in trans_groups.items():
        if len(group) >= 2:
            dupes[trans] = group

    return dupes


def generate_disambiguations(dupes):
    """Ask the LLM for disambiguation text for each group."""
    groups_block = ""
    group_list = list(dupes.items())
    for i, (trans, group) in enumerate(group_list, 1):
        words = ", ".join(g["word"] for g in group)
        existing = []
        for g in group:
            if g["disambiguation"]:
                existing.append(f'  {g["word"]} already has: "{g["disambiguation"]}"')
        existing_block = "\n".join(existing) if existing else "  (none have disambiguation yet)"
        groups_block += f"{i}. Translation: \"{trans}\" → Words: {words}\n{existing_block}\n"

    prompt = f"""\
You are helping disambiguate German vocabulary flashcards. Multiple German words
share the same English translation. For each word, provide a SHORT disambiguation
that describes the MEANING CONTEXT for this specific word.

The disambiguation appears on the card as "NOT: <your text>". So your text should
describe the meaning that this card is NOT — i.e. the meaning of the OTHER word(s),
without naming them.

Rules:
- Keep it very short (3-8 words)
- Use ONLY English — never include German words (naming the sibling gives away the answer)
- NEVER name the other German word(s) — only describe meanings
- Describe the semantic context, register, or usage that this word is NOT
- For gendered pairs (Lehrer/Lehrerin), use "male" or "female"
- Use British English

Examples of GOOD disambiguation:
  "lively/colloquial" (for a formal synonym)
  "literary/poetic register" (for an everyday synonym)
  "physical direction" (for a static-location synonym)
  "animals, not humans" (for a human-eating synonym)

Examples of BAD disambiguation:
  "der Körper (modern body)" ← WRONG, contains German
  "not aufwachen" ← WRONG, contains German
  "erwischen, fangen" ← WRONG, lists German synonyms
  "deshalb" ← WRONG, just a German word

Groups to disambiguate:
{groups_block}
Return ONLY a JSON array (no markdown). Each element:
{{
  "translation": "<the shared English translation>",
  "words": [
    {{
      "word": "<German word>",
      "disambiguation": "<meaning context NOT applicable to this word>"
    }}
  ]
}}"""

    token = get_floodgate_token()
    messages = [{"role": "user", "content": prompt}]
    return call_llm_with_retry(messages, token, max_tokens=4096)


def apply_disambiguations(dupes, llm_result, dry_run=False):
    """Apply the LLM-generated disambiguations to notes."""
    # Index LLM results by translation
    llm_by_trans = {}
    for group in llm_result:
        trans = group.get("translation", "").strip().lower()
        for w in group.get("words", []):
            llm_by_trans.setdefault(trans, {})[w["word"]] = w["disambiguation"]

    updates = []
    for trans, group in dupes.items():
        llm_group = llm_by_trans.get(trans, {})
        for g in group:
            new_disambig = llm_group.get(g["word"], "")
            if new_disambig and new_disambig != g["disambiguation"]:
                updates.append((g["noteId"], g["word"], trans, new_disambig))

    if not updates:
        print("No disambiguations to add.")
        return

    print(f"{'[dry-run] ' if dry_run else ''}Disambiguation updates ({len(updates)}):\n")
    for nid, word, trans, disambig in updates:
        print(f"  {word:<30} ({trans})")
        print(f"    → NOT: {disambig}")

    if dry_run:
        print(f"\n[dry-run] Would update {len(updates)} notes.")
        return

    for nid, word, trans, disambig in updates:
        anki("updateNoteFields", note={
            "id": nid,
            "fields": {"WordTranslationDisambiguate": disambig}
        })

    print(f"\nUpdated {len(updates)} notes.")


def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    print("Finding duplicate translations...")
    dupes = find_duplicate_translations()
    if not dupes:
        print("No duplicate translations found.")
        return

    print(f"Found {len(dupes)} groups of duplicate translations:")
    for trans, group in sorted(dupes.items()):
        words = ", ".join(g["word"] for g in group)
        print(f"  '{trans}' → {words}")

    print(f"\nGenerating disambiguations via LLM...")
    result = generate_disambiguations(dupes)
    if not result:
        print("LLM generation failed.")
        return

    apply_disambiguations(dupes, result, dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
