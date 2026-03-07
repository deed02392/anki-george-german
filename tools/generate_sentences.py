#!/usr/bin/env python3
"""Generate randomized cloze sentence variants using Claude via Floodgate.

For each note in George's German Vocabulary, generates 2 alternative sentences
with translations and cloze words. Stores them as pipe-separated variants in
the Sentence, SentenceTranslation, and ClozeWord fields.

The cloze card JS already picks a random variant per review session, so once
variants are populated, each review shows a different sentence.

Usage:
    python3 generate_sentence_variants.py                  # generate for all notes
    python3 generate_sentence_variants.py --dry-run        # preview without changes
    python3 generate_sentence_variants.py --limit 5        # process only 5 notes
    python3 generate_sentence_variants.py --batch-size 5   # 5 words per LLM call

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
MODEL = "George's German Vocab"
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
    """Build the prompt for a batch of words.

    Each item in batch is a dict with: word, pos, article, sentence,
    sentence_translation, cloze_word.
    """
    words_block = ""
    for i, item in enumerate(batch, 1):
        article_part = f" ({item['article']})" if item["article"] else ""
        words_block += (
            f"{i}. {item['word']}{article_part} [{item['pos']}]\n"
            f"   Example: {item['sentence']}\n"
            f"   Translation: {item['sentence_translation']}\n"
        )

    return f"""\
You are generating German example sentences for an adult learning German vocabulary \
to speak with children aged 4-6. The sentences should be natural German that a parent \
or caregiver would say to/about young children, or that might occur in a children's \
story or everyday family life.

For each word below, generate exactly 2 new German sentences (different from the \
example) with their English translations. All English must use British English \
spelling and vocabulary (e.g. "colour" not "color", "mum" not "mom", \
"favourite" not "favorite"). Each sentence must:
- Use the word naturally (conjugated/declined as appropriate)
- Be age-appropriate in topic (animals, food, play, family, colours, etc.)
- Be 5-15 words long
- Use simple grammar (present tense preferred, past tense OK for stories)

For each sentence, also provide the exact form of the word as it appears in that \
sentence (the "cloze word"). For separable verbs where the prefix separates from \
the stem, use ~ between the parts (e.g. "macht~auf" for aufmachen in "Er macht \
die Tür auf."). The cloze word must be an exact substring of the sentence \
(case-sensitive).

Words:
{words_block}
Respond with ONLY a JSON array (no markdown, no commentary). Each element:
{{
  "word": "<dictionary form>",
  "sentences": [
    {{
      "de": "<German sentence 1>",
      "en": "<English translation 1>",
      "cloze": "<exact word form in sentence 1, ~ for separable parts>"
    }},
    {{
      "de": "<German sentence 2>",
      "en": "<English translation 2>",
      "cloze": "<exact word form in sentence 2, ~ for separable parts>"
    }}
  ]
}}"""


def call_llm(token, prompt):
    """Call Claude via Floodgate OpenAI-compatible API and parse the JSON response."""
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


def validate_result(result, batch):
    """Validate LLM output matches the batch and cloze words exist in sentences."""
    if not isinstance(result, list):
        return False, "response is not a list"
    if len(result) != len(batch):
        return False, f"expected {len(batch)} items, got {len(result)}"

    errors = []
    for i, item in enumerate(result):
        word = item.get("word", "?")
        sentences = item.get("sentences", [])
        if len(sentences) != 2:
            errors.append(f"  {word}: expected 2 sentences, got {len(sentences)}")
            continue
        for j, s in enumerate(sentences):
            de = s.get("de", "")
            en = s.get("en", "")
            cloze = s.get("cloze", "")
            if not de or not en or not cloze:
                errors.append(f"  {word} sentence {j+1}: missing de/en/cloze")
                continue
            # Check each cloze part exists in the sentence
            parts = [p.strip() for p in cloze.split("~") if p.strip()]
            for part in parts:
                if part not in de:
                    errors.append(
                        f"  {word} sentence {j+1}: cloze '{part}' not in '{de}'"
                    )

    if errors:
        return False, "\n".join(errors)
    return True, ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without applying changes")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Words per LLM call (default: 10)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N notes (0=all)")
    args = parser.parse_args()

    # Get OIDC token
    print("Authenticating via appleconnect...")
    token = get_oidc_token()
    print("OK\n")

    # Fetch all notes
    note_ids = anki("findNotes", query=f'"deck:{DECK}"')
    all_notes = anki("notesInfo", notes=note_ids)
    print(f"Fetched {len(all_notes)} notes.")

    # Filter to notes that don't already have variants
    notes_to_process = []
    skipped = 0
    for note in all_notes:
        sentence = note["fields"]["Sentence"]["value"]
        if not sentence:
            skipped += 1
            continue
        if "|" in sentence:
            skipped += 1
            continue
        notes_to_process.append(note)

    if args.limit:
        notes_to_process = notes_to_process[:args.limit]

    print(f"To process: {len(notes_to_process)} notes "
          f"(skipped {skipped} — no sentence or already has variants)")
    if not notes_to_process:
        print("Nothing to do.")
        return

    # Process in batches
    total_updated = 0
    total_errors = 0
    total_retries = 0

    for batch_start in range(0, len(notes_to_process), args.batch_size):
        batch_notes = notes_to_process[batch_start:batch_start + args.batch_size]
        batch_num = batch_start // args.batch_size + 1
        total_batches = (len(notes_to_process) + args.batch_size - 1) // args.batch_size

        # Build batch data
        batch = []
        for note in batch_notes:
            fields = note["fields"]
            batch.append({
                "word": fields["Word"]["value"],
                "pos": fields["POS"]["value"],
                "article": fields.get("Article", {}).get("value", ""),
                "sentence": fields["Sentence"]["value"],
                "sentence_translation": fields["SentenceTranslation"]["value"],
                "cloze_word": fields.get("ClozeWord", {}).get("value", ""),
                "note_id": note["noteId"],
            })

        print(f"\n── Batch {batch_num}/{total_batches} "
              f"({len(batch)} words) ──────────────────")
        words_str = ", ".join(b["word"] for b in batch)
        print(f"  Words: {words_str}")

        # Call LLM (with one retry on validation failure)
        prompt = build_prompt(batch)
        result = None
        for attempt in range(2):
            try:
                result = call_llm(token, prompt)
                valid, err_msg = validate_result(result, batch)
                if valid:
                    break
                print(f"  Validation failed (attempt {attempt + 1}):\n{err_msg}")
                if attempt == 0:
                    total_retries += 1
                    result = None
            except (json.JSONDecodeError, requests.RequestException) as e:
                print(f"  LLM error (attempt {attempt + 1}): {e}")
                if attempt == 0:
                    total_retries += 1
                    # Refresh token on auth failure
                    if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 401:
                        print("  Refreshing OIDC token...")
                        token = get_oidc_token()
                    time.sleep(2)

        if result is None:
            print(f"  SKIPPING batch after 2 failed attempts.")
            total_errors += len(batch)
            continue

        # Apply results
        # Build a lookup by word for matching back to notes
        result_by_word = {item["word"]: item for item in result}

        for note_data in batch:
            word = note_data["word"]
            nid = note_data["note_id"]
            item = result_by_word.get(word)

            if not item:
                print(f"  MISS: {word} — not in LLM response")
                total_errors += 1
                continue

            s1 = item["sentences"][0]
            s2 = item["sentences"][1]

            new_sentence = f"{note_data['sentence']}|{s1['de']}|{s2['de']}"
            new_translation = f"{note_data['sentence_translation']}|{s1['en']}|{s2['en']}"

            # Build ClozeWord: existing | new1 | new2
            existing_cw = note_data["cloze_word"]
            new_cloze = f"{existing_cw}|{s1['cloze']}|{s2['cloze']}"

            prefix = "[dry-run] " if args.dry_run else "  "
            print(f"{prefix}{word}")
            print(f"    existing: {note_data['sentence']}")
            print(f"              cloze: {existing_cw}")
            print(f"    + {s1['de']}")
            print(f"      ({s1['en']})")
            print(f"      cloze: {s1['cloze']}")
            print(f"    + {s2['de']}")
            print(f"      ({s2['en']})")
            print(f"      cloze: {s2['cloze']}")

            if not args.dry_run:
                anki("updateNoteFields", note={
                    "id": nid,
                    "fields": {
                        "Sentence": new_sentence,
                        "SentenceTranslation": new_translation,
                        "ClozeWord": new_cloze,
                    },
                })

            total_updated += 1

        # Brief pause between batches to avoid overwhelming Floodgate
        if batch_start + args.batch_size < len(notes_to_process):
            time.sleep(1)

    # Summary
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"\n{prefix}Summary:")
    print(f"  Updated:  {total_updated}")
    print(f"  Errors:   {total_errors}")
    print(f"  Retries:  {total_retries}")
    print(f"\nRun backfill_clozeword.py --verify to confirm all cloze words match.")


if __name__ == "__main__":
    main()
