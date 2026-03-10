"""Manage a weekly launchd agent for auto-unsuspend."""

import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from string import Template

from . import PROJECT_ROOT

LABEL = "com.anki-george-german.unsuspend"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = PLIST_DIR / f"{LABEL}.plist"
STATE_DIR = Path.home() / ".local" / "share" / "anki-george-german"
LOG_PATH = STATE_DIR / "unsuspend.log"
TEMPLATES = Path(__file__).parent / "templates"

WEEKDAY_MAP = {
    "MON": 1, "TUE": 2, "WED": 3, "THU": 4,
    "FRI": 5, "SAT": 6, "SUN": 7,
}
DAY_NAMES = {v: k for k, v in WEEKDAY_MAP.items()}

ANKICONNECT_URL = "http://localhost:8765"
ANKICONNECT_TIMEOUT = 30  # seconds


def _uid():
    return os.getuid()


def _resolve_uv():
    uv = shutil.which("uv")
    if not uv:
        print("ERROR: 'uv' not found on PATH. Install it first.")
        raise SystemExit(1)
    return uv


def _validate_project(uv):
    if not (PROJECT_ROOT / "pyproject.toml").exists():
        print(f"ERROR: pyproject.toml not found in {PROJECT_ROOT}")
        raise SystemExit(1)
    result = subprocess.run(
        [uv, "run", "anki-german", "--help"],
        cwd=PROJECT_ROOT, capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        print("ERROR: 'uv run anki-german --help' failed:")
        print(result.stderr.decode())
        raise SystemExit(1)


def _launchctl_bootout():
    """Unload the agent. Ignores errors (already unloaded, missing plist)."""
    subprocess.run(
        ["launchctl", "bootout", f"gui/{_uid()}", str(PLIST_PATH)],
        capture_output=True,
    )


def _launchctl_bootstrap():
    """Load the agent. If already loaded, bootout first and retry."""
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{_uid()}", str(PLIST_PATH)],
        capture_output=True,
    )
    if result.returncode != 0:
        # Might be already loaded — bootout and retry
        _launchctl_bootout()
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{_uid()}", str(PLIST_PATH)],
            capture_output=True,
        )
        if result.returncode != 0:
            print("ERROR: launchctl bootstrap failed:")
            print(result.stderr.decode())
            raise SystemExit(1)


def _is_loaded():
    result = subprocess.run(
        ["launchctl", "print", f"gui/{_uid()}/{LABEL}"],
        capture_output=True,
    )
    return result.returncode == 0


# -- Anki launch / AnkiConnect wait -----------------------------------------

def ensure_anki():
    """Launch Anki in the background if it's not already running."""
    result = subprocess.run(["pgrep", "-x", "Anki"], capture_output=True)
    if result.returncode != 0:
        print("Launching Anki (background)...")
        subprocess.run(["open", "-g", "-a", "Anki"])
        return True
    return False


def wait_for_ankiconnect(timeout=ANKICONNECT_TIMEOUT):
    """Poll AnkiConnect until it responds, up to *timeout* seconds."""
    payload = json.dumps({"action": "version", "version": 6}).encode()
    for i in range(timeout):
        try:
            req = urllib.request.Request(
                ANKICONNECT_URL, data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            if i == timeout - 1:
                return False
            time.sleep(1)
    return False


# -- Commands ----------------------------------------------------------------

def install(args):
    day_key = args.day.upper()
    if day_key not in WEEKDAY_MAP:
        print(f"ERROR: --day must be one of {', '.join(WEEKDAY_MAP)}")
        raise SystemExit(1)
    weekday = WEEKDAY_MAP[day_key]
    hour = args.hour
    if not 0 <= hour <= 23:
        print("ERROR: --hour must be 0-23")
        raise SystemExit(1)
    max_cards = getattr(args, "max", 5) or 5

    uv = _resolve_uv()
    _validate_project(uv)

    # Read and substitute plist template
    plist_tmpl = Template((TEMPLATES / "unsuspend.plist").read_text())
    plist_text = plist_tmpl.substitute(
        UV_PATH=uv,
        PROJECT_PATH=PROJECT_ROOT,
        MAX=max_cards,
        WEEKDAY=weekday,
        HOUR=hour,
        LOG_PATH=LOG_PATH,
    )

    # Write plist
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_DIR.mkdir(parents=True, exist_ok=True)

    PLIST_PATH.write_text(plist_text)
    PLIST_PATH.chmod(0o600)

    # Load agent
    _launchctl_bootstrap()

    print(f"Installed launchd agent: {LABEL}")
    print(f"  Schedule:  {day_key} at {hour:02d}:00")
    print(f"  Max cards: {max_cards} per type")
    print(f"  Plist:     {PLIST_PATH}")
    print(f"  Log:       {LOG_PATH}")


def uninstall(_args):
    _launchctl_bootout()

    try:
        PLIST_PATH.unlink()
        print(f"Removed: {PLIST_PATH}")
    except FileNotFoundError:
        print("Nothing to remove (already uninstalled).")

    if LOG_PATH.exists():
        print(f"Log file preserved at {LOG_PATH}")


def status(_args):
    installed = PLIST_PATH.exists()
    loaded = _is_loaded()

    if not installed and not loaded:
        print("No launchd agent installed.")
        print("Run: anki-german schedule install")
        return

    print(f"Agent: {LABEL}")
    print(f"  Plist on disk: {'yes' if installed else 'no'}")
    print(f"  Loaded:        {'yes' if loaded else 'no'}")

    # Parse plist to show schedule
    if installed:
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(PLIST_PATH)
            root = tree.getroot()
            main_dict = root.find("dict")
            keys = list(main_dict)
            for i, el in enumerate(keys):
                if el.tag == "key" and el.text == "StartCalendarInterval":
                    cal_dict = keys[i + 1]
                    cal_keys = list(cal_dict)
                    weekday = hour = None
                    for j, cel in enumerate(cal_keys):
                        if cel.tag == "key" and cel.text == "Weekday":
                            weekday = int(cal_keys[j + 1].text)
                        if cel.tag == "key" and cel.text == "Hour":
                            hour = int(cal_keys[j + 1].text)
                    if weekday and hour is not None:
                        day_name = DAY_NAMES.get(weekday, str(weekday))
                        print(f"  Schedule:      {day_name} at {hour:02d}:00")
                    break
        except Exception:
            pass

    # Parse log for recent activity
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text().splitlines()
        if lines:
            last_timestamp = None
            last_run_lines = []
            current_run = []
            for line in lines:
                if line.startswith("=== ") and line.endswith(" ==="):
                    current_run = [line]
                    last_timestamp = line[4:-4]
                else:
                    current_run.append(line)
            last_run_lines = current_run

            if last_timestamp:
                print(f"  Last run:      {last_timestamp}")
                run_text = "\n".join(last_run_lines)
                if "ERROR:" in run_text:
                    for rl in last_run_lines:
                        if "ERROR:" in rl:
                            print(f"  Last result:   {rl.strip()}")
                            break
                elif "Unsuspended" in run_text:
                    for rl in last_run_lines:
                        if "Unsuspended" in rl:
                            print(f"  Last result:   {rl.strip()}")
                            break
                elif "Nothing to unsuspend" in run_text:
                    print("  Last result:   Nothing to unsuspend")

            print()
            print("Recent log output:")
            for line in lines[-10:]:
                print(f"  {line}")
    else:
        print("  Log:           (no runs yet)")


def run(args):
    """Called by launchd — launch Anki, wait for AnkiConnect, run unsuspend."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a")

    def emit(msg):
        log.write(msg + "\n")
        log.flush()
        print(msg)

    emit(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} ===")

    launched = ensure_anki()
    if launched:
        emit("Launched Anki (background)")

    if not wait_for_ankiconnect():
        emit(f"ERROR: AnkiConnect not responding after {ANKICONNECT_TIMEOUT}s")
        log.close()
        raise SystemExit(1)

    from .unsuspend_candidates import run as unsuspend_run
    import types
    unsuspend_args = types.SimpleNamespace(apply=True, max=args.max)
    unsuspend_run(unsuspend_args)

    emit("--- done ---")
    log.close()
