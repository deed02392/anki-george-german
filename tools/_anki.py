"""Shared AnkiConnect helper.

Usage:
    from tools._anki import anki, ANKI_URL
"""

import requests

ANKI_URL = "http://localhost:8765"
DECK = "George's German Vocabulary"
MODEL = "George's German Vocab"


def anki(action, **params):
    """Send a request to AnkiConnect and return the result."""
    resp = requests.post(
        ANKI_URL, json={"action": action, "params": params, "version": 6}
    ).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {resp['error']}")
    return resp["result"]
