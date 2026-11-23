"""Hand a downloaded URL to the same media resolver as a local input."""

from pathlib import Path
import time


def run_after_url_download(pipeline, source, *, link_format=None, **options):
    if link_format is None:
        # The pinned core now handles the ordinary URL and batch cases.
        return pipeline(source, **options)

    from finesub.run_metadata import stage_record
    from finesub.stages import (
        compose_url_extra_info,
        resolve_asr_context,
        resolve_llm_switches,
    )
    from desktop.backend.worker.media_tools import download_selected_video

    if not options["output_path"]:
        raise ValueError("指定下载格式需要任务目录 / Selected formats require a task directory")
    stage = options["stage"]
    switches, _ = resolve_llm_switches(
        stage, options["llm_media"], options["llm_retrieval"],
        options["llm_difficulty"], options["llm_continuity"], options["knowledge"],
        options["llm_output_scale"], options["llm_parallel_windows"],
    )
    started = time.perf_counter()
    local = download_selected_video(source, link_format, Path(options["output_path"]).parent)
    options.update(
        extra_info=compose_url_extra_info(
            source, f"媒体文件: {local}", options["extra_info"], stage=stage,
            asr_context=resolve_asr_context(options["asr_context"], knowledge=switches.knowledge),
        ),
        _run_started_monotonic=started,
        _prior_timing={"download": stage_record(status="executed", elapsed_sec=time.perf_counter() - started)},
    )
    return pipeline(str(local), **options)
