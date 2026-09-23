from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib.metadata
from io import StringIO
from pathlib import Path
import shutil

from finesub_bootstrap.environment import (
    RuntimeEnvironment,
    WorkerContext,
    shared_environment_overrides,
    token_counter_overrides,
)
from finesub_bootstrap.capabilities import required_capabilities
from finesub_bootstrap.model_caches import (
    PIPELINE_MODEL_IDS,
    SEPARATOR_CHECKPOINT,
    existing_hf_home,
    existing_separator_dir,
    managed_model_dirs,
    missing_pipeline_models,
)
from finesub_bootstrap.downloader import DownloadPaused
from finesub_bootstrap.models import DownloadProgress, ResourceStatus
from desktop.backend.resources import manual_wheels, python_interpreter
from desktop.backend.resources.model_prefetch import run_model_prefetch
from desktop.backend.resources.local_reuse import LocalResourceReuse
from finesub_bootstrap.system_tools import (
    SystemTool,
    find_system_ffmpeg,
    find_system_git,
    find_system_token_counter,
)


# Everything the ResourceManager installs the same way. `uv` is not here: it
# also drives the Python runtime install, so it keeps its own branch.
BOOTSTRAP_RESOURCES = ("ffmpeg", "git", "yt-dlp", "tokcount")

# Every pipeline run needs these two. URL-only and optional tooling stays in
# `capability_requirements`, the same shared rule the CLI uses, so a local-file
# task cannot be blocked by an unrelated yt-dlp or git installation.
ALWAYS_REQUIRED = ("uv", "ffmpeg")

# The model weights, as one row. Not in BOOTSTRAP_RESOURCES: nothing about them
# goes through the manifest downloader -- the pipeline's own libraries fetch
# them, so this id gets its own branch the way `uv` does.
#
# Never in ALWAYS_REQUIRED either. A task that finds them missing downloads them
# itself, exactly as before this row existed; the row only lets the user pay
# that cost up front instead of inside their first run. Requiring them would
# turn a 3GB download into a gate on ever starting.
MODELS_RESOURCE = "models"

# The weights are not versioned by us -- each library pins its own revision --
# so the row carries a token rather than a number that would only ever be a
# guess about somebody else's release. A token, not display text: `version`
# reaches the UI verbatim, and the UI has two languages while this string has
# one. The front end translates the models row's version line itself.
_MODELS_VERSION = "on-demand"

# Tools the user may already have. Reusing a capable system copy is worth ~150MB
# on a machine that has ffmpeg. yt-dlp is missing on purpose: the pipeline
# imports it from the managed interpreter, which cannot see the user's
# site-packages, so a system install is invisible and there is nothing to reuse.
SYSTEM_TOOL_FINDERS = {
    "ffmpeg": find_system_ffmpeg,
    "git": find_system_git,
    "tokcount": find_system_token_counter,
}


def capability_requirements(request) -> tuple[str, ...]:
    """Which on-demand resources this particular request needs.

    Thin adapter over the shared rule so the desktop and the CLI cannot drift
    into disagreeing about what a run requires.
    """

    return required_capabilities(
        knowledge=str(getattr(request, "knowledge", "none")),
        source=str(getattr(request, "input", "")),
        stage=str(getattr(request, "stage", "raw-srt")),
    )


class DesktopResourceService:
    def __init__(
        self,
        *,
        bootstrap,
        runtime: RuntimeEnvironment,
        system_tool_finders: Mapping[str, Callable[[], SystemTool | None]]
        | None = None,
        model_prefetch: Callable[..., None] | None = None,
        local_reuse: LocalResourceReuse | None = None,
        interpreter_prober: python_interpreter.InterpreterProbe | None = None,
    ) -> None:
        self.bootstrap = bootstrap
        self.runtime = runtime
        self.interpreter_prober = interpreter_prober
        # Injectable for the same reason as the tool finders: otherwise testing
        # the `models` branch means spawning an interpreter and downloading
        # gigabytes.
        self.model_prefetch = (
            run_model_prefetch if model_prefetch is None else model_prefetch
        )
        # Injectable, because otherwise every answer this class gives depends on
        # what happens to be installed on the machine running it -- including in
        # tests and CI.
        self.system_tool_finders = (
            SYSTEM_TOOL_FINDERS if system_tool_finders is None else system_tool_finders
        )
        self._system_tools: dict[str, SystemTool | None] = {}
        self.local_reuse = local_reuse or LocalResourceReuse(bootstrap)

    def system_tool(self, resource_id: str) -> SystemTool | None:
        """A usable system copy of `resource_id`, probed at most once."""

        finder = self.system_tool_finders.get(resource_id)
        if finder is None:
            return None
        if resource_id not in self._system_tools:
            self._system_tools[resource_id] = finder()
        return self._system_tools[resource_id]

    def check_all(self) -> list[ResourceStatus]:
        """Every resource the user can act on, required ones first.

        On-demand tools are included so that a task refused for a missing one
        has somewhere to send the user -- but flagged optional, so they do not
        make a perfectly usable install look half-finished.
        """

        required = [self.status(resource_id) for resource_id in ALWAYS_REQUIRED]
        optional = [
            self.status(resource_id).model_copy(update={"optional": True})
            for resource_id in (*BOOTSTRAP_RESOURCES, MODELS_RESOURCE)
            if resource_id not in ALWAYS_REQUIRED
        ]
        return required + optional

    def status(self, resource_id: str) -> ResourceStatus:
        if resource_id == "uv":
            return self._runtime_status()
        if resource_id == MODELS_RESOURCE:
            return self._models_status()
        if resource_id not in BOOTSTRAP_RESOURCES:
            raise KeyError(f"Unknown desktop resource: {resource_id}")
        found = self.system_tool(resource_id)
        if found is not None:
            return ResourceStatus(
                id=resource_id,
                version=found.version,
                state="ready",
                detail=f"使用系统已安装的版本：{found.path}",
            )
        return self.bootstrap.status(resource_id)

    def _runtime_status(self, *, force_probe: bool = False) -> ResourceStatus:
        """Read managed-runtime state without starting discovery during polling."""

        prober = self.interpreter_prober
        if force_probe and prober is not None:
            self._reset_interpreter_probe(
                self.runtime.development_python
                or python_interpreter.load_configured_interpreter(
                    self.runtime.paths.user_data
                )
            )
        if prober is None or force_probe or prober.done:
            return self.runtime.status(force_probe=force_probe)
        marker = getattr(self.runtime, "marker_path", None)
        if self.runtime.development_python is not None or (
            self.runtime.python_executable.is_file()
            and isinstance(marker, Path)
            and marker.is_file()
        ):
            return self.runtime.status(force_probe=force_probe)
        return ResourceStatus(
            id="uv",
            version=f"Python {self.runtime.python_version}",
            state="missing",
            detail=(
                f"尚未检查本机 Python {self.runtime.python_version}；"
                "开始安装后会在后台检查，最长约 12 秒。"
            ),
        )

    def interpreter_choice(self, *, refresh: bool = False) -> dict[str, object]:
        """Which Python the runtime will be built from, and which were refused.

        Deliberately not part of ``status("uv")``: that answer has to stay a
        pure filesystem check because the bridge polls it. This one spawns
        subprocesses, so it belongs with ``diagnostics()`` -- asked for
        explicitly, by a user who is already looking at a failure.

        Never raises: the probes swallow their own errors, and a machine with
        no Python at all is an answer, not a fault.
        """

        configured = self.runtime.development_python or (
            python_interpreter.load_configured_interpreter(
                self.runtime.paths.user_data
            )
        )
        if refresh:
            self._reset_interpreter_probe(configured)
        if self.interpreter_prober is None:
            rejected: list[python_interpreter.RejectedCandidate] = []
            outcome = python_interpreter.locate_interpreter(
                preferred=configured,
                python_version=self.runtime.python_version,
                rejected=rejected,
            )
        else:
            outcome, rejected = self.interpreter_prober.report()
        return {
            "configured": str(configured) if configured is not None else None,
            "found": str(outcome.path) if outcome.path is not None else None,
            "version": outcome.version,
            "detail": (
                ""
                if outcome.ok
                else outcome.reason
                or python_interpreter.describe_failure(rejected)
            ),
            "rejected": [
                {"path": str(item.path), "reason": item.reason}
                for item in rejected
            ],
        }

    def configure_interpreter(self, interpreter: Path | None) -> Path | None:
        """Persist a choice and make it effective for the next install now."""

        chosen = python_interpreter.save_configured_interpreter(
            self.runtime.paths.user_data, interpreter
        )
        self._reset_interpreter_probe(chosen)
        return chosen

    def _reset_interpreter_probe(self, preferred: Path | None) -> None:
        """Forget both caches so an explicit check sees current installations."""

        if self.interpreter_prober is not None:
            self.interpreter_prober.reset(preferred)
        # FineSub 0.5.1 memoises the injected prober but has no public reset.
        if hasattr(self.runtime, "_system_python_checked"):
            self.runtime._system_python_checked = False
            self.runtime._system_python = None

    def _models_status(
        self, *, runtime_status: ResourceStatus | None = None
    ) -> ResourceStatus:
        models_root = self.runtime.paths.models
        missing = missing_pipeline_models(models_root)
        if not missing:
            return ResourceStatus(
                id=MODELS_RESOURCE,
                version=_MODELS_VERSION,
                state="ready",
                detail="模型权重已就绪",
            )
        if not (runtime_status or self._runtime_status()).usable:
            # There is no interpreter to fetch them with yet, and a button that
            # fails on click is worse than one that says why it cannot run.
            return ResourceStatus(
                id=MODELS_RESOURCE,
                version=_MODELS_VERSION,
                state="missing",
                detail="需要先安装 Python 运行环境",
                blocked_by="uv",
            )
        return ResourceStatus(
            id=MODELS_RESOURCE,
            version=_MODELS_VERSION,
            state="missing",
            detail=f"还需下载 {len(missing)}/{len(PIPELINE_MODEL_IDS)} 个模型",
        )

    def _prefetch_one(
        self,
        model_id: str,
        *,
        position: tuple[int, int],
        stage: Callable[[str, str], None] | None,
        log: Callable[[str], None] | None,
        should_pause: Callable[[], bool] | None,
    ) -> None:
        from finesub_bootstrap import model_fetch
        from finesub_bootstrap.download_routes import resolve_region

        data_root = self.runtime.paths.data_root
        region = resolve_region(data_root).region

        def run(environment) -> None:
            # The attempt's endpoint is authoritative, applied *after* the
            # context is built. `worker_context` fills in the configured
            # endpoint by default -- correct for an ordinary run, but it would
            # quietly put the mirror back into the attempt that exists
            # precisely to avoid it, so the fallback would retry the host that
            # just failed.
            context = self.worker_context({})
            resolved = dict(context.environment)
            endpoint = environment.get(model_fetch.HF_ENDPOINT, "")
            if endpoint:
                resolved[model_fetch.HF_ENDPOINT] = endpoint
            else:
                resolved.pop(model_fetch.HF_ENDPOINT, None)
            self.model_prefetch(
                [model_id],
                context=replace(context, environment=resolved),
                stage=stage,
                log=log,
                should_pause=should_pause,
            )

        def retryable(error: BaseException) -> bool:
            # The same question fetch_fixed_files asks, and for the same
            # reason: "not paused" is far too wide. A full disk, a permission
            # error or a model that fails to load would each be recorded as a
            # mirror failure and answered by re-downloading gigabytes from the
            # official source, which fails again for the identical local
            # reason -- and three of those disable the mirror for this machine.
            return model_fetch.is_mirror_failure(error)

        index, total = position
        if stage is not None:
            stage("models", f"正在获取模型 {index}/{total}")
        model_fetch.fetch_with_fallback(
            run,
            base_environment={},
            data_root=data_root,
            region=region,
            is_retryable=retryable,
        )

    def _install_models(
        self,
        stage: Callable[[str, str], None] | None,
        log: Callable[[str], None] | None,
        should_pause: Callable[[], bool] | None,
    ) -> ResourceStatus:
        missing = missing_pipeline_models(self.runtime.paths.models)
        if not missing:
            return self._models_status()
        if not self._runtime_status().usable:
            raise RuntimeError("需要先安装 Python 运行环境，再下载模型权重。")
        # One process per model, and one endpoint decision per process. The
        # endpoint is read at import time by huggingface_hub, so falling back
        # means starting again; batching all three would then re-download the
        # ones that had already finished.
        for index, model_id in enumerate(missing, start=1):
            self._prefetch_one(
                model_id,
                position=(index, len(missing)),
                stage=stage,
                log=log,
                should_pause=should_pause,
            )
        status = self._models_status()
        if not status.usable:
            # A zero exit code is not enough: an upstream downloader can change
            # where it writes, or a cache file can disappear before the final
            # status check. ResourceInstallManager treats every normal return as
            # success, so refuse to let an incomplete row become "ready".
            raise RuntimeError(
                "模型下载进程已结束，但完整性检查仍发现缺失文件；请重试并查看安装日志。"
            )
        return status

    def install(
        self,
        resource_id: str,
        progress: Callable[[DownloadProgress], None],
        *,
        stage: Callable[[str, str], None] | None = None,
        log: Callable[[str], None] | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> ResourceStatus:
        if resource_id == MODELS_RESOURCE:
            return self._install_models(stage, log, should_pause)
        background = any(
            callback is not None
            for callback in (stage, log, should_pause)
        )
        if resource_id == "uv":
            if self.interpreter_prober is not None and not self.interpreter_prober.done:
                if stage is not None:
                    stage(
                        "discovering_python",
                        f"正在检查本机 Python {self.runtime.python_version}（最长约 12 秒）",
                    )

                def announce(candidate: Path) -> None:
                    if should_pause is not None and should_pause():
                        raise DownloadPaused("Python interpreter discovery paused")
                    if log is not None:
                        log(f"Checking Python candidate: {candidate}")

                self.interpreter_prober.report(on_candidate=announce)
                if should_pause is not None and should_pause():
                    raise DownloadPaused("Python interpreter discovery paused")
            self._prepare_local_archive(
                resource_id,
                stage=stage,
                log=log,
                should_pause=should_pause,
            )
            if background:
                self.bootstrap.install(
                    "uv",
                    progress,
                    stage=stage,
                    should_pause=should_pause,
                )
                return self.runtime.install(
                    stage=stage,
                    log=log,
                    should_pause=should_pause,
                )
            self.bootstrap.install("uv", progress)
            return self.runtime.install()
        if resource_id not in BOOTSTRAP_RESOURCES:
            raise KeyError(f"Unknown desktop resource: {resource_id}")
        if self.system_tool(resource_id) is not None:
            return self.status(resource_id)
        self._prepare_local_archive(
            resource_id,
            stage=stage,
            log=log,
            should_pause=should_pause,
        )
        if not background:
            return self.bootstrap.install(resource_id, progress)
        return self.bootstrap.install(
            resource_id,
            progress,
            stage=stage,
            should_pause=should_pause,
        )

    def _prepare_local_archive(
        self,
        resource_id: str,
        *,
        stage: Callable[[str, str], None] | None,
        log: Callable[[str], None] | None,
        should_pause: Callable[[], bool] | None,
    ) -> None:
        # An installed exact version wins without touching the disks. Missing
        # and outdated resources get one shared local scan before the normal,
        # hash-verifying downloader is allowed to contact the network.
        if self.bootstrap.status(resource_id).state == "ready":
            return
        self.local_reuse.prepare(
            resource_id,
            stage=stage,
            log=log,
            should_pause=should_pause,
        )

    def ensure(self, resource_ids: tuple[str, ...]) -> list[str]:
        """Names of the given resources that are still missing."""

        return [
            resource_id
            for resource_id in resource_ids
            if not self.status(resource_id).usable
        ]

    def locations(self, resource_id: str) -> tuple[Path, Path]:
        if resource_id == "uv":
            return (
                self.bootstrap.cache_path("uv"),
                self.runtime.runtime_root,
            )
        if resource_id == MODELS_RESOURCE:
            # No staging download of our own: each library writes straight into
            # its cache, so both halves point at the models root.
            managed_hf, _ = managed_model_dirs(self.runtime.paths.models)
            return (managed_hf, self.runtime.paths.models)
        if resource_id not in BOOTSTRAP_RESOURCES:
            raise KeyError(f"Unknown desktop resource: {resource_id}")
        return (
            self.bootstrap.cache_path(resource_id),
            self.bootstrap.install_path(resource_id),
        )

    def manual_download(
        self, resource_id: str, error: Exception
    ) -> dict[str, str] | None:
        if resource_id != "uv":
            return None
        lock = self.runtime.runtime_lock
        command = getattr(error, "cmd", ())
        if isinstance(command, (list, tuple)) and "--requirement" in command:
            index = command.index("--requirement") + 1
            if index < len(command):
                regional = lock.with_name(lock.name.replace(".toml", ".cn.toml"))
                if (
                    Path(command[index]).name
                    in {regional.name, manual_wheels.install_lock_name(regional)}
                    and regional.is_file()
                ):
                    lock = regional
        wheel = manual_wheels.failed_wheel(lock, error)
        if wheel is None or not wheel.url.startswith("https://"):
            return None
        return {
            "filename": wheel.filename,
            "url": wheel.url,
            "sha256": wheel.sha256,
            "directory": str(self.runtime.paths.cache / "downloads"),
        }

    def task_ready(self, request=None) -> bool:
        required = ALWAYS_REQUIRED + (
            capability_requirements(request) if request is not None else ()
        )
        return not self.ensure(required)

    def diagnostics(self) -> dict[str, object]:
        """Run the expensive health probe and return frontend-neutral facts."""

        # A manual diagnostic means "look again", including system tools that
        # were installed after launch.
        self._system_tools.clear()
        forced_runtime = self._runtime_status(force_probe=True)
        resources = [
            forced_runtime if resource_id == "uv" else self.status(resource_id)
            for resource_id in ALWAYS_REQUIRED
        ]
        resources.extend(
            (
                self._models_status(runtime_status=forced_runtime)
                if resource_id == MODELS_RESOURCE
                else self.status(resource_id)
            ).model_copy(update={"optional": True})
            for resource_id in (*BOOTSTRAP_RESOURCES, MODELS_RESOURCE)
            if resource_id not in ALWAYS_REQUIRED
        )
        blocking = [
            status.id
            for status in resources
            if not getattr(status, "optional", False) and not status.usable
        ]
        paths = self.runtime.paths
        try:
            disk_free_bytes: int | None = shutil.disk_usage(paths.big_data).free
        except OSError:
            disk_free_bytes = None
        try:
            core_version = importlib.metadata.version("finesub")
        except importlib.metadata.PackageNotFoundError:
            core_version = "source"
        return {
            "healthy": not blocking,
            "core_version": core_version,
            "resources": resources,
            "blocking_resources": blocking,
            "python_executable": self.runtime.python_executable,
            # Which CPython the runtime will be built from. Carried here rather
            # than in `status("uv")`, which has to stay a filesystem check: this
            # one probes interpreters, and a user looking at a failed Python
            # install is exactly who needs the answer.
            "python_interpreter": self.interpreter_choice(),
            # Where the weights actually are, which is not always `paths.models`.
            # Both halves fall back to the conventional per-user cache when it
            # already holds the files (`existing_hf_home` /
            # `existing_separator_dir`), and the rule lives in the pipeline, so
            # it is asked rather than reimplemented. Publishing only the managed
            # path made "relocate big data" and "purge rebuildable data" look
            # like they covered several GB that were never there.
            "model_locations": self._model_locations(),
            "disk_free_bytes": disk_free_bytes,
            "paths": {
                "install": paths.root,
                "personal_data": paths.user_data,
                "big_data": paths.big_data,
                "models": paths.models,
                "cache": paths.cache,
                "tasks": paths.tasks,
                "logs": paths.logs,
            },
        }

    def _model_locations(self) -> dict[str, object]:
        """The managed model directories, and the ones actually in use.

        The two differ whenever the conventional per-user cache already holds
        the weights: the pipeline prefers that copy, so the install's own
        `models/` stays empty and every byte lives under `~/.cache`. Asking the
        pipeline's own helpers keeps this honest -- reimplementing the rule
        here is how the two would drift apart.
        """

        managed_hf, _ = managed_model_dirs(self.runtime.paths.models)
        return {
            "managed": str(managed_hf),
            "hf_home": str(existing_hf_home(managed_hf)),
            "separator": str(
                existing_separator_dir(
                    self.runtime.paths.models / "audio-separator",
                    SEPARATOR_CHECKPOINT,
                )
            ),
        }

    def storage_state(self) -> dict[str, object]:
        """Current core-owned storage locations, without running a health probe."""

        paths = self.runtime.paths
        return {
            "big_data": str(paths.big_data),
            "default_big_data": str(paths.root),
            "runtime": str(paths.runtime),
            "models": str(paths.models),
            "cache": str(paths.cache),
            "tasks": str(paths.tasks),
            "agent_capsules": str(paths.agent_capsules),
            "relocated": paths.big_data != paths.root,
        }

    def relocate_big_data(
        self,
        destination: Path | None = None,
        *,
        reset: bool = False,
    ) -> dict[str, object]:
        """Use FineSub core's locked, crash-safe big-data relocation."""

        if reset:
            arguments = ["--reset"]
        elif destination is not None:
            arguments = [str(destination)]
        else:
            raise ValueError("请选择新的大文件目录。")
        message = self._run_core_storage_command("relocate", arguments)
        return {
            "storage": self.storage_state(),
            "resources": self.check_all(),
            "message": message,
        }

    def purge_rebuildable_data(self) -> dict[str, object]:
        """Remove runtime, downloads, models, and agent capsules, never user work."""

        message = self._run_core_storage_command(
            "uninstall", ["--purge-big-data"]
        )
        return {
            "storage": self.storage_state(),
            "resources": self.check_all(),
            "message": message,
        }

    def _run_core_storage_command(
        self, method_name: str, arguments: list[str]
    ) -> str:
        """Run one allowlisted Shell method and adopt any paths it changes."""

        from finesub_bootstrap.shell import Shell

        stdout = StringIO()
        stderr = StringIO()
        shell = Shell(
            paths=self.runtime.paths,
            resources=self.bootstrap,
            runtime=self.runtime,
        )
        with redirect_stdout(stdout), redirect_stderr(stderr):
            return_code = getattr(shell, method_name)(arguments)
        output = "\n".join(
            part.strip()
            for part in (stdout.getvalue(), stderr.getvalue())
            if part.strip()
        )
        if return_code != 0:
            raise RuntimeError(output or "FineSub 核心未能完成存储维护。")
        # Shell owns the relocation record and returns the authoritative paths.
        # These services are long-lived, so the next operation adopts it now.
        self.bootstrap.paths = shell.paths
        self.runtime.paths = shell.paths
        return output

    def tool_directory(self, resource_id: str, filename: str) -> Path | None:
        """Directory to put on PATH for `resource_id`, system copy first."""

        found = self.system_tool(resource_id)
        if found is not None:
            return found.directory
        active = self.bootstrap.active_file(resource_id, filename)
        return active.parent if active is not None else None

    def tool_file(self, resource_id: str, filename: str) -> Path | None:
        """The executable itself, for tools we name rather than put on PATH.

        `filename` describes the managed copy; a system one is taken as found,
        since the machine may well have named it something else.
        """

        found = self.system_tool(resource_id)
        if found is not None:
            return found.path
        return self.bootstrap.active_file(resource_id, filename)

    def worker_context(
        self,
        extra_env: Mapping[str, str],
    ) -> WorkerContext:
        # Same overrides the CLI applies: both launch the same pipeline against
        # the same user-data tree. Settings (API keys) go last so an explicitly
        # configured value always wins.
        environment = {
            **shared_environment_overrides(self.runtime.paths),
            # Optional, so it is resolved here rather than gated on: whatever
            # the panel has installed (or the machine already had) is what the
            # worker gets, and nothing at all when there is neither.
            **token_counter_overrides(
                lambda: self.tool_file("tokcount", "tokcount.exe")
            ),
            **extra_env,
        }
        git_bin = self.tool_directory("git", "git.exe")
        # yt-dlp is imported, not executed, so it joins PYTHONPATH rather than
        # PATH -- and only when it is actually installed, since a URL task is
        # what pulls it down.
        yt_dlp = (
            [self.bootstrap.install_path("yt-dlp")]
            if self.bootstrap.active_version("yt-dlp") is not None
            else []
        )
        return self.runtime.worker_context(
            ffmpeg_bin=self.tool_directory("ffmpeg", "ffmpeg.exe"),
            extra_env=environment,
            extra_path_dirs=[git_bin] if git_bin is not None else [],
            extra_python_path=yt_dlp,
        )
