"""Shared test fixtures for anki-george-german."""
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# -- AnkiConnect mock -------------------------------------------------------

@pytest.fixture
def mock_anki(monkeypatch):
    """Mock anki_george_german._anki.anki to return canned responses keyed by action name.

    Usage:
        mock_anki["findNotes"] = [111, 222]
        mock_anki["notesInfo"] = lambda params: [...]
    """
    responses = {}

    def _anki(action, **params):
        if action in responses:
            val = responses[action]
            return val(params) if callable(val) else val
        return []

    monkeypatch.setattr("anki_george_german._anki.anki", _anki)
    return responses


# -- LLM mock ---------------------------------------------------------------

@pytest.fixture
def mock_llm(monkeypatch):
    """Mock anki_george_german._llm functions so no real API calls are made."""
    monkeypatch.setattr("anki_george_german._llm.get_floodgate_token", lambda: "mock-token")
    results = {}

    def _call(messages, token, **kw):
        return results.get("response", [])

    monkeypatch.setattr("anki_george_german._llm.call_llm", _call)
    return results


# -- Sample card fixtures ----------------------------------------------------

@pytest.fixture
def sample_card():
    """A valid noun card dict with sentences array."""
    return {
        "word": "der Apfel",
        "article": "das",  # intentionally wrong for some tests
        "translation": "apple",
        "disambiguation": "",
        "sentences": [
            {
                "sentence": "Ich esse den Apfel.",
                "cloze_word": "den Apfel",
                "sentence_translation": "I eat the apple.",
                "pos": "noun",
            },
            {
                "sentence": "Der Apfel ist rot.",
                "cloze_word": "Der Apfel",
                "sentence_translation": "The apple is red.",
                "pos": "noun",
            },
        ],
        "domains": "food",
        "note": "",
    }


@pytest.fixture
def sample_valid_noun_card():
    """A correctly-formed noun card for validation tests."""
    return {
        "word": "der Apfel",
        "article": "der",
        "translation": "apple",
        "disambiguation": "",
        "sentences": [
            {
                "sentence": "Ich esse den Apfel.",
                "cloze_word": "den Apfel",
                "sentence_translation": "I eat the apple.",
                "pos": "noun",
            },
            {
                "sentence": "Der Apfel ist rot.",
                "cloze_word": "Der Apfel",
                "sentence_translation": "The apple is red.",
                "pos": "noun",
            },
        ],
        "domains": "food",
        "note": "",
    }


@pytest.fixture
def sample_verb_card():
    """A valid verb card dict."""
    return {
        "word": "laufen",
        "article": "",
        "translation": "to run",
        "disambiguation": "",
        "sentences": [
            {
                "sentence": "Er läuft jeden Tag im Park.",
                "cloze_word": "läuft",
                "sentence_translation": "He runs in the park every day.",
                "pos": "verb",
            },
        ],
        "domains": "sport",
        "note": "",
    }


@pytest.fixture
def sample_separable_verb_card():
    """A valid separable verb card dict."""
    return {
        "word": "aufmachen",
        "article": "",
        "translation": "to open",
        "disambiguation": "",
        "sentences": [
            {
                "sentence": "Er machte die Tür auf.",
                "cloze_word": "machte~auf",
                "sentence_translation": "He opened the door.",
                "pos": "verb",
            },
        ],
        "domains": "everyday",
        "note": "",
    }


@pytest.fixture
def prefix_data():
    """Load prefix_data.json."""
    path = PROJECT_ROOT / "data" / "prefix_data.json"
    with open(path) as f:
        return json.load(f)


# -- spaCy fixture (session-scoped, slow) ------------------------------------

@pytest.fixture(scope="session")
def nlp():
    """Load the spaCy German transformer model (slow, session-scoped)."""
    import spacy
    return spacy.load("de_dep_news_trf")
