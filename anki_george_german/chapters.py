"""Chapter detection and text chunking for book processing.

Splits a book into named sections for per-section vocabulary extraction.
Two kinds of section:

- **chapter**: the author's own structural divisions (Kapitel, Teil, *).
  Respected as-is regardless of length. Tagged as ``chapter::<name>``.
- **chunk**: synthetic reading-sized divisions based on word count.
  Used when the text has no chapter markers or when explicitly requested
  via ``--chunk-minutes``. Tagged as ``chunk::<name>``.

Three resolution strategies (in priority order):

1. Manual override via ``--chapters-file`` (JSON) → kind = ``"chapter"``
2. Auto-detection of chapter/section markers → kind = ``"chapter"``
3. Word-count fallback (~N-minute reading chunks) → kind = ``"chunk"``
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_READING_SPEED = 100  # words per minute for an intermediate learner
DEFAULT_CHUNK_MINUTES = 20


@dataclass
class Chapter:
    """A chapter or reading chunk from a book.

    kind is "chapter" for author-defined divisions or "chunk" for
    synthetic word-count-based splits. The tag prefix follows the kind:
    chapter::Kapitel 1 vs chunk::3.
    """

    name: str
    kind: str  # "chapter" or "chunk"
    start_para: int  # 1-based inclusive paragraph number
    end_para: int  # 1-based inclusive paragraph number
    text: str
    word_count: int

    @property
    def tag(self):
        """Anki tag for this section, e.g. 'chapter::Kapitel 1' or 'chunk::3'."""
        return f"{self.kind}::{self.name}"


# ── Chapter marker detection ────────────────────────────────────────────────

_CHAPTER_PATTERNS = [
    # "Kapitel 1", "KAPITEL I"
    re.compile(r"^Kapitel\s+\S+", re.IGNORECASE),
    # "Erstes Kapitel", "Zweites Kapitel", etc.
    re.compile(
        r"^(?:Erst|Zweit|Dritt|Viert|Fünft|Sechst|Siebt|Acht|Neunt|Zehnt)"
        r"\w*\s+Kapitel",
        re.IGNORECASE,
    ),
    # "Erster Teil", "Zweiter Teil"
    re.compile(
        r"^(?:Erst|Zweit|Dritt|Viert|Fünft|Sechst|Siebt|Acht|Neunt|Zehnt)"
        r"\w*\s+Teil",
        re.IGNORECASE,
    ),
    # "Teil 1", "Teil I"
    re.compile(r"^Teil\s+\S+", re.IGNORECASE),
    # Roman numerals alone: I, II, III, IV, ... (with optional period)
    re.compile(r"^[IVXLC]+\.?$"),
    # Asterisk section breaks: *, **, ***
    re.compile(r"^\*{1,3}$"),
]


def _is_chapter_marker(line):
    """Check if a line looks like a chapter heading or section break."""
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    return any(p.match(stripped) for p in _CHAPTER_PATTERNS)


def _marker_name(line):
    """Extract a display name from a chapter marker line.

    Returns empty string for asterisk breaks (named sequentially later).
    """
    stripped = line.strip().rstrip(".:")
    if re.match(r"^\*{1,3}$", stripped):
        return ""
    return stripped


# ── Core detection ───────────────────────────────────────────────────────────


def parse_lines(filepath):
    """Read a text file and return non-blank lines."""
    path = Path(filepath)
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def detect_chapters(lines):
    """Detect chapter/section boundaries from structural markers.

    Returns list of Chapters if markers found, None otherwise.
    Requires at least 2 resulting chapters to count as a successful detection.
    """
    markers = []
    for i, line in enumerate(lines):
        if _is_chapter_marker(line):
            markers.append((i, _marker_name(line)))

    if not markers:
        return None

    # A short first line that doesn't match chapter patterns is likely the
    # book title — drop it from markers.
    if markers[0][0] == 0:
        first = lines[0].strip()
        if not any(p.match(first) for p in _CHAPTER_PATTERNS):
            markers = markers[1:]

    if not markers:
        return None

    # Build chapters: each marker starts a chapter, content runs to next marker
    chapters = []
    section_num = 0

    # Include preamble (text before first marker) if substantial
    first_marker_idx = markers[0][0]
    if first_marker_idx > 0:
        pre_lines = lines[:first_marker_idx]
        # Filter out title-like lines (very short)
        content = [l for l in pre_lines if len(l.split()) > 3]
        if content:
            text = "\n".join(content)
            wc = len(text.split())
            if wc > 50:
                section_num += 1
                chapters.append(Chapter(
                    name=str(section_num),
                    kind="chapter",
                    start_para=1,
                    end_para=first_marker_idx,
                    text=text,
                    word_count=wc,
                ))
    for j, (marker_idx, name) in enumerate(markers):
        content_start = marker_idx + 1
        content_end = markers[j + 1][0] if j + 1 < len(markers) else len(lines)

        content_lines = lines[content_start:content_end]
        if not content_lines:
            continue

        section_num += 1
        if not name:
            name = str(section_num)

        text = "\n".join(content_lines)
        chapters.append(Chapter(
            name=name,
            kind="chapter",
            start_para=content_start + 1,  # 1-based
            end_para=content_end,
            text=text,
            word_count=len(text.split()),
        ))

    return chapters if len(chapters) >= 2 else None


# ── Word-count chunking ─────────────────────────────────────────────────────


def chunk_by_word_count(lines, target_words):
    """Split lines into chunks of approximately target_words each.

    Splits only at paragraph (line) boundaries, never mid-paragraph.
    Each chunk ends at the first paragraph that causes the accumulated
    word count to reach or exceed the target.
    """
    if not lines:
        return []

    chunks = []
    current_lines = []
    current_words = 0
    chunk_start = 1  # 1-based paragraph number

    for i, line in enumerate(lines):
        line_words = len(line.split())
        current_lines.append(line)
        current_words += line_words

        if current_words >= target_words:
            text = "\n".join(current_lines)
            chunks.append(Chapter(
                name=str(len(chunks) + 1),
                kind="chunk",
                start_para=chunk_start,
                end_para=i + 1,  # 1-based
                text=text,
                word_count=current_words,
            ))
            current_lines = []
            current_words = 0
            chunk_start = i + 2  # 1-based, next line

    # Final chunk (may be smaller than target)
    if current_lines:
        text = "\n".join(current_lines)
        chunks.append(Chapter(
            name=str(len(chunks) + 1),
            kind="chunk",
            start_para=chunk_start,
            end_para=chunk_start + len(current_lines) - 1,
            text=text,
            word_count=current_words,
        ))

    return chunks


# ── Manual chapters file ────────────────────────────────────────────────────


def load_chapters_file(path, lines):
    """Load chapter definitions from a JSON file.

    Expected format:
    [
        {"name": "1", "start": 1, "end": 64},
        {"name": "2", "start": 66, "end": 130}
    ]

    Paragraph numbers are 1-based and refer to non-blank lines.
    """
    with open(path, encoding="utf-8") as f:
        defs = json.load(f)

    chapters = []
    for d in defs:
        start = d["start"] - 1  # to 0-based index
        end = d["end"]  # 1-based end → exclusive slice
        chapter_lines = lines[start:end]
        text = "\n".join(chapter_lines)
        chapters.append(Chapter(
            name=str(d["name"]),
            kind="chapter",
            start_para=d["start"],
            end_para=d["end"],
            text=text,
            word_count=len(text.split()),
        ))

    return chapters


# ── Main entry point ────────────────────────────────────────────────────────


def resolve_chapters(lines, chapters_file=None, chunk_minutes=None,
                     reading_speed=DEFAULT_READING_SPEED):
    """Determine chapter/chunk boundaries for a book.

    Priority:
    1. Manual chapters file (if provided)
    2. Auto-detected chapter markers
    3. Word-count chunking (default ~20 min at 100 wpm)
    """
    if chapters_file:
        return load_chapters_file(chapters_file, lines)

    if chunk_minutes is None:
        # Try auto-detection first
        chapters = detect_chapters(lines)
        if chapters:
            return chapters
        # Fall back to word-count chunking
        chunk_minutes = DEFAULT_CHUNK_MINUTES

    target_words = chunk_minutes * reading_speed
    return chunk_by_word_count(lines, target_words)


def parse_chapter_selection(spec):
    """Parse a chapter selection spec like '3', '1-5', or '1,3,5'.

    Returns a set of chapter name strings.
    """
    names = set()
    for part in spec.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)-(\d+)$", part)
        if m:
            for i in range(int(m.group(1)), int(m.group(2)) + 1):
                names.add(str(i))
        else:
            names.add(part)
    return names
