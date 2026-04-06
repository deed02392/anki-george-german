#!/usr/bin/env python3
"""Quick query to show fields for a specific word."""
import sys

from ._anki import anki


def _field(note, name):
    """Get a field value, returning empty string if missing."""
    return note["fields"].get(name, {}).get("value", "")


def _print_note(note):
    word = _field(note, "Word")
    translation = _field(note, "WordTranslation")
    pos = _field(note, "POS")
    article = _field(note, "Article")
    ipa = _field(note, "IPA")
    disambig = _field(note, "WordTranslationDisambiguate")
    translation_pos = _field(note, "TranslationPOS")
    usage_note = _field(note, "Note")

    # Header
    header = word
    if article:
        header = f"{article} {word}" if article not in word else word
    if ipa:
        header += f"  /{ipa}/"
    print(f"  {header}")

    # Translation + POS
    line = f"  {translation}"
    if pos:
        line += f"  ({pos})"
    # Show EN POS when it differs from DE POS (first variant)
    if translation_pos:
        de_pos = pos.split("|")[0].strip() if pos else ""
        en_pos = translation_pos.split("|")[0].strip()
        if de_pos and en_pos and en_pos != de_pos:
            line += f"  [EN: {en_pos}]"
    print(line)

    if disambig:
        print(f"  NOT: {disambig}")

    # Sentences
    sentences = _field(note, "Sentence").split("|")
    translations = _field(note, "SentenceTranslation").split("|")
    cloze_words = _field(note, "ClozeWord").split("|")

    if any(s.strip() for s in sentences):
        print()
        for i, sent in enumerate(sentences):
            sent = sent.strip()
            if not sent:
                continue
            tr = translations[i].strip() if i < len(translations) else ""
            cw = cloze_words[i].strip() if i < len(cloze_words) else ""
            cloze_label = f"  [{cw}]" if cw else ""
            print(f"  {i+1}. {sent}{cloze_label}")
            if tr:
                print(f"     {tr}")

    # Footer
    meta = []
    meta.append(f"#{note['noteId']}")
    if usage_note:
        print(f"\n  Note: {usage_note}")
    print(f"\n  {' / '.join(meta)}")


def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    word = args.word
    if " " in word:
        field_query = f"Word:\"{word}\""
    else:
        field_query = f"Word:*{word}*"
    ids = anki("findNotes", query=f"deck:\"George's German Vocabulary\" {field_query}")
    notes = anki("notesInfo", notes=ids)
    if not notes:
        print(f"No notes found matching: {word}")
        return
    for i, n in enumerate(notes):
        if i > 0:
            print()
            print("  ─────────────────────────────────")
        print()
        _print_note(n)
    print()


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "der Saft"

    class Args:
        pass

    args = Args()
    args.word = word
    run(args)


if __name__ == "__main__":
    main()
