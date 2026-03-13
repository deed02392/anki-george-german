#!/usr/bin/env python3
"""Enrich German vocabulary Anki notes with IPA and audio from Wiktionary.

Fetches IPA transcriptions and audio files from de.wiktionary.org for notes
in "George's German Vocabulary" that are missing them. Audio files are
downloaded from Wikimedia Commons and stored in Anki's media folder.

Usage:
    uv run python tools/enrich_ipa_audio.py              # IPA + audio
    uv run python tools/enrich_ipa_audio.py --ipa-only   # just IPA (fast)
    uv run python tools/enrich_ipa_audio.py --audio-only  # just audio downloads
    uv run python tools/enrich_ipa_audio.py --dry-run     # preview without changes
"""
import argparse
import base64
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time

import requests

from ._anki import anki, DECK, MODEL, ARTICLES
from ._llm import get_floodgate_token, call_llm_with_retry

WIKT_API = "https://de.wiktionary.org/w/api.php"

# Wikimedia requires a descriptive User-Agent (https://w.wiki/4wJS)
web = requests.Session()
web.headers["User-Agent"] = "anki-george-german/1.0 (German vocab enrichment script)"


# ── Word extraction ──────────────────────────────────────────────────────────

def extract_lookup_word(word_field):
    """Strip articles and determine if a word is a single-word lookup candidate."""
    clean = word_field.strip()
    for article in ARTICLES:
        prefix = article + " "
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
            break
    clean = clean.strip()
    is_phrase = any(c in clean for c in [" ", "?", "!", "…"]) or "..." in clean
    return clean, is_phrase


# ── Wiktionary fetching ──────────────────────────────────────────────────────

def fetch_wikitext(word):
    """Fetch the wikitext for a German Wiktionary page."""
    candidates = [word]
    if word.lower() != word:
        candidates.append(word.lower())
    for attempt in candidates:
        params = {"action": "parse", "page": attempt, "format": "json", "prop": "wikitext"}
        try:
            resp = web.get(WIKT_API, params=params, timeout=10)
            data = resp.json()
            if "parse" in data:
                wikitext = data["parse"]["wikitext"]["*"]
                if "{{Sprache|Deutsch}}" in wikitext:
                    return wikitext
        except (KeyError, requests.RequestException):
            pass
    return None


def extract_german_section(wikitext):
    """Extract only the German language section from a Wiktionary page."""
    lines = wikitext.split("\n")
    in_german = False
    german_lines = []
    for line in lines:
        if "{{Sprache|Deutsch}}" in line:
            in_german = True
            continue
        elif in_german and re.match(r"^==\s", line) and "{{Sprache|" in line:
            break
        if in_german:
            german_lines.append(line)
    return "\n".join(german_lines) if german_lines else wikitext


def extract_aussprache_block(section):
    """Extract the {{Aussprache}} block from a German section."""
    lines = section.split("\n")
    in_block = False
    block_lines = []
    for line in lines:
        if "{{Aussprache}}" in line:
            in_block = True
            continue
        elif in_block and line.startswith("{{") and not line.startswith(":"):
            break
        if in_block:
            block_lines.append(line)
    return "\n".join(block_lines) if block_lines else section


def extract_ipa(wikitext):
    """Extract the first IPA transcription from the German section."""
    section = extract_german_section(wikitext)
    pron = extract_aussprache_block(section)
    m = re.search(r"\{\{IPA\}\}\s*\{\{Lautschrift\|([^}]+)\}\}", pron)
    if m:
        return m.group(1)
    m = re.search(r"\{\{Lautschrift\|([^}]+)\}\}", pron)
    return m.group(1) if m else None


def extract_audio_filename(wikitext):
    """Extract the first German audio filename from wikitext."""
    section = extract_german_section(wikitext)
    pron = extract_aussprache_block(section)
    m = re.search(r"\{\{Audio\|([^|}]+\.ogg)", pron)
    return m.group(1) if m else None


# ── Audio download ───────────────────────────────────────────────────────────

def commons_url_from_filename(filename):
    """Compute the direct Wikimedia Commons URL using MD5 hash path."""
    md5 = hashlib.md5(filename.encode()).hexdigest()
    return (f"https://upload.wikimedia.org/wikipedia/commons"
            f"/{md5[0]}/{md5[:2]}/{requests.utils.quote(filename)}")


def download_audio(url, retries=3):
    """Download audio file. Retries on 429 respecting Retry-After header."""
    for attempt in range(retries):
        try:
            resp = web.get(url, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                wait = max(wait, 10)
                print(f"    (rate limited, waiting {wait}s...)")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            return None
    return None


def store_audio_in_anki(filename, data):
    """Convert ogg to mp3 and store in Anki's media folder via AnkiConnect.

    Returns the stored filename (*.mp3).
    """
    mp3_name = filename.rsplit(".", 1)[0] + ".mp3"
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_ogg:
        tmp_ogg.write(data)
        tmp_ogg_path = tmp_ogg.name
    tmp_mp3_path = tmp_ogg_path.rsplit(".", 1)[0] + ".mp3"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", tmp_ogg_path, "-codec:a", "libmp3lame",
             "-q:a", "2", tmp_mp3_path, "-y"],
            capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed for {filename}")
        with open(tmp_mp3_path, "rb") as f:
            mp3_b64 = base64.b64encode(f.read()).decode("ascii")
        anki("storeMediaFile", filename=mp3_name, data=mp3_b64)
    finally:
        for p in (tmp_ogg_path, tmp_mp3_path):
            if os.path.exists(p):
                os.unlink(p)
    return mp3_name


def store_pcm_audio_in_anki(mp3_name, pcm_data):
    """Convert raw PCM (s16le, 24kHz, mono) to mp3 and store in Anki.

    Returns the stored filename (*.mp3).
    """
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as tmp_pcm:
        tmp_pcm.write(pcm_data)
        tmp_pcm_path = tmp_pcm.name
    tmp_mp3_path = tmp_pcm_path.rsplit(".", 1)[0] + ".mp3"
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "s16le", "-ar", "24000", "-ac", "1",
             "-i", tmp_pcm_path, "-codec:a", "libmp3lame",
             "-q:a", "2", tmp_mp3_path, "-y"],
            capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg PCM→mp3 failed for {mp3_name}")
        with open(tmp_mp3_path, "rb") as f:
            mp3_b64 = base64.b64encode(f.read()).decode("ascii")
        anki("storeMediaFile", filename=mp3_name, data=mp3_b64)
    finally:
        for p in (tmp_pcm_path, tmp_mp3_path):
            if os.path.exists(p):
                os.unlink(p)
    return mp3_name


# ── LLM fallback for IPA ────────────────────────────────────────────────────

def _llm_ipa_fallback(missing_words, dry_run=False):
    """Ask the LLM to generate IPA for words Wiktionary couldn't provide.

    Args:
        missing_words: list of (note_id, word_field) tuples.
        dry_run: Preview without applying.

    Returns:
        Number of notes updated.
    """
    if not missing_words:
        return 0

    words_block = "\n".join(
        f"{i}. {w}" for i, (_, w) in enumerate(missing_words, 1)
    )
    prompt = f"""\
Provide the IPA (International Phonetic Alphabet) pronunciation for each \
German word below. Use standard High German (Hochdeutsch) pronunciation.

Return ONLY a JSON array (no markdown). Each element:
{{
  "word": "<the word as given>",
  "ipa": "<IPA transcription without brackets>"
}}

Rules:
- Use standard IPA symbols for German
- Do NOT include square brackets — just the transcription
- For nouns with articles (der/die/das): only transcribe the NOUN, not the article
- For compound words, provide the full compound pronunciation
- For phrases, provide the pronunciation of the key words
- If unsure, provide the most standard/common pronunciation

Words:
{words_block}"""

    print(f"\n  LLM fallback for {len(missing_words)} words...")
    token = get_floodgate_token()
    result = call_llm_with_retry(
        [{"role": "user", "content": prompt}], token, max_tokens=4096,
    )
    if not result:
        print("  LLM IPA generation failed.")
        return 0

    ipa_by_word = {}
    for item in result:
        word = item.get("word", "")
        ipa = item.get("ipa", "").strip()
        if word and ipa:
            ipa_by_word[word] = ipa

    updated = 0
    for nid, word in missing_words:
        ipa = ipa_by_word.get(word, "")
        if not ipa:
            continue
        prefix = "[dry-run] " if dry_run else "  "
        print(f"{prefix}{word:<30} IPA={ipa} (LLM)")
        if not dry_run:
            anki("updateNoteFields", note={"id": nid, "fields": {"IPA": ipa}})
        updated += 1

    return updated


# ── Gemini TTS fallback for audio ─────────────────────────────────────────────

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_VOICE = "Iapetus"
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models"
    f"/{GEMINI_TTS_MODEL}:generateContent"
)


def _gemini_tts_single(word, api_key):
    """Generate TTS audio for a single word via Gemini API.

    Returns raw PCM bytes (s16le, 24kHz, mono) or None on failure.
    """
    payload = {
        "contents": [{"role": "user", "parts": [{"text":
            "Say in clear, standard German (Hochdeutsch) pronunciation, "
            f"as a dictionary recording: {word}"
        }]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}
                },
            },
        },
    }
    try:
        resp = requests.post(
            GEMINI_API_URL, params={"key": api_key},
            json=payload, timeout=30,
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 30))
            print(f"    (TTS rate limited, waiting {wait}s...)")
            time.sleep(wait)
            resp = requests.post(
                GEMINI_API_URL, params={"key": api_key},
                json=payload, timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return base64.b64decode(audio_b64)
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"    TTS error for '{word}': {e}")
        return None


def _gemini_tts_fallback(audio_misses, dry_run=False):
    """Generate TTS audio via Gemini for words missing Wiktionary audio.

    Args:
        audio_misses: list of (note_id, word_field) tuples.
        dry_run: Preview without applying.

    Returns:
        Number of notes updated.
    """
    if not audio_misses:
        return 0

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("\n  Skipping TTS fallback (GEMINI_API_KEY not set)")
        return 0

    print(f"\n  TTS fallback for {len(audio_misses)} words...")
    updated = 0

    for nid, word_field in audio_misses:
        lookup, _ = extract_lookup_word(word_field)
        prefix = "[dry-run] " if dry_run else "  "

        if dry_run:
            print(f"{prefix}{word_field:<30} audio=TTS (would generate)")
            updated += 1
            continue

        # Send the full word field (e.g. "das Boot") so the article
        # provides German context for the TTS model.  For non-nouns
        # the bare word is unambiguously German.
        pcm_data = _gemini_tts_single(word_field, api_key)
        if not pcm_data:
            print(f"  {word_field:<30} audio=TTS fail")
            continue

        mp3_name = f"tts_{lookup}.mp3"
        store_pcm_audio_in_anki(mp3_name, pcm_data)
        anki("updateNoteFields", note={
            "id": nid,
            "fields": {"Audio": f"[sound:{mp3_name}]"},
        })
        print(f"  {word_field:<30} audio=TTS ok")
        updated += 1
        time.sleep(1)  # gentle rate limiting

    return updated


# ── Core enrichment function (importable) ────────────────────────────────────

def enrich_notes(note_ids=None, *, ipa_only=False, audio_only=False,
                 audio_delay=5.0, dry_run=False, llm_fallback=True):
    """Enrich notes with IPA and/or audio from Wiktionary.

    Args:
        note_ids: List of note IDs to enrich. If None, finds all notes
                  missing IPA/audio in the deck.
        ipa_only: Only fetch IPA (skip audio).
        audio_only: Only fetch audio (skip IPA).
        audio_delay: Seconds between audio downloads.
        dry_run: Preview without applying changes.
        llm_fallback: Use LLM to generate IPA for Wiktionary misses.

    Returns:
        Dict with counts: ipa_added, audio_added, skipped_phrase, not_found.
    """
    do_ipa = not audio_only
    do_audio = not ipa_only

    # Ensure the Audio field exists
    if do_audio and not dry_run:
        fields = anki("modelFieldNames", modelName=MODEL)
        if "Audio" not in fields:
            ipa_idx = fields.index("IPA") if "IPA" in fields else len(fields) - 1
            anki("modelFieldAdd", modelName=MODEL,
                 fieldName="Audio", index=ipa_idx + 1)
            print("Added 'Audio' field to note type (after IPA).")

    # Find notes needing enrichment
    if note_ids is not None:
        all_ids = sorted(set(note_ids))
    else:
        all_ids = set()
        if do_ipa:
            all_ids |= set(anki("findNotes", query=f'\"deck:{DECK}\" IPA:'))
        if do_audio:
            all_ids |= set(anki("findNotes", query=f'\"deck:{DECK}\" Audio:'))
        all_ids = sorted(all_ids)

    if not all_ids:
        print("Nothing to enrich.")
        return {"ipa_added": 0, "audio_added": 0, "skipped_phrase": 0, "not_found": 0}

    notes = anki("notesInfo", notes=all_ids)

    mode = "IPA" if ipa_only else ("audio" if audio_only else "IPA + audio")
    print(f"Enrichment mode: {mode} ({len(notes)} notes)")

    stats = {"ipa_added": 0, "ipa_miss": 0, "audio_added": 0, "audio_miss": 0,
             "skipped_phrase": 0, "no_page": 0, "already_ok": 0,
             "ipa_llm": 0, "audio_tts": 0}
    ipa_misses = []    # (note_id, word_field) for LLM fallback
    audio_misses = []  # (note_id, word_field) for TTS fallback

    for note in notes:
        nid = note["noteId"]
        word_field = note["fields"]["Word"]["value"]
        has_ipa = bool(note["fields"]["IPA"]["value"])
        has_audio = bool(note["fields"].get("Audio", {}).get("value", ""))

        needs_ipa = do_ipa and not has_ipa
        needs_audio = do_audio and not has_audio

        if not needs_ipa and not needs_audio:
            stats["already_ok"] += 1
            continue

        lookup, is_phrase = extract_lookup_word(word_field)
        if is_phrase:
            print(f"  SKIP (phrase): {word_field}")
            stats["skipped_phrase"] += 1
            continue

        # Fetch from Wiktionary
        wikitext = fetch_wikitext(lookup)
        if not wikitext:
            print(f"  MISS: {word_field} -> no Wiktionary page for '{lookup}'")
            stats["no_page"] += 1
            if needs_ipa:
                ipa_misses.append((nid, word_field))
            if needs_audio:
                audio_misses.append((nid, word_field))
            continue

        # Extract IPA
        ipa = None
        if needs_ipa:
            ipa = extract_ipa(wikitext)
            if not ipa:
                stats["ipa_miss"] += 1
                ipa_misses.append((nid, word_field))

        # Extract and download audio
        audio_filename = None
        audio_data = None
        if needs_audio:
            audio_filename = extract_audio_filename(wikitext)
            if not audio_filename:
                stats["audio_miss"] += 1
                audio_misses.append((nid, word_field))
            elif not dry_run:
                url = commons_url_from_filename(audio_filename)
                audio_data = download_audio(url)

        # Report
        parts = []
        if do_ipa:
            if ipa:
                parts.append(f"IPA={ipa}")
            elif has_ipa:
                parts.append("IPA=ok")
            else:
                parts.append("IPA=miss")
        if do_audio:
            if has_audio:
                parts.append("audio=ok")
            elif audio_filename:
                if audio_data or dry_run:
                    parts.append(f"audio={audio_filename}")
                else:
                    parts.append(f"audio=fail ({audio_filename})")
            else:
                parts.append("audio=miss")

        prefix = "[dry-run] " if dry_run else "  "
        status_str = "  ".join(parts)
        print(f"{prefix}{word_field:<30} {status_str}")

        if dry_run:
            if ipa:
                stats["ipa_added"] += 1
            if audio_filename:
                stats["audio_added"] += 1
            continue

        # Apply changes
        fields_update = {}
        if ipa:
            fields_update["IPA"] = ipa
            stats["ipa_added"] += 1
        if audio_data:
            mp3_name = store_audio_in_anki(audio_filename, audio_data)
            fields_update["Audio"] = f"[sound:{mp3_name}]"
            stats["audio_added"] += 1

        if fields_update:
            anki("updateNoteFields", note={"id": nid, "fields": fields_update})

        # Rate limiting
        if needs_audio and audio_filename:
            time.sleep(audio_delay)
        else:
            time.sleep(0.5)

    # LLM fallback for IPA misses
    if llm_fallback and ipa_misses and do_ipa:
        llm_count = _llm_ipa_fallback(ipa_misses, dry_run=dry_run)
        stats["ipa_llm"] = llm_count
        stats["ipa_added"] += llm_count

    # TTS fallback for audio misses (only for targeted enrichment —
    # free-tier Gemini TTS quota is ~10 requests/day)
    if audio_misses and do_audio and note_ids is not None:
        tts_count = _gemini_tts_fallback(audio_misses, dry_run=dry_run)
        stats["audio_tts"] = tts_count
        stats["audio_added"] += tts_count

    # Summary
    prefix = "[dry-run] " if dry_run else ""
    print(f"\n{prefix}Enrichment summary:")
    if do_ipa:
        wikt_ipa = stats["ipa_added"] - stats["ipa_llm"]
        llm_ipa = stats["ipa_llm"]
        detail = f" ({wikt_ipa} Wiktionary + {llm_ipa} LLM)" if llm_ipa else ""
        print(f"  IPA added:        {stats['ipa_added']}{detail}")
        if stats["ipa_miss"]:
            print(f"  IPA not on page:  {stats['ipa_miss']}")
    if do_audio:
        wikt_audio = stats["audio_added"] - stats["audio_tts"]
        tts_audio = stats["audio_tts"]
        detail = f" ({wikt_audio} Wiktionary + {tts_audio} TTS)" if tts_audio else ""
        print(f"  Audio added:      {stats['audio_added']}{detail}")
        if stats["audio_miss"]:
            print(f"  Audio not on page:{stats['audio_miss']}")
    print(f"  Skipped (phrase): {stats['skipped_phrase']}")
    print(f"  No Wiktionary page: {stats['no_page']}")
    if stats["already_ok"]:
        print(f"  Already complete: {stats['already_ok']}")

    return stats


# ── CLI entry point ──────────────────────────────────────────────────────────

def run(args):
    """Execute with pre-parsed args (called by CLI dispatcher)."""
    note_ids = None
    words = getattr(args, "words", None)
    if words:
        from ._anki import DECK
        note_ids = []
        for word in words:
            if " " in word:
                q = f'"deck:{DECK}" "Word:{word}"'
            else:
                q = f'"deck:{DECK}" Word:*{word}*'
            ids = anki("findNotes", query=q)
            if not ids:
                print(f"  No note found for: {word}")
            else:
                note_ids.extend(ids)
        if not note_ids:
            print("No matching notes found.")
            return

    enrich_notes(
        note_ids=note_ids,
        ipa_only=args.ipa_only,
        audio_only=args.audio_only,
        audio_delay=args.audio_delay,
        dry_run=args.dry_run,
        llm_fallback=not args.no_llm,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without applying them")
    parser.add_argument("--ipa-only", action="store_true",
                        help="Only fetch and update IPA (fast, no audio downloads)")
    parser.add_argument("--audio-only", action="store_true",
                        help="Only download and store audio files")
    parser.add_argument("--audio-delay", type=float, default=5.0,
                        help="Seconds between audio downloads (default: 5)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM fallback for Wiktionary misses")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
