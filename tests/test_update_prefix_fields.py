"""Tests for update_prefix_fields.py — prefix HTML formatting."""
import pytest

import anki_george_german.update_prefix_fields as upf


# ═══════════════════════════════════════════════════════════════════════════
# A. format_examples_html()
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatExamplesHtml:

    def test_prefix_highlighted(self):
        """Prefix is wrapped in <span class="pfx">."""
        examples = [{"verb": "absetzen", "translation": "take off"}]
        result = upf.format_examples_html("ab", examples)
        assert '<span class="pfx">ab</span>setzen' in result
        assert "take off" in result

    def test_case_insensitive(self):
        """Prefix matching is case-insensitive, preserving original case."""
        examples = [{"verb": "Aufmachen", "translation": "open"}]
        result = upf.format_examples_html("auf", examples)
        assert '<span class="pfx">Auf</span>machen' in result

    def test_no_prefix_match(self):
        """Verb without the prefix gets no span wrapping."""
        examples = [{"verb": "laufen", "translation": "to run"}]
        result = upf.format_examples_html("ab", examples)
        assert "<span" not in result
        assert "laufen" in result

    def test_multiple_examples_joined(self):
        """Multiple examples are joined with <br>."""
        examples = [
            {"verb": "absetzen", "translation": "take off"},
            {"verb": "abbrechen", "translation": "break off"},
            {"verb": "abziehen", "translation": "pull off"},
        ]
        result = upf.format_examples_html("ab", examples)
        assert result.count("<br>") == 2
        assert "setzen" in result
        assert "brechen" in result
        assert "ziehen" in result
        assert "take off" in result
        assert "break off" in result
        assert "pull off" in result

    def test_real_prefix_data(self, prefix_data):
        """format_examples_html works with actual prefix_data.json entries."""
        entry = prefix_data[0]  # "ab"
        result = upf.format_examples_html(entry["prefix"], entry["examples"])
        assert '<span class="pfx">' in result
        assert "<br>" in result
