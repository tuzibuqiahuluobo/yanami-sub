import pytest
from pydantic import ValidationError

from desktop.backend.common.models import (
    BatchRequest,
    RoutingUpdate,
    TaskDefaults,
    TaskRequest,
)


def test_task_request_defaults_to_local_raw_srt() -> None:
    request = TaskRequest.model_validate({"input": "D:/media/a.mp4"})

    assert request.stage == "raw-srt"
    # None, not "cuda": "not chosen" has to stay distinguishable from a
    # choice, or `--gpu-tier cpu` plus an explicit cuda cannot be refused.
    assert request.device is None
    assert request.model_name == "large-v3-turbo"
    assert request.gpu_tier == "auto"
    assert request.language is None
    assert request.gap_sec == 0.3
    assert request.asr_decode_batch == "auto"
    assert request.asr_context == "off"
    assert request.llm_media == "audio"
    assert request.llm_correction_media == ""
    assert request.llm_planning_media == ""
    assert request.llm_retrieval == "local"
    assert request.llm_difficulty == "quality"
    assert request.llm_continuity == "serial"
    assert request.llm_parallel_windows == 1
    assert request.llm_model == []
    assert request.max_retries_per_window == 5
    assert request.max_replacements_per_window == 1
    assert request.resume is True


def test_the_difficulty_is_the_word_the_llm_layer_actually_accepts() -> None:
    """The worker passes this straight through to `resolve_profile`.

    It used to send the retired `high`/`med`/`minimum`, which that function
    rejects -- so any desktop run reaching the LLM stage died there, *after*
    ASR had already paid for itself. Nothing caught it because a plain
    transcription never reads the value.
    """

    from finesub.llm.routing.profiles import DIFFICULTY

    request = TaskRequest.model_validate({"input": "D:/media/a.mp4"})

    assert request.llm_difficulty in DIFFICULTY


def test_history_written_before_the_rename_still_loads() -> None:
    """Old task records must not vanish from the user's history.

    `jobs/history.py` skips entries it cannot validate rather than failing --
    one unreadable record must not cost the rest of the list. That makes a
    narrowed vocabulary silently destructive: every record predating the
    2026-08-12 rename carries `high`, so rejecting it would empty the task
    list with no error anywhere.
    """

    request = TaskRequest.model_validate(
        {"input": "D:/media/a.mp4", "llm_difficulty": "high"}
    )

    assert request.llm_difficulty == "quality"


def test_task_request_rejects_fields_that_could_become_commands() -> None:
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(
            {"input": "D:/media/a.mp4", "command": "calc.exe"}
        )


def test_task_request_normalizes_blank_language_to_auto_detection() -> None:
    request = TaskRequest.model_validate(
        {"input": "D:/media/a.mp4", "language": "  "}
    )

    assert request.language is None


def test_task_request_rejects_an_unknown_gpu_tier() -> None:
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(
            {"input": "D:/media/a.mp4", "gpu_tier": "gigantic"}
        )


def test_task_request_accepts_a_named_tier_and_auto() -> None:
    """`auto` is a legal value, not just the default: the backend resolves it."""

    request = TaskRequest.model_validate(
        {"input": "D:/media/a.mp4", "gpu_tier": "standard"}
    )
    assert request.gpu_tier == "standard"

    detected = TaskRequest.model_validate(
        {"input": "D:/media/a.mp4", "gpu_tier": "auto"}
    )
    assert detected.gpu_tier == "auto"


def test_task_request_accepts_all_pipeline_postprocess_profiles() -> None:
    for profile in (-1, 0, 1, 2, 3, 4):
        request = TaskRequest.model_validate(
            {
                "input": "D:/media/a.mp4",
                "postprocess_profile": profile,
            }
        )

        assert request.postprocess_profile == profile


@pytest.mark.parametrize("value", [0, -1, "many", True])
def test_asr_decode_batch_rejects_values_the_form_cannot_run(value: object) -> None:
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(
            {"input": "D:/media/a.mp4", "asr_decode_batch": value}
        )
    with pytest.raises(ValidationError):
        TaskDefaults.model_validate({"asr_decode_batch": value})


def test_asr_decode_batch_accepts_auto_and_positive_numeric_text() -> None:
    automatic = TaskRequest.model_validate(
        {"input": "D:/media/a.mp4", "asr_decode_batch": " AUTO "}
    )
    explicit = TaskRequest.model_validate(
        {"input": "D:/media/a.mp4", "asr_decode_batch": " 4 "}
    )

    assert automatic.asr_decode_batch == "auto"
    assert explicit.asr_decode_batch == 4


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gap_sec", -0.1),
        ("split_length_scale", 0.5),
        ("split_length_scale", 1.7),
        ("llm_parallel_windows", 0),
        ("llm_output_scale", 0),
        ("max_retries_per_window", -1),
        ("max_replacements_per_window", -1),
    ],
)
def test_task_request_rejects_invalid_numeric_tuning(
    field: str, value: float
) -> None:
    with pytest.raises(ValidationError):
        TaskRequest.model_validate({"input": "D:/media/a.mp4", field: value})


def test_optional_advanced_paths_and_style_normalize_blank_to_none() -> None:
    request = TaskRequest.model_validate(
        {
            "input": "D:/media/a.mp4",
            "llm_video": " ",
            "refined_srt": "\t",
            "style": "",
        }
    )

    assert request.llm_video is None
    assert request.refined_srt is None
    assert request.style is None


def test_task_request_accepts_core_model_route_overrides() -> None:
    request = TaskRequest.model_validate(
        {
            "input": "D:/media/a.mp4",
            "llm_model": [
                "gemini-free-3_5-flash-lite",
                "correction-text=correction-capable",
            ],
        }
    )

    assert request.llm_model == [
        "gemini-free-3_5-flash-lite",
        "correction-text=correction-capable",
    ]


@pytest.mark.parametrize(
    "value",
    [
        ["unknown-task=correction-capable"],
        ["correction-text=does-not-exist"],
        ["correction-text="],
    ],
)
def test_task_request_rejects_invalid_core_model_route_overrides(value) -> None:
    with pytest.raises(ValidationError):
        TaskRequest.model_validate({"input": "D:/media/a.mp4", "llm_model": value})


def test_routing_parallelism_does_not_add_a_desktop_only_ceiling() -> None:
    update = RoutingUpdate.model_validate(
        {
            "preset": "default",
            "execution_policy": "default",
            "local_agent_timeout_seconds": 900,
            "local_agent_max_parallel": 64,
        }
    )

    assert update.local_agent_max_parallel == 64


def test_batch_request_defaults_match_the_core_scheduler() -> None:
    request = BatchRequest.model_validate(
        {"items": [{"input": "D:/media/a.mp4"}, {"input": "D:/media/b.mp4"}]}
    )

    assert request.workers.model_dump() == {"download": 2, "asr": 1, "llm": 2}
    assert request.asr_queue_size == 4
    assert request.retry_failed == 1
    assert request.items[0].priority == 0


def test_batch_request_rejects_duplicate_sources_and_unsafe_worker_counts() -> None:
    with pytest.raises(ValidationError):
        BatchRequest.model_validate(
            {"items": [{"input": "D:/media/a.mp4"}, {"input": "d:/MEDIA/A.mp4"}]}
        )
    with pytest.raises(ValidationError):
        BatchRequest.model_validate(
            {"items": [{"input": "D:/media/a.mp4"}], "workers": {"asr": 0}}
        )


def test_batch_request_requires_one_process_wide_model_route() -> None:
    with pytest.raises(ValidationError):
        BatchRequest.model_validate(
            {
                "items": [
                    {
                        "input": "D:/media/a.mp4",
                        "llm_model": ["gemini-free-3_5-flash-lite"],
                    },
                    {
                        "input": "D:/media/b.mp4",
                        "llm_model": ["correction-capable"],
                    },
                ]
            }
        )
