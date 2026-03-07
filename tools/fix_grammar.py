#!/usr/bin/env python3
"""Fix grammar in original sentences and translations using Claude via Floodgate.

Sends each batch of German sentences + English translations to Claude, which
checks both the German for grammar/naturalness and the English for grammar,
naturalness, and British English conventions. Only the first (original) variant
is checked — generated variants are already high quality.

Usage:
    python3 fix_translations.py --dry-run           # preview corrections
    python3 fix_translations.py --dry-run --limit 20 # preview first 20
    python3 fix_translations.py                      # apply corrections
    python3 fix_translations.py --batch-size 20      # 20 per LLM call

Requires:
    - Anki running with AnkiConnect
    - appleconnect CLI for OIDC authentication
"""
import argparse
import json
import subprocess
import sys
import time

import requests

DECK = "George's German Vocabulary"
ANKI_URL = "http://localhost:8765"
FLOODGATE_URL = "https://floodgate.g.apple.com/api/openai/v1/chat/completions"
FLOODGATE_MODEL = "aws:anthropic.claude-sonnet-4-20250514-v1:0"


# ── OIDC auth ────────────────────────────────────────────────────────────────

def get_oidc_token():
    """Get an OIDC token via appleconnect CLI."""
    result = subprocess.run(
        ["appleconnect", "getToken", "-t", "oauth", "-G", "pkce",
         "-C", "hvys3fcwcteqrvw3qzkvtk86viuoqv",
         "-o", "openid,dsid,accountname,email,groups",
         "--interactivity-type", "none"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: appleconnect getToken failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    for line in result.stdout.strip().split("\n"):
        if "id-token" in line:
            return line.split()[-1]

    print(f"ERROR: no id-token in appleconnect output:\n{result.stdout}", file=sys.stderr)
    sys.exit(1)


# ── AnkiConnect ──────────────────────────────────────────────────────────────

def anki(action, **params):
    resp = requests.post(ANKI_URL, json={"action": action, "params": params, "version": 6}).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {resp['error']}")
    return resp["result"]


# ── LLM ──────────────────────────────────────────────────────────────────────

def build_prompt(batch):
    """Build the prompt for a batch of sentence pairs."""
    items_block = ""
    for i, item in enumerate(batch, 1):
        items_block += (
            f"{i}. German: {item['sentence']}\n"
            f"   English: {item['translation']}\n"
        )

    return f"""\
You are reviewing German sentences and their English translations. The sentences \
were written by a non-native speaker and may contain grammatical errors, \
unnatural phrasing, or incorrect word usage.

For each pair below, check:
1. Whether the German sentence is grammatically correct and natural. Fix any \
grammar errors, awkward phrasing, or unnatural constructions. Keep the same \
meaning and vocabulary level (conversational, suitable for talking to young children).
2. Whether the English translation is grammatically correct and natural. Use \
British English spelling and vocabulary (e.g. "colour" not "color", "mum" not \
"mom"). The translation must accurately convey the meaning of the German sentence.

If a sentence is already correct and natural, return it unchanged. Only fix \
what genuinely needs fixing.

Pairs:
{items_block}
Respond with ONLY a JSON array (no markdown, no commentary). Each element:
{{
  "index": <1-based index>,
  "original_de": "<original German>",
  "fixed_de": "<corrected German or same if no fix needed>",
  "changed_de": <true if you modified the German, false if already correct>,
  "original_en": "<original English>",
  "fixed_en": "<corrected English or same if no fix needed>",
  "changed_en": <true if you modified the English, false if already correct>
}}"""


def call_llm(token, prompt):
    """Call Claude via Floodgate and parse the JSON response."""
    resp = requests.post(
        FLOODGATE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "anki-george-german/1.0",
        },
        json={
            "model": FLOODGATE_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()

    # Strip markdown code fence if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return json.loads(text)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview corrections without applying them")
    parser.add_argument("--batch-size", type=int, default=20,
                        help="Sentence pairs per LLM call (default: 20)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N notes (0=all)")
    args = parser.parse_args()

    # Authenticate
    print("Authenticating via appleconnect...")
    token = get_oidc_token()
    print("OK\n")

    # Fetch all notes
    note_ids = anki("findNotes", query=f'"deck:{DECK}"')
    all_notes = anki("notesInfo", notes=note_ids)
    print(f"Fetched {len(all_notes)} notes.")

    # Build list: extract the original (first) sentence + translation
    notes_to_check = []
    skipped = 0
    for note in all_notes:
        sentence_field = note["fields"]["Sentence"]["value"]
        translation_field = note["fields"]["SentenceTranslation"]["value"]
        if not sentence_field or not translation_field:
            skipped += 1
            continue

        # Take only the first (original) variant
        sentence = sentence_field.split("|")[0].strip()
        translation = translation_field.split("|")[0].strip()

        notes_to_check.append({
            "note_id": note["noteId"],
            "word": note["fields"]["Word"]["value"],
            "sentence": sentence,
            "translation": translation,
            "sentence_field": sentence_field,
            "translation_field": translation_field,
        })

    if args.limit:
        notes_to_check = notes_to_check[:args.limit]

    print(f"To check: {len(notes_to_check)} notes (skipped {skipped} — no sentence/translation)")
    if not notes_to_check:
        print("Nothing to do.")
        return

    # Process in batches
    total_fixed = 0
    total_ok = 0
    total_errors = 0

    for batch_start in range(0, len(notes_to_check), args.batch_size):
        batch_notes = notes_to_check[batch_start:batch_start + args.batch_size]
        batch_num = batch_start // args.batch_size + 1
        total_batches = (len(notes_to_check) + args.batch_size - 1) // args.batch_size

        print(f"\n── Batch {batch_num}/{total_batches} ({len(batch_notes)} pairs) ──────────────────")

        prompt = build_prompt(batch_notes)
        result = None

        for attempt in range(2):
            try:
                result = call_llm(token, prompt)
                if isinstance(result, list) and len(result) == len(batch_notes):
                    break
                print(f"  Bad response shape (attempt {attempt + 1})")
                result = None
            except (json.JSONDecodeError, requests.RequestException) as e:
                print(f"  LLM error (attempt {attempt + 1}): {e}")
                if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 401:
                    print("  Refreshing OIDC token...")
                    token = get_oidc_token()
                time.sleep(2)
                result = None

        if result is None:
            print(f"  SKIPPING batch after 2 failed attempts.")
            total_errors += len(batch_notes)
            continue

        # Apply corrections
        for item, note_data in zip(result, batch_notes):
            de_changed = item.get("changed_de", False)
            en_changed = item.get("changed_en", False)

            if not de_changed and not en_changed:
                total_ok += 1
                continue

            fixed_de = item.get("fixed_de", "")
            fixed_en = item.get("fixed_en", "")
            original_de = item.get("original_de", "")
            original_en = item.get("original_en", "")

            # Validate: skip if "fixed" is empty or same as original
            if de_changed and (not fixed_de or fixed_de == original_de):
                de_changed = False
            if en_changed and (not fixed_en or fixed_en == original_en):
                en_changed = False

            if not de_changed and not en_changed:
                total_ok += 1
                continue

            prefix = "[dry-run] " if args.dry_run else "  "
            print(f"{prefix}{note_data['word']}")

            fields_to_update = {}

            if de_changed:
                # Replace the first variant's sentence in the pipe-separated field
                parts = note_data["sentence_field"].split("|")
                parts[0] = fixed_de
                new_sentence_field = "|".join(parts)
                fields_to_update["Sentence"] = new_sentence_field
                print(f"    de- {original_de}")
                print(f"    de+ {fixed_de}")

            if en_changed:
                # Replace the first variant's translation in the pipe-separated field
                parts = note_data["translation_field"].split("|")
                parts[0] = fixed_en
                new_translation_field = "|".join(parts)
                fields_to_update["SentenceTranslation"] = new_translation_field
                print(f"    en- {original_en}")
                print(f"    en+ {fixed_en}")

            if not args.dry_run and fields_to_update:
                anki("updateNoteFields", note={
                    "id": note_data["note_id"],
                    "fields": fields_to_update,
                })

            total_fixed += 1

        # Brief pause between batches
        if batch_start + args.batch_size < len(notes_to_check):
            time.sleep(1)

    # Summary
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"\n{prefix}Summary:")
    print(f"  Fixed:    {total_fixed}")
    print(f"  OK:       {total_ok}")
    print(f"  Errors:   {total_errors}")


if __name__ == "__main__":
    main()
