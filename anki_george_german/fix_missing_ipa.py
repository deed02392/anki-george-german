#!/usr/bin/env python3
"""Fill missing IPA pronunciations via LLM.

For notes where Wiktionary lookup failed, ask the LLM to generate IPA.

Usage:
    uv run python tools/fix_missing_ipa.py --dry-run
    uv run python tools/fix_missing_ipa.py
"""
import argparse

from ._anki import anki, DECK, MODEL, fetch_vocab_notes
from ._llm import get_floodgate_token, call_llm_with_retry


def find_missing_ipa():
    """Find notes with empty IPA field."""
    notes = fetch_vocab_notes()

    missing = []
    for note in notes:
        ipa = note["fields"].get("IPA", {}).get("value", "").strip()
        word = note["fields"]["Word"]["value"]
        if not ipa:
            missing.append({"noteId": note["noteId"], "word": word})

    return missing


def generate_ipa(words):
    """Ask LLM to generate IPA for a list of German words."""
    words_block = "\n".join(f"{i}. {w['word']}" for i, w in enumerate(words, 1))

    prompt = f"""\
Provide the IPA (International Phonetic Alphabet) pronunciation for each \
German word below. Use standard High German (Hochdeutsch) pronunciation.

Return ONLY a JSON array (no markdown). Each element:
{{
  "word": "<the word as given>",
  "ipa": "<IPA transcription without brackets>"
}}

Rules:
- Use standard IPA symbols for German
- Do NOT include square brackets — just the transcription
- For nouns with articles (der/die/das): only transcribe the NOUN, not the article
- For compound words, provide the full compound pronunciation
- For phrases, provide the pronunciation of the key words
- If unsure, provide the most standard/common pronunciation

Words:
{words_block}"""

    token = get_floodgate_token()
    messages = [{"role": "user", "content": prompt}]
    return call_llm_with_retry(messages, token, max_tokens=4096)


def apply_ipa(missing, llm_result, dry_run=False):
    """Apply LLM-generated IPA to notes."""
    # Index by word
    ipa_by_word = {}
    for item in llm_result:
        word = item.get("word", "")
        ipa = item.get("ipa", "").strip()
        if word and ipa:
            ipa_by_word[word] = ipa

    updates = []
    for m in missing:
        ipa = ipa_by_word.get(m["word"], "")
        if ipa:
            updates.append((m["noteId"], m["word"], ipa))

    if not updates:
        print("No IPA updates to apply.")
        return

    print(f"{'[dry-run] ' if dry_run else ''}IPA updates ({len(updates)}):\n")
    for nid, word, ipa in updates:
        print(f"  {word:<30} [{ipa}]")

    if dry_run:
        print(f"\n[dry-run] Would update {len(updates)} notes.")
        return

    for nid, word, ipa in updates:
        anki("updateNoteFields", note={"id": nid, "fields": {"IPA": ipa}})

    print(f"\nUpdated {len(updates)} notes.")


def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    print("Finding notes with missing IPA...")
    missing = find_missing_ipa()
    if not missing:
        print("All notes have IPA!")
        return

    print(f"Found {len(missing)} notes missing IPA:")
    for m in missing:
        print(f"  {m['word']}")

    print(f"\nGenerating IPA via LLM...")
    result = generate_ipa(missing)
    if not result:
        print("LLM generation failed.")
        return

    apply_ipa(missing, result, dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
