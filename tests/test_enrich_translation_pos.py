"""Tests for enrich_translation_pos module."""
import pytest

from anki_george_german.enrich_translation_pos import (
    classify_sentence_pos,
    SPACY_TO_POS,
)


# -- Session-scoped English spaCy fixture ------------------------------------

@pytest.fixture(scope="session")
def nlp_en():
    """Load the spaCy English model (slow, session-scoped)."""
    import spacy
    return spacy.load("en_core_web_trf")


# -- classify_sentence_pos tests ---------------------------------------------

@pytest.mark.slow
class TestClassifySentencePOS:
    def test_dying_as_noun(self, nlp_en):
        assert classify_sentence_pos(
            "The dying of the old chess master saddened all players.",
            "dying", nlp_en,
        ) == "noun"

    def test_die_as_verb(self, nlp_en):
        assert classify_sentence_pos(
            "He returned to his home village to die.",
            "dying", nlp_en,
        ) == "verb"

    def test_apple_as_noun(self, nlp_en):
        assert classify_sentence_pos(
            "I eat the apple.", "apple", nlp_en,
        ) == "noun"

    def test_help_as_noun(self, nlp_en):
        assert classify_sentence_pos(
            "Help is on the way.", "help", nlp_en,
        ) == "noun"

    def test_empty_sentence(self, nlp_en):
        assert classify_sentence_pos("", "", nlp_en) == ""

    def test_empty_word(self, nlp_en):
        assert classify_sentence_pos("Some sentence.", "", nlp_en) == ""

    def test_to_eat_verb(self, nlp_en):
        assert classify_sentence_pos(
            "I like to eat fresh bread.", "to eat", nlp_en,
        ) == "verb"

    def test_presentably_matches_presentable(self, nlp_en):
        assert classify_sentence_pos(
            "The master dressed presentably for the tournament.",
            "presentable", nlp_en,
        ) == "adverb"


# -- run() tests with mocked AnkiConnect -------------------------------------

def test_run_updates_notes_pipe_separated(mock_anki, monkeypatch):
    """run() should produce pipe-separated TranslationPOS per variant."""
    mock_anki["modelFieldNames"] = [
        "Word", "POS", "Article", "WordTranslation",
        "WordTranslationDisambiguate", "TranslationPOS",
        "IPA", "Audio", "Sentence", "ClozeWord", "ClozeHint",
        "SentenceTranslation", "Note",
    ]

    mock_anki["findNotes"] = [111]
    mock_anki["notesInfo"] = [
        {
            "noteId": 111,
            "fields": {
                "Word": {"value": "das Sterben"},
                "POS": {"value": "noun|noun|noun"},
                "WordTranslation": {"value": "dying"},
                "TranslationPOS": {"value": ""},
                "SentenceTranslation": {
                    "value": "The dying of the old chess master saddened all players."
                             "|He never spoke about dying."
                             "|He returned to his home village to die.",
                },
            },
        },
    ]

    updates = []

    def track_update(params):
        updates.append(params)
        return None

    mock_anki["updateNoteFields"] = track_update

    import anki_george_german.enrich_translation_pos as mod

    def mock_classify(sent_tr, word_tr, nlp=None):
        mapping = {
            "The dying of the old chess master saddened all players.": "noun",
            "He never spoke about dying.": "noun",
            "He returned to his home village to die.": "verb",
        }
        return mapping.get(sent_tr.strip(), "")

    monkeypatch.setattr(mod, "classify_sentence_pos", mock_classify)
    monkeypatch.setattr(mod, "_nlp_en", "mock")
    monkeypatch.setattr(
        "anki_george_german.enrich_translation_pos.anki",
        lambda action, **params: mock_anki.get(action, lambda p: [])(params)
        if callable(mock_anki.get(action)) else mock_anki.get(action, []),
    )
    monkeypatch.setattr(
        "anki_george_german.enrich_translation_pos.fetch_vocab_notes",
        lambda extra_query="": mock_anki["notesInfo"],
    )

    class Args:
        dry_run = False

    mod.run(Args())

    assert len(updates) == 1
    assert updates[0]["note"]["id"] == 111
    assert updates[0]["note"]["fields"]["TranslationPOS"] == "noun|noun|verb"


def test_run_skips_unchanged(mock_anki, monkeypatch):
    """run() should skip notes where TranslationPOS hasn't changed."""
    mock_anki["modelFieldNames"] = [
        "Word", "POS", "Article", "WordTranslation",
        "WordTranslationDisambiguate", "TranslationPOS",
        "SentenceTranslation",
    ]

    mock_anki["findNotes"] = [111]
    mock_anki["notesInfo"] = [
        {
            "noteId": 111,
            "fields": {
                "Word": {"value": "essen"},
                "POS": {"value": "verb"},
                "WordTranslation": {"value": "to eat"},
                "TranslationPOS": {"value": "verb"},
                "SentenceTranslation": {"value": "I like to eat fresh bread."},
            },
        },
    ]

    updates = []
    mock_anki["updateNoteFields"] = lambda params: updates.append(params)

    import anki_george_german.enrich_translation_pos as mod

    def mock_classify(sent_tr, word_tr, nlp=None):
        return "verb"

    monkeypatch.setattr(mod, "classify_sentence_pos", mock_classify)
    monkeypatch.setattr(mod, "_nlp_en", "mock")
    monkeypatch.setattr(
        "anki_george_german.enrich_translation_pos.anki",
        lambda action, **params: mock_anki.get(action, lambda p: [])(params)
        if callable(mock_anki.get(action)) else mock_anki.get(action, []),
    )
    monkeypatch.setattr(
        "anki_george_german.enrich_translation_pos.fetch_vocab_notes",
        lambda extra_query="": mock_anki["notesInfo"],
    )

    class Args:
        dry_run = False

    mod.run(Args())

    assert len(updates) == 0


def test_run_dry_run_no_updates(mock_anki, monkeypatch, capsys):
    """run() with --dry-run should not call updateNoteFields."""
    mock_anki["modelFieldNames"] = [
        "Word", "POS", "Article", "WordTranslation",
        "WordTranslationDisambiguate", "TranslationPOS",
        "SentenceTranslation",
    ]

    notes = [
        {
            "noteId": 111,
            "fields": {
                "Word": {"value": "das Sterben"},
                "POS": {"value": "noun"},
                "WordTranslation": {"value": "dying"},
                "TranslationPOS": {"value": ""},
                "SentenceTranslation": {
                    "value": "He returned to his home village to die.",
                },
            },
        },
    ]
    mock_anki["findNotes"] = [111]
    mock_anki["notesInfo"] = notes

    updates = []
    mock_anki["updateNoteFields"] = lambda params: updates.append(params)

    import anki_george_german.enrich_translation_pos as mod

    def mock_classify(sent_tr, word_tr, nlp=None):
        return "verb"

    monkeypatch.setattr(mod, "classify_sentence_pos", mock_classify)
    monkeypatch.setattr(mod, "_nlp_en", "mock")
    monkeypatch.setattr(
        "anki_george_german.enrich_translation_pos.anki",
        lambda action, **params: mock_anki.get(action, lambda p: [])(params)
        if callable(mock_anki.get(action)) else mock_anki.get(action, []),
    )
    monkeypatch.setattr(
        "anki_george_german.enrich_translation_pos.fetch_vocab_notes",
        lambda extra_query="": notes,
    )

    class Args:
        dry_run = True

    mod.run(Args())

    assert len(updates) == 0
    captured = capsys.readouterr()
    assert "MISMATCH" in captured.out
