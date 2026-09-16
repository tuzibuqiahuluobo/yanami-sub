"""The desktop-side Python interpreter discovery.

The upstream probe in ``RuntimeEnvironment._find_system_python`` has two
defects that this module exists to route around, and both are pinned here so a
future reader can tell intended behaviour from an accident:

* it compares the **complete** version tuple, so any extra token on the
  interpreter's stdout turns a match into a silent miss;
* it only consults ``shutil.which``, so an interpreter the ``py`` launcher
  knows about but ``PATH`` does not is never found at all.

Finding no interpreter is what sends the install down the path that fails on
some Windows machines, so both defects are load-bearing, not cosmetic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from desktop.backend.resources import python_interpreter as pi


class FakeRunner:
    """A ``subprocess.run`` stand-in keyed by the interpreter path.

    ``outputs`` maps a path to ``(returncode, stdout)``. Anything not listed
    behaves like a file that is not a Python interpreter at all.
    """

    def __init__(self, outputs: dict[str, tuple[int, str]]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        key = str(command[0])
        returncode, stdout = self.outputs.get(key, (2, ""))
        return subprocess.CompletedProcess(
            args=list(command), returncode=returncode, stdout=stdout, stderr=""
        )


@pytest.fixture()
def python_exe(tmp_path: Path) -> Path:
    """A real file standing in for an interpreter.

    ``probe_interpreter`` requires the path to exist before it runs anything,
    which is the check that keeps a bare ``python`` shim from being probed
    forever. The extension is deliberately not ``.exe``: nothing here executes
    it -- ``FakeRunner`` answers every command -- and a test that creates an
    executable is a test that cannot run under a policy that forbids writing
    them.
    """

    executable = tmp_path / "python-interpreter"
    executable.write_bytes(b"MZ")
    return executable


# --------------------------------------------------------------------------
# The version judgement
# --------------------------------------------------------------------------


def test_probe_accepts_the_version_the_lock_is_built_for(python_exe: Path) -> None:
    runner = FakeRunner({str(python_exe): (0, "3.12.6\n")})

    outcome = pi.probe_interpreter(python_exe, runner=runner)

    assert outcome.ok
    assert outcome.version == "3.12.6"
    assert outcome.path is not None


def test_probe_reads_the_version_numbers_not_the_whole_line(
    python_exe: Path,
) -> None:
    """The regression upstream does not survive.

    Upstream builds ``tuple(int(p) for p in stdout.split())`` and compares it
    to ``(3, 12)``. An interpreter whose stdout carries anything more -- a
    wrapper, a startup hook, a warning -- yields a longer tuple, the comparison
    is false, and the interpreter is discarded without a word. Reading the
    %d.%d.%d we ask for, instead of whatever arrives, is the fix.
    """

    noisy = FakeRunner({str(python_exe): (0, "3.12.6\nextra noise\n")})
    assert pi.probe_interpreter(python_exe, runner=noisy).ok

    trailing = FakeRunner({str(python_exe): (0, "3.12.6 (main, Nov 2025)\n")})
    outcome = pi.probe_interpreter(python_exe, runner=trailing)
    assert outcome.ok, outcome.reason
    assert outcome.version == "3.12.6"


def test_probe_rejects_a_different_minor_version(python_exe: Path) -> None:
    runner = FakeRunner({str(python_exe): (0, "3.13.1\n")})

    outcome = pi.probe_interpreter(python_exe, runner=runner)

    assert not outcome.ok
    assert "3.12" in outcome.reason
    assert "3.13" in outcome.reason


def test_probe_reports_a_missing_file_rather_than_running_it(tmp_path: Path) -> None:
    runner = FakeRunner({})

    outcome = pi.probe_interpreter(tmp_path / "absent-interpreter", runner=runner)

    assert not outcome.ok
    assert runner.calls == [], "a missing file must not be executed"


def test_probe_reports_a_non_python_executable(python_exe: Path) -> None:
    """``cmd.exe`` prints a banner and exits 0; that is not a version."""

    runner = FakeRunner({str(python_exe): (0, "Microsoft Windows [Version 10]\n")})

    outcome = pi.probe_interpreter(python_exe, runner=runner)

    assert not outcome.ok
    assert "版本" in outcome.reason


def test_probe_reports_a_failing_interpreter(python_exe: Path) -> None:
    runner = FakeRunner({str(python_exe): (1, "")})

    outcome = pi.probe_interpreter(python_exe, runner=runner)

    assert not outcome.ok
    assert "退出码" in outcome.reason


def test_probe_isolates_the_interpreter_from_the_environment(
    python_exe: Path,
) -> None:
    """``-I`` because a stray PYTHONSTARTUP would otherwise join the stdout."""

    runner = FakeRunner({str(python_exe): (0, "3.12.6\n")})

    pi.probe_interpreter(python_exe, runner=runner)

    assert runner.calls[0][1] == "-I"


# --------------------------------------------------------------------------
# The search surface
# --------------------------------------------------------------------------


def test_launcher_row_keeps_a_path_containing_spaces() -> None:
    """Splitting on whitespace truncates this path; the truncated directory
    does not exist, so the interpreter is rejected for the wrong reason."""

    line = (
        r"-V:Astral/CPython3.12.13 E:\FineSub Desktop\runtime"
        r"\python-builds\cpython-3.12.13-windows-x86_64-none\python.exe"
    )

    parsed = pi._path_from_launcher_line(line)

    assert parsed is not None
    assert "FineSub Desktop" in str(parsed)


def test_launcher_row_accepts_a_quoted_path() -> None:
    line = r'-V:3.12          "C:\Program Files\Python312\python.exe"'

    parsed = pi._path_from_launcher_line(line)

    assert parsed == Path(r"C:\Program Files\Python312\python.exe")


def test_launcher_row_accepts_an_alias_label() -> None:
    """The label may be ``Astral/CPython3.12.13`` rather than a number, which
    is why the path decides and the label is only skipped."""

    line = r"-V:3.12 *        G:\python3.12\python.exe"

    assert pi._path_from_launcher_line(line) == Path(r"G:\python3.12\python.exe")


def test_launcher_row_ignores_output_that_is_not_a_row() -> None:
    assert pi._path_from_launcher_line("no interpreters found") is None


def test_launcher_candidates_skip_entries_that_are_not_interpreters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``py -0p`` lists directory entries too -- e.g. the minor-version link
    directory for an interpreter uv installed. Probing those fails slowly, so
    they are dropped by name first."""

    # The stub runner is keyed by the executable path, so the launcher lookup
    # has to answer with that same string.
    monkeypatch.setattr(
        pi.shutil, "which", lambda name: "py" if name == "py" else None
    )
    runner = FakeRunner(
        {
            "py": (
                0,
                "-V:3.12 *        G:\\python3.12\\python.exe\n"
                "-V:3.10          E:\\FineSub Desktop\\runtime\\python-builds"
                "\\cpython-3.10.19-windows-x86_64-none\n",
            )
        }
    )

    found = pi._py_launcher_candidates(runner=runner, rejected=[])

    assert found == [Path(r"G:\python3.12\python.exe")]


# --------------------------------------------------------------------------
# Choosing between candidates
# --------------------------------------------------------------------------


def test_preferred_interpreter_is_tried_before_discovery(
    tmp_path: Path, python_exe: Path
) -> None:
    chosen = tmp_path / "chosen-interpreter"
    chosen.write_bytes(b"MZ")
    runner = FakeRunner({str(chosen): (0, "3.12.9\n")})

    outcome = pi.locate_interpreter(preferred=chosen, runner=runner)

    assert outcome.ok
    assert outcome.path == chosen.resolve()
    assert runner.calls[0][0] == str(chosen.resolve())


def test_a_stale_preference_falls_back_instead_of_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stored path whose interpreter has been uninstalled must not fail the
    install: it degrades to discovery, and is recorded as a rejection so the
    user can see their choice was the problem."""

    good = tmp_path / "good-interpreter"
    good.write_bytes(b"MZ")
    runner = FakeRunner({str(good.resolve()): (0, "3.12.6\n")})
    monkeypatch.setattr(pi.shutil, "which", lambda name: str(good) if name == "python" else None)
    monkeypatch.setattr(pi, "_py_launcher_candidates", lambda **kwargs: [])
    monkeypatch.setattr(pi, "common_install_locations", lambda environ=None: [])

    rejected: list[pi.RejectedCandidate] = []
    outcome = pi.locate_interpreter(
        preferred=tmp_path / "gone-interpreter", runner=runner, rejected=rejected
    )

    assert outcome.ok
    assert outcome.path == good.resolve()
    assert [item.path.name for item in rejected] == ["gone-interpreter"]


def test_the_message_says_which_python_was_seen_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of recording rejections: a user whose Python exists but
    is the wrong version needs to be told that, not told to install one."""

    older = tmp_path / "python311-interpreter"
    older.write_bytes(b"MZ")
    runner = FakeRunner({str(older.resolve()): (0, "3.11.9\n")})
    monkeypatch.setattr(pi.shutil, "which", lambda name: str(older) if name == "python" else None)
    monkeypatch.setattr(pi, "_py_launcher_candidates", lambda **kwargs: [])
    monkeypatch.setattr(pi, "common_install_locations", lambda environ=None: [])

    rejected: list[pi.RejectedCandidate] = []
    outcome = pi.locate_interpreter(runner=runner, rejected=rejected)
    message = pi.describe_failure(rejected)

    assert not outcome.ok
    assert str(older) in message
    assert "3.11" in message
    assert "3.12" in message


def test_no_candidates_at_all_still_explains_what_to_do() -> None:
    message = pi.describe_failure([])

    assert "3.12" in message
    assert "PATH" in message


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def test_saved_interpreter_round_trips(tmp_path: Path, python_exe: Path) -> None:
    written = pi.save_configured_interpreter(tmp_path, python_exe)

    assert written == python_exe.resolve()
    assert pi.load_configured_interpreter(tmp_path) == python_exe.resolve()


def test_clearing_the_choice_restores_discovery(tmp_path: Path, python_exe: Path) -> None:
    pi.save_configured_interpreter(tmp_path, python_exe)

    pi.save_configured_interpreter(tmp_path, None)

    assert pi.load_configured_interpreter(tmp_path) is None


def test_a_damaged_preference_file_is_not_fatal(tmp_path: Path) -> None:
    """This is read on the start-up path; a truncated JSON file is worth less
    than the application opening."""

    pi.config_path(tmp_path).write_text("{ not json", encoding="utf-8")

    assert pi.load_configured_interpreter(tmp_path) is None


def test_a_preference_file_with_the_wrong_shape_is_ignored(tmp_path: Path) -> None:
    pi.config_path(tmp_path).write_text(
        json.dumps({"interpreter": 42}), encoding="utf-8"
    )

    assert pi.load_configured_interpreter(tmp_path) is None


def test_an_oversized_preference_file_is_ignored(tmp_path: Path) -> None:
    pi.config_path(tmp_path).write_text(
        json.dumps({"interpreter": "x" * (pi._MAX_BYTES + 1)}), encoding="utf-8"
    )

    assert pi.load_configured_interpreter(tmp_path) is None


def test_an_empty_interpreter_value_means_discover(tmp_path: Path) -> None:
    pi.save_configured_interpreter(tmp_path, None)

    assert pi.load_configured_interpreter(tmp_path) is None


def test_development_python_wins_over_the_stored_choice(
    tmp_path: Path, python_exe: Path
) -> None:
    """Someone already running inside an interpreter means that one."""

    pi.save_configured_interpreter(tmp_path, python_exe)

    preferred = pi.locate_preferred(
        development_python=Path(r"C:\dev\python.exe"), user_data=tmp_path
    )

    assert preferred == Path(r"C:\dev\python.exe")


def test_locate_preferred_is_none_without_any_choice(tmp_path: Path) -> None:
    assert pi.locate_preferred(development_python=None, user_data=tmp_path) is None


# --------------------------------------------------------------------------
# The prober handed to RuntimeEnvironment
# --------------------------------------------------------------------------


def test_prober_probes_once_and_memoises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``RuntimeEnvironment.status()`` calls this from the bridge thread on
    every poll, and it spawns subprocesses."""

    good = tmp_path / "python-interpreter"
    good.write_bytes(b"MZ")
    runner = FakeRunner({str(good.resolve()): (0, "3.12.6\n")})
    prober = pi.make_prober(preferred=good, runner=runner)

    assert prober() == good.resolve()
    assert prober() == good.resolve()
    assert len(runner.calls) == 1


def test_prober_reports_its_finding_to_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rejection list has to leave the prober, or the reason the install
    cannot proceed dies with it.

    Discovery is stubbed out because this test is about the callback, not about
    what happens to be installed on the machine running the suite.
    """

    monkeypatch.setattr(pi.shutil, "which", lambda name: None)
    monkeypatch.setattr(pi, "_py_launcher_candidates", lambda **kwargs: [])
    monkeypatch.setattr(pi, "common_install_locations", lambda environ=None: [])

    seen: list[tuple[pi.ProbeOutcome, list[pi.RejectedCandidate]]] = []
    prober = pi.make_prober(
        preferred=None,
        runner=FakeRunner({}),
        environ={},
        on_result=lambda outcome, rejected: seen.append((outcome, rejected)),
    )

    assert prober() is None
    assert len(seen) == 1
    outcome, rejected = seen[0]
    assert not outcome.ok
    assert isinstance(rejected, list)
