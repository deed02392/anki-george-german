"""Shared Floodgate (LLM) helper.

Usage:
    from tools._llm import get_floodgate_token, call_llm
"""

import json
import subprocess
import sys

import requests

FLOODGATE_URL = "https://floodgate.g.apple.com/api/openai/v1/chat/completions"
FLOODGATE_MODEL = "aws:anthropic.claude-sonnet-4-20250514-v1:0"


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
