"""Tests for fix_missing_ipa.py — LLM IPA application."""
import pytest

import anki_george_german.fix_missing_ipa as fmi


# ═══════════════════════════════════════════════════════════════════════════
# A. apply_ipa()
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_fmi_anki(monkeypatch):
    """Mock anki() at the fix_missing_ipa module level."""
    responses = {}

    def _anki(action, **params):
        if action in responses:
            val = responses[action]
            return val(params) if callable(val) else val
        return []

    monkeypatch.setattr(fmi, "anki", _anki)
    return responses


class TestApplyIpa:

    def test_match_by_word(self, mock_fmi_anki):
        """When LLM returns matching word, updateNoteFields is called."""
        updates = []
        def track_update(params):
            updates.append(params)
            return None
        mock_fmi_anki["updateNoteFields"] = track_update

        missing = [{"noteId": 123, "word": "der Hund"}]
        llm_result = [{"word": "der Hund", "ipa": "hʊnt"}]

        fmi.apply_ipa(missing, llm_result, dry_run=False)

        assert len(updates) == 1
        assert updates[0]["note"]["fields"]["IPA"] == "hʊnt"

    def test_no_match(self, mock_fmi_anki):
        """When LLM returns a different word, no update is made."""
        updates = []
        def track_update(params):
            updates.append(params)
            return None
        mock_fmi_anki["updateNoteFields"] = track_update

        missing = [{"noteId": 123, "word": "der Hund"}]
        llm_result = [{"word": "die Katze", "ipa": "ˈkat͡sə"}]

        fmi.apply_ipa(missing, llm_result, dry_run=False)

        assert len(updates) == 0

    def test_dry_run(self, mock_fmi_anki):
        """In dry_run mode, no AnkiConnect calls are made."""
        updates = []
        def track_update(params):
            updates.append(params)
            return None
        mock_fmi_anki["updateNoteFields"] = track_update

        missing = [{"noteId": 123, "word": "der Hund"}]
        llm_result = [{"word": "der Hund", "ipa": "hʊnt"}]

        fmi.apply_ipa(missing, llm_result, dry_run=True)

        assert len(updates) == 0
