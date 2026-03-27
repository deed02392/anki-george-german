"""Tests for update_grammar_fields.py — vocab example collection and formatting."""
import pytest

from anki_george_german.update_grammar_fields import (
    _collect_vocab_examples,
    _select_examples,
    _highlight_cloze_in_sentence,
    format_vocab_examples,
)


def _make_note(word, translation, sentence, cloze_word, cloze_hint, note_id=1):
    """Build a fake vocab note dict matching AnkiConnect notesInfo shape."""
    return {
        "noteId": note_id,
        "fields": {
            "Word": {"value": word},
            "WordTranslation": {"value": translation},
            "Sentence": {"value": sentence},
            "ClozeWord": {"value": cloze_word},
            "ClozeHint": {"value": cloze_hint},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# A. _collect_vocab_examples
# ═══════════════════════════════════════════════════════════════════════════


class TestCollectVocabExamples:

    def test_basic_match(self):
        notes = [
            _make_note("die Tür", "the door", "Er öffnete die Tür.", "Tür",
                        "Akkusativ · feminin", note_id=1),
        ]
        result = _collect_vocab_examples(notes, {"Akkusativ", "feminin"})
        assert "Akkusativ" in result
        assert "feminin" in result
        assert len(result["Akkusativ"]) == 1

    def test_case_insensitive_matching(self):
        """ClozeHint 'Dativ · Maskulin' matches grammar term 'maskulin'."""
        notes = [
            _make_note("der Mann", "the man", "Ich gab dem Mann das Buch.",
                        "Mann", "Dativ · Maskulin", note_id=1),
        ]
        result = _collect_vocab_examples(notes, {"Dativ", "maskulin"})
        assert "maskulin" in result
        assert len(result["maskulin"]) == 1

    def test_pipe_variant_uses_first(self):
        """Only first variant (before |) is used."""
        notes = [
            _make_note("gehen", "to go",
                        "Er geht nach Hause.|Sie ging zum Laden.",
                        "geht|ging",
                        "Präsens|Präteritum", note_id=1),
        ]
        result = _collect_vocab_examples(notes, {"Präsens", "Präteritum"})
        # First variant is Präsens
        assert "Präsens" in result
        ex = result["Präsens"]["Präsens"][0]
        assert ex["sentence"] == "Er geht nach Hause."
        assert ex["cloze_word"] == "geht"

    def test_empty_hint_skipped(self):
        notes = [
            _make_note("Haus", "house", "Das Haus ist groß.", "Haus", "",
                        note_id=1),
        ]
        result = _collect_vocab_examples(notes, {"Nominativ"})
        assert len(result) == 0

    def test_no_sentence_skipped(self):
        notes = [
            _make_note("Haus", "house", "", "Haus", "Nominativ", note_id=1),
        ]
        result = _collect_vocab_examples(notes, {"Nominativ"})
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════
# B. _select_examples
# ═══════════════════════════════════════════════════════════════════════════


class TestSelectExamples:

    def test_variety_across_patterns(self):
        """Selects from different sub-patterns round-robin."""
        by_pattern = {
            "Dativ · maskulin": [
                {"word": "der Mann", "translation": "man",
                 "sentence": "s1", "cloze_word": "c1", "hint": "h1"},
                {"word": "der Tisch", "translation": "table",
                 "sentence": "s2", "cloze_word": "c2", "hint": "h2"},
            ],
            "Dativ · feminin": [
                {"word": "die Frau", "translation": "woman",
                 "sentence": "s3", "cloze_word": "c3", "hint": "h3"},
            ],
        }
        result = _select_examples(by_pattern, max_n=3)
        assert len(result) == 3
        words = [e["word"] for e in result]
        # Should have one from each pattern first
        assert "die Frau" in words
        assert "der Mann" in words or "der Tisch" in words

    def test_max_limit(self):
        by_pattern = {
            "pat1": [
                {"word": f"w{i}", "translation": "t", "sentence": "s",
                 "cloze_word": "c", "hint": "h"}
                for i in range(10)
            ],
        }
        result = _select_examples(by_pattern, max_n=5)
        assert len(result) == 5

    def test_empty(self):
        assert _select_examples({}) == []

    def test_no_duplicate_words(self):
        by_pattern = {
            "pat1": [
                {"word": "Haus", "translation": "house", "sentence": "s1",
                 "cloze_word": "c1", "hint": "h1"},
            ],
            "pat2": [
                {"word": "Haus", "translation": "house", "sentence": "s2",
                 "cloze_word": "c2", "hint": "h2"},
            ],
        }
        result = _select_examples(by_pattern, max_n=5)
        assert len(result) == 1
        assert result[0]["word"] == "Haus"


# ═══════════════════════════════════════════════════════════════════════════
# C. _highlight_cloze_in_sentence
# ═══════════════════════════════════════════════════════════════════════════


class TestHighlightCloze:

    def test_simple(self):
        result = _highlight_cloze_in_sentence(
            "Er öffnete die Tür.", "Tür"
        )
        assert '<span class="hl gram">Tür</span>' in result

    def test_separable_verb(self):
        result = _highlight_cloze_in_sentence(
            "Er machte die Tür auf.", "machte~auf"
        )
        assert '<span class="hl gram">machte</span>' in result
        assert '<span class="hl gram">auf</span>' in result

    def test_html_escaping(self):
        result = _highlight_cloze_in_sentence(
            "A & B sind gut.", "A"
        )
        assert "&amp;" in result
        assert '<span class="hl gram">A</span>' in result

    def test_empty_cloze_word(self):
        result = _highlight_cloze_in_sentence("Hallo Welt.", "")
        assert result == "Hallo Welt."


# ═══════════════════════════════════════════════════════════════════════════
# D. format_vocab_examples
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatVocabExamples:

    def test_basic_output(self):
        examples = [{
            "word": "die Tür",
            "translation": "the door",
            "sentence": "Er öffnete die Tür.",
            "cloze_word": "Tür",
            "hint": "Akkusativ · feminin",
        }]
        result = format_vocab_examples(examples)
        assert 'class="vocab-ex-word"' in result
        assert "die Tür" in result
        assert 'class="vocab-ex-trans"' in result
        assert "the door" in result
        assert 'class="hl gram"' in result
        assert 'class="example-item"' in result

    def test_empty_list(self):
        assert format_vocab_examples([]) == ""

    def test_multiple_examples(self):
        examples = [
            {"word": "die Tür", "translation": "the door",
             "sentence": "Er öffnete die Tür.", "cloze_word": "Tür",
             "hint": "h"},
            {"word": "der Mann", "translation": "the man",
             "sentence": "Ich sah den Mann.", "cloze_word": "Mann",
             "hint": "h"},
        ]
        result = format_vocab_examples(examples)
        assert result.count('class="example-item"') == 2
