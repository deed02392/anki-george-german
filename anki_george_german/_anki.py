"""Shared AnkiConnect helper.

Usage:
    from anki_george_german._anki import anki, ANKI_URL, strip_article, ARTICLES
"""

import re

import requests

ANKI_URL = "http://localhost:8765"
DECK = "George's German Vocabulary"
MODEL = "George's German Vocab"

# All German article/determiner forms used across the pipeline.
# definite + indefinite + negative + demonstrative + universal
ARTICLES = (
    # definite
    "der", "die", "das", "den", "dem", "des",
    # indefinite
    "ein", "eine", "einen", "einem", "eines", "einer",
    # negative
    "kein", "keine", "keinen", "keinem", "keines", "keiner",
    # demonstrative / universal (used by normalise_cloze article-mismatch)
    "dieser", "diese", "dieses", "diesen", "diesem",
    "jeder", "jede", "jedes", "jeden", "jedem",
)
ARTICLE_SET = frozenset(a.lower() for a in ARTICLES)

_STRIP_RE = re.compile(
    r"^(der|die|das|den|dem|des|ein|eine|einen|einem|eines|einer|"
    r"kein|keine|keinen|keinem|keines|keiner|sich)\s+",
    re.IGNORECASE,
)


def strip_article(word):
    """Strip a leading article (or 'sich') and return the bare word, lowercased."""
    return _STRIP_RE.sub("", word).strip().lower()


def anki(action, **params):
    """Send a request to AnkiConnect and return the result."""
    resp = requests.post(
        ANKI_URL, json={"action": action, "params": params, "version": 6}
    ).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {resp['error']}")
    return resp["result"]


def fetch_vocab_notes(extra_query=""):
    """Fetch all notes for the vocab deck+model, with optional extra query terms.

    Returns a list of note info dicts from AnkiConnect's notesInfo.
    """
    query = f'deck:"{DECK}" "note:{MODEL}"'
    if extra_query:
        query += f" {extra_query}"
    note_ids = anki("findNotes", query=query)
    if not note_ids:
        return []
    return anki("notesInfo", notes=note_ids)
