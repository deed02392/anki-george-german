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
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import requests

from ._anki import anki, DECK, MODEL, ARTICLES
from ._llm import get_floodgate_token, call_llm_with_retry
from . import DATA_DIR

WIKT_API = "https://de.wiktionary.org/w/api.php"
WIKT_REST = "https://de.wiktionary.org/w/rest.php/v1"
CHECKPOINT_PATH = DATA_DIR / "enrich_index.json"

# If Wiktionary's Retry-After exceeds this (seconds), save checkpoint and exit
MAX_RATE_LIMIT_WAIT = 120

# Wikimedia requires a descriptive User-Agent (https://w.wiki/4wJS)
web = requests.Session()
web.headers["User-Agent"] = "anki-george-german/1.0 (German vocab enrichment script)"

# Sentinel: request failed due to rate limiting or transient error (not a data miss)
_DEFERRED = "DEFERRED"

# Sentinel: rate limit wait exceeds MAX_RATE_LIMIT_WAIT — save checkpoint and exit
_DEFERRED_BAIL = "DEFERRED_BAIL"


# ── Checkpoint persistence ────────────────────────────────────────────────────

def _load_checkpoint():
    """Load a saved index checkpoint. Returns (plan, ipa_misses, tts_candidates, indexed_nids)."""
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        data = json.loads(CHECKPOINT_PATH.read_text())
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def _save_checkpoint(plan, ipa_misses, tts_candidates):
    """Save the current index state to disk."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "plan": plan,
        "ipa_misses": ipa_misses,
        "tts_candidates": tts_candidates,
    }
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _clear_checkpoint():
    """Remove the checkpoint file after successful completion."""
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


def _note_needs_work(note, do_ipa, do_audio, redownload):
    """Check if a note needs any enrichment work."""
    if "Word" not in note["fields"]:
        return False  # not a vocab note (e.g. Prefix, Grammar)
    has_ipa = bool(note["fields"].get("IPA", {}).get("value", ""))
    has_audio = bool(note["fields"].get("Audio", {}).get("value", ""))
    needs_ipa = do_ipa and not has_ipa
    needs_audio = do_audio and (not has_audio or redownload)
    if not needs_ipa and not needs_audio:
        return False
    _, is_phrase = extract_lookup_word(note["fields"]["Word"]["value"])
    return not is_phrase


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

    Returns wikitext string on success, _DEFERRED if retries exhausted
    due to 429 or transient errors, _DEFERRED_BAIL if the server asks us
    to wait longer than MAX_RATE_LIMIT_WAIT, or None if the page genuinely
    doesn't exist (got a clean response with no German section).
    """
    candidates = [word]
    if word.lower() != word:
        candidates.append(word.lower())
    hit_rate_limit = False
    hit_transient = False
    for attempt in candidates:
        params = {"action": "parse", "page": attempt, "format": "json", "prop": "wikitext"}
        for retry in range(3):
            try:
                resp = web.get(WIKT_API, params=params, timeout=10)
                if resp.status_code == 429:
                    hit_rate_limit = True
                    wait = int(resp.headers.get("Retry-After", 30))
                    wait = max(wait, 10)
                    if wait > MAX_RATE_LIMIT_WAIT:
                        print(f"    (Wiktionary rate limited for {wait}s — "
                              f"exceeds {MAX_RATE_LIMIT_WAIT}s threshold)")
                        return _DEFERRED_BAIL
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
                hit_transient = True
                if retry < 2:
                    time.sleep(2)
                    continue
                break
    # Rate limits or transient errors → defer (don't misclassify as "page missing")
    if hit_rate_limit or hit_transient:
        return _DEFERRED
    return None


def fetch_wikitext_batch(words):
    """Fetch wikitext for up to 50 words in a single API call.

    Uses action=query with prop=revisions (raw content, no server-side parse).
    Returns dict mapping each input word to its wikitext (str), _DEFERRED,
    _DEFERRED_BAIL, or None.
    """
    results = {}
    # Build title list — try original case first; we'll retry lowercase misses
    titles = "|".join(words)
    params = {
        "action": "query", "titles": titles, "format": "json",
        "prop": "revisions", "rvprop": "content", "rvslots": "main",
    }
    for retry in range(3):
        try:
            resp = web.get(WIKT_API, params=params, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                wait = max(wait, 10)
                if wait > MAX_RATE_LIMIT_WAIT:
                    print(f"    (Wiktionary rate limited for {wait}s — "
                          f"exceeds {MAX_RATE_LIMIT_WAIT}s threshold)")
                    return {w: _DEFERRED_BAIL for w in words}
                print(f"    (Wiktionary rate limited, waiting {wait}s...)")
                time.sleep(wait)
                continue
            data = resp.json()
            break
        except (requests.RequestException, ValueError):
            if retry < 2:
                time.sleep(2)
                continue
            return {w: _DEFERRED for w in words}
    else:
        return {w: _DEFERRED for w in words}

    # Map normalised titles back to input words
    # MediaWiki may normalise titles (e.g. capitalisation), track via "normalized"
    normalised = {}
    for entry in data.get("query", {}).get("normalized", []):
        normalised[entry["to"]] = entry["from"]

    # Build a lookup from title → wikitext
    title_to_wikitext = {}
    for page in data.get("query", {}).get("pages", {}).values():
        title = page.get("title", "")
        if page.get("missing") is not None:
            title_to_wikitext[title] = None
            continue
        try:
            content = page["revisions"][0]["slots"]["main"]["*"]
            if "{{Sprache|Deutsch}}" in content:
                title_to_wikitext[title] = content
            else:
                title_to_wikitext[title] = None
        except (KeyError, IndexError):
            title_to_wikitext[title] = None

    # Map results back to input words
    for word in words:
        # Check exact title match first
        if word in title_to_wikitext:
            results[word] = title_to_wikitext[word]
        else:
            # Check if MediaWiki normalised our title
            found = False
            for title, wikitext in title_to_wikitext.items():
                orig = normalised.get(title, title)
                if orig == word:
                    results[word] = wikitext
                    found = True
                    break
            if not found:
                results[word] = None

    return results


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



# ── Audio discovery via REST API ─────────────────────────────────────────────

def fetch_best_audio(word):
    """Find the best German audio file for a word via the Wiktionary REST API.

    Calls /page/{word}/links/media to get all media files linked from the
    Wiktionary page, filters to German audio (De-*.ogg/wav), and picks the
    best candidate by quality heuristics.

    Returns (filename, direct_url) on success, or (None, None) if no audio
    is available. Returns (_DEFERRED, None) on rate limit / transient error.
    """
    for attempt_word in [word, word.lower()] if word.lower() != word else [word]:
        url = f"{WIKT_REST}/page/{requests.utils.quote(attempt_word, safe='')}/links/media"
        for retry in range(3):
            try:
                resp = web.get(url, timeout=10)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 30))
                    wait = max(wait, 10)
                    if wait > MAX_RATE_LIMIT_WAIT:
                        return _DEFERRED_BAIL, None
                    print(f"    (REST media rate limited, waiting {wait}s...)")
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    break  # page doesn't exist, try lowercase
                resp.raise_for_status()
                data = resp.json()
                files = data.get("files", [])
                result = _pick_best_audio(files, attempt_word)
                if result:
                    return result
                # Debug: log what files existed but didn't match
                audio_titles = [f.get("title", "?") for f in files
                                if f.get("preferred", {}).get("mediatype") == "AUDIO"]
                if audio_titles:
                    print(f"    (REST: {attempt_word} has audio files but none matched: "
                          f"{audio_titles[:5]})")
                break  # page exists but no matching audio
            except (requests.RequestException, ValueError):
                if retry < 2:
                    time.sleep(2)
                    continue
                return _DEFERRED, None
    return None, None


def _pick_best_audio(files, word):
    """Pick the best German audio file from a media links response.

    Accepts two filename conventions:
      - Standard:      De-{word}.ogg / De-{word}N.ogg
      - Lingua Libre:  LL-Q188 (deu)-{speaker}-{word}.ogg

    Returns (filename, direct_url) or None.
    """
    # Regex for Lingua Libre German: LL-Q188 (deu)-Speaker-Word.ogg
    ll_re = re.compile(
        r"^LL-Q188\s*\(deu\)-[^-]+-(.+)\.(ogg|wav|mp3)$", re.IGNORECASE
    )

    candidates = []
    for f in files:
        if f.get("preferred", {}).get("mediatype") != "AUDIO":
            continue
        title = f.get("title", "")
        # REST API may include "File:" namespace prefix — strip it
        if title.startswith("File:"):
            title = title[5:]
        fn_lower = title.lower()

        # Try standard De-{word}.ogg/.wav/.mp3 format
        audio_ext = fn_lower.endswith((".ogg", ".wav", ".mp3"))
        is_standard = fn_lower.startswith("de-") and audio_ext
        is_lingua = False
        ll_match = None

        if is_standard:
            if fn_lower.startswith("de-at-") or fn_lower.startswith("de-by-"):
                continue
            basename = title.rsplit(".", 1)[0]  # "De-Hund2"
            stem = basename[3:]  # "Hund2"  (strip "De-")
            stem_base = re.sub(r"\d+$", "", stem)  # "Hund"
            if " " in stem or stem_base.lower() != word.lower():
                continue
        else:
            ll_match = ll_re.match(title)
            if ll_match:
                ll_word = ll_match.group(1)
                if ll_word.lower() != word.lower():
                    continue
                is_lingua = True
            else:
                continue  # neither standard nor Lingua Libre

        original = f.get("original", {})
        url = original.get("url", "")
        if url.startswith("//"):
            url = "https:" + url
        duration = original.get("duration") or 0
        timestamp = f.get("latest", {}).get("timestamp", "")

        # Score: numbered standard variants best, then Lingua Libre, then base
        if is_lingua:
            score = 2
        elif re.search(r"\d\.(ogg|wav|mp3)$", fn_lower):
            score = 3
        else:
            score = 1

        candidates.append((score, timestamp, duration, title, url))

    if not candidates:
        return None
    # Best score, then newest, then longest duration
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    best = candidates[-1]
    return best[3], best[4]


def commons_url_from_filename(filename):
    """Compute the direct Wikimedia Commons URL using MD5 hash path.

    Fallback for when the REST API doesn't return a direct URL.
    """
    filename = filename.replace(" ", "_")
    md5 = hashlib.md5(filename.encode()).hexdigest()
    return (f"https://upload.wikimedia.org/wikipedia/commons"
            f"/{md5[0]}/{md5[:2]}/{requests.utils.quote(filename)}")


def download_audio(url, retries=3, progress_ctx=""):
    """Download audio file. Retries on 429 and transient errors.

    Returns bytes on success, _DEFERRED if 429 exhausted retries,
    or None on other failures.
    progress_ctx: optional string like "[42/100] Hund" for rate-limit messages.
    """
    hit_rate_limit = False
    for attempt in range(retries):
        try:
            resp = web.get(url, timeout=30)
            if resp.status_code == 429:
                hit_rate_limit = True
                wait = int(resp.headers.get("Retry-After", 60))
                wait = max(wait, 10)
                print(f"    (rate limited, waiting {wait}s..."
                      f"{' — ' + progress_ctx if progress_ctx else ''})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(3)
                continue
            return None
    return _DEFERRED if hit_rate_limit else None


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

def _parse_gemini_retry_delay(resp):
    """Extract quota info from a Gemini 429 response for diagnostics.

    Gemini returns retry info in the JSON body (google.rpc.RetryInfo),
    not in HTTP headers. Returns (retry_delay_str, quota_id) or defaults.
    """
    try:
        data = resp.json()
        details = data.get("error", {}).get("details", [])
        delay_str = None
        quota_id = None
        for detail in details:
            dtype = detail.get("@type", "")
            if dtype.endswith("RetryInfo"):
                delay_str = detail.get("retryDelay", "unknown")
            elif dtype.endswith("QuotaFailure"):
                for v in detail.get("violations", []):
                    quota_id = v.get("quotaId", "")
        return delay_str or "unknown", quota_id or "unknown"
    except (ValueError, KeyError, AttributeError):
        return "unknown", "unknown"


def _gemini_tts_single(word, api_key):
    """Generate TTS audio for a single word via Gemini API.

    Returns raw PCM bytes (s16le, 24kHz, mono), _DEFERRED if rate
    limited, or None on other failures.
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
            return _DEFERRED, resp
        resp.raise_for_status()
        data = resp.json()
        audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return base64.b64decode(audio_b64), None
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"    TTS error for '{word}': {e}")
        return None, None


def _gemini_tts_fallback(audio_misses, dry_run=False):
    """Generate TTS audio via Gemini for words missing Wiktionary audio.

    Gemini's free tier has a daily quota (e.g. 10 req/day), so on the
    first 429 we stop immediately — retrying is pointless within a run.

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

    for i, (nid, word_field) in enumerate(audio_misses):
        lookup, _ = extract_lookup_word(word_field)
        prefix = "[dry-run] " if dry_run else "  "

        if dry_run:
            print(f"{prefix}{word_field:<30} audio=TTS (would generate)")
            updated += 1
            continue

        pcm_data, err_resp = _gemini_tts_single(word_field, api_key)
        if pcm_data is _DEFERRED:
            remaining = len(audio_misses) - i
            delay_str, quota_id = _parse_gemini_retry_delay(err_resp)
            print(f"  TTS daily quota reached ({quota_id}, retry after {delay_str})")
            print(f"  Skipping remaining {remaining} words — re-run tomorrow")
            break
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

    return updated


# ── Core enrichment function (importable) ────────────────────────────────────

def enrich_notes(note_ids=None, *, ipa_only=False, audio_only=False,
                 audio_delay=5.0, dry_run=False, llm_fallback=True,
                 redownload=False):
    """Enrich notes with IPA and/or audio from Wiktionary.

    Three-phase architecture:
      1. **Index** — scan all words on Wiktionary (lightweight API calls),
         classify each into has-IPA, has-audio, needs-LLM, needs-TTS.
      2. **Fallback** — run LLM IPA generation for all misses (one batch call).
      3. **Download & apply** — fetch Wiktionary audio, apply IPA + audio to
         Anki, then run TTS for remaining audio misses.

    This lets LLM work happen while we already know the full picture, and
    avoids interleaving slow downloads with Wiktionary API calls.

    Args:
        note_ids: List of note IDs to enrich. If None, finds all notes
                  missing IPA/audio in the deck.
        ipa_only: Only fetch IPA (skip audio).
        audio_only: Only fetch audio (skip IPA).
        audio_delay: Seconds between audio downloads.
        dry_run: Preview without applying changes.
        llm_fallback: Use LLM/TTS fallback for Wiktionary misses.
        redownload: Re-fetch audio from Wiktionary even if already present.

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

    stats = {"ipa_added": 0, "ipa_miss": 0, "audio_added": 0,
             "skipped_phrase": 0, "no_page": 0, "already_ok": 0,
             "ipa_llm": 0, "audio_tts": 0}

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 1: INDEX — scan Wiktionary for all words (API calls only, no
    # downloads).  Builds a plan of what each word needs.
    # Checkpoint-aware: resumes from a saved index if one exists.
    # ══════════════════════════════════════════════════════════════════════════
    # Plan entry per note: {nid, word, lookup, needs_ipa, needs_audio,
    #   ipa, audio_filename, existing_audio}
    plan = []          # fully indexed entries
    deferred = {}      # nid -> {word, lookup, needs_ipa, needs_audio} (rate-limited)
    ipa_misses = []    # (nid, word) — genuinely no IPA on Wiktionary
    tts_candidates = []  # (nid, word) — genuinely no audio on Wiktionary

    # Try to resume from checkpoint
    checkpoint = _load_checkpoint()
    indexed_nids = set()
    if checkpoint:
        plan = checkpoint["plan"]
        ipa_misses = [tuple(x) for x in checkpoint["ipa_misses"]]
        tts_candidates = [tuple(x) for x in checkpoint["tts_candidates"]]
        indexed_nids = {e["nid"] for e in plan}
        indexed_nids |= {nid for nid, _ in ipa_misses}
        indexed_nids |= {nid for nid, _ in tts_candidates}
        remaining = sum(1 for n in notes
                        if n["noteId"] not in indexed_nids
                        and _note_needs_work(n, do_ipa, do_audio, redownload))
        print(f"\n── Phase 1: Indexing Wiktionary "
              f"(resumed: {len(indexed_nids)} cached, {remaining} remaining) ──")
    else:
        print("\n── Phase 1: Indexing Wiktionary ──")

    bailed = False

    # Collect notes that need work (pre-filter before API calls)
    work_items = []  # (note, word_field, lookup, needs_ipa, needs_audio, existing_audio)
    for note in notes:
        nid = note["noteId"]
        if nid in indexed_nids:
            continue  # already in checkpoint

        word_field = note["fields"].get("Word", {}).get("value", "")
        if not word_field:
            continue  # not a vocab note (e.g. Prefix, Grammar)
        has_ipa = bool(note["fields"].get("IPA", {}).get("value", ""))
        has_audio = bool(note["fields"].get("Audio", {}).get("value", ""))
        existing_audio = note["fields"].get("Audio", {}).get("value", "")

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

        work_items.append((note, word_field, lookup, needs_ipa, needs_audio, existing_audio))

    # ── Audio-only fast path: skip wikitext fetch, go straight to Phase 3 ────
    BATCH_SIZE = 50
    if audio_only:
        for item in work_items:
            note, word_field, lookup, needs_ipa, needs_audio, existing_audio = item
            plan.append({
                "nid": note["noteId"], "word": word_field, "lookup": lookup,
                "needs_ipa": False, "needs_audio": True,
                "ipa": None, "existing_audio": existing_audio,
            })
        print(f"  {len(plan)} words to check")
    else:
        # Batch-fetch wikitext from Wiktionary (up to 50 titles per request)
        lookup_to_item = {}  # lookup -> list of work_items sharing that lookup
        for item in work_items:
            lookup = item[2]
            lookup_to_item.setdefault(lookup, []).append(item)

        all_lookups = list(lookup_to_item.keys())
        wikitext_cache = {}  # lookup -> wikitext | None | _DEFERRED | _DEFERRED_BAIL

        for batch_start in range(0, len(all_lookups), BATCH_SIZE):
            batch = all_lookups[batch_start:batch_start + BATCH_SIZE]
            batch_results = fetch_wikitext_batch(batch)

            # Check for bail — but first process any successful results from this batch
            has_bail = any(v is _DEFERRED_BAIL for v in batch_results.values())

            wikitext_cache.update(batch_results)

            # Retry misses with lowercase (some words need lowercase lookup)
            lowercase_retry = []
            if not has_bail:
                for word in batch:
                    result = batch_results.get(word)
                    if result is None and word.lower() != word:
                        lowercase_retry.append((word, word.lower()))

                if lowercase_retry:
                    lc_words = [lc for _, lc in lowercase_retry]
                    lc_results = fetch_wikitext_batch(lc_words)
                    if any(v is _DEFERRED_BAIL for v in lc_results.values()):
                        has_bail = True
                    else:
                        for orig, lc in lowercase_retry:
                            if lc_results.get(lc):
                                wikitext_cache[orig] = lc_results[lc]

            # Process this batch's results into plan/misses
            for lookup in batch:
                wikitext = wikitext_cache.get(lookup)
                for item in lookup_to_item[lookup]:
                    note, word_field, _, needs_ipa, needs_audio, existing_audio = item
                    nid = note["noteId"]

                    if wikitext is _DEFERRED or wikitext is _DEFERRED_BAIL:
                        deferred[nid] = {"word": word_field, "lookup": lookup,
                                         "needs_ipa": needs_ipa, "needs_audio": needs_audio,
                                         "existing_audio": existing_audio}
                        continue
                    if not wikitext:
                        stats["no_page"] += 1
                        if needs_ipa:
                            ipa_misses.append((nid, word_field))
                        if needs_audio:
                            tts_candidates.append((nid, word_field))
                        continue

                    ipa = extract_ipa(wikitext) if needs_ipa else None
                    if needs_ipa and not ipa:
                        stats["ipa_miss"] += 1
                        ipa_misses.append((nid, word_field))

                    # Audio discovery deferred to Phase 3 (REST API); Phase 1
                    # only records that the word has a Wiktionary page.
                    plan.append({
                        "nid": nid, "word": word_field, "lookup": lookup,
                        "needs_ipa": needs_ipa, "needs_audio": needs_audio,
                        "ipa": ipa, "existing_audio": existing_audio,
                    })

            if has_bail:
                print(f"\n  Rate limit too long — saving checkpoint "
                      f"({len(plan)} words indexed so far)")
                _save_checkpoint(plan, ipa_misses, tts_candidates)
                print(f"  Checkpoint saved to {CHECKPOINT_PATH}")
                print("  Re-run the same command to resume.")
                bailed = True
                break

            indexed_so_far = len(plan) + len(ipa_misses) + len(tts_candidates) + len(deferred)
            print(f"  Batch {batch_start // BATCH_SIZE + 1}: "
                  f"indexed {len(batch)} words ({indexed_so_far} total)")
            time.sleep(1)  # gentle pacing between batches

    if bailed:
        return stats

    # ── Retry deferred Wiktionary lookups (batched) ─────────────────────────
    if deferred and not dry_run:
        for pass_num in range(3):
            if not deferred:
                break
            wait = 30 * (pass_num + 1)
            print(f"\n  Wiktionary retry pass {pass_num + 1} "
                  f"({len(deferred)} words, waiting {wait}s)...")
            time.sleep(wait)

            # Batch-fetch all deferred lookups
            deferred_lookups = list({info["lookup"] for info in deferred.values()})
            retry_cache = {}
            bail_retry = False
            for batch_start in range(0, len(deferred_lookups), BATCH_SIZE):
                batch = deferred_lookups[batch_start:batch_start + BATCH_SIZE]
                batch_results = fetch_wikitext_batch(batch)
                if any(v is _DEFERRED_BAIL for v in batch_results.values()):
                    bail_retry = True
                    break
                retry_cache.update(batch_results)

                # Lowercase retry for misses
                lc_retry = [(w, w.lower()) for w in batch
                            if retry_cache.get(w) is None and w.lower() != w]
                if lc_retry:
                    lc_results = fetch_wikitext_batch([lc for _, lc in lc_retry])
                    if any(v is _DEFERRED_BAIL for v in lc_results.values()):
                        bail_retry = True
                        break
                    for orig, lc in lc_retry:
                        if lc_results.get(lc):
                            retry_cache[orig] = lc_results[lc]

            done_nids = []
            for nid, info in deferred.items():
                wikitext = retry_cache.get(info["lookup"])
                if wikitext is None or wikitext is _DEFERRED:
                    if wikitext is None and info["lookup"] in retry_cache:
                        # Genuinely missing
                        if info["needs_ipa"]:
                            ipa_misses.append((nid, info["word"]))
                        if info["needs_audio"]:
                            tts_candidates.append((nid, info["word"]))
                        done_nids.append(nid)
                    continue  # still deferred or not in this batch

                ipa = extract_ipa(wikitext) if info["needs_ipa"] else None
                if info["needs_ipa"] and not ipa:
                    stats["ipa_miss"] += 1
                    ipa_misses.append((nid, info["word"]))

                plan.append({
                    "nid": nid, "word": info["word"], "lookup": info["lookup"],
                    "needs_ipa": info["needs_ipa"], "needs_audio": info["needs_audio"],
                    "ipa": ipa, "existing_audio": info["existing_audio"],
                })
                done_nids.append(nid)
                print(f"  {info['word']:<30} indexed (Wiktionary retry)")

            for nid in done_nids:
                del deferred[nid]

            if bail_retry:
                print(f"\n  Rate limit too long during retry — saving checkpoint "
                      f"({len(plan)} words indexed so far)")
                _save_checkpoint(plan, ipa_misses, tts_candidates)
                print(f"  Checkpoint saved to {CHECKPOINT_PATH}")
                print("  Re-run the same command to resume.")
                return stats

        # Still rate-limited after all retries — skip entirely
        for nid, info in deferred.items():
            print(f"  {info['word']:<30} still rate-limited, skipping (re-run later)")

    # Print the index summary
    total_indexed = len(plan) + len(ipa_misses) + len(tts_candidates)
    if audio_only:
        print(f"\n  {total_indexed} words queued for audio check")
    else:
        wikt_ipa_count = sum(1 for e in plan if e["ipa"])
        print(f"\n  Index complete: {total_indexed} words"
              f" ({len(plan)} on Wiktionary, {stats['no_page']} no page,"
              f" {stats['skipped_phrase']} phrases)")
        if do_ipa:
            print(f"    IPA from Wiktionary: {wikt_ipa_count}, "
                  f"need LLM: {len(ipa_misses)}")
    needs_audio_count = sum(1 for e in plan if e["needs_audio"])
    if do_audio:
        print(f"    Audio to check: {needs_audio_count}, "
              f"no Wikt page (→TTS): {len(tts_candidates)}")
    if deferred:
        print(f"    Rate-limited (skipped): {len(deferred)}")

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 2: LLM FALLBACK — generate IPA for all Wiktionary misses in one
    # batch.  This runs while we haven't started downloading audio yet.
    # ══════════════════════════════════════════════════════════════════════════
    if llm_fallback and ipa_misses and do_ipa:
        print("\n── Phase 2: LLM IPA fallback ──")
        llm_count = _llm_ipa_fallback(ipa_misses, dry_run=dry_run)
        stats["ipa_llm"] = llm_count
        stats["ipa_added"] += llm_count

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 3: DOWNLOAD & APPLY — fetch audio files from Commons, apply all
    # IPA + audio updates to Anki, then run TTS for remaining misses.
    # ══════════════════════════════════════════════════════════════════════════
    if plan:
        print(f"\n── Phase 3: Download & apply ({len(plan)} words) ──")

    for entry_idx, entry in enumerate(plan, 1):
        nid = entry["nid"]
        word_field = entry["word"]
        ipa = entry["ipa"]

        # Discover best audio via REST API (one call per word)
        audio_filename = None
        audio_data = None
        audio_url = None
        if entry["needs_audio"] and not dry_run:
            lookup = entry["lookup"]
            best_file, best_url = fetch_best_audio(lookup)
            if best_file is _DEFERRED or best_file is _DEFERRED_BAIL:
                # REST API rate-limited — skip audio for this word
                pass
            elif best_file:
                audio_filename = best_file
                audio_url = best_url
            else:
                # No audio on Wiktionary → TTS candidate
                tts_candidates.append((nid, word_field))
        elif entry["needs_audio"] and dry_run:
            audio_filename = f"De-{entry['lookup']}.ogg"  # placeholder for dry-run

        # Skip download if we already have this exact file
        if audio_filename and not dry_run:
            best_mp3 = audio_filename.rsplit(".", 1)[0] + ".mp3"
            existing = entry["existing_audio"]
            if existing == f"[sound:{best_mp3}]":
                if redownload:
                    print(f"  [{entry_idx}/{len(plan)}] "
                          f"{word_field:<30} audio=same ({best_mp3})")
                stats["already_ok"] += 1
                audio_filename = None
                if not ipa:
                    continue

        # Download audio from Commons
        if audio_filename and not dry_run:
            url = audio_url or commons_url_from_filename(audio_filename)
            ctx = f"[{entry_idx}/{len(plan)}] {word_field}"
            audio_data = download_audio(url, progress_ctx=ctx)
            if audio_data is _DEFERRED:
                print(f"  [{entry_idx}/{len(plan)}] "
                      f"{word_field:<30} audio=download rate-limited, skipping")
                audio_data = None
                audio_filename = None
            elif not audio_data:
                # Non-rate-limit download failure → fall back to TTS
                tts_candidates.append((nid, word_field))

        # Report
        parts = []
        if do_ipa:
            if ipa:
                parts.append(f"IPA={ipa}")
            elif entry["needs_ipa"]:
                parts.append("IPA=miss (→LLM)")
            else:
                parts.append("IPA=ok")
        if do_audio:
            if audio_filename:
                if audio_data or dry_run:
                    parts.append(f"audio=Wiktionary ({audio_filename})")
                else:
                    parts.append(f"audio=Wiktionary fail ({audio_filename})")
            elif entry["needs_audio"]:
                parts.append("audio=none (→TTS)")
            else:
                parts.append("audio=ok")

        if parts:
            prefix = "[dry-run] " if dry_run else "  "
            progress = f"[{entry_idx}/{len(plan)}] " if not dry_run else ""
            print(f"{prefix}{progress}{word_field:<30} {'  '.join(parts)}")

        if dry_run:
            if ipa:
                stats["ipa_added"] += 1
            if audio_filename:
                stats["audio_added"] += 1
            continue

        # Apply changes to Anki
        fields_update = {}
        if ipa:
            fields_update["IPA"] = ipa
            stats["ipa_added"] += 1
        if audio_data and audio_data is not _DEFERRED:
            mp3_name = store_audio_in_anki(audio_filename, audio_data)
            fields_update["Audio"] = f"[sound:{mp3_name}]"
            stats["audio_added"] += 1

        if fields_update:
            anki("updateNoteFields", note={"id": nid, "fields": fields_update})

        # Rate limiting between downloads
        if audio_data:
            time.sleep(audio_delay)

    # ── TTS fallback for audio (genuinely missing from Wiktionary) ───────────
    if llm_fallback and tts_candidates and do_audio:
        tts_count = _gemini_tts_fallback(tts_candidates, dry_run=dry_run)
        stats["audio_tts"] = tts_count
        stats["audio_added"] += tts_count

    # ── Summary ──────────────────────────────────────────────────────────────
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
    print(f"  Skipped (phrase): {stats['skipped_phrase']}")
    print(f"  No Wiktionary page: {stats['no_page']}")
    if stats["already_ok"]:
        print(f"  Already complete: {stats['already_ok']}")
    if deferred:
        print(f"  Wikt rate-limited: {len(deferred)} (re-run later)")

    # All phases completed — clear any saved checkpoint
    _clear_checkpoint()

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
