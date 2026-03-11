"""Tests for chapter detection and text chunking."""
import json
import textwrap
from pathlib import Path

import pytest

from anki_george_german.chapters import (
    Chapter,
    _is_chapter_marker,
    _marker_name,
    chunk_by_word_count,
    detect_chapters,
    load_chapters_file,
    parse_chapter_selection,
    parse_lines,
    resolve_chapters,
)


# ═══════════════════════════════════════════════════════════════════════════
# _is_chapter_marker
# ═══════════════════════════════════════════════════════════════════════════


class TestIsChapterMarker:

    @pytest.mark.parametrize("line", [
        "Kapitel 1",
        "KAPITEL I",
        "Kapitel eins",
        "Erstes Kapitel",
        "Zweites Kapitel",
        "Drittes Kapitel",
        "Erster Teil",
        "Zweiter Teil",
        "Teil 1",
        "Teil II",
        "I",
        "II.",
        "III",
        "IV.",
        "XII",
        "*",
        "**",
        "***",
    ])
    def test_matches_chapter_markers(self, line):
        assert _is_chapter_marker(line) is True

    @pytest.mark.parametrize("line", [
        "",
        "Ein ganz normaler Satz über das Leben.",
        "SCHACHNOVELLE",  # title, short but doesn't match patterns
        "Er spielte zäh und langsam.",
        "1922",  # year, not a chapter number
        "A" * 100,  # too long
    ])
    def test_rejects_non_markers(self, line):
        assert _is_chapter_marker(line) is False


class TestMarkerName:

    def test_kapitel(self):
        assert _marker_name("Kapitel 3") == "Kapitel 3"

    def test_asterisk_returns_empty(self):
        assert _marker_name("*") == ""
        assert _marker_name("***") == ""

    def test_strips_trailing_period(self):
        assert _marker_name("III.") == "III"

    def test_strips_trailing_colon(self):
        assert _marker_name("Kapitel 1:") == "Kapitel 1"


# ═══════════════════════════════════════════════════════════════════════════
# detect_chapters
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectChapters:

    def test_kapitel_markers(self):
        lines = [
            "Mein Buch",
            "Kapitel 1",
            "Hier ist der erste Absatz mit genug Wörtern zum Testen.",
            "Und noch ein Satz dazu.",
            "Kapitel 2",
            "Hier ist der zweite Absatz.",
            "Mit noch mehr Text darin.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert len(chapters) == 2
        assert chapters[0].name == "Kapitel 1"
        assert chapters[1].name == "Kapitel 2"
        assert "erste" in chapters[0].text
        assert "zweite" in chapters[1].text

    def test_roman_numeral_markers(self):
        lines = [
            "I",
            "Text of part one with enough words.",
            "More text here.",
            "II",
            "Text of part two.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert len(chapters) == 2
        assert chapters[0].name == "I"
        assert chapters[1].name == "II"

    def test_asterisk_section_break(self):
        """Single * creates two chapters from surrounding content."""
        # Need >50 words in preamble for it to be included as a chapter
        long_para = " ".join(["Wort"] * 20)
        lines = [
            "TITLE",
            f"First part {long_para} with enough words.",
            f"More text {long_para} in the first section.",
            "*",
            f"Second part {long_para} begins here.",
            "More of the second part to read.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert len(chapters) == 2
        # Preamble before * becomes chapter 1
        assert chapters[0].name == "1"
        assert "First part" in chapters[0].text
        # Content after * becomes chapter 2
        assert chapters[1].name == "2"
        assert "Second part" in chapters[1].text

    def test_no_markers_returns_none(self):
        lines = [
            "Just a normal paragraph.",
            "Another normal paragraph.",
            "Nothing special here.",
        ]
        assert detect_chapters(lines) is None

    def test_single_marker_returns_none(self):
        """A single marker without enough structure isn't useful."""
        lines = [
            "Kapitel 1",
            "Some text.",
        ]
        assert detect_chapters(lines) is None

    def test_title_line_not_treated_as_marker(self):
        """Short title on first line shouldn't be a chapter marker."""
        lines = [
            "SCHACHNOVELLE",
            "Kapitel 1",
            "Text of chapter one.",
            "Kapitel 2",
            "Text of chapter two.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        # Title should not create its own chapter
        assert chapters[0].name == "Kapitel 1"

    def test_word_count_calculated(self):
        lines = [
            "Kapitel 1",
            "Eins zwei drei vier fünf.",
            "Kapitel 2",
            "Sechs sieben acht.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert chapters[0].word_count == 5
        assert chapters[1].word_count == 3

    def test_paragraph_numbers_correct(self):
        lines = [
            "Title",
            "Kapitel 1",       # line index 1 → para 2
            "First para.",     # line index 2 → para 3
            "Second para.",    # line index 3 → para 4
            "Kapitel 2",       # line index 4 → para 5
            "Third para.",     # line index 5 → para 6
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert chapters[0].start_para == 3  # content starts after "Kapitel 1"
        assert chapters[0].end_para == 4    # up to line before "Kapitel 2"
        assert chapters[1].start_para == 6  # content starts after "Kapitel 2"
        assert chapters[1].end_para == 6    # last line

    def test_preamble_included_if_substantial(self):
        """Text before the first chapter marker is included if >50 words."""
        preamble = " ".join(["Wort"] * 60)  # 60 words
        lines = [
            preamble,
            "Kapitel 1",
            "Some chapter text here.",
            "Kapitel 2",
            "More chapter text here.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert len(chapters) == 3
        assert chapters[0].name == "1"  # preamble
        assert chapters[0].word_count == 60

    def test_preamble_excluded_if_short(self):
        """Short text before first chapter marker is skipped."""
        lines = [
            "Vorwort",  # too short (1 word)
            "Kapitel 1",
            "Some chapter text here.",
            "Kapitel 2",
            "More chapter text here.",
        ]
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert len(chapters) == 2
        assert chapters[0].name == "Kapitel 1"

    def test_empty_chapter_skipped(self):
        """Consecutive markers without content don't create empty chapters."""
        lines = [
            "Kapitel 1",
            "Kapitel 2",  # no content for chapter 1
            "Some text here.",
        ]
        chapters = detect_chapters(lines)
        # Only one chapter has content
        assert chapters is None or len(chapters) < 2


# ═══════════════════════════════════════════════════════════════════════════
# chunk_by_word_count
# ═══════════════════════════════════════════════════════════════════════════


class TestChunkByWordCount:

    def test_basic_chunking(self):
        # 5 lines of 10 words each = 50 words total
        lines = [" ".join(["wort"] * 10) for _ in range(5)]
        chunks = chunk_by_word_count(lines, target_words=20)
        # 20-word target: first 2 lines = 20 words → chunk 1
        # next 2 lines = 20 words → chunk 2
        # last line = 10 words → chunk 3
        assert len(chunks) == 3
        assert chunks[0].word_count == 20
        assert chunks[1].word_count == 20
        assert chunks[2].word_count == 10

    def test_single_large_paragraph(self):
        """A single paragraph exceeding target gets its own chunk."""
        lines = [" ".join(["wort"] * 50)]  # 50 words in one line
        chunks = chunk_by_word_count(lines, target_words=20)
        assert len(chunks) == 1
        assert chunks[0].word_count == 50

    def test_names_are_sequential(self):
        lines = [" ".join(["w"] * 10) for _ in range(3)]
        chunks = chunk_by_word_count(lines, target_words=10)
        assert [ch.name for ch in chunks] == ["1", "2", "3"]

    def test_paragraph_numbers_correct(self):
        lines = [" ".join(["w"] * 10) for _ in range(4)]
        chunks = chunk_by_word_count(lines, target_words=20)
        # Chunk 1: lines 0-1 → paras 1-2
        assert chunks[0].start_para == 1
        assert chunks[0].end_para == 2
        # Chunk 2: lines 2-3 → paras 3-4
        assert chunks[1].start_para == 3
        assert chunks[1].end_para == 4

    def test_empty_input(self):
        assert chunk_by_word_count([], target_words=100) == []

    def test_all_in_one_chunk(self):
        lines = ["short line"] * 3
        chunks = chunk_by_word_count(lines, target_words=10000)
        assert len(chunks) == 1
        assert chunks[0].start_para == 1
        assert chunks[0].end_para == 3

    def test_respects_paragraph_boundaries(self):
        """Chunks never split mid-paragraph."""
        lines = [
            " ".join(["w"] * 15),  # 15 words
            " ".join(["w"] * 15),  # 15+15=30 >= 20 → chunk ends here
            " ".join(["w"] * 5),   # 5 words → final chunk
        ]
        chunks = chunk_by_word_count(lines, target_words=20)
        # First chunk includes both lines (30 words) because the target is
        # only checked after adding each line
        assert chunks[0].word_count == 30
        assert chunks[1].word_count == 5


# ═══════════════════════════════════════════════════════════════════════════
# load_chapters_file
# ═══════════════════════════════════════════════════════════════════════════


class TestLoadChaptersFile:

    def test_basic_load(self, tmp_path):
        chapters_json = [
            {"name": "intro", "start": 1, "end": 3},
            {"name": "main", "start": 4, "end": 5},
        ]
        path = tmp_path / "chapters.json"
        path.write_text(json.dumps(chapters_json))

        lines = ["Line one.", "Line two.", "Line three.", "Line four.", "Line five."]
        chapters = load_chapters_file(path, lines)

        assert len(chapters) == 2
        assert chapters[0].name == "intro"
        assert chapters[0].start_para == 1
        assert chapters[0].end_para == 3
        assert "Line one" in chapters[0].text
        assert "Line three" in chapters[0].text
        assert chapters[1].name == "main"
        assert "Line four" in chapters[1].text


# ═══════════════════════════════════════════════════════════════════════════
# resolve_chapters
# ═══════════════════════════════════════════════════════════════════════════


class TestResolveChapters:

    def test_manual_file_takes_priority(self, tmp_path):
        chapters_json = [
            {"name": "A", "start": 1, "end": 2},
            {"name": "B", "start": 3, "end": 4},
        ]
        path = tmp_path / "ch.json"
        path.write_text(json.dumps(chapters_json))

        lines = [
            "Kapitel 1",  # would be detected, but manual overrides
            "Text one.",
            "Kapitel 2",
            "Text two.",
        ]
        chapters = resolve_chapters(lines, chapters_file=path)
        assert chapters[0].name == "A"

    def test_auto_detect_when_markers_present(self):
        lines = [
            "Kapitel 1",
            "First chapter text here.",
            "Kapitel 2",
            "Second chapter text here.",
        ]
        chapters = resolve_chapters(lines)
        assert len(chapters) == 2
        assert chapters[0].name == "Kapitel 1"

    def test_fallback_to_word_count(self):
        """No markers → falls back to word-count chunking."""
        lines = [" ".join(["wort"] * 100) for _ in range(5)]  # 500 words total
        chapters = resolve_chapters(lines)
        # Default: 20 min × 100 wpm = 2000 words → all in one chunk
        assert len(chapters) == 1

    def test_explicit_chunk_minutes(self):
        """--chunk-minutes forces word-count chunking even with markers."""
        lines = [
            "Kapitel 1",
            " ".join(["wort"] * 500),
            "Kapitel 2",
            " ".join(["wort"] * 500),
        ]
        # With chunk_minutes=5, target = 500 words
        chapters = resolve_chapters(lines, chunk_minutes=5, reading_speed=100)
        # Should use word-count chunking, not chapter detection
        assert all("Kapitel" not in ch.name for ch in chapters)

    def test_custom_reading_speed(self):
        lines = [" ".join(["w"] * 100) for _ in range(10)]  # 1000 words
        # 10 min × 50 wpm = 500 word target → 2 chunks
        chapters = resolve_chapters(lines, chunk_minutes=10, reading_speed=50)
        assert len(chapters) == 2


# ═══════════════════════════════════════════════════════════════════════════
# parse_chapter_selection
# ═══════════════════════════════════════════════════════════════════════════


class TestParseChapterSelection:

    def test_single_number(self):
        assert parse_chapter_selection("3") == {"3"}

    def test_range(self):
        assert parse_chapter_selection("1-3") == {"1", "2", "3"}

    def test_comma_list(self):
        assert parse_chapter_selection("1,3,5") == {"1", "3", "5"}

    def test_mixed(self):
        assert parse_chapter_selection("1-3,7") == {"1", "2", "3", "7"}

    def test_named_chapter(self):
        assert parse_chapter_selection("Kapitel 1") == {"Kapitel 1"}


# ═══════════════════════════════════════════════════════════════════════════
# parse_lines
# ═══════════════════════════════════════════════════════════════════════════


class TestParseLines:

    def test_strips_blank_lines(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Line one.\n\nLine two.\n\n\nLine three.\n")
        lines = parse_lines(f)
        assert lines == ["Line one.", "Line two.", "Line three."]

    def test_preserves_content(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("  Indented line.  \nNormal line.\n")
        lines = parse_lines(f)
        assert len(lines) == 2
        assert lines[0] == "  Indented line.  "


# ═══════════════════════════════════════════════════════════════════════════
# Chapter.kind and Chapter.tag
# ═══════════════════════════════════════════════════════════════════════════


class TestChapterKindAndTag:

    def test_detected_chapters_have_chapter_kind(self):
        lines = [
            "Kapitel 1",
            "First chapter text.",
            "Kapitel 2",
            "Second chapter text.",
        ]
        chapters = detect_chapters(lines)
        assert all(ch.kind == "chapter" for ch in chapters)

    def test_word_chunks_have_chunk_kind(self):
        lines = [" ".join(["w"] * 100) for _ in range(5)]
        chunks = chunk_by_word_count(lines, target_words=200)
        assert all(ch.kind == "chunk" for ch in chunks)

    def test_chapter_tag_property(self):
        lines = [
            "Kapitel 1",
            "First chapter text.",
            "Kapitel 2",
            "Second chapter text.",
        ]
        chapters = detect_chapters(lines)
        assert chapters[0].tag == "chapter::Kapitel 1"
        assert chapters[1].tag == "chapter::Kapitel 2"

    def test_chunk_tag_property(self):
        lines = [" ".join(["w"] * 100) for _ in range(4)]
        chunks = chunk_by_word_count(lines, target_words=200)
        assert chunks[0].tag == "chunk::1"
        assert chunks[1].tag == "chunk::2"

    def test_manual_chapters_have_chapter_kind(self, tmp_path):
        chapters_json = [
            {"name": "intro", "start": 1, "end": 2},
            {"name": "main", "start": 3, "end": 4},
        ]
        path = tmp_path / "ch.json"
        path.write_text(json.dumps(chapters_json))
        lines = ["Line 1.", "Line 2.", "Line 3.", "Line 4."]
        chapters = load_chapters_file(path, lines)
        assert all(ch.kind == "chapter" for ch in chapters)
        assert chapters[0].tag == "chapter::intro"

    def test_resolve_auto_detect_gives_chapter_kind(self):
        lines = [
            "Kapitel 1",
            "First chapter text.",
            "Kapitel 2",
            "Second chapter text.",
        ]
        chapters = resolve_chapters(lines)
        assert all(ch.kind == "chapter" for ch in chapters)

    def test_resolve_fallback_gives_chunk_kind(self):
        lines = [" ".join(["w"] * 100) for _ in range(5)]
        chapters = resolve_chapters(lines)
        assert all(ch.kind == "chunk" for ch in chapters)

    def test_resolve_explicit_chunk_minutes_gives_chunk_kind(self):
        """Even with chapter markers, --chunk-minutes forces chunk kind."""
        lines = [
            "Kapitel 1",
            " ".join(["w"] * 500),
            "Kapitel 2",
            " ".join(["w"] * 500),
        ]
        chapters = resolve_chapters(lines, chunk_minutes=5, reading_speed=100)
        assert all(ch.kind == "chunk" for ch in chapters)




class TestSchachnovelleLike:
    """Test with a structure similar to Stefan Zweig's Schachnovelle."""

    def test_asterisk_break_creates_two_parts(self):
        lines = (
            ["SCHACHNOVELLE"]
            + [f"Paragraph {i} with enough words for content." for i in range(1, 20)]
            + ["*"]
            + [f"Second half paragraph {i} with content." for i in range(1, 15)]
        )
        chapters = detect_chapters(lines)
        assert chapters is not None
        assert len(chapters) == 2

    def test_no_markers_uses_word_chunking(self):
        """A book with no structural markers falls back to word-count chunks."""
        # ~200 words per line, 10 lines = 2000 words
        lines = [" ".join(["wort"] * 200) for _ in range(10)]
        chapters = resolve_chapters(lines)
        # At default 2000 words/chunk, should get 1 chunk
        assert len(chapters) == 1
        assert chapters[0].word_count == 2000

    def test_word_chunking_with_short_target(self):
        """Force small chunks to simulate ~5 minute reading sessions."""
        # 10 lines of 100 words each = 1000 total
        lines = [" ".join(["wort"] * 100) for _ in range(10)]
        # 5 min × 100 wpm = 500 words per chunk → 2 chunks
        chapters = resolve_chapters(lines, chunk_minutes=5, reading_speed=100)
        assert len(chapters) == 2
        assert chapters[0].word_count == 500
        assert chapters[1].word_count == 500
