"""Tests for LLM IPA fallback in enrich_ipa_audio.py."""
import pytest

import anki_george_german.enrich_ipa_audio as eia


# ═══════════════════════════════════════════════════════════════════════════
# A. _llm_ipa_fallback()
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_eia(monkeypatch):
    """Mock anki() and LLM helpers at the enrich_ipa_audio module level."""
    updates = []

    def _anki(action, **params):
        if action == "updateNoteFields":
            updates.append(params)
        return []

    monkeypatch.setattr(eia, "anki", _anki)
    monkeypatch.setattr(eia, "get_floodgate_token", lambda: "fake-token")
    return {"updates": updates}


class TestLlmIpaFallback:

    def test_match_by_word(self, mock_eia, monkeypatch):
        """When LLM returns matching word, updateNoteFields is called."""
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: [{"word": "der Hund", "ipa": "hʊnt"}])

        count = eia._llm_ipa_fallback([(123, "der Hund")])

        assert count == 1
        assert mock_eia["updates"][0]["note"]["fields"]["IPA"] == "hʊnt"

    def test_no_match(self, mock_eia, monkeypatch):
        """When LLM returns a different word, no update is made."""
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: [{"word": "die Katze", "ipa": "ˈkat͡sə"}])

        count = eia._llm_ipa_fallback([(123, "der Hund")])

        assert count == 0
        assert len(mock_eia["updates"]) == 0

    def test_dry_run(self, mock_eia, monkeypatch):
        """In dry_run mode, no AnkiConnect calls are made."""
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: [{"word": "der Hund", "ipa": "hʊnt"}])

        count = eia._llm_ipa_fallback([(123, "der Hund")], dry_run=True)

        assert count == 1
        assert len(mock_eia["updates"]) == 0

    def test_llm_failure(self, mock_eia, monkeypatch):
        """When LLM returns None, nothing happens."""
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: None)

        count = eia._llm_ipa_fallback([(123, "der Hund")])

        assert count == 0

    def test_empty_list(self, mock_eia):
        """Empty input returns 0 without calling LLM."""
        count = eia._llm_ipa_fallback([])
        assert count == 0
