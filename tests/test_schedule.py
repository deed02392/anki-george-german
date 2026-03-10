"""Tests for schedule.py — launchd agent install/uninstall/status/_run."""

import subprocess
import types
from pathlib import Path

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

    app_bundle = state / "Anki German Unsuspend.app"

    monkeypatch.setattr(sched, "STATE_DIR", state)
    monkeypatch.setattr(sched, "LOG_PATH", state / "unsuspend.log")
    monkeypatch.setattr(sched, "APP_BUNDLE", app_bundle)
    monkeypatch.setattr(sched, "AGENT_BINARY",
                        app_bundle / "Contents" / "MacOS" / "unsuspend-agent")
    monkeypatch.setattr(sched, "PLIST_DIR", agents)
    monkeypatch.setattr(sched, "PLIST_PATH", agents / f"{sched.LABEL}.plist")

    return types.SimpleNamespace(state=state, agents=agents,
                                 app_bundle=app_bundle)


@pytest.fixture
def fake_uv(monkeypatch):
    """Make _resolve_uv() return a fake path, skip project validation."""
    monkeypatch.setattr(sched, "_resolve_uv", lambda: "/usr/local/bin/uv")
    monkeypatch.setattr(sched, "_validate_project", lambda uv: None)


@pytest.fixture
def no_launchctl(monkeypatch):
    """Stub out launchctl and lsregister calls so tests never talk to the real system."""
    monkeypatch.setattr(sched, "_launchctl_bootstrap", lambda: None)
    monkeypatch.setattr(sched, "_launchctl_bootout", lambda: None)
    monkeypatch.setattr(sched, "_is_loaded", lambda: False)
    monkeypatch.setattr(sched, "_lsregister", lambda: None)


@pytest.fixture
def no_compile(monkeypatch):
    """Stub out Swift compilation."""
    monkeypatch.setattr(sched, "_compile_agent", lambda: None)


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
            AGENT_PATH="/test/unsuspend-agent",
            UV_PATH="/usr/local/bin/uv",
            PROJECT_PATH="/home/user/project",
            MAX=5,
            WEEKDAY=3,
            HOUR=14,
            LOG_PATH="/test/log",
        )
        assert "<string>/test/unsuspend-agent</string>" in result
        assert "<string>/usr/local/bin/uv</string>" in result
        assert "<string>/home/user/project</string>" in result
        assert "<string>5</string>" in result
        assert "<integer>3</integer>" in result
        assert "<integer>14</integer>" in result
        assert sched.LABEL in result

    def test_plist_has_associated_bundle(self):
        """Plist includes AssociatedBundleIdentifiers for our own app bundle."""
        from string import Template
        tmpl = Template((sched.TEMPLATES / "unsuspend.plist").read_text())
        result = tmpl.substitute(
            AGENT_PATH="/a", UV_PATH="/uv", PROJECT_PATH="/p", MAX=5,
            WEEKDAY=1, HOUR=9, LOG_PATH="/log",
        )
        assert "AssociatedBundleIdentifiers" in result
        assert sched.LABEL in result

    def test_plist_calls_agent_binary(self):
        """Plist ProgramArguments starts with the agent binary, not uv or bash."""
        from string import Template
        tmpl = Template((sched.TEMPLATES / "unsuspend.plist").read_text())
        result = tmpl.substitute(
            AGENT_PATH="/my/unsuspend-agent", UV_PATH="/uv",
            PROJECT_PATH="/p", MAX=5, WEEKDAY=1, HOUR=9, LOG_PATH="/log",
        )
        assert "/bin/bash" not in result
        # Agent binary is the first ProgramArguments string
        lines = result.splitlines()
        prog_idx = next(i for i, l in enumerate(lines) if "ProgramArguments" in l)
        first_string = lines[prog_idx + 2]  # skip <array>
        assert "/my/unsuspend-agent" in first_string

    def test_agent_swift_source_exists(self):
        """The Swift source for the agent binary exists."""
        assert (sched.TEMPLATES / "unsuspend_agent.swift").exists()

    def test_icon_generator_swift_source_exists(self):
        """The Swift source for the icon generator exists."""
        assert (sched.TEMPLATES / "generate_icon.swift").exists()

    def test_app_info_plist_template_exists(self):
        """The Info.plist template for the .app bundle exists."""
        assert (sched.TEMPLATES / "app_info.plist").exists()


# -- Compile agent -----------------------------------------------------------

class TestCompileAgent:
    def test_compiles_successfully(self, dirs):
        """_compile_agent produces a binary inside the .app bundle."""
        sched._compile_agent()
        assert sched.AGENT_BINARY.exists()

    def test_binary_is_executable(self, dirs):
        """Compiled binary has mode 0o700."""
        sched._compile_agent()
        mode = sched.AGENT_BINARY.stat().st_mode & 0o777
        assert mode == 0o700

    def test_creates_app_bundle(self, dirs):
        """_compile_agent creates a valid .app bundle structure."""
        sched._compile_agent()
        assert dirs.app_bundle.exists()
        assert (dirs.app_bundle / "Contents" / "Info.plist").exists()
        assert (dirs.app_bundle / "Contents" / "Resources" / "AppIcon.icns").exists()

    def test_info_plist_has_correct_bundle_id(self, dirs):
        """Info.plist contains the correct bundle identifier."""
        sched._compile_agent()
        info = (dirs.app_bundle / "Contents" / "Info.plist").read_text()
        assert sched.LABEL in info

    def test_compile_failure_exits(self, dirs, monkeypatch):
        """Exits with code 1 when swiftc fails."""
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: types.SimpleNamespace(returncode=1, stderr=b"error"),
        )
        with pytest.raises(SystemExit) as exc:
            sched._compile_agent()
        assert exc.value.code == 1


# -- Install -----------------------------------------------------------------

class TestInstall:
    def test_creates_plist(self, dirs, fake_uv, no_launchctl, no_compile):
        """Install writes the plist to the expected location."""
        sched.install(_make_args())
        assert (dirs.agents / f"{sched.LABEL}.plist").exists()

    def test_plist_permissions(self, dirs, fake_uv, no_launchctl, no_compile):
        """Plist is mode 0o600."""
        sched.install(_make_args())
        mode = (dirs.agents / f"{sched.LABEL}.plist").stat().st_mode & 0o777
        assert mode == 0o600

    def test_plist_contains_agent_path(self, dirs, fake_uv, no_launchctl, no_compile):
        """Plist embeds the agent binary path inside the .app bundle."""
        sched.install(_make_args())
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert str(sched.AGENT_BINARY) in plist

    def test_plist_contains_uv_path(self, dirs, fake_uv, no_launchctl, no_compile):
        """Plist passes uv path as an argument."""
        sched.install(_make_args())
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<string>/usr/local/bin/uv</string>" in plist

    def test_plist_contains_max_arg(self, dirs, fake_uv, no_launchctl, no_compile):
        """Plist embeds the --max argument."""
        sched.install(_make_args(max=10))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<string>10</string>" in plist

    def test_plist_weekday_mapping(self, dirs, fake_uv, no_launchctl, no_compile):
        """Plist gets the correct weekday integer for each day."""
        for day, expected in sched.WEEKDAY_MAP.items():
            sched.install(_make_args(day=day))
            plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
            assert f"<integer>{expected}</integer>" in plist

    def test_plist_hour(self, dirs, fake_uv, no_launchctl, no_compile):
        """Plist embeds the requested hour."""
        sched.install(_make_args(hour=17))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<integer>17</integer>" in plist

    def test_invalid_day_exits(self, dirs, fake_uv, no_launchctl, no_compile):
        """Bad --day value exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            sched.install(_make_args(day="XDAY"))
        assert exc.value.code == 1

    def test_invalid_hour_exits(self, dirs, fake_uv, no_launchctl, no_compile):
        """Hour outside 0-23 exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            sched.install(_make_args(hour=25))
        assert exc.value.code == 1

    def test_calls_compile_agent(self, dirs, fake_uv, no_launchctl, monkeypatch):
        """Install compiles the agent binary."""
        calls = []
        monkeypatch.setattr(sched, "_compile_agent", lambda: calls.append(1))
        sched.install(_make_args())
        assert len(calls) == 1

    def test_calls_launchctl_bootstrap(self, dirs, fake_uv, no_compile, monkeypatch):
        """Install invokes _launchctl_bootstrap to load the agent."""
        calls = []
        monkeypatch.setattr(sched, "_launchctl_bootstrap", lambda: calls.append(1))
        monkeypatch.setattr(sched, "_launchctl_bootout", lambda: None)
        monkeypatch.setattr(sched, "_lsregister", lambda: None)
        sched.install(_make_args())
        assert len(calls) == 1

    def test_reinstall_overwrites(self, dirs, fake_uv, no_launchctl, no_compile):
        """Running install twice overwrites plist without error."""
        sched.install(_make_args(hour=9))
        sched.install(_make_args(hour=15))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<integer>15</integer>" in plist

    def test_day_case_insensitive(self, dirs, fake_uv, no_launchctl, no_compile):
        """--day accepts lowercase input."""
        sched.install(_make_args(day="wed"))
        plist = (dirs.agents / f"{sched.LABEL}.plist").read_text()
        assert "<integer>3</integer>" in plist


# -- Uninstall ---------------------------------------------------------------

class TestUninstall:
    def test_removes_plist_and_app_bundle(self, dirs, fake_uv, no_launchctl, no_compile):
        """Uninstall deletes plist and .app bundle."""
        sched.install(_make_args())
        # Create a fake .app bundle since we stubbed compilation
        macos = dirs.app_bundle / "Contents" / "MacOS"
        macos.mkdir(parents=True, exist_ok=True)
        (macos / "unsuspend-agent").write_bytes(b"fake")
        sched.uninstall(None)
        assert not (dirs.agents / f"{sched.LABEL}.plist").exists()
        assert not dirs.app_bundle.exists()

    def test_preserves_log(self, dirs, fake_uv, no_launchctl, no_compile):
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

    def test_calls_launchctl_bootout(self, dirs, fake_uv, no_compile, monkeypatch):
        """Uninstall invokes _launchctl_bootout."""
        monkeypatch.setattr(sched, "_launchctl_bootstrap", lambda: None)
        monkeypatch.setattr(sched, "_lsregister", lambda: None)
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

    def test_installed_shows_schedule(self, dirs, fake_uv, no_launchctl, no_compile, capsys):
        """Status after install shows the schedule day and hour."""
        sched.install(_make_args(day="WED", hour=14))
        sched.status(None)
        out = capsys.readouterr().out
        assert "WED" in out
        assert "14:00" in out

    def test_shows_last_run_timestamp(self, dirs, fake_uv, no_launchctl, no_compile, capsys):
        """Status parses the timestamp from the log."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nUnsuspended 3 DE→EN card(s)\n--- done ---\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "2026-03-10 09:00:00" in out

    def test_shows_unsuspend_result(self, dirs, fake_uv, no_launchctl, no_compile, capsys):
        """Status shows the unsuspend result from the log."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nUnsuspended 3 DE→EN card(s) and 2 Cloze card(s).\n--- done ---\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "Unsuspended" in out

    def test_shows_error_from_log(self, dirs, fake_uv, no_launchctl, no_compile, capsys):
        """Status surfaces ERROR lines from the log."""
        sched.install(_make_args())
        log = dirs.state / "unsuspend.log"
        log.write_text("=== 2026-03-10 09:00:00 ===\nERROR: AnkiConnect not responding after 30s\n")
        sched.status(None)
        out = capsys.readouterr().out
        assert "ERROR:" in out

    def test_shows_nothing_to_unsuspend(self, dirs, fake_uv, no_launchctl, no_compile, capsys):
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
        """Calls 'open -g -j -a Anki' when pgrep finds no Anki process."""
        opened = []
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw:
            types.SimpleNamespace(returncode=1) if cmd[0] == "pgrep"
            else opened.append(cmd) or types.SimpleNamespace(returncode=0))
        assert sched.ensure_anki() is True
        assert opened and opened[0] == ["open", "-g", "-j", "-a", "Anki"]

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


# -- _run command (manual test path) ----------------------------------------

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
