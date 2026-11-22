"""Hand a downloaded URL to the same media resolver as a local input."""

from functools import wraps
import time

from desktop.backend.common.core_compat import unified_llm_contract


def _local_media_handoff(payload, *, explicit_video):
    if explicit_video is not None or payload.get("llm_video") is None:
        return payload
    # The core download helper returns the saved MP4 as an implicit attachment,
    # independent of media mode. The local pipeline attaches it only for video.
    line = f"\nLLM 视频文件: {payload['llm_video']}"
    return {
        **payload,
        "llm_video": None,
        "extra_info": payload["extra_info"].replace(line, "", 1),
    }


def run_after_url_download(pipeline, source, **options):
    from finesub.media.source import is_url

    if not is_url(str(source)) or not unified_llm_contract():
        return pipeline(source, **options)

    from finesub.run_metadata import stage_record
    from finesub.stages import (
        compose_url_extra_info,
        prepare_url_input,
        resolve_asr_context,
        resolve_llm_switches,
    )

    stage = options["stage"]
    switches, _ = resolve_llm_switches(
        stage, options["llm_media"], options["llm_retrieval"],
        options["llm_difficulty"], options["llm_continuity"], options["knowledge"],
        options["llm_output_scale"], options["llm_parallel_windows"],
    )
    started = time.perf_counter()
    explicit_video = options["llm_video"]
    local, paths, video, info = prepare_url_input(
        source, output_path=options["output_path"], llm_video=explicit_video,
        download_video_source=options["download_video_source"],
    )
    handoff = _local_media_handoff({"llm_video": video, "extra_info": info}, explicit_video=explicit_video)
    options.update(
        output_path=paths.final_srt,
        llm_video=handoff["llm_video"],
        extra_info=compose_url_extra_info(
            source, handoff["extra_info"], options["extra_info"], stage=stage,
            asr_context=resolve_asr_context(options["asr_context"], knowledge=switches.knowledge),
        ),
        _run_started_monotonic=started,
        _prior_timing={"download": stage_record(status="executed", elapsed_sec=time.perf_counter() - started)},
    )
    return pipeline(str(local), **options)


def normalize_batch_url_download(item, explicit_video):
    if "download" not in item.stages or not unified_llm_contract():
        return
    original = item.stages["download"]

    @wraps(original)
    def download(payload):
        return _local_media_handoff(original(payload), explicit_video=explicit_video)

    item.stages = {**item.stages, "download": download}
