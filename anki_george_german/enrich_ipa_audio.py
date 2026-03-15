#!/usr/bin/env python3
"""Enrich German vocabulary Anki notes with IPA and audio.

Sources (in priority order):
  1. de.wiktionary.org — IPA transcriptions and native-speaker audio
  2. LLM (Floodgate) — IPA fallback for words Wiktionary doesn't have
  3. Gemini TTS — audio fallback for words without Wiktionary recordings

Usage:
    anki-german enrich audio              # IPA + audio (all missing)
    anki-german enrich audio --ipa-only   # just IPA (fast)
    anki-german enrich audio --audio-only # just audio downloads
    anki-german enrich audio --dry-run    # preview without changes
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

# Sentinel returned when a request fails due to rate limiting (not a data miss)
_RATE_LIMITED = "RATE_LIMITED"


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
    """Fetch the wikitext for a German Wiktionary page.

    Returns wikitext string on success, _RATE_LIMITED if all retries
    exhausted due to 429, or None if the page genuinely doesn't exist.
    """
    candidates = [word]
    if word.lower() != word:
        candidates.append(word.lower())
    hit_rate_limit = False
    for attempt in candidates:
        params = {"action": "parse", "page": attempt, "format": "json", "prop": "wikitext"}
        for retry in range(3):
            try:
                resp = web.get(WIKT_API, params=params, timeout=10)
                if resp.status_code == 429:
                    hit_rate_limit = True
                    wait = int(resp.headers.get("Retry-After", 30))
                    wait = max(wait, 10)
                    print(f"    (Wiktionary rate limited, waiting {wait}s...)")
                    time.sleep(wait)
                    continue
                data = resp.json()
                if "parse" in data:
                    wikitext = data["parse"]["wikitext"]["*"]
                    if "{{Sprache|Deutsch}}" in wikitext:
                        return wikitext
                break  # got a response (even if no German section) — don't retry
            except (KeyError, requests.RequestException):
                if retry < 2:
                    time.sleep(2)
                    continue
                break
    # If we never got a clean response and hit rate limits, report that
    return _RATE_LIMITED if hit_rate_limit else None


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
    """Extract the best German audio filename from wikitext.

    Priority: Lingua Libre > numbered De variants (De-X2, De-X3) > De-X.ogg.
    Skips Austrian (spr=at, De-at-) and Bavarian (spr=by, Bar-, BY-) recordings.
    """
    section = extract_german_section(wikitext)
    pron = extract_aussprache_block(section)
    # Find all Audio templates — capture the full template content
    all_audio = re.findall(r"\{\{Audio\|([^}]+)\}\}", pron)
    if not all_audio:
        return None

    candidates = []
    for entry in all_audio:
        # entry may be "De-Hund.ogg" or "De-at-Hund.ogg|spr=at" etc.
        parts = entry.split("|")
        filename = parts[0].strip()
        rest = "|".join(parts[1:]).lower()

        # Skip regional dialects
        if "spr=at" in rest or "spr=by" in rest:
            continue
        fn_lower = filename.lower()
        if fn_lower.startswith("de-at-") or fn_lower.startswith("bar-") or fn_lower.startswith("by-"):
            continue

        # Must be .ogg or .wav
        if not (fn_lower.endswith(".ogg") or fn_lower.endswith(".wav")):
            continue

        # Score: Lingua Libre best, then numbered, then base
        if fn_lower.startswith("ll-"):
            score = 3
        elif re.search(r"\d\.(ogg|wav)$", fn_lower):
            score = 2
        else:
            score = 1

        candidates.append((score, filename))

    if not candidates:
        return None
    # Highest score wins; among ties, last one (often newest)
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


# ── Audio download ───────────────────────────────────────────────────────────

def commons_url_from_filename(filename):
    """Compute the direct Wikimedia Commons URL using MD5 hash path."""
    md5 = hashlib.md5(filename.encode()).hexdigest()
    return (f"https://upload.wikimedia.org/wikipedia/commons"
            f"/{md5[0]}/{md5[:2]}/{requests.utils.quote(filename)}")


def probe_commons_variants(base_filename):
    """Probe Wikimedia Commons for higher-quality numbered variants.

    Given "De-mögen.ogg", checks if "De-mögen2.ogg" or "De-mögen3.ogg"
    exist on Commons (via HEAD request). Returns the highest-numbered
    variant found, or the original filename if none exist.
    """
    # Only probe for standard De-Word.ogg pattern
    m = re.match(r"^(De-[^.]+)(\.ogg)$", base_filename)
    if not m:
        return base_filename

    stem, ext = m.group(1), m.group(2)
    # Already a numbered variant — don't probe further
    if re.search(r"\d$", stem):
        return base_filename

    best = base_filename
    for suffix in ("2", "3"):
        candidate = f"{stem}{suffix}{ext}"
        url = commons_url_from_filename(candidate)
        try:
            resp = web.head(url, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                best = candidate
        except requests.RequestException:
            break
    return best


def download_audio(url, retries=3):
    """Download audio file. Retries on 429 and transient errors.

    Returns bytes on success, _RATE_LIMITED if 429 exhausted retries,
    or None on other failures.
    """
    hit_rate_limit = False
    for attempt in range(retries):
        try:
            resp = web.get(url, timeout=30)
            if resp.status_code == 429:
                hit_rate_limit = True
                wait = int(resp.headers.get("Retry-After", 60))
                wait = max(wait, 10)
                print(f"    (rate limited, waiting {wait}s...)")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(3)
                continue
            return None
    return _RATE_LIMITED if hit_rate_limit else None


def store_audio_in_anki(filename, data):
    """Convert ogg/wav to mp3 and store in Anki's media folder via AnkiConnect.

    Returns the stored filename (*.mp3).
    """
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".ogg"
    mp3_name = filename.rsplit(".", 1)[0] + ".mp3"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_src:
        tmp_src.write(data)
        tmp_src_path = tmp_src.name
    tmp_mp3_path = tmp_src_path.rsplit(".", 1)[0] + ".mp3"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", tmp_src_path, "-codec:a", "libmp3lame",
             "-q:a", "2", tmp_mp3_path, "-y"],
            capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed for {filename}")
        with open(tmp_mp3_path, "rb") as f:
            mp3_b64 = base64.b64encode(f.read()).decode("ascii")
        anki("storeMediaFile", filename=mp3_name, data=mp3_b64)
    finally:
        for p in (tmp_src_path, tmp_mp3_path):
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

    Returns raw PCM bytes (s16le, 24kHz, mono), _RATE_LIMITED if rate
    limited after retries, or None on other failures.
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
    for attempt in range(3):
        try:
            resp = requests.post(
                GEMINI_API_URL, params={"key": api_key},
                json=payload, timeout=30,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                wait = max(wait, 15)
                if attempt < 2:
                    print(f"    (TTS rate limited, waiting {wait}s...)")
                    time.sleep(wait)
                    continue
                return _RATE_LIMITED
            resp.raise_for_status()
            data = resp.json()
            audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            return base64.b64decode(audio_b64)
        except (requests.RequestException, KeyError, IndexError) as e:
            print(f"    TTS error for '{word}': {e}")
            return None
    return _RATE_LIMITED


def _gemini_tts_fallback(audio_misses, dry_run=False):
    """Generate TTS audio via Gemini for words missing Wiktionary audio.

    Processes all words, deferring rate-limited ones for a retry pass.

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
    deferred = []  # words that hit rate limits — retry later

    for nid, word_field in audio_misses:
        lookup, _ = extract_lookup_word(word_field)
        prefix = "[dry-run] " if dry_run else "  "

        if dry_run:
            print(f"{prefix}{word_field:<30} audio=TTS (would generate)")
            updated += 1
            continue

        pcm_data = _gemini_tts_single(word_field, api_key)
        if pcm_data is _RATE_LIMITED:
            print(f"  {word_field:<30} audio=TTS deferred (rate limited)")
            deferred.append((nid, word_field))
            continue
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
        time.sleep(1)

    # Retry deferred words with longer waits
    if deferred and not dry_run:
        print(f"\n  Retrying {len(deferred)} rate-limited TTS words (60s wait)...")
        time.sleep(60)
        for nid, word_field in deferred:
            lookup, _ = extract_lookup_word(word_field)
            pcm_data = _gemini_tts_single(word_field, api_key)
            if pcm_data is _RATE_LIMITED or not pcm_data:
                print(f"  {word_field:<30} audio=TTS retry fail")
                continue
            mp3_name = f"tts_{lookup}.mp3"
            store_pcm_audio_in_anki(mp3_name, pcm_data)
            anki("updateNoteFields", note={
                "id": nid,
                "fields": {"Audio": f"[sound:{mp3_name}]"},
            })
            print(f"  {word_field:<30} audio=TTS retry ok")
            updated += 1
            time.sleep(3)

    return updated


# ── Core enrichment function (importable) ────────────────────────────────────

def enrich_notes(note_ids=None, *, ipa_only=False, audio_only=False,
                 audio_delay=5.0, dry_run=False, llm_fallback=True,
                 redownload=False):
    """Enrich notes with IPA and/or audio from Wiktionary.

    Args:
        note_ids: List of note IDs to enrich. If None, finds all notes
                  missing IPA/audio in the deck.
        ipa_only: Only fetch IPA (skip audio).
        audio_only: Only fetch audio (skip IPA).
        audio_delay: Seconds between audio downloads.
        dry_run: Preview without applying changes.
        llm_fallback: Use LLM/TTS fallback for Wiktionary misses.
        redownload: Re-fetch audio from Wiktionary even if already present.
        audio_delay: Seconds between audio downloads.
        dry_run: Preview without applying changes.
        llm_fallback: Use LLM/TTS fallback for Wiktionary misses.

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
            if redownload:
                # All notes — we'll re-fetch audio for everything
                all_ids |= set(anki("findNotes", query=f'\"deck:{DECK}\"'))
            else:
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
    ipa_misses = []          # genuinely no IPA on Wiktionary → LLM candidates
    tts_candidates = []      # genuinely no audio on Wiktionary → TTS candidates
    wikt_ipa_deferred = []   # IPA exists but rate-limited → retry Wiktionary
    wikt_audio_deferred = [] # audio exists but rate-limited → retry Wiktionary
    retry_map = {}           # populated during Wiktionary retry phase

    for note in notes:
        nid = note["noteId"]
        word_field = note["fields"]["Word"]["value"]
        has_ipa = bool(note["fields"]["IPA"]["value"])
        has_audio = bool(note["fields"].get("Audio", {}).get("value", ""))

        needs_ipa = do_ipa and not has_ipa
        needs_audio = do_audio and (not has_audio or redownload)

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
        if wikitext is _RATE_LIMITED:
            print(f"  DEFERRED (rate limited): {word_field}")
            if needs_ipa:
                wikt_ipa_deferred.append((nid, word_field, lookup))
            if needs_audio:
                wikt_audio_deferred.append((nid, word_field, lookup))
            continue
        if not wikitext:
            print(f"  MISS: {word_field} -> no Wiktionary page for '{lookup}'")
            stats["no_page"] += 1
            if needs_ipa:
                ipa_misses.append((nid, word_field))
            if needs_audio:
                tts_candidates.append((nid, word_field))
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
                tts_candidates.append((nid, word_field))
            elif not dry_run:
                # Probe Commons for higher-quality numbered variants
                audio_filename = probe_commons_variants(audio_filename)
                # Skip download if we already have this exact file
                new_mp3 = audio_filename.rsplit(".", 1)[0] + ".mp3"
                existing = note["fields"].get("Audio", {}).get("value", "")
                if existing == f"[sound:{new_mp3}]":
                    if redownload:
                        print(f"  {word_field:<30} audio=same ({new_mp3})")
                    stats["already_ok"] += 1
                    continue
                else:
                    url = commons_url_from_filename(audio_filename)
                    audio_data = download_audio(url)
                    if audio_data is _RATE_LIMITED:
                        print(f"  DEFERRED (download rate limited): {word_field}")
                        wikt_audio_deferred.append((nid, word_field, lookup))
                        audio_data = None
                        audio_filename = None

        # Report — show source for each enrichment
        parts = []
        if do_ipa:
            if ipa:
                parts.append(f"IPA={ipa} (Wiktionary)")
            elif has_ipa:
                parts.append("IPA=ok")
            else:
                parts.append("IPA=miss (→LLM)")
        if do_audio:
            if has_audio and not needs_audio:
                parts.append("audio=ok")
            elif audio_filename:
                if audio_data or dry_run:
                    parts.append(f"audio=Wiktionary ({audio_filename})")
                else:
                    parts.append(f"audio=Wiktionary fail ({audio_filename})")
            elif any(nid == n and word_field == w for n, w, _ in wikt_audio_deferred):
                pass  # already printed DEFERRED line
            else:
                parts.append("audio=miss (→TTS)")

        if parts:
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
        if audio_data and audio_data is not _RATE_LIMITED:
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

    # ── Retry Wiktionary-deferred items ──────────────────────────────────────
    if (wikt_ipa_deferred or wikt_audio_deferred) and not dry_run:
        # Merge into a single retry list keyed by note id
        retry_map = {}  # nid -> {word_field, lookup, needs_ipa, needs_audio}
        for nid, wf, lk in wikt_ipa_deferred:
            retry_map.setdefault(nid, {"word": wf, "lookup": lk,
                                       "ipa": True, "audio": False})
        for nid, wf, lk in wikt_audio_deferred:
            entry = retry_map.setdefault(nid, {"word": wf, "lookup": lk,
                                               "ipa": False, "audio": False})
            entry["audio"] = True

        for pass_num in range(3):
            if not retry_map:
                break
            wait = 30 * (pass_num + 1)
            print(f"\n  Wiktionary retry pass {pass_num + 1} "
                  f"({len(retry_map)} words, waiting {wait}s)...")
            time.sleep(wait)

            done_nids = []
            for nid, info in retry_map.items():
                wikitext = fetch_wikitext(info["lookup"])
                if wikitext is _RATE_LIMITED:
                    continue  # still limited, try next pass
                if not wikitext:
                    # Page genuinely doesn't exist — move to fallback lists
                    if info["ipa"]:
                        ipa_misses.append((nid, info["word"]))
                    if info["audio"]:
                        tts_candidates.append((nid, info["word"]))
                    done_nids.append(nid)
                    continue

                fields_update = {}
                if info["ipa"]:
                    ipa = extract_ipa(wikitext)
                    if ipa:
                        fields_update["IPA"] = ipa
                        stats["ipa_added"] += 1
                        print(f"  {info['word']:<30} IPA={ipa} (Wiktionary retry)")
                    else:
                        ipa_misses.append((nid, info["word"]))
                    info["ipa"] = False

                if info["audio"]:
                    af = extract_audio_filename(wikitext)
                    if not af:
                        tts_candidates.append((nid, info["word"]))
                    else:
                        af = probe_commons_variants(af)
                        url = commons_url_from_filename(af)
                        data = download_audio(url)
                        if data is _RATE_LIMITED:
                            continue  # still limited
                        if data:
                            mp3_name = store_audio_in_anki(af, data)
                            fields_update["Audio"] = f"[sound:{mp3_name}]"
                            stats["audio_added"] += 1
                            print(f"  {info['word']:<30} audio=Wiktionary retry ({af})")
                            time.sleep(audio_delay)
                        else:
                            tts_candidates.append((nid, info["word"]))
                    info["audio"] = False

                if fields_update:
                    anki("updateNoteFields", note={"id": nid, "fields": fields_update})

                if not info["ipa"] and not info["audio"]:
                    done_nids.append(nid)

            for nid in done_nids:
                del retry_map[nid]

        # Anything still in retry_map after all passes — move to fallback
        for nid, info in retry_map.items():
            # Still rate-limited after retries — do NOT send to TTS/LLM.
            # These words have Wiktionary data, just couldn't fetch it.
            # They'll be picked up on the next run.
            print(f"  {info['word']:<30} still rate-limited, skipping (re-run later)")

    # ── LLM fallback for IPA (genuinely missing from Wiktionary) ─────────────
    if llm_fallback and ipa_misses and do_ipa:
        llm_count = _llm_ipa_fallback(ipa_misses, dry_run=dry_run)
        stats["ipa_llm"] = llm_count
        stats["ipa_added"] += llm_count

    # ── TTS fallback for audio (genuinely missing from Wiktionary) ───────────
    if llm_fallback and tts_candidates and do_audio:
        tts_count = _gemini_tts_fallback(tts_candidates, dry_run=dry_run)
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
    if retry_map:
        print(f"  Wikt rate-limited: {len(retry_map)} (re-run later)")

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
        redownload=getattr(args, "redownload", False),
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
                        help="Skip LLM/TTS fallback for Wiktionary misses")
    parser.add_argument("--redownload", action="store_true",
                        help="Re-fetch audio from Wiktionary (prefer higher quality)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
