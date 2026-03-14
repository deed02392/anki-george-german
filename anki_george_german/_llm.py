"""Shared Floodgate (LLM) helper.

Usage:
    from anki_george_german._llm import get_floodgate_token, call_llm, call_llm_with_retry
"""

import json
import subprocess
import sys
import time

import requests

FLOODGATE_URL = "https://floodgate.g.apple.com/api/openai/v1/chat/completions"
FLOODGATE_MODEL = "aws:anthropic.claude-opus-4-6-v1"


def get_floodgate_token():
    """Get an OIDC token via appleconnect CLI."""
    result = subprocess.run(
        [
            "appleconnect", "getToken", "-t", "oauth", "-G", "pkce",
            "-C", "hvys3fcwcteqrvw3qzkvtk86viuoqv",
            "-o", "openid,dsid,accountname,email,groups",
            "--interactivity-type", "none",
        ],
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


def call_llm(messages, token, *, model=FLOODGATE_MODEL, max_tokens=4096):
    """Call Claude via Floodgate OpenAI-compatible API.

    Args:
        messages: List of message dicts (role + content).
        token: OIDC bearer token.
        model: Floodgate model identifier.
        max_tokens: Max response tokens.

    Returns:
        Parsed JSON from the response content.

    Raises:
        requests.HTTPError: On non-200 status.
        json.JSONDecodeError: If response isn't valid JSON.
    """
    resp = requests.post(
        FLOODGATE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "anki-george-german/1.0",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
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


def call_llm_text(messages, token, *, model=FLOODGATE_MODEL, max_tokens=4096):
    """Call Claude via Floodgate and return the raw text response (no JSON parsing).

    Args:
        messages: List of message dicts (role + content).
        token: OIDC bearer token.
        model: Floodgate model identifier.
        max_tokens: Max response tokens.

    Returns:
        Raw text string from the response.

    Raises:
        requests.HTTPError: On non-200 status.
    """
    resp = requests.post(
        FLOODGATE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "anki-george-german/1.0",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def call_llm_with_retry(messages, token, *, model=FLOODGATE_MODEL,
                         max_tokens=8192, expect_len=None):
    """Call the LLM with retry, 401 token refresh, and shape validation.

    Args:
        messages: Chat messages to send.
        token: OIDC bearer token (refreshed on 401).
        model: Floodgate model identifier.
        max_tokens: Max response tokens.
        expect_len: If set, require the response list to have this length.

    Returns:
        Parsed list on success, None on failure after retries.
    """
    for attempt in range(2):
        try:
            result = call_llm(messages, token, model=model,
                              max_tokens=max_tokens)
            if not isinstance(result, list):
                print(f"  Bad response shape (attempt {attempt + 1}): not a list")
                if attempt == 0:
                    continue
                return None

            if expect_len is not None and len(result) != expect_len:
                print(f"  Bad response length (attempt {attempt + 1}): "
                      f"expected {expect_len}, got {len(result)}")
                if attempt == 0:
                    continue
                return None

            return result

        except json.JSONDecodeError as e:
            print(f"  JSON parse error (attempt {attempt + 1}): {e}")
            if attempt == 0:
                continue
            return None
        except requests.HTTPError as e:
            print(f"  HTTP error (attempt {attempt + 1}): {e}")
            if hasattr(e, "response") and getattr(e.response, "status_code", 0) == 401:
                print("  Refreshing OIDC token...")
                token = get_floodgate_token()
            if attempt == 0:
                time.sleep(2)
                continue
            return None
        except requests.ConnectionError as e:
            print(f"  Connection error (attempt {attempt + 1}): "
                  f"cannot reach Floodgate. Check VPN/network.")
            if attempt == 0:
                time.sleep(5)
                continue
            return None

    return None
