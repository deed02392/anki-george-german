"""Tests for enrich_ipa_audio.py — Wiktionary parsing."""
import hashlib

import pytest
import requests.utils

import anki_george_german.enrich_ipa_audio as eia


# ═══════════════════════════════════════════════════════════════════════════
# A. extract_lookup_word()
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractLookupWord:

    def test_strip_der(self):
        word, is_phrase = eia.extract_lookup_word("der Freund")
        assert word == "Freund"
        assert is_phrase is False

    def test_strip_die(self):
        word, is_phrase = eia.extract_lookup_word("die Katze")
        assert word == "Katze"
        assert is_phrase is False

    def test_strip_das(self):
        word, is_phrase = eia.extract_lookup_word("das Kind")
        assert word == "Kind"
        assert is_phrase is False

    def test_no_article(self):
        word, is_phrase = eia.extract_lookup_word("laufen")
        assert word == "laufen"
        assert is_phrase is False

    def test_phrase_detected_space(self):
        word, is_phrase = eia.extract_lookup_word("Auf Wiedersehen")
        assert is_phrase is True

    def test_phrase_detected_question_mark(self):
        word, is_phrase = eia.extract_lookup_word("Wie geht es?")
        assert is_phrase is True

    def test_strip_ein(self):
        word, is_phrase = eia.extract_lookup_word("ein Buch")
        assert word == "Buch"
        assert is_phrase is False

    def test_strip_eine(self):
        word, is_phrase = eia.extract_lookup_word("eine Frage")
        assert word == "Frage"
        assert is_phrase is False


# ═══════════════════════════════════════════════════════════════════════════
# B. extract_german_section()
# ═══════════════════════════════════════════════════════════════════════════

WIKITEXT_MULTI_LANG = """\
== Freund ({{Sprache|Deutsch}}) ==
=== Substantiv ===
Freund content here

== friend ({{Sprache|Englisch}}) ==
=== Noun ===
English content here
"""

WIKITEXT_GERMAN_ONLY = """\
== Hund ({{Sprache|Deutsch}}) ==
=== Substantiv ===
Hund content here
More German content.
"""

WIKITEXT_NO_GERMAN = """\
== ami ({{Sprache|Französisch}}) ==
=== Substantif ===
French content here
"""


class TestExtractGermanSection:

    def test_multi_language(self):
        """Extracts only the German section from multi-language wikitext."""
        result = eia.extract_german_section(WIKITEXT_MULTI_LANG)
        assert "Freund content here" in result
        assert "English content here" not in result

    def test_single_language(self):
        """Full content returned when only German is present."""
        result = eia.extract_german_section(WIKITEXT_GERMAN_ONLY)
        assert "Hund content here" in result
        assert "More German content." in result

    def test_no_german_fallback(self):
        """Full wikitext returned when no German section is found."""
        result = eia.extract_german_section(WIKITEXT_NO_GERMAN)
        assert "French content here" in result


# ═══════════════════════════════════════════════════════════════════════════
# C. extract_ipa()
# ═══════════════════════════════════════════════════════════════════════════

WIKITEXT_WITH_IPA = """\
== Freund ({{Sprache|Deutsch}}) ==
=== Substantiv ===
{{Aussprache}}
:{{IPA}} {{Lautschrift|fʁɔɪ̯nt}}
:{{Audio|De-Freund.ogg}}
"""

WIKITEXT_LAUTSCHRIFT_ONLY = """\
== Hund ({{Sprache|Deutsch}}) ==
=== Substantiv ===
{{Aussprache}}
:{{Lautschrift|hʊnt}}
"""

WIKITEXT_NO_IPA = """\
== Hund ({{Sprache|Deutsch}}) ==
=== Substantiv ===
Some content without IPA.
"""


class TestExtractIpa:

    def test_standard_format(self):
        """Extracts IPA from standard {{IPA}} {{Lautschrift|...}} format."""
        result = eia.extract_ipa(WIKITEXT_WITH_IPA)
        assert result == "fʁɔɪ̯nt"

    def test_lautschrift_only(self):
        """Extracts IPA from {{Lautschrift|...}} without {{IPA}} prefix."""
        result = eia.extract_ipa(WIKITEXT_LAUTSCHRIFT_ONLY)
        assert result == "hʊnt"

    def test_no_ipa(self):
        """Returns None when no IPA is found."""
        result = eia.extract_ipa(WIKITEXT_NO_IPA)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# D. extract_audio_filename()
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractAudioFilename:

    def test_standard_audio(self):
        """Extracts audio filename from {{Audio|...}} template."""
        result = eia.extract_audio_filename(WIKITEXT_WITH_IPA)
        assert result == "De-Freund.ogg"

    def test_no_audio(self):
        """Returns None when no audio template is found."""
        result = eia.extract_audio_filename(WIKITEXT_NO_IPA)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# E. commons_url_from_filename()
# ═══════════════════════════════════════════════════════════════════════════


class TestCommonsUrlFromFilename:

    def test_url_structure(self):
        """URL has correct MD5-based directory structure."""
        filename = "De-Freund.ogg"
        md5 = hashlib.md5(filename.encode()).hexdigest()
        url = eia.commons_url_from_filename(filename)

        expected_prefix = (
            f"https://upload.wikimedia.org/wikipedia/commons"
            f"/{md5[0]}/{md5[:2]}/"
        )
        assert url.startswith(expected_prefix)
        assert requests.utils.quote(filename) in url

    def test_different_filenames_different_urls(self):
        """Different filenames produce different URLs."""
        url1 = eia.commons_url_from_filename("De-Hund.ogg")
        url2 = eia.commons_url_from_filename("De-Katze.ogg")
        assert url1 != url2
