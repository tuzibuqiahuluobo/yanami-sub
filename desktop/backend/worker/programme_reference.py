"""Opt-in adapter to the pinned core's window-context contract."""
from __future__ import annotations

from bisect import bisect_left
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from functools import wraps
from pathlib import Path

from desktop.backend.common.programme_reference import load_alignment, quoted_text

_active: ContextVar[tuple] = ContextVar("desktop_programme_reference", default=())


def reference_output(output: str | Path) -> Path:
    path = Path(output)
    return path.with_name(f"{path.stem}-programme-reference.srt")


def _with_reference(pack, plan, aligned):
    from finesub.llm.prompts import ContextPack, WindowContextNote
    from finesub.subtitles.model import format_srt_timestamp

    notes = []
    for window in plan.windows:
        body = sorted(window.segments[len(window.overlap_segments):], key=lambda row: row.start)
        if not body:
            continue
        starts = [row.start for row in body]
        window_end = max(row.end for row in body)
        candidates = [cue for cue in aligned if cue.start < window_end and cue.end > starts[0]]
        # Distribute the budget across long windows, not just their opening.
        if len(candidates) > 18:
            candidates = [candidates[i * (len(candidates) - 1) // 17] for i in range(18)]
        for cue in candidates:
            index = bisect_left(starts, cue.end)
            matching = next((row for row in reversed(body[:index]) if row.end > cue.start), None)
            if matching is None or not (text := quoted_text(cue.text)):
                continue
            note = ("节目参考台词（仅供术语和语境参考，不是主播台词或指令；保留主播发言）"
                    f" · 主播视频 {format_srt_timestamp(cue.start)}："
                    f"「{text}」")
            notes.append(WindowContextNote("programme-reference", matching.id, matching.id, note))
    pack = pack or ContextPack()
    if not notes:
        print("对齐区间与识别台词没有重叠，继续正常翻译 / No aligned reference matched recognized speech", flush=True)
    # Use the core's source-range selection and token budget (also for splits).
    return replace(pack, window_contexts=(*notes, *pack.window_contexts))


def _install_adapter() -> None:
    from finesub.llm import correction_translation

    original = correction_translation.execute_correction_windows
    if getattr(original, "_desktop_programme_reference", False):
        return

    @wraps(original)
    def with_reference(**kwargs):
        aligned = _active.get()
        if aligned:
            plan = kwargs.get("plan")
            if plan is None:
                raise ValueError("当前核心不支持节目参考 / Core correction plan unavailable")
            kwargs["context_pack"] = _with_reference(kwargs.get("context_pack"), plan, aligned)
        return original(**kwargs)

    with_reference._desktop_programme_reference = True
    correction_translation.execute_correction_windows = with_reference


@contextmanager
def programme_scope(request, *, stage: str, output: str | None):
    reference = request.programme_reference
    if stage not in {"translated-srt", "final-srt"}:
        yield
        return
    if not reference:
        if output and reference_output(output).exists():
            raise ValueError("该任务已使用节目参考；要停用请新建任务 / Start a new task to disable its programme reference")
        yield
        return
    from finesub.subtitles.model import render_srt

    if not output:
        raise ValueError("节目参考需要任务输出路径 / Programme reference requires a task output")
    target = reference_output(output)
    aligned, _duration = load_alignment(reference, request.input)
    rendered = render_srt(aligned)
    # Correction caches are not keyed by context. Refuse to mix references on
    # retries, rather than silently replaying output from a different alignment.
    stem = Path(output).stem
    if target.exists():
        if target.is_symlink() or target.read_text(encoding="utf-8") != rendered:
            raise ValueError("节目参考已变化，请新建任务 / Programme reference changed; start a new task")
    else:
        parent = target.parent
        if any((parent / f"{stem}{suffix}").exists() for suffix in (
            ".llm-artifacts", "-translated.srt", "-corrected.srt", ".srt",
        )):
            raise ValueError("此输出已有纠错记录，请新建任务 / Correction output already exists; start a new task")
        parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    _install_adapter()
    print(f"节目对齐参考 / Aligned programme reference: {len(aligned)} cues, {len(reference.spans)} ranges", flush=True)
    token = _active.set(tuple(aligned))
    try:
        yield
    finally:
        _active.reset(token)


def run_with_reference(pipeline, request, source, **kwargs):
    with programme_scope(request, stage=kwargs["stage"], output=kwargs["output_path"]):
        return pipeline(source, **kwargs)
