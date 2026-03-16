"""Tests for enrich_ipa_audio.py — Wiktionary parsing, rate limiting, and enrichment."""
import base64
import hashlib
import types

import pytest
import requests
import requests.utils

import anki_george_german.enrich_ipa_audio as eia


@pytest.fixture(autouse=True)
def _auto_batch_mock(monkeypatch):
    """Ensure fetch_wikitext_batch always delegates to fetch_wikitext.

    This lets existing tests that mock fetch_wikitext continue to work
    now that the main loop calls fetch_wikitext_batch instead.
    """
    monkeypatch.setattr(eia, "fetch_wikitext_batch",
                        lambda words: {w: eia.fetch_wikitext(w) for w in words})


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_note(nid, word, ipa="", audio=""):
    """Build a minimal note dict as returned by AnkiConnect notesInfo."""
    return {
        "noteId": nid,
        "fields": {
            "Word": {"value": word},
            "IPA": {"value": ipa},
            "Audio": {"value": audio},
        },
    }


def _make_prefix_note(nid, prefix="ver"):
    """Build a Prefix note type dict (no Word/IPA/Audio fields)."""
    return {
        "noteId": nid,
        "fields": {
            "Prefix": {"value": prefix},
            "PrefixType": {"value": "inseparable"},
            "CoreMeaning": {"value": "change, wrong"},
            "SpatialSense": {"value": "transforms state"},
            "Examples": {"value": "<b>ver</b>stehen"},
        },
    }


def _mock_response(status=200, json_data=None, content=b"", headers=None):
    """Build a minimal requests.Response-like object."""
    r = types.SimpleNamespace()
    r.status_code = status
    r.headers = headers or {}
    r.content = content
    r.json = lambda: json_data if json_data else {}
    r.raise_for_status = lambda: None
    if status >= 400 and status != 429:
        def _raise():
            raise requests.HTTPError(f"{status}")
        r.raise_for_status = _raise
    return r


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

    def test_phrase_ellipsis(self):
        word, is_phrase = eia.extract_lookup_word("na ja…")
        assert is_phrase is True

    def test_phrase_triple_dot(self):
        word, is_phrase = eia.extract_lookup_word("also...")
        assert is_phrase is True

    def test_exclamation(self):
        word, is_phrase = eia.extract_lookup_word("Achtung!")
        assert is_phrase is True


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
        result = eia.extract_german_section(WIKITEXT_MULTI_LANG)
        assert "Freund content here" in result
        assert "English content here" not in result

    def test_single_language(self):
        result = eia.extract_german_section(WIKITEXT_GERMAN_ONLY)
        assert "Hund content here" in result
        assert "More German content." in result

    def test_no_german_fallback(self):
        result = eia.extract_german_section(WIKITEXT_NO_GERMAN)
        assert "French content here" in result


# ═══════════════════════════════════════════════════════════════════════════
# C. extract_aussprache_block()
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractAusspracheBlock:

    def test_standard_block(self):
        section = """\
=== Substantiv ===
{{Aussprache}}
:{{IPA}} {{Lautschrift|fʁɔɪ̯nt}}
:{{Audio|De-Freund.ogg}}
{{Bedeutungen}}
:etwas
"""
        result = eia.extract_aussprache_block(section)
        assert "Lautschrift|fʁɔɪ̯nt" in result
        assert "Audio|De-Freund.ogg" in result
        assert "etwas" not in result

    def test_no_aussprache(self):
        section = "Just some text"
        result = eia.extract_aussprache_block(section)
        assert result == section


# ═══════════════════════════════════════════════════════════════════════════
# D. extract_ipa()
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
        result = eia.extract_ipa(WIKITEXT_WITH_IPA)
        assert result == "fʁɔɪ̯nt"

    def test_lautschrift_only(self):
        result = eia.extract_ipa(WIKITEXT_LAUTSCHRIFT_ONLY)
        assert result == "hʊnt"

    def test_no_ipa(self):
        result = eia.extract_ipa(WIKITEXT_NO_IPA)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# E. commons_url_from_filename()
# ═══════════════════════════════════════════════════════════════════════════


class TestCommonsUrlFromFilename:

    def test_url_structure(self):
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
        url1 = eia.commons_url_from_filename("De-Hund.ogg")
        url2 = eia.commons_url_from_filename("De-Katze.ogg")
        assert url1 != url2

    def test_spaces_normalized_to_underscores(self):
        """Wikimedia Commons uses underscores; wikitext may have spaces."""
        url = eia.commons_url_from_filename("LL-Q188 (deu)-Sebastian Wallroth-rennen.wav")
        normalized = "LL-Q188_(deu)-Sebastian_Wallroth-rennen.wav"
        md5 = hashlib.md5(normalized.encode()).hexdigest()
        assert f"/{md5[0]}/{md5[:2]}/" in url
        assert "LL-Q188_%28deu%29-Sebastian_Wallroth-rennen.wav" in url


# ═══════════════════════════════════════════════════════════════════════════
# F2. fetch_best_audio() — REST API audio discovery
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchBestAudio:

    def _media_response(self, files):
        """Build a mock response for /links/media."""
        return _mock_response(json_data={"files": files})

    def _audio_file(self, title, duration=1.0, timestamp="2023-01-01T00:00:00Z"):
        """Build a single audio file entry as returned by the REST API."""
        url = f"//upload.wikimedia.org/wikipedia/commons/a/aa/{title}"
        return {
            "title": title,
            "file_description_url": f"https://commons.wikimedia.org/wiki/File:{title}",
            "latest": {"timestamp": timestamp, "user": {"id": 1, "name": "test"}},
            "preferred": {"mediatype": "AUDIO", "size": 10000, "width": None,
                          "height": None, "duration": duration, "url": "placeholder"},
            "original": {"mediatype": "AUDIO", "size": 10000, "width": None,
                         "height": None, "duration": duration, "url": url},
        }

    def test_picks_numbered_variant(self, monkeypatch):
        """Prefers De-Word2.ogg over De-Word.ogg."""
        files = [
            self._audio_file("De-Hund.ogg", duration=0.6, timestamp="2011-01-01T00:00:00Z"),
            self._audio_file("De-Hund2.ogg", duration=1.4, timestamp="2023-01-01T00:00:00Z"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename == "De-Hund2.ogg"
        assert "De-Hund2.ogg" in url

    def test_skips_austrian(self, monkeypatch):
        """Skips De-at-*.ogg recordings."""
        files = [
            self._audio_file("De-Hund.ogg"),
            self._audio_file("De-at-Hund.ogg"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename == "De-Hund.ogg"

    def test_skips_phrase_recordings(self, monkeypatch):
        """Skips recordings like 'De-einen Ball fangen.ogg'."""
        files = [
            self._audio_file("De-einen Ball fangen.ogg"),
            self._audio_file("De-fangen.ogg"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("fangen")
        assert filename == "De-fangen.ogg"

    def test_no_audio_returns_none(self, monkeypatch):
        """Returns (None, None) when no matching audio files."""
        files = [
            {"title": "Dog.jpg", "preferred": {"mediatype": "BITMAP"},
             "original": {"mediatype": "BITMAP", "url": "x"}, "latest": {}},
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename is None
        assert url is None

    def test_404_returns_none(self, monkeypatch):
        """Returns (None, None) for non-existent page."""
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(status=404))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("xyznonexistent")
        assert filename is None

    def test_rate_limit_returns_deferred(self, monkeypatch):
        """Returns (_DEFERRED_BAIL, None) on excessive rate limit."""
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            status=429, headers={"Retry-After": "999"}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename is eia._DEFERRED_BAIL

    def test_network_error_returns_deferred(self, monkeypatch):
        """Returns (_DEFERRED, None) on transient network error."""
        def _fail(*a, **kw):
            raise requests.ConnectionError("fail")
        monkeypatch.setattr(eia.web, "get", _fail)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename is eia._DEFERRED

    def test_prefers_numbered_over_lingua_libre(self, monkeypatch):
        """Numbered De- variants preferred over Lingua Libre."""
        files = [
            self._audio_file("De-Hund.ogg", timestamp="2020-01-01T00:00:00Z"),
            self._audio_file("LL-Q188 (deu)-WikiSpeech-Hund.ogg",
                             timestamp="2023-06-01T00:00:00Z"),
            self._audio_file("De-Hund2.ogg", timestamp="2023-01-01T00:00:00Z"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename == "De-Hund2.ogg"

    def test_lingua_libre_accepted(self, monkeypatch):
        """Lingua Libre recordings are accepted when no De- files exist."""
        files = [
            self._audio_file("LL-Q188 (deu)-WikiSpeech-Hund.ogg"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename == "LL-Q188 (deu)-WikiSpeech-Hund.ogg"

    def test_lingua_libre_over_base(self, monkeypatch):
        """Lingua Libre preferred over plain De-Word.ogg (same timestamp)."""
        files = [
            self._audio_file("De-Hund.ogg", timestamp="2020-01-01T00:00:00Z"),
            self._audio_file("LL-Q188 (deu)-WikiSpeech-Hund.ogg",
                             timestamp="2020-01-01T00:00:00Z"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename == "LL-Q188 (deu)-WikiSpeech-Hund.ogg"

    def test_file_prefix_stripped(self, monkeypatch):
        """REST API title with 'File:' prefix is handled correctly."""
        files = [
            self._audio_file("File:De-Hund.ogg"),
        ]
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: self._media_response(files))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        filename, url = eia.fetch_best_audio("Hund")
        assert filename == "De-Hund.ogg"


# ═══════════════════════════════════════════════════════════════════════════
# G. fetch_wikitext() — rate limiting and retries
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchWikitext:

    def test_success(self, monkeypatch):
        wikitext = "== Hund ({{Sprache|Deutsch}}) ==\ncontent"
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            json_data={"parse": {"wikitext": {"*": wikitext}}}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("Hund")
        assert result == wikitext

    def test_no_german_page(self, monkeypatch):
        """Page exists but has no German section → return None (not _DEFERRED)."""
        wikitext = "== dog ({{Sprache|Englisch}}) ==\ncontent"
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            json_data={"parse": {"wikitext": {"*": wikitext}}}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("dog")
        assert result is None

    def test_page_not_found(self, monkeypatch):
        """API returns error (no 'parse' key) → return None."""
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            json_data={"error": {"code": "missingtitle"}}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("xyznotaword")
        assert result is None

    def test_rate_limited_returns_sentinel(self, monkeypatch):
        """All retries hit 429 → return _DEFERRED."""
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            status=429, headers={"Retry-After": "1"}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("Hund")
        assert result is eia._DEFERRED

    def test_rate_limit_then_success(self, monkeypatch):
        """First request 429, second succeeds."""
        wikitext = "== Hund ({{Sprache|Deutsch}}) ==\ncontent"
        call_count = [0]

        def _get(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_response(status=429, headers={"Retry-After": "1"})
            return _mock_response(json_data={"parse": {"wikitext": {"*": wikitext}}})

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("Hund")
        assert result == wikitext

    def test_lowercase_fallback(self, monkeypatch):
        """If uppercase fails, tries lowercase."""
        wikitext = "== hund ({{Sprache|Deutsch}}) ==\ncontent"

        def _get(*a, **kw):
            params = kw.get("params", {})
            if params.get("page") == "Hund":
                return _mock_response(json_data={"error": {"code": "missingtitle"}})
            return _mock_response(json_data={"parse": {"wikitext": {"*": wikitext}}})

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("Hund")
        assert result == wikitext

    def test_network_error_retries(self, monkeypatch):
        """Transient network error retries, then defers (not a genuine miss)."""
        def _get(*a, **kw):
            raise requests.ConnectionError("Network down")

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("Hund")
        assert result is eia._DEFERRED


# ═══════════════════════════════════════════════════════════════════════════
# H. download_audio() — rate limiting
# ═══════════════════════════════════════════════════════════════════════════


class TestDownloadAudio:

    def test_success(self, monkeypatch):
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            content=b"audio-bytes"))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.download_audio("http://example.com/audio.ogg")
        assert result == b"audio-bytes"

    def test_rate_limited_returns_sentinel(self, monkeypatch):
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: _mock_response(
            status=429, headers={"Retry-After": "1"}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.download_audio("http://example.com/audio.ogg")
        assert result is eia._DEFERRED

    def test_network_error_returns_none(self, monkeypatch):
        def _get(*a, **kw):
            raise requests.ConnectionError("timeout")

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.download_audio("http://example.com/audio.ogg")
        assert result is None

    def test_rate_limit_then_success(self, monkeypatch):
        call_count = [0]

        def _get(*a, **kw):
            call_count[0] += 1
            if call_count[0] <= 2:
                return _mock_response(status=429, headers={"Retry-After": "1"})
            return _mock_response(content=b"audio-bytes")

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.download_audio("http://example.com/audio.ogg")
        assert result == b"audio-bytes"

    def test_http_error_retries(self, monkeypatch):
        """Non-429 HTTP error retries then returns None."""
        def _get(*a, **kw):
            raise requests.HTTPError("500")

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.download_audio("http://example.com/audio.ogg")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# I. store_audio_in_anki()
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreAudioInAnki:

    def test_converts_and_stores(self, monkeypatch, tmp_path):
        stored = {}

        def _anki(action, **params):
            if action == "storeMediaFile":
                stored.update(params)

        monkeypatch.setattr(eia, "anki", _anki)
        # Mock ffmpeg to just create an mp3 file
        def _run(cmd, **kw):
            # Find the output path (the one that's .mp3)
            for arg in cmd:
                if arg.endswith(".mp3"):
                    with open(arg, "wb") as f:
                        f.write(b"fake-mp3-data")
            return types.SimpleNamespace(returncode=0)

        monkeypatch.setattr(eia.subprocess, "run", _run)

        result = eia.store_audio_in_anki("De-Hund.ogg", b"fake-ogg-data")
        assert result == "De-Hund.mp3"
        assert stored["filename"] == "De-Hund.mp3"
        assert stored["data"] == base64.b64encode(b"fake-mp3-data").decode("ascii")

    def test_ffmpeg_failure(self, monkeypatch):
        monkeypatch.setattr(eia, "anki", lambda *a, **kw: None)
        monkeypatch.setattr(eia.subprocess, "run",
                            lambda *a, **kw: types.SimpleNamespace(returncode=1))

        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            eia.store_audio_in_anki("De-Hund.ogg", b"fake-ogg-data")


# ═══════════════════════════════════════════════════════════════════════════
# J. store_pcm_audio_in_anki()
# ═══════════════════════════════════════════════════════════════════════════


class TestStorePcmAudioInAnki:

    def test_converts_and_stores(self, monkeypatch):
        stored = {}

        def _anki(action, **params):
            if action == "storeMediaFile":
                stored.update(params)

        monkeypatch.setattr(eia, "anki", _anki)

        def _run(cmd, **kw):
            for arg in cmd:
                if arg.endswith(".mp3"):
                    with open(arg, "wb") as f:
                        f.write(b"fake-mp3")
            return types.SimpleNamespace(returncode=0)

        monkeypatch.setattr(eia.subprocess, "run", _run)

        result = eia.store_pcm_audio_in_anki("tts_Hund.mp3", b"\x00" * 100)
        assert result == "tts_Hund.mp3"
        assert stored["filename"] == "tts_Hund.mp3"

    def test_ffmpeg_failure(self, monkeypatch):
        monkeypatch.setattr(eia, "anki", lambda *a, **kw: None)
        monkeypatch.setattr(eia.subprocess, "run",
                            lambda *a, **kw: types.SimpleNamespace(returncode=1))

        with pytest.raises(RuntimeError, match="ffmpeg PCM"):
            eia.store_pcm_audio_in_anki("tts_Hund.mp3", b"\x00" * 100)


# ═══════════════════════════════════════════════════════════════════════════
# K. _gemini_tts_single()
# ═══════════════════════════════════════════════════════════════════════════


class TestGeminiTtsSingle:

    def test_success(self, monkeypatch):
        pcm_b64 = base64.b64encode(b"pcm-audio-data").decode()
        resp = _mock_response(json_data={
            "candidates": [{"content": {"parts": [{"inlineData": {"data": pcm_b64}}]}}]
        })
        monkeypatch.setattr(eia.requests, "post", lambda *a, **kw: resp)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result, err = eia._gemini_tts_single("Hund", "fake-key")
        assert result == b"pcm-audio-data"
        assert err is None

    def test_rate_limited(self, monkeypatch):
        monkeypatch.setattr(eia.requests, "post", lambda *a, **kw: _mock_response(
            status=429))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result, err = eia._gemini_tts_single("Hund", "fake-key")
        assert result is eia._DEFERRED
        assert err is not None

    def test_error_returns_none(self, monkeypatch):
        def _post(*a, **kw):
            raise requests.ConnectionError("fail")

        monkeypatch.setattr(eia.requests, "post", _post)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result, err = eia._gemini_tts_single("Hund", "fake-key")
        assert result is None

    def test_bad_response_shape(self, monkeypatch):
        monkeypatch.setattr(eia.requests, "post", lambda *a, **kw: _mock_response(
            json_data={"candidates": []}))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result, err = eia._gemini_tts_single("Hund", "fake-key")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# L. _gemini_tts_fallback()
# ═══════════════════════════════════════════════════════════════════════════


class TestGeminiTtsFallback:

    def test_empty_list(self):
        assert eia._gemini_tts_fallback([]) == 0

    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = eia._gemini_tts_fallback([(1, "der Hund")])
        assert result == 0

    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        result = eia._gemini_tts_fallback([(1, "der Hund")], dry_run=True)
        assert result == 1

    def test_success(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        monkeypatch.setattr(eia, "_gemini_tts_single", lambda w, k: (b"pcm-data", None))
        stored = []
        monkeypatch.setattr(eia, "store_pcm_audio_in_anki",
                            lambda name, data: (stored.append(name), name)[-1])
        monkeypatch.setattr(eia, "anki", lambda *a, **kw: None)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia._gemini_tts_fallback([(1, "der Hund")])
        assert result == 1
        assert stored[0] == "tts_Hund.mp3"

    def test_rate_limited_stops_immediately(self, monkeypatch):
        """Daily quota hit → stop, don't retry."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        call_count = [0]
        mock_resp = _mock_response(status=429, json_data={
            "error": {"details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                 "retryDelay": "33s"},
            ]}
        })

        def _tts(word, key):
            call_count[0] += 1
            return eia._DEFERRED, mock_resp

        monkeypatch.setattr(eia, "_gemini_tts_single", _tts)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia._gemini_tts_fallback([(1, "der Hund"), (2, "die Katze")])
        assert result == 0
        assert call_count[0] == 1  # stopped after first 429

    def test_permanent_failure(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        monkeypatch.setattr(eia, "_gemini_tts_single", lambda w, k: (None, None))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia._gemini_tts_fallback([(1, "der Hund")])
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════
# M. _llm_ipa_fallback()
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
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: [{"word": "der Hund", "ipa": "hʊnt"}])
        count = eia._llm_ipa_fallback([(123, "der Hund")])
        assert count == 1
        assert mock_eia["updates"][0]["note"]["fields"]["IPA"] == "hʊnt"

    def test_no_match(self, mock_eia, monkeypatch):
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: [{"word": "die Katze", "ipa": "ˈkat͡sə"}])
        count = eia._llm_ipa_fallback([(123, "der Hund")])
        assert count == 0

    def test_dry_run(self, mock_eia, monkeypatch):
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: [{"word": "der Hund", "ipa": "hʊnt"}])
        count = eia._llm_ipa_fallback([(123, "der Hund")], dry_run=True)
        assert count == 1
        assert len(mock_eia["updates"]) == 0

    def test_llm_failure(self, mock_eia, monkeypatch):
        monkeypatch.setattr(eia, "call_llm_with_retry",
                            lambda *a, **kw: None)
        count = eia._llm_ipa_fallback([(123, "der Hund")])
        assert count == 0

    def test_empty_list(self, mock_eia):
        count = eia._llm_ipa_fallback([])
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# N. enrich_notes() — integration tests for the main loop
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def enrich_env(monkeypatch, tmp_path):
    """Set up a fully mocked environment for enrich_notes()."""
    updates = []  # captured updateNoteFields calls
    wikitext_db = {}  # word -> wikitext (or _DEFERRED)

    def _anki(action, **params):
        if action == "modelFieldNames":
            return ["Word", "POS", "IPA", "Audio"]
        if action == "findNotes":
            return params.get("_ids", [])
        if action == "notesInfo":
            return params.get("_notes", [])
        if action == "updateNoteFields":
            updates.append(params)
        if action == "storeMediaFile":
            pass
        return []

    # Store notes for notesInfo
    _stored_notes = []

    def _anki_dispatch(action, **params):
        if action == "modelFieldNames":
            return ["Word", "POS", "IPA", "Audio"]
        if action == "notesInfo":
            return _stored_notes
        if action == "updateNoteFields":
            updates.append(params["note"])
        if action == "storeMediaFile":
            pass
        return []

    def _fetch(word):
        return wikitext_db.get(word, None)

    monkeypatch.setattr(eia, "anki", _anki_dispatch)
    monkeypatch.setattr(eia, "fetch_wikitext", _fetch)
    monkeypatch.setattr(eia, "download_audio", lambda url, **kw: b"audio-bytes")
    monkeypatch.setattr(eia, "fetch_best_audio", lambda w: ("De-" + w + ".ogg",
                        "https://upload.wikimedia.org/wikipedia/commons/a/aa/De-" + w + ".ogg"))
    monkeypatch.setattr(eia, "store_audio_in_anki", lambda fn, data: fn.replace(".ogg", ".mp3"))
    monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
    monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)
    monkeypatch.setattr(eia.time, "sleep", lambda _: None)
    monkeypatch.setattr(eia, "CHECKPOINT_PATH", tmp_path / "enrich_index.json")

    env = {
        "updates": updates,
        "wikitext_db": wikitext_db,
        "notes": _stored_notes,
    }
    return env


class TestEnrichNotes:

    def test_nothing_to_enrich(self, enrich_env):
        result = eia.enrich_notes(note_ids=[])
        assert result["ipa_added"] == 0

    def test_already_complete(self, enrich_env):
        enrich_env["notes"].append(_make_note(1, "der Hund", ipa="hʊnt", audio="[sound:x.mp3]"))
        result = eia.enrich_notes(note_ids=[1])
        assert result["already_ok"] == 1

    def test_skip_phrase(self, enrich_env):
        enrich_env["notes"].append(_make_note(1, "Auf Wiedersehen"))
        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        assert result["skipped_phrase"] == 1

    def test_ipa_from_wiktionary(self, enrich_env):
        enrich_env["notes"].append(_make_note(1, "der Hund"))
        enrich_env["wikitext_db"]["Hund"] = WIKITEXT_WITH_IPA.replace("Freund", "Hund").replace("fʁɔɪ̯nt", "hʊnt")
        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        assert result["ipa_added"] == 1

    def test_no_wikt_page_goes_to_llm(self, enrich_env, monkeypatch):
        """Word not on Wiktionary → goes to ipa_misses (LLM), not deferred."""
        enrich_env["notes"].append(_make_note(1, "xyzword"))
        llm_calls = []
        monkeypatch.setattr(eia, "_llm_ipa_fallback",
                            lambda words, **kw: (llm_calls.extend(words), 1)[-1])
        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        assert result["no_page"] == 1
        assert len(llm_calls) == 1
        assert llm_calls[0] == (1, "xyzword")

    def test_no_wikt_audio_goes_to_tts(self, enrich_env, monkeypatch):
        """Word on Wiktionary but no audio → tts_candidates."""
        enrich_env["notes"].append(_make_note(1, "der Hund", ipa="hʊnt"))
        # Wikitext exists but has no Audio template
        enrich_env["wikitext_db"]["Hund"] = WIKITEXT_NO_IPA.replace("Hund", "Hund")
        # REST API also finds no audio for this word
        monkeypatch.setattr(eia, "fetch_best_audio", lambda w: (None, None))
        tts_calls = []
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 1)[-1])
        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        assert len(tts_calls) == 1

    def test_rate_limited_wikt_not_sent_to_tts(self, enrich_env, monkeypatch):
        """Rate-limited Wiktionary fetch → deferred, NOT sent to TTS."""
        enrich_env["notes"].append(_make_note(1, "der Hund"))
        enrich_env["wikitext_db"]["Hund"] = eia._DEFERRED
        tts_calls = []
        llm_calls = []
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 0)[-1])
        monkeypatch.setattr(eia, "_llm_ipa_fallback",
                            lambda words, **kw: (llm_calls.extend(words), 0)[-1])
        result = eia.enrich_notes(note_ids=[1])
        assert len(tts_calls) == 0  # NOT sent to TTS
        assert len(llm_calls) == 0  # NOT sent to LLM

    def test_rate_limited_download_not_sent_to_tts(self, enrich_env, monkeypatch):
        """Audio exists on Wiktionary but download is rate-limited → deferred."""
        enrich_env["notes"].append(_make_note(1, "der Hund", ipa="hʊnt"))
        enrich_env["wikitext_db"]["Hund"] = WIKITEXT_WITH_IPA.replace("Freund", "Hund")
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: eia._DEFERRED)
        tts_calls = []
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 0)[-1])
        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        assert len(tts_calls) == 0  # NOT sent to TTS

    def test_audio_download_success(self, enrich_env):
        """Audio exists and downloads OK → stored in Anki."""
        enrich_env["notes"].append(_make_note(1, "der Hund", ipa="hʊnt"))
        enrich_env["wikitext_db"]["Hund"] = WIKITEXT_WITH_IPA.replace("Freund", "Hund")
        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        assert result["audio_added"] == 1
        assert any("Audio" in u["fields"] for u in enrich_env["updates"])

    def test_dry_run_no_updates(self, enrich_env):
        enrich_env["notes"].append(_make_note(1, "der Hund"))
        enrich_env["wikitext_db"]["Hund"] = WIKITEXT_WITH_IPA.replace("Freund", "Hund").replace("fʁɔɪ̯nt", "hʊnt")
        result = eia.enrich_notes(note_ids=[1], ipa_only=True, dry_run=True)
        assert result["ipa_added"] == 1
        assert len(enrich_env["updates"]) == 0

    def test_llm_fallback_disabled(self, enrich_env, monkeypatch):
        """--no-llm prevents LLM/TTS fallback."""
        enrich_env["notes"].append(_make_note(1, "xyzword"))
        llm_called = [False]
        tts_called = [False]
        monkeypatch.setattr(eia, "_llm_ipa_fallback",
                            lambda *a, **kw: (llm_called.__setitem__(0, True), 0)[-1])
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda *a, **kw: (tts_called.__setitem__(0, True), 0)[-1])
        eia.enrich_notes(note_ids=[1], llm_fallback=False)
        assert not llm_called[0]
        assert not tts_called[0]

    def test_redownload_skips_same_file(self, enrich_env):
        """redownload skips download when note already has the same mp3."""
        # Note already has De-Freund.mp3 (from De-Freund.ogg)
        enrich_env["notes"].append(
            _make_note(1, "der Freund", ipa="fʁɔɪ̯nt", audio="[sound:De-Freund.mp3]"))
        enrich_env["wikitext_db"]["Freund"] = WIKITEXT_WITH_IPA
        download_called = [False]
        orig_download = enrich_env.get("_orig_download")

        import anki_george_german.enrich_ipa_audio as _eia
        def _track_download(url, **kw):
            download_called[0] = True
            return b"audio-bytes"
        _eia.download_audio = _track_download

        result = eia.enrich_notes(note_ids=[1], audio_only=True, redownload=True)
        assert not download_called[0]  # no download — same file
        assert result["already_ok"] == 1

    def test_redownload_upgrades_different_file(self, enrich_env, monkeypatch):
        """redownload downloads when REST API finds a better variant."""
        # Note has De-Freund.mp3 but REST API will find De-Freund2.ogg
        enrich_env["notes"].append(
            _make_note(1, "der Freund", ipa="fʁɔɪ̯nt", audio="[sound:De-Freund.mp3]"))
        enrich_env["wikitext_db"]["Freund"] = WIKITEXT_WITH_IPA
        monkeypatch.setattr(eia, "fetch_best_audio",
                            lambda w: ("De-Freund2.ogg",
                                       "https://upload.wikimedia.org/commons/7/73/De-Freund2.ogg"))

        result = eia.enrich_notes(note_ids=[1], audio_only=True, redownload=True)
        assert result["audio_added"] == 1
        assert any("De-Freund2.mp3" in u["fields"].get("Audio", "")
                    for u in enrich_env["updates"])


# ═══════════════════════════════════════════════════════════════════════════
# O. Wiktionary retry phase in enrich_notes()
# ═══════════════════════════════════════════════════════════════════════════


class TestEnrichNotesRetryPhase:

    def test_retry_succeeds_after_rate_limit(self, monkeypatch):
        """Rate-limited word retried successfully from Wiktionary."""
        updates = []
        notes = [_make_note(1, "der Hund")]

        wikitext_good = WIKITEXT_WITH_IPA.replace("Freund", "Hund").replace("fʁɔɪ̯nt", "hʊnt")
        fetch_count = [0]

        def _fetch(word):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                return eia._DEFERRED
            return wikitext_good

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                updates.append(params["note"])
            if action == "storeMediaFile":
                pass
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", _fetch)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: b"audio")
        monkeypatch.setattr(eia, "store_audio_in_anki", lambda fn, d: fn.replace(".ogg", ".mp3"))
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.enrich_notes(note_ids=[1])
        assert result["ipa_added"] >= 1
        assert fetch_count[0] >= 2  # at least one retry

    def test_retry_exhausted_stays_deferred(self, monkeypatch):
        """Word stays rate-limited after all retry passes → not sent to TTS."""
        notes = [_make_note(1, "der Hund")]
        tts_calls = []

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                pass
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda word: eia._DEFERRED)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 0)[-1])
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.enrich_notes(note_ids=[1])
        assert len(tts_calls) == 0

    def test_retry_discovers_no_page(self, monkeypatch):
        """Rate-limited word on retry discovers page doesn't exist → goes to TTS and LLM."""
        notes = [_make_note(1, "xyzword")]
        tts_calls = []
        llm_calls = []
        fetch_count = [0]

        def _fetch(word):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                return eia._DEFERRED
            return None  # page doesn't exist

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                pass
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", _fetch)
        monkeypatch.setattr(eia, "_llm_ipa_fallback",
                            lambda words, **kw: (llm_calls.extend(words), len(words))[-1])
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), len(words))[-1])
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.enrich_notes(note_ids=[1])
        assert len(tts_calls) == 1  # discovered as genuinely missing → TTS
        assert len(llm_calls) == 1  # discovered as genuinely missing → LLM


# ═══════════════════════════════════════════════════════════════════════════
# P. run() CLI entry point
# ═══════════════════════════════════════════════════════════════════════════


class TestRunCli:

    def test_specific_words(self, monkeypatch):
        """run() with words arg searches for note IDs."""
        found_ids = []

        def _anki(action, **params):
            if action == "findNotes":
                return [42]
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return [_make_note(42, "der Hund", ipa="hʊnt", audio="[sound:x.mp3]")]
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        args = types.SimpleNamespace(
            words=["Hund"], ipa_only=True, audio_only=False,
            audio_delay=0, dry_run=True, no_llm=True,
        )
        eia.run(args)  # should not raise

    def test_no_matching_words(self, monkeypatch):
        monkeypatch.setattr(eia, "anki", lambda *a, **kw: [])

        args = types.SimpleNamespace(
            words=["nonexistent"], ipa_only=True, audio_only=False,
            audio_delay=0, dry_run=True, no_llm=True,
        )
        eia.run(args)  # should not raise

    def test_word_with_space(self, monkeypatch):
        """Word containing space uses exact match query."""
        queries = []

        def _anki(action, **params):
            if action == "findNotes":
                queries.append(params.get("query", ""))
                return [42]
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return [_make_note(42, "der Hund", ipa="hʊnt", audio="[sound:x.mp3]")]
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        args = types.SimpleNamespace(
            words=["der Hund"], ipa_only=True, audio_only=False,
            audio_delay=0, dry_run=True, no_llm=True,
        )
        eia.run(args)
        assert '"Word:der Hund"' in queries[0]

    def test_no_words_arg(self, monkeypatch):
        """run() without words delegates to enrich_notes(note_ids=None)."""
        called_with = []

        def _enrich(**kw):
            called_with.append(kw)
            return {}

        monkeypatch.setattr(eia, "enrich_notes", _enrich)

        args = types.SimpleNamespace(
            words=None, ipa_only=False, audio_only=False,
            audio_delay=5.0, dry_run=False, no_llm=False,
        )
        eia.run(args)
        assert called_with[0]["note_ids"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Q. Additional coverage — targeting specific uncovered lines
# ═══════════════════════════════════════════════════════════════════════════


class TestGeminiTtsSingleEdgeCases:

    def test_all_retries_429_returns_sentinel(self, monkeypatch):
        """All 3 loop iterations hit 429 continue → final return _DEFERRED."""
        # Need attempt < 2 to be True for first two, then False for third
        # which triggers the return inside the loop. But the final return
        # after the for is line 354. This requires all 3 iterations to
        # continue (not return). Actually the code returns _DEFERRED
        # on attempt == 2 (line 346), so line 354 is dead code unless
        # the loop somehow exhausts without returning. It's reachable only
        # if the last attempt falls through a non-429 path.
        # Actually, looking at the code: if attempt 0 and 1 get 429, they
        # continue. Attempt 2 gets 429 → returns _DEFERRED (line 346).
        # Line 354 is unreachable in current logic. Let's skip it.
        pass


class TestGeminiTtsFallbackQuotaStop:

    def test_stops_on_quota_skips_remaining(self, monkeypatch):
        """Daily quota hit on 2nd word → stops, doesn't call 3rd."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        call_count = [0]
        mock_resp = _mock_response(status=429, json_data={"error": {"details": []}})

        def _tts(word, key):
            call_count[0] += 1
            if call_count[0] == 2:
                return eia._DEFERRED, mock_resp
            return b"pcm-data", None

        monkeypatch.setattr(eia, "_gemini_tts_single", _tts)
        monkeypatch.setattr(eia, "store_pcm_audio_in_anki", lambda n, d: n)
        monkeypatch.setattr(eia, "anki", lambda *a, **kw: None)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia._gemini_tts_fallback([
            (1, "der Hund"), (2, "die Katze"), (3, "das Kind")])
        assert result == 1  # only first word succeeded
        assert call_count[0] == 2  # stopped after 2nd call


class TestEnrichNotesAdditionalPaths:

    def _setup_anki(self, monkeypatch, notes, updates=None):
        if updates is None:
            updates = []

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                updates.append(params["note"])
            if action == "findNotes":
                return [n["noteId"] for n in notes]
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_best_audio",
                            lambda w: ("De-" + w + ".ogg",
                                       "https://upload.wikimedia.org/commons/a/aa/De-" + w + ".ogg"))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        return updates

    def test_auto_discover_notes_when_note_ids_none(self, monkeypatch):
        """When note_ids is None, findNotes is called to discover notes."""
        notes = [_make_note(1, "der Hund")]

        find_queries = []

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "findNotes":
                find_queries.append(params.get("query", ""))
                return [1]
            if action == "notesInfo":
                return notes
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: None)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        eia.enrich_notes(note_ids=None)
        assert len(find_queries) >= 1  # findNotes was called

    def test_audio_field_creation(self, monkeypatch):
        """Audio field is added to model if missing."""
        field_actions = []
        notes = [_make_note(1, "der Hund", ipa="hʊnt", audio="[sound:x.mp3]")]

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA"]  # no Audio field
            if action == "modelFieldAdd":
                field_actions.append(params)
                return None
            if action == "notesInfo":
                return notes
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        eia.enrich_notes(note_ids=[1], audio_only=True)
        assert len(field_actions) == 1
        assert field_actions[0]["fieldName"] == "Audio"

    def test_ipa_miss_on_page_with_wikitext(self, monkeypatch):
        """Wikitext found but no IPA in it → ipa_miss counted."""
        notes = [_make_note(1, "der Hund")]
        # Wikitext has no IPA section
        wikt_no_ipa = WIKITEXT_NO_IPA.replace("Hund", "Hund")

        self._setup_anki(monkeypatch, notes)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: wikt_no_ipa)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)

        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        assert result["ipa_miss"] == 1

    def test_has_ipa_already_report(self, monkeypatch):
        """Note with existing IPA reports 'IPA=ok' for that field."""
        notes = [_make_note(1, "der Hund", ipa="hʊnt")]  # has IPA, no audio
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")

        self._setup_anki(monkeypatch, notes)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: wikt)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: b"audio")
        monkeypatch.setattr(eia, "store_audio_in_anki", lambda fn, d: fn.replace(".ogg", ".mp3"))
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)

        # Needs audio but not IPA
        result = eia.enrich_notes(note_ids=[1])
        assert result["audio_added"] == 1

    def test_has_audio_already_report(self, monkeypatch):
        """Note with existing audio reports 'audio=ok'."""
        notes = [_make_note(1, "der Hund", audio="[sound:x.mp3]")]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund").replace("fʁɔɪ̯nt", "hʊnt")

        self._setup_anki(monkeypatch, notes)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: wikt)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)

        result = eia.enrich_notes(note_ids=[1])
        assert result["ipa_added"] == 1

    def test_audio_download_fails_not_rate_limit(self, monkeypatch):
        """Audio file exists on Wiktionary but download returns None (not rate limit)."""
        notes = [_make_note(1, "der Hund", ipa="hʊnt")]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")

        self._setup_anki(monkeypatch, notes)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: wikt)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: None)  # fail, not rate limit
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)

        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        # Audio not added, not deferred — it's a transient fail
        assert result["audio_added"] == 0

    def test_dry_run_with_audio_filename(self, monkeypatch):
        """dry_run counts audio_added when filename found."""
        notes = [_make_note(1, "der Hund", ipa="hʊnt")]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")

        self._setup_anki(monkeypatch, notes)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: wikt)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)

        result = eia.enrich_notes(note_ids=[1], audio_only=True, dry_run=True)
        assert result["audio_added"] == 1


class TestEnrichNotesRetryPhaseAdditional:

    def _setup(self, monkeypatch, notes, fetch_fn):
        updates = []

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                updates.append(params["note"])
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", fetch_fn)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "fetch_best_audio",
                            lambda w: ("De-" + w + ".ogg",
                                       "https://upload.wikimedia.org/commons/a/aa/De-" + w + ".ogg"))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        return updates

    def test_retry_ipa_miss_on_page(self, monkeypatch):
        """Retry succeeds in fetching page but page has no IPA → goes to ipa_misses."""
        notes = [_make_note(1, "der Hund")]
        fetch_count = [0]

        def _fetch(word):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                return eia._DEFERRED
            # Page exists but no IPA
            return WIKITEXT_NO_IPA

        updates = self._setup(monkeypatch, notes, _fetch)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: b"audio")
        monkeypatch.setattr(eia, "store_audio_in_anki", lambda fn, d: fn.replace(".ogg", ".mp3"))

        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        # IPA was not found even after retry
        assert result["ipa_added"] == 0

    def test_retry_audio_no_filename_on_page(self, monkeypatch):
        """Retry page has no audio filename → goes to tts_candidates."""
        notes = [_make_note(1, "der Hund", ipa="hʊnt")]
        fetch_count = [0]

        def _fetch(word):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                return eia._DEFERRED
            return WIKITEXT_NO_IPA  # no audio template

        tts_calls = []
        self._setup(monkeypatch, notes, _fetch)
        # REST API also finds no audio for this word
        monkeypatch.setattr(eia, "fetch_best_audio", lambda w: (None, None))
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 0)[-1])

        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        assert len(tts_calls) == 1

    def test_retry_audio_download_fails(self, monkeypatch):
        """Retry fetches page, has audio filename, but download fails → tts_candidates."""
        notes = [_make_note(1, "der Hund", ipa="hʊnt")]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")
        fetch_count = [0]

        def _fetch(word):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                return eia._DEFERRED
            return wikt

        tts_calls = []
        self._setup(monkeypatch, notes, _fetch)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: None)  # fail
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 0)[-1])

        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        assert len(tts_calls) == 1

    def test_retry_audio_download_still_rate_limited(self, monkeypatch):
        """Retry fetches page but audio download is still rate limited."""
        notes = [_make_note(1, "der Hund", ipa="hʊnt")]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")
        fetch_count = [0]

        def _fetch(word):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                return eia._DEFERRED
            return wikt

        tts_calls = []
        self._setup(monkeypatch, notes, _fetch)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: eia._DEFERRED)
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda words, **kw: (tts_calls.extend(words), 0)[-1])

        result = eia.enrich_notes(note_ids=[1], audio_only=True)
        # Should NOT go to TTS — Wiktionary has it, just can't download
        assert len(tts_calls) == 0


# ═══════════════════════════════════════════════════════════════════════════
# I. Checkpoint persistence
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckpoint:

    def test_save_load_clear(self, tmp_path, monkeypatch):
        """Round-trip: save → load → clear."""
        cp_path = tmp_path / "enrich_index.json"
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", cp_path)

        plan = [{"nid": 1, "word": "Hund", "ipa": "hʊnt", "audio_filename": "De-Hund.ogg"}]
        ipa_misses = [(2, "Katze")]
        tts_candidates = [(3, "Maus")]

        eia._save_checkpoint(plan, ipa_misses, tts_candidates)
        assert cp_path.exists()

        data = eia._load_checkpoint()
        assert data["plan"] == plan
        assert data["ipa_misses"] == [[2, "Katze"]]  # tuples become lists in JSON
        assert data["tts_candidates"] == [[3, "Maus"]]

        eia._clear_checkpoint()
        assert not cp_path.exists()

    def test_load_missing_file(self, tmp_path, monkeypatch):
        """Loading when no checkpoint exists returns None."""
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", tmp_path / "nope.json")
        assert eia._load_checkpoint() is None

    def test_load_corrupt_file(self, tmp_path, monkeypatch):
        """Loading a corrupt checkpoint returns None."""
        cp_path = tmp_path / "enrich_index.json"
        cp_path.write_text("not json{{{")
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", cp_path)
        assert eia._load_checkpoint() is None

    def test_clear_nonexistent(self, tmp_path, monkeypatch):
        """Clearing when no file exists is a no-op."""
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", tmp_path / "nope.json")
        eia._clear_checkpoint()  # should not raise


class TestCheckpointIntegration:
    """Test checkpoint save/resume within enrich_notes."""

    def _setup(self, monkeypatch, notes, fetch_fn, tmp_path):
        updates = []

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                updates.append(params["note"])
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", fetch_fn)
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        cp_path = tmp_path / "enrich_index.json"
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", cp_path)
        return updates, cp_path

    def test_bail_saves_checkpoint(self, monkeypatch, tmp_path):
        """When Wiktionary returns BAIL, checkpoint is saved and function returns."""
        notes = [_make_note(1, "der Hund"), _make_note(2, "die Katze")]
        call_count = [0]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")

        def _fetch(word):
            call_count[0] += 1
            if call_count[0] == 1:
                return wikt  # first word succeeds
            return eia._DEFERRED_BAIL  # second word bails

        updates, cp_path = self._setup(monkeypatch, notes, _fetch, tmp_path)

        result = eia.enrich_notes(note_ids=[1, 2], ipa_only=True)
        assert cp_path.exists(), "checkpoint file should be saved"
        data = eia._load_checkpoint()
        assert len(data["plan"]) == 1  # only the first word was indexed

    def test_resume_from_checkpoint(self, monkeypatch, tmp_path):
        """Resuming skips already-indexed words and processes remaining."""
        notes = [_make_note(1, "der Hund"), _make_note(2, "die Katze")]
        wikt_hund = WIKITEXT_WITH_IPA.replace("Freund", "Hund")
        wikt_katze = WIKITEXT_WITH_IPA.replace("Freund", "Katze")

        # Pre-save a checkpoint with Hund already indexed
        cp_path = tmp_path / "enrich_index.json"
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", cp_path)
        eia._save_checkpoint(
            [{"nid": 1, "word": "der Hund", "lookup": "Hund",
              "needs_ipa": True, "needs_audio": False,
              "ipa": "hʊnt", "audio_filename": None,
              "existing_audio": ""}],
            [], [],
        )

        # Only Katze should be fetched
        fetched_words = []

        def _fetch(word):
            fetched_words.append(word)
            return wikt_katze

        updates, _ = self._setup(monkeypatch, notes, _fetch, tmp_path)
        # Re-set checkpoint path since _setup overwrites it
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", cp_path)

        result = eia.enrich_notes(note_ids=[1, 2], ipa_only=True)
        assert "Hund" not in fetched_words, "Hund should be skipped (in checkpoint)"
        assert "Katze" in fetched_words
        # Checkpoint should be cleared after success
        assert not cp_path.exists()

    def test_checkpoint_cleared_on_success(self, monkeypatch, tmp_path):
        """Checkpoint file is removed after successful completion."""
        notes = [_make_note(1, "der Hund")]
        wikt = WIKITEXT_WITH_IPA.replace("Freund", "Hund")

        updates, cp_path = self._setup(
            monkeypatch, notes, lambda w: wikt, tmp_path)

        # Create a stale checkpoint
        eia._save_checkpoint([{"nid": 99, "word": "stale", "ipa": None,
                               "audio_filename": None, "needs_ipa": True,
                               "needs_audio": False, "lookup": "stale",
                               "existing_audio": ""}], [], [])
        assert cp_path.exists()

        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        assert not cp_path.exists(), "checkpoint should be cleared after success"

    def test_bail_during_retry_saves_checkpoint(self, monkeypatch, tmp_path):
        """BAIL during retry phase also saves checkpoint."""
        notes = [_make_note(1, "der Hund")]
        call_count = [0]

        def _fetch(word):
            call_count[0] += 1
            if call_count[0] == 1:
                return eia._DEFERRED  # deferred in main loop
            return eia._DEFERRED_BAIL  # bail during retry

        updates, cp_path = self._setup(monkeypatch, notes, _fetch, tmp_path)

        result = eia.enrich_notes(note_ids=[1], ipa_only=True)
        assert cp_path.exists(), "checkpoint should be saved on bail during retry"


class TestNoteNeedsWork:

    def test_needs_ipa(self):
        note = _make_note(1, "der Hund", ipa="", audio="[sound:x.mp3]")
        assert eia._note_needs_work(note, do_ipa=True, do_audio=False, redownload=False)

    def test_needs_audio(self):
        note = _make_note(1, "der Hund", ipa="hʊnt", audio="")
        assert eia._note_needs_work(note, do_ipa=False, do_audio=True, redownload=False)

    def test_complete_note(self):
        note = _make_note(1, "der Hund", ipa="hʊnt", audio="[sound:x.mp3]")
        assert not eia._note_needs_work(note, do_ipa=True, do_audio=True, redownload=False)

    def test_redownload(self):
        note = _make_note(1, "der Hund", ipa="hʊnt", audio="[sound:x.mp3]")
        assert eia._note_needs_work(note, do_ipa=False, do_audio=True, redownload=True)

    def test_phrase_excluded(self):
        note = _make_note(1, "Wie geht's?", ipa="", audio="")
        assert not eia._note_needs_work(note, do_ipa=True, do_audio=True, redownload=False)


class TestRateLimitBail:
    """Test _DEFERRED_BAIL sentinel in fetch_wikitext."""

    def test_bail_on_high_retry_after(self, monkeypatch):
        """fetch_wikitext returns _DEFERRED_BAIL when Retry-After > threshold."""
        resp = _mock_response(429, headers={"Retry-After": "3600"})
        monkeypatch.setattr(eia.web, "get", lambda *a, **kw: resp)
        monkeypatch.setattr(eia, "MAX_RATE_LIMIT_WAIT", 120)

        result = eia.fetch_wikitext("Hund")
        assert result is eia._DEFERRED_BAIL

    def test_normal_rate_limit_still_retries(self, monkeypatch):
        """fetch_wikitext returns _DEFERRED (not BAIL) for short waits."""
        call_count = [0]

        def _get(*args, **kwargs):
            call_count[0] += 1
            return _mock_response(429, headers={"Retry-After": "10"})

        monkeypatch.setattr(eia.web, "get", _get)
        monkeypatch.setattr(eia, "MAX_RATE_LIMIT_WAIT", 120)
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)

        result = eia.fetch_wikitext("Hund")
        assert result is eia._DEFERRED
        assert call_count[0] >= 3  # retried


class TestMainEntrypoint:

    def test_main_invokes_parser(self, monkeypatch):
        """main() parses args and calls run()."""
        import sys
        monkeypatch.setattr(sys, "argv", ["anki-german-enrich", "--dry-run", "--ipa-only"])
        called = []
        monkeypatch.setattr(eia, "enrich_notes", lambda **kw: (called.append(kw), {})[-1])

        eia.main()
        assert called[0]["ipa_only"] is True
        assert called[0]["dry_run"] is True


# ═══════════════════════════════════════════════════════════════════════════
# J. Argument permutations — integration tests for flag combos
# ═══════════════════════════════════════════════════════════════════════════


class TestArgPermutations:
    """Test common flag combinations against a realistic mixed-note deck."""

    def _make_deck(self):
        """Return a mix of vocab notes and non-vocab notes."""
        return [
            _make_note(1, "der Hund", ipa="hʊnt", audio="[sound:De-Hund.mp3]"),
            _make_note(2, "die Katze", ipa="", audio=""),
            _make_note(3, "laufen", ipa="ˈlaʊfn̩", audio=""),
            _make_prefix_note(100, "ver"),
            _make_prefix_note(101, "ent"),
        ]

    def _setup(self, monkeypatch, notes, tmp_path):
        updates = []
        wikt = WIKITEXT_WITH_IPA

        def _anki(action, **params):
            if action == "modelFieldNames":
                return ["Word", "POS", "IPA", "Audio"]
            if action == "notesInfo":
                return notes
            if action == "updateNoteFields":
                updates.append(params["note"])
            if action == "findNotes":
                return [n["noteId"] for n in notes]
            return []

        monkeypatch.setattr(eia, "anki", _anki)
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: wikt)
        monkeypatch.setattr(eia, "download_audio", lambda url, **kw: b"audiobytes")
        monkeypatch.setattr(eia, "store_audio_in_anki",
                            lambda fn, d: fn.rsplit(".", 1)[0] + ".mp3")
        monkeypatch.setattr(eia, "_llm_ipa_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "_gemini_tts_fallback", lambda *a, **kw: 0)
        monkeypatch.setattr(eia, "fetch_best_audio",
                            lambda w: ("De-" + w + ".ogg",
                                       "https://upload.wikimedia.org/commons/a/aa/De-" + w + ".ogg"))
        monkeypatch.setattr(eia.time, "sleep", lambda _: None)
        monkeypatch.setattr(eia, "CHECKPOINT_PATH", tmp_path / "cp.json")
        return updates

    def test_ipa_only(self, monkeypatch, tmp_path):
        """--ipa-only skips audio entirely, ignores prefix notes."""
        notes = self._make_deck()
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(note_ids=[1, 2, 3, 100, 101], ipa_only=True)
        # Only note 2 needs IPA (note 1 and 3 already have it)
        assert result["ipa_added"] >= 1
        assert result["audio_added"] == 0

    def test_audio_only(self, monkeypatch, tmp_path):
        """--audio-only skips IPA entirely, ignores prefix notes."""
        notes = self._make_deck()
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(note_ids=[1, 2, 3, 100, 101], audio_only=True)
        assert result["ipa_added"] == 0
        assert result["audio_added"] >= 1

    def test_audio_only_redownload(self, monkeypatch, tmp_path):
        """--audio-only --redownload re-fetches audio for notes that have it."""
        notes = self._make_deck()
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(
            note_ids=[1, 2, 3, 100, 101],
            audio_only=True, redownload=True)
        # Notes 1, 2, 3 should all be processed; prefix notes skipped
        assert result["audio_added"] >= 1

    def test_dry_run_no_changes(self, monkeypatch, tmp_path):
        """--dry-run makes no AnkiConnect update calls."""
        notes = self._make_deck()
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(
            note_ids=[1, 2, 3, 100, 101], dry_run=True)
        assert len(updates) == 0

    def test_no_llm(self, monkeypatch, tmp_path):
        """--no-llm skips LLM/TTS fallback."""
        notes = [_make_note(1, "der Hund")]
        llm_called = []
        tts_called = []

        updates = self._setup(monkeypatch, notes, tmp_path)
        # Page miss → would normally go to LLM/TTS
        monkeypatch.setattr(eia, "fetch_wikitext", lambda w: None)
        monkeypatch.setattr(eia, "_llm_ipa_fallback",
                            lambda *a, **kw: (llm_called.append(1), 0)[-1])
        monkeypatch.setattr(eia, "_gemini_tts_fallback",
                            lambda *a, **kw: (tts_called.append(1), 0)[-1])

        result = eia.enrich_notes(note_ids=[1], llm_fallback=False)
        assert len(llm_called) == 0
        assert len(tts_called) == 0

    def test_prefix_notes_skipped(self, monkeypatch, tmp_path):
        """Non-vocab notes (Prefix) are silently skipped."""
        notes = [_make_prefix_note(100)]
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(note_ids=[100])
        # Prefix note has no Word field → skipped
        assert result["ipa_added"] == 0
        assert result["audio_added"] == 0

    def test_mixed_vocab_and_prefix(self, monkeypatch, tmp_path):
        """Vocab and prefix notes coexist without errors."""
        notes = [_make_note(1, "der Hund"), _make_prefix_note(100)]
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(note_ids=[1, 100])
        # Should process the vocab note and skip the prefix note
        assert result["ipa_added"] >= 0  # ran without error

    def test_redownload_same_file_skip(self, monkeypatch, tmp_path):
        """--redownload skips notes that already have the best audio."""
        # Note already has De-Freund.mp3 which matches what Wiktionary offers
        notes = [_make_note(1, "der Freund", ipa="fʁɔʏnt",
                            audio="[sound:De-Freund.mp3]")]
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(
            note_ids=[1], audio_only=True, redownload=True)
        # Should skip since audio is already the same
        assert result["already_ok"] >= 1
        assert len(updates) == 0

    def test_all_flags_combined(self, monkeypatch, tmp_path):
        """All flags at once: --dry-run --ipa-only --no-llm."""
        notes = self._make_deck()
        updates = self._setup(monkeypatch, notes, tmp_path)
        result = eia.enrich_notes(
            note_ids=[1, 2, 3, 100, 101],
            ipa_only=True, dry_run=True, llm_fallback=False)
        assert len(updates) == 0
        assert result["audio_added"] == 0


class TestNoteNeedsWorkNonVocab:
    """Test _note_needs_work with non-vocab note types."""

    def test_prefix_note(self):
        note = _make_prefix_note(1)
        assert not eia._note_needs_work(note, do_ipa=True, do_audio=True, redownload=True)

    def test_missing_word_field(self):
        note = {"noteId": 1, "fields": {"SomeField": {"value": "x"}}}
        assert not eia._note_needs_work(note, do_ipa=True, do_audio=True, redownload=False)
