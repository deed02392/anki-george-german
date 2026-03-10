"""Tests for schedule.py — launchd agent install/uninstall/status/_run."""

import json
import subprocess
import types
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread

import pytest

import anki_george_german.schedule as sched


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Redirect all schedule paths into tmp_path so nothing touches real disk."""
    state = tmp_path / "state"
    agents = tmp_path / "LaunchAgents"
    state.mkdir()
    agents.mkdir()

    monkeypatch.setattr(sched, "STATE_DIR", state)
    monkeypatch.setattr(sched, "LOG_PATH", state / "unsuspend.log")
    monkeypatch.setattr(sched, "PLIST_DIR", agents)
    monkeypatch.setattr(sched, "PLIST_PATH", agents / f"{sched.LABEL}.plist")

    return types.SimpleNamespace(state=state, agents=agents)


@pytest.fixture
def fake_uv(monkeypatch):
    """Make _resolve_uv() return a fake path, skip project validation."""
    monkeypatch.setattr(sched, "_resolve_uv", lambda: "/usr/local/bin/uv")
    monkeypatch.setattr(sched, "_validate_project", lambda uv: None)


@pytest.fixture
def no_launchctl(monkeypatch):
    """Stub out launchctl calls so tests never talk to the real agent system."""
    monkeypatch.setattr(sched, "_launchctl_bootstrap", lambda: None)
    monkeypatch.setattr(sched, "_launchctl_bootout", lambda: None)
    monkeypatch.setattr(sched, "_is_loaded", lambda: False)


def _make_args(**overrides):
    """Build a namespace mimicking argparse output for schedule install."""
    defaults = {"day": "MON", "hour": 9, "max": 5}
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


# -- Template substitution ---------------------------------------------------

class TestTemplateSubstitution:
    def test_plist_substitutes_all_placeholders(self):
        """Plist template produces valid XML with correct values."""
        from string import Template
        tmpl = Template((sched.TEMPLATES / "unsuspend.plist").read_text())
        result = tmpl.substitute(
            UV_PATH="/usr/local/bin/uv",
            PROJECT_PATH="/home/user/project",
            MAX=5,
            WEEKDAY=3,
            HOUR=14,
            LOG_PATH="/test/log",
        )
        assert "<string>/usr/local/bin/uv</string>" in result
        assert "<string>/home/user/project</string>" in result
        assert "<string>5</string>" in result
        assert "<integer>3</integer>" in result
        assert "<integer>14</integer>" in result
        assert sched.LABEL in result

    def test_plist_has_associated_bundle(self):
        """Plist includes AssociatedBundleIdentifiers for Anki."""
        from string import Template
        tmpl = Template((sched.TEMPLATES / "unsuspend.plist").read_text())
        result = tmpl.substitute(
            UV_PATH="/uv", PROJECT_PATH="/p", MAX=5,
            WEEKDAY=1, HOUR=9, LOG_PATH="/log",
        )
        assert "AssociatedBundleIdentifiers" in result
        assert "net.ankiweb.launcher" in result

    def test_plist_has_working_directory(self):
        """Plist includes WorkingDirectory pointing to the project."""
        from string import Template
        tmpl = Template((sched.TEMPLATES / "unsuspend.plist").read_text())
        result = tmpl.substitute(
            UV_PATH="/uv", PROJECT_PATH="/my/project", MAX=5,
            WEEKDAY=1, HOUR=9, LOG_PATH="/log",
        )
        assert "<key>WorkingDirectory</key>" in result
        assert "<string>/my/project</string>" in result

    def test_plist_invokes_uv_directly(self):
        """Plist ProgramArguments starts with uv, not /bin/bash."""
        from string import Template
        tmpl = Template((sched.TEMPLATES / "unsuspend.plist").read_text())
        result = tmpl.substitute(
            UV_PATH="/opt/homebrew/bin/uv", PROJECT_PATH="/p", MAX=5,
            WEEKDAY=1, HOUR=9, LOG_PATH="/log",
        )
        assert "/bin/bash" not in result
        assert "<string>/opt/homebrew/bin/uv</string>" in result

    def test_no_bash_wrapper_template(self):
        """The bash wrapper template no longer exists."""
        assert not (sched.TEMPLATES / "unsuspend.sh").exists()


# -- Install -----------------------------------------------------------------

class TestInstall:
    def test_creates_plist(self, dirs, fake_uv, no_launchctl):
        """Install writes the plist to the expected location."""
        sched.install(_make_args())
        assert (dirs.agents / f"{sched.LABEL}.plist").exists()

    def test_no_wrapper_created(self, dirs, fake_uv, no_launchctl):
        """Install does not create a bash wrapper script."""
        sched.install(_make_args())
        assert not (dirs.state / "unsuspend.sh").exists()

    def test_plist_permissions(self, dirs, fake_uv, no_launchctl):
        """Plist is mode 0o600."""
        sched.install(_make_args())
        mode = (dirs.agents / f"{sched.LABEL}.plist").stat().st_mode & 0o777
        assert mode == 0o600

    def test_plist_contains_uv_path(self, dirs, fake_uv, no_launchctl):
        """Plist embeds the resolved uv path."""
        sched.install(_make_args())
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<string>/usr/local/bin/uv</string>" in plist

    def test_plist_contains_max_arg(self, dirs, fake_uv, no_launchctl):
        """Plist embeds the --max argument."""
        sched.install(_make_args(max=10))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<string>10</string>" in plist

    def test_plist_weekday_mapping(self, dirs, fake_uv, no_launchctl):
        """Plist gets the correct weekday integer for each day."""
        for day, expected in sched.WEEKDAY_MAP.items():
            sched.install(_make_args(day=day))
            plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
            assert f"<integer>{expected}</integer>" in plist

    def test_plist_hour(self, dirs, fake_uv, no_launchctl):
        """Plist embeds the requested hour."""
        sched.install(_make_args(hour=17))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<integer>17</integer>" in plist

    def test_invalid_day_exits(self, dirs, fake_uv, no_launchctl):
        """Bad --day value exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            sched.install(_make_args(day="XDAY"))
        assert exc.value.code == 1

    def test_invalid_hour_exits(self, dirs, fake_uv, no_launchctl):
        """Hour outside 0-23 exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            sched.install(_make_args(hour=25))
        assert exc.value.code == 1

    def test_calls_launchctl_bootstrap(self, dirs, fake_uv, monkeypatch):
        """Install invokes _launchctl_bootstrap to load the agent."""
        calls = []
        monkeypatch.setattr(sched, "_launchctl_bootstrap", lambda: calls.append(1))
        monkeypatch.setattr(sched, "_launchctl_bootout", lambda: None)
        sched.install(_make_args())
        assert len(calls) == 1

    def test_reinstall_overwrites(self, dirs, fake_uv, no_launchctl):
        """Running install twice overwrites plist without error."""
        sched.install(_make_args(hour=9))
        sched.install(_make_args(hour=15))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<integer>15</integer>" in plist

    def test_day_case_insensitive(self, dirs, fake_uv, no_launchctl):
        """--day accepts lowercase input."""
        sched.install(_make_args(day="wed"))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<integer>3</integer>" in plist


# -- Uninstall ---------------------------------------------------------------

class TestUninstall:
    def test_removes_plist(self, dirs, fake_uv, no_launchctl):
        """Uninstall deletes the plist."""
        sched.install(_make_args())
        sched.uninstall(None)
        assert not (dirs.agents / f"{sched.LABEL}.plist").exists()

    def test_preserves_log(self, dirs, fake_uv, no_launchctl):
        """Uninstall does not delete the log file."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\ntest\n")
        sched.uninstall(None)
        assert log.exists()

    def test_idempotent(self, dirs, no_launchctl):
        """Uninstall when nothing is installed doesn't error."""
        sched.uninstall(None)  # no files exist
        sched.uninstall(None)  # still no error

    def test_calls_launchctl_bootout(self, dirs, fake_uv, monkeypatch):
        """Uninstall invokes _launchctl_bootout."""
        monkeypatch.setattr(sched, "_launchctl_bootstrap", lambda: None)
        calls = []
        monkeypatch.setattr(sched, "_launchctl_bootout", lambda: calls.append(1))
        sched.install(_make_args())
        sched.uninstall(None)
        assert len(calls) >= 1


# -- Status ------------------------------------------------------------------

class TestStatus:
    def test_not_installed(self, dirs, no_launchctl, capsys):
        """Status when nothing is installed shows install instructions."""
        sched.status(None)
        out = capsys.readouterr().out
        assert "No launchd agent installed" in out
        assert "anki-german schedule install" in out

    def test_installed_shows_schedule(self, dirs, fake_uv, no_launchctl, capsys):
        """Status after install shows the schedule day and hour."""
        sched.install(_make_args(day="WED", hour=14))
        sched.status(None)
        out = capsys.readouterr().out
        assert "WED" in out
        assert "14:00" in out

    def test_shows_last_run_timestamp(self, dirs, fake_uv, no_launchctl, capsys):
        """Status parses the timestamp from the log."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nUnsuspended 3 DE→EN card(s)\n--- done ---\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "2026-03-10 09:00:00" in out

    def test_shows_unsuspend_result(self, dirs, fake_uv, no_launchctl, capsys):
        """Status shows the unsuspend result from the log."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nUnsuspended 3 DE→EN card(s) and 2 Cloze card(s).\n--- done ---\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "Unsuspended" in out

    def test_shows_error_from_log(self, dirs, fake_uv, no_launchctl, capsys):
        """Status surfaces ERROR lines from the log."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nERROR: AnkiConnect not responding after 30s\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "ERROR:" in out

    def test_shows_nothing_to_unsuspend(self, dirs, fake_uv, no_launchctl, capsys):
        """Status shows 'Nothing to unsuspend' when log reports it."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nNothing to unsuspend.\n--- done ---\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "Nothing to unsuspend" in out


# -- ensure_anki / wait_for_ankiconnect -------------------------------------

class TestEnsureAnki:
    def test_launches_when_not_running(self, monkeypatch):
        """Calls 'open -g -a Anki' when pgrep finds no Anki process."""
        opened = []
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw:
            types.SimpleNamespace(returncode=1) if cmd[0] == "pgrep"
            else opened.append(cmd) or types.SimpleNamespace(returncode=0))
        assert sched.ensure_anki() is True
        assert opened and opened[0] == ["open", "-g", "-a", "Anki"]

    def test_skips_when_already_running(self, monkeypatch):
        """Does not launch Anki when pgrep finds it running."""
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw:
            types.SimpleNamespace(returncode=0))
        assert sched.ensure_anki() is False


class TestWaitForAnkiConnect:
    def test_returns_true_on_immediate_response(self, monkeypatch):
        """Returns True when AnkiConnect responds immediately."""
        monkeypatch.setattr(sched.urllib.request, "urlopen",
            lambda req, **kw: True)
        assert sched.wait_for_ankiconnect(timeout=1) is True

    def test_returns_false_after_timeout(self, monkeypatch):
        """Returns False when AnkiConnect never responds."""
        def fail(*a, **kw):
            raise ConnectionRefusedError()
        monkeypatch.setattr(sched.urllib.request, "urlopen", fail)
        monkeypatch.setattr(sched.time, "sleep", lambda s: None)
        assert sched.wait_for_ankiconnect(timeout=2) is False

    def test_retries_until_success(self, monkeypatch):
        """Succeeds after a few failed attempts."""
        attempts = []
        def maybe_succeed(*a, **kw):
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionRefusedError()
            return True
        monkeypatch.setattr(sched.urllib.request, "urlopen", maybe_succeed)
        monkeypatch.setattr(sched.time, "sleep", lambda s: None)
        assert sched.wait_for_ankiconnect(timeout=5) is True
        assert len(attempts) == 3


# -- _run command ------------------------------------------------------------

class TestRun:
    def test_calls_unsuspend(self, dirs, monkeypatch):
        """_run launches Anki if needed, waits, and calls unsuspend."""
        monkeypatch.setattr(sched, "ensure_anki", lambda: False)
        monkeypatch.setattr(sched, "wait_for_ankiconnect", lambda: True)
        unsuspend_calls = []
        monkeypatch.setattr(
            "anki_george_german.unsuspend_candidates.run",
            lambda args: unsuspend_calls.append(args),
        )
        sched.run(types.SimpleNamespace(max=5))
        assert len(unsuspend_calls) == 1
        assert unsuspend_calls[0].apply is True
        assert unsuspend_calls[0].max == 5

    def test_writes_log(self, dirs, monkeypatch):
        """_run writes timestamped entries to the log file."""
        monkeypatch.setattr(sched, "ensure_anki", lambda: False)
        monkeypatch.setattr(sched, "wait_for_ankiconnect", lambda: True)
        monkeypatch.setattr(
            "anki_george_german.unsuspend_candidates.run", lambda args: None,
        )
        sched.run(types.SimpleNamespace(max=5))
        log = (dirs.state / "unsuspend.log").read_text()
        assert "===" in log
        assert "--- done ---" in log

    def test_exits_on_ankiconnect_timeout(self, dirs, monkeypatch):
        """_run exits with code 1 when AnkiConnect doesn't respond."""
        monkeypatch.setattr(sched, "ensure_anki", lambda: True)
        monkeypatch.setattr(sched, "wait_for_ankiconnect", lambda: False)
        with pytest.raises(SystemExit) as exc:
            sched.run(types.SimpleNamespace(max=5))
        assert exc.value.code == 1
        log = (dirs.state / "unsuspend.log").read_text()
        assert "ERROR:" in log

    def test_logs_anki_launch(self, dirs, monkeypatch):
        """_run logs when it had to launch Anki."""
        monkeypatch.setattr(sched, "ensure_anki", lambda: True)
        monkeypatch.setattr(sched, "wait_for_ankiconnect", lambda: True)
        monkeypatch.setattr(
            "anki_george_german.unsuspend_candidates.run", lambda args: None,
        )
        sched.run(types.SimpleNamespace(max=5))
        log = (dirs.state / "unsuspend.log").read_text()
        assert "Launched Anki" in log


# -- Resolve UV / Validate --------------------------------------------------

class TestResolveUv:
    def test_uv_not_found_exits(self, monkeypatch):
        """Exits with code 1 when uv is not on PATH."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        with pytest.raises(SystemExit) as exc:
            sched._resolve_uv()
        assert exc.value.code == 1

    def test_uv_found_returns_path(self, monkeypatch):
        """Returns the path when uv is found."""
        monkeypatch.setattr("shutil.which", lambda x: "/opt/homebrew/bin/uv")
        assert sched._resolve_uv() == "/opt/homebrew/bin/uv"


class TestValidateProject:
    def test_missing_pyproject_exits(self, tmp_path, monkeypatch):
        """Exits when pyproject.toml doesn't exist."""
        monkeypatch.setattr(sched, "PROJECT_ROOT", tmp_path)
        with pytest.raises(SystemExit) as exc:
            sched._validate_project("/usr/local/bin/uv")
        assert exc.value.code == 1

    def test_uv_run_failure_exits(self, tmp_path, monkeypatch):
        """Exits when 'uv run anki-german --help' fails."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        monkeypatch.setattr(sched, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: types.SimpleNamespace(returncode=1, stderr=b"error"),
        )
        with pytest.raises(SystemExit) as exc:
            sched._validate_project("/usr/local/bin/uv")
        assert exc.value.code == 1


# -- Weekday mapping ---------------------------------------------------------

class TestWeekdayMap:
    def test_all_days_present(self):
        """All seven days are mapped."""
        assert len(sched.WEEKDAY_MAP) == 7

    def test_monday_is_1(self):
        """launchd weekday 1 = Monday."""
        assert sched.WEEKDAY_MAP["MON"] == 1

    def test_sunday_is_7(self):
        """launchd weekday 7 = Sunday."""
        assert sched.WEEKDAY_MAP["SUN"] == 7

    def test_reverse_map_consistent(self):
        """DAY_NAMES is the exact inverse of WEEKDAY_MAP."""
        for name, num in sched.WEEKDAY_MAP.items():
            assert sched.DAY_NAMES[num] == name
