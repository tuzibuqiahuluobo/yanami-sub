"""Which Python the managed runtime is built from, and how we find it.

The pipeline runs inside a virtual environment that ``uv`` creates under the
installation root. That environment has to be created *from* a CPython 3.12, and
there are exactly two ways to get one:

* ``uv`` downloads and installs its own (``uv python install``), or
* ``uv venv`` builds from an interpreter that already exists on the machine.

The second is what we want, and it is also the one that fails on some Windows
machines. ``uv`` implements patch-level upgrades by pointing a *junction* named
after the minor version (``cpython-3.12-windows-x86_64-none``) at the patch
directory it installed. Creating or traversing that link can fail outright with
``os error 448`` (``ERROR_UNTRUSTED_MOUNT_POINT``, "cannot traverse the path
because it contains an untrusted mount point"), which surfaces to the user as
"资源安装失败" with a 2.8 GB download already spent and no way forward: pressing
retry walks the identical path.

Reusing an existing interpreter never touches a junction -- ``uv venv --python
<absolute path>`` just reads it -- so this module exists to make that branch
reachable. It does the same job as ``RuntimeEnvironment._find_system_python``
but from the desktop side, where we can fix two things the upstream probe does
not:

* **The version comparison.** Upstream builds ``expected = (3, 12)`` and
  compares it to ``tuple(int(p) for p in stdout.split())`` -- the **complete**
  version. It happens to be true for a bare ``python``, but any extra token on
  stdout (a wrapper script, a startup hook) makes it a 3-tuple and the
  interpreter is discarded in silence. We compare ``[:2]`` and record why a
  candidate was rejected instead of swallowing it.
* **The search surface.** Upstream only tries ``shutil.which`` for
  ``py``/``python3.12``/``python``. A Python installed with the official
  installer and *without* "Add to PATH" is registered under PEP 514 and visible
  to the ``py`` launcher, but invisible to ``shutil.which`` -- so it is never
  found, and the install falls through to the junction branch.

A caller may also name an interpreter outright. That is the escape hatch for a
machine where automatic discovery does not turn one up: the choice is persisted
here, read at start-up, and handed to ``RuntimeEnvironment`` through its
``system_python_prober`` seam -- a keyword that already exists upstream, so none
of this requires forking the pinned ``finesub_bootstrap``.

Nothing in this module downloads, installs or writes outside ``user-data``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Iterable, Sequence

from finesub_bootstrap.fsops import write_atomic

CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]

#: The interpreter version the packaged lock is built for. Matches
#: ``pylock.win-py312.toml`` and ``RuntimeEnvironment.python_version``.
PYTHON_VERSION = "3.12"

#: ``user-data/python.json``. Next to ``settings.json`` and for the same
#: reason: this is desktop program state, not a pipeline option, and the
#: pipeline never reads it.
CONFIG_FILENAME = "python.json"
SCHEMA_VERSION = 1

#: A chosen path, not a document.
_MAX_BYTES = 8 * 1024
_PROBE_TIMEOUT_SECONDS = 15.0


def _write_config(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_atomic(path, text)


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    """What probing one interpreter found.

    ``path`` is set only when ``ok`` is true. ``reason`` is user-facing Chinese
    on failure, because it travels all the way to the resources page.
    """

    ok: bool
    path: Path | None = None
    version: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    path: Path
    reason: str


def config_path(user_data: Path) -> Path:
    return user_data.expanduser().resolve() / CONFIG_FILENAME


def load_configured_interpreter(user_data: Path) -> Path | None:
    """The interpreter the user chose, if any.

    Never raises: this sits on the start-up path, and a damaged preference is
    worth less than the application opening. A missing or empty value means
    "discover one", not "there is none".
    """

    path = config_path(user_data)
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > _MAX_BYTES:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("interpreter")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return Path(value).expanduser() if value else None


def save_configured_interpreter(user_data: Path, interpreter: Path | None) -> Path | None:
    """Persist the choice; ``None`` clears it and restores auto-discovery.

    Returns the resolved path that was written, or ``None`` when cleared.
    """

    resolved = (
        interpreter.expanduser().resolve() if interpreter is not None else None
    )
    _write_config(
        config_path(user_data),
        {
            "schema": SCHEMA_VERSION,
            "pythonVersion": PYTHON_VERSION,
            "interpreter": str(resolved) if resolved is not None else "",
        },
    )
    return resolved


def _run(
    command: Sequence[str],
    *,
    runner: CommandRunner | None,
) -> subprocess.CompletedProcess[str] | None:
    """One probe subprocess, with every failure turned into ``None``.

    A missing executable, a hang, a non-Python file: all of them mean "not this
    candidate", and none of them may take the application down.
    """

    execute = subprocess.run if runner is None else runner
    try:
        return execute(
            list(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_SECONDS,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt"
                else 0
            ),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


#: Reads the version tuple as *numbers*, so an extra token on stdout cannot
#: turn a match into a mismatch the way a whole-line `tuple(int(...))` does.
_VERSION_SOURCE = (
    "import sys;print('%d.%d.%d' % sys.version_info[:3])"
)


def probe_interpreter(
    path: Path,
    *,
    python_version: str = PYTHON_VERSION,
    runner: CommandRunner | None = None,
) -> ProbeOutcome:
    """Whether ``path`` is a usable CPython of the version the lock needs.

    ``-I`` keeps the probe away from ``PYTHONPATH``/``PYTHONSTARTUP`` and the
    user's site-packages, so the answer describes the interpreter rather than
    the environment it happens to be launched in.
    """

    target = path.expanduser()
    try:
        resolved = target.resolve()
    except OSError:
        return ProbeOutcome(False, reason=f"路径无法解析：{target}")
    if not resolved.is_file():
        return ProbeOutcome(False, reason=f"找不到可执行文件：{resolved}")

    result = _run([str(resolved), "-I", "-c", _VERSION_SOURCE], runner=runner)
    if result is None:
        return ProbeOutcome(
            False, reason=f"无法运行该程序，可能不是 Python 解释器：{resolved}"
        )
    if result.returncode != 0:
        return ProbeOutcome(
            False, reason=f"该程序执行失败（退出码 {result.returncode}）：{resolved}"
        )

    # Find the version *anywhere* in what came back, rather than trusting the
    # last line to be only the version. The interpreter we asked is a plain
    # CPython, but a wrapper script, a startup hook or a warning on the same
    # stream is enough to put something else there -- and treating that as
    # "not a Python" is the same silent-miss shape this module exists to fix.
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout or "")
    if match is None:
        return ProbeOutcome(False, reason=f"无法识别版本号：{resolved}")

    major, minor = match.group(1), match.group(2)
    version = f"{major}.{minor}.{match.group(3)}"
    if f"{major}.{minor}" != python_version:
        return ProbeOutcome(
            False,
            reason=(
                f"需要 Python {python_version}，该解释器是 "
                f"{major}.{minor}：{resolved}"
            ),
        )
    return ProbeOutcome(True, path=resolved, version=version)


def _py_launcher_candidates(
    *,
    runner: CommandRunner | None,
    rejected: list[RejectedCandidate],
) -> list[Path]:
    """Interpreters the ``py`` launcher knows about, PATH or not.

    This is the surface upstream does not consult. ``py -0p`` lists every
    registered interpreter with its path, which is exactly the set a user gets
    from the official installer whether or not they ticked "Add to PATH".
    """

    launcher = shutil.which("py")
    if not launcher:
        return []
    result = _run([launcher, "-0p"], runner=runner)
    if result is None or result.returncode != 0:
        return []

    found: list[Path] = []
    for line in (result.stdout or "").splitlines():
        # Rows look like `-V:3.12 *        C:\Python312\python.exe`; the active
        # one carries a `*`. Version labels may be aliases rather than numbers
        # ("Astral/CPython3.12.13"), so the path is the only thing we trust --
        # and it is also the thing that decides, since probing the interpreter
        # answers the version question far more reliably than parsing a label.
        stripped = line.strip()
        if not stripped.startswith("-V:"):
            continue
        candidate = _path_from_launcher_line(stripped)
        if candidate is None:
            continue
        # The launcher lists implementations we cannot use as the *base* for
        # this runtime (PyPy, GraalPy) and directory entries that are not an
        # interpreter at all. Both are cheap to drop here; probing would
        # reject them anyway, just more slowly.
        if not candidate.name.casefold().startswith("python"):
            continue
        found.append(candidate)
    return found


#: One `py -0p` row: a version label, a run of spaces, then the path. The
#: label is never a number we can use -- it may be an alias such as
#: "Astral/CPython3.12.13" -- so it is skipped and only the path is kept.
_LAUNCHER_ROW = re.compile(
    r"""^-V:\S+\s+\*?\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>\S.*?))\s*$"""
)


def _path_from_launcher_line(line: str) -> Path | None:
    """The path at the end of one ``py -0p`` row, if there is one.

    Splitting on whitespace is not enough: a path may contain spaces
    (``E:\\FineSub Desktop\\runtime\\...``), and truncating it yields a
    directory that does not exist, which then reports the unhelpful "not a
    Python interpreter" instead of the real answer.
    """

    match = _LAUNCHER_ROW.match(line)
    if match is None:
        return None
    value = match.group("quoted") or match.group("bare")
    if not value:
        return None
    return Path(value.strip().strip('"'))


def common_install_locations(
    environ: dict[str, str] | None = None,
) -> list[Path]:
    """Where the official installer puts a per-user or machine-wide Python.

    Reached only after ``py`` and ``PATH`` have both failed to produce one, so
    this is a last resort rather than the primary surface. Newest first, since
    a machine with several installed versions almost always wants the recent
    one and the version check rejects the rest anyway.
    """

    env = os.environ if environ is None else environ
    roots: list[Path] = []
    local = env.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Programs" / "Python")
    program_files = env.get("ProgramFiles")
    if program_files:
        roots.append(Path(program_files))

    found: list[Path] = []
    for root in roots:
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in reversed(entries):
            if not entry.name.casefold().startswith("python"):
                continue
            executable = entry / "python.exe"
            if executable.is_file():
                found.append(executable)
    return found


def candidate_interpreters(
    *,
    python_version: str = PYTHON_VERSION,
    runner: CommandRunner | None = None,
    environ: dict[str, str] | None = None,
    rejected: list[RejectedCandidate] | None = None,
) -> list[Path]:
    """Every path worth probing, most-likely first, de-duplicated."""

    env = os.environ if environ is None else environ
    bucket = rejected if rejected is not None else []
    ordered: list[Path] = []

    for name in (f"python{python_version}", "python"):
        executable = shutil.which(name)
        if executable:
            ordered.append(Path(executable))
    ordered.extend(
        _py_launcher_candidates(runner=runner, rejected=bucket)
    )
    ordered.extend(common_install_locations(env))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in ordered:
        try:
            key = os.path.normcase(os.path.abspath(candidate))
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def locate_interpreter(
    *,
    preferred: Path | None = None,
    python_version: str = PYTHON_VERSION,
    runner: CommandRunner | None = None,
    environ: dict[str, str] | None = None,
    rejected: list[RejectedCandidate] | None = None,
) -> ProbeOutcome:
    """The best interpreter for the managed runtime, or why there is none.

    ``preferred`` is the user's explicit choice and is tried first. It is
    *validated*, not merely trusted: a path that has been uninstalled or
    retargeted must fall back to discovery rather than fail the install with a
    confusing error. Only when nothing is found at all do the recorded
    rejections become the message, because that is the case where the user
    needs to know their Python was seen and refused.
    """

    bucket = rejected if rejected is not None else []

    if preferred is not None:
        outcome = probe_interpreter(
            preferred, python_version=python_version, runner=runner
        )
        if outcome.ok:
            return outcome
        bucket.append(RejectedCandidate(preferred.expanduser(), outcome.reason))

    for candidate in candidate_interpreters(
        python_version=python_version,
        runner=runner,
        environ=environ,
        rejected=bucket,
    ):
        outcome = probe_interpreter(
            candidate, python_version=python_version, runner=runner
        )
        if outcome.ok:
            return outcome
        bucket.append(RejectedCandidate(candidate, outcome.reason))

    return ProbeOutcome(False)


def locate_preferred(
    *,
    development_python: Path | None,
    user_data: Path | None,
) -> Path | None:
    """The interpreter to try first, without probing anything yet.

    A development run wins over the stored choice: whoever passed
    ``--dev``/``YANAMI_SUB_DEV_URL`` is already running inside the interpreter
    they mean. Probing happens later, inside the prober, so that a stored path
    which has since been uninstalled degrades to auto-discovery instead of
    failing the install.
    """

    if development_python is not None:
        return development_python
    if user_data is None:
        return None
    return load_configured_interpreter(user_data)


def describe_failure(rejected: Iterable[RejectedCandidate]) -> str:
    """The explanation shown when no interpreter could be used."""

    items = list(rejected)
    if not items:
        return (
            f"没有找到 Python {PYTHON_VERSION}。请安装 64 位 Python "
            f"{PYTHON_VERSION}（安装时勾选“Add python.exe to PATH”），"
            "或手动指定已有的解释器。"
        )
    lines = [f"已检查 {len(items)} 个候选解释器，没有可用的 Python {PYTHON_VERSION}："]
    for item in items[:5]:
        lines.append(f"· {item.path} — {item.reason}")
    if len(items) > 5:
        lines.append(f"· 另有 {len(items) - 5} 个候选被跳过")
    lines.append("可手动指定一个 Python 解释器。")
    return "\n".join(lines)


def make_prober(
    *,
    preferred: Path | None,
    python_version: str = PYTHON_VERSION,
    runner: CommandRunner | None = None,
    environ: dict[str, str] | None = None,
    on_result: Callable[[ProbeOutcome, list[RejectedCandidate]], None] | None = None,
) -> Callable[[], Path | None]:
    """A ``system_python_prober`` for ``RuntimeEnvironment``.

    Probed once and memoised, matching what the upstream class does with its own
    probe: ``status()`` is called from the bridge thread on every poll, and this
    one spawns subprocesses.
    """

    state: dict[str, object] = {"done": False, "path": None}

    def prober() -> Path | None:
        if state["done"]:
            return state["path"]  # type: ignore[return-value]
        rejected: list[RejectedCandidate] = []
        outcome = locate_interpreter(
            preferred=preferred,
            python_version=python_version,
            runner=runner,
            environ=environ,
            rejected=rejected,
        )
        state["done"] = True
        state["path"] = outcome.path
        if on_result is not None:
            on_result(outcome, rejected)
        return outcome.path

    return prober
