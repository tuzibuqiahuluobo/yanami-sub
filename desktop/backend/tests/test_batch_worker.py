from __future__ import annotations

from pathlib import Path
import sys
import json
from types import SimpleNamespace

from finesub.scheduler import BatchItem, ItemResult
from finesub.llm.routing.model_routes import runtime_preferred

from desktop.backend.batches.protocol import BatchWorkerEvent
from desktop.backend.common.models import BatchRequest
from desktop.backend.worker import batch_main


def test_batch_worker_uses_core_scheduler_and_isolates_a_bad_item(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "finesub.pipeline", None)
    good = tmp_path / "good.wav"
    bad = tmp_path / "missing.wav"
    good.write_bytes(b"audio")
    request = BatchRequest.model_validate(
        {
            "items": [
                {
                    "input": str(good),
                    "llm_model": ["correction-text=correction-capable"],
                },
                {
                    "input": str(bad),
                    "llm_model": ["correction-text=correction-capable"],
                },
            ],
            "workers": {"download": 3, "asr": 1, "llm": 2},
            "retry_failed": 2,
        }
    )
    scheduler_calls: list[dict] = []
    built_options: list[dict] = []
    route_seen: dict[str, str] = {}
    published_file = tmp_path / "good-raw.srt"

    def build_item(options, *, claims):
        built_options.append(options)
        if options["source"] == str(bad):
            raise FileNotFoundError(str(bad))
        return BatchItem(
            label=good.name,
            stages={},
            payload={"audio": good, "output": options.get("output")},
            row=options,
        )

    def run_batch(items, **kwargs):
        route_seen.update(runtime_preferred())
        scheduler_calls.append(kwargs)
        results = [ItemResult(label=items[0].label, status="done", payload=items[0].payload)]
        failed = ItemResult(label=items[1].label, status="failed")
        failed.error = "FileNotFoundError: missing.wav"
        results.append(failed)
        kwargs["publish"](items, results)
        return results

    def publish_output(*_args, **_kwargs):
        published_file.write_text("subtitle", encoding="utf-8")
        return {"rawSrt": str(published_file)}

    monkeypatch.setattr(batch_main, "_publish_output", publish_output)
    events: list[BatchWorkerEvent] = []

    final = batch_main.run_batch_request(
        request,
        batch_id="batch-test",
        batch_root=tmp_path / "batch",
        emit=events.append,
        build_item=build_item,
        run_batch=run_batch,
        default_pipeline_paths=lambda *_args, **_kwargs: SimpleNamespace(
            final_srt=tmp_path / "internal.srt"
        ),
        claims=object(),
    )

    assert [item.state for item in final] == ["done", "failed"]
    assert final[0].outputs == {"rawSrt": str(published_file)}
    assert scheduler_calls[0]["workers"] == {"download": 3, "asr": 1, "llm": 2}
    assert scheduler_calls[0]["retry_failed"] == 2
    assert all("llm_model" not in options for options in built_options)
    assert all("llm_source" not in options for options in built_options)
    assert route_seen == {"correction-text": "correction-capable"}
    assert scheduler_calls[0]["status_path"] == tmp_path / "batch" / "batch-status.jsonl"
    assert events[-1].type == "completed"


def test_batch_worker_reuses_a_still_present_published_output(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "source-raw.srt"
    output.write_text("existing", encoding="utf-8")
    batch_root = tmp_path / "batch"
    batch_root.mkdir()
    (batch_root / "published.json").write_text(
        '{"0":{"rawSrt":"' + str(output).replace("\\", "\\\\") + '"}}',
        encoding="utf-8",
    )
    request = BatchRequest.model_validate({"items": [{"input": str(source)}]})

    def build_item(options, *, claims):
        return BatchItem(
            label=source.name,
            stages={},
            payload={"audio": source, "output": options.get("output")},
        )

    def run_batch(items, **kwargs):
        results = [ItemResult(label=items[0].label, status="done", payload=items[0].payload)]
        kwargs["publish"](items, results)
        return results

    publish_calls: list[object] = []
    monkeypatch.setattr(
        batch_main,
        "_publish_output",
        lambda *_args, **_kwargs: publish_calls.append(object()),
    )

    final = batch_main.run_batch_request(
        request,
        batch_id="batch-test",
        batch_root=batch_root,
        emit=lambda _event: None,
        build_item=build_item,
        run_batch=run_batch,
        default_pipeline_paths=lambda *_args, **_kwargs: SimpleNamespace(
            final_srt=tmp_path / "internal.srt"
        ),
        claims=object(),
    )

    assert publish_calls == []
    assert final[0].outputs == {"rawSrt": str(output)}


def test_batch_without_agent_runs_raw_and_marks_partial_result(
    monkeypatch, tmp_path: Path
) -> None:
    from desktop.backend.settings.local_agents import COMMANDS_ENV

    monkeypatch.delenv("GEMINI_FREE", raising=False)
    monkeypatch.delenv(COMMANDS_ENV, raising=False)
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "run" / "a.srt"
    request = BatchRequest.model_validate({"items": [{
        "input": str(source), "output": str(output),
        "stage": "final-srt", "llm_source": "auto",
    }]})
    built: list[dict] = []
    events: list[BatchWorkerEvent] = []
    published = tmp_path / "published-raw.srt"
    published.write_text("raw", encoding="utf-8")

    def build_item(options, *, claims):
        built.append(options)
        return BatchItem(
            label=source.name, stages={},
            payload={"audio": source, "output": output},
        )

    def run_batch(items, **kwargs):
        results = [ItemResult(label=items[0].label, status="done", payload=items[0].payload)]
        kwargs["publish"](items, results)
        return results

    monkeypatch.setattr(batch_main, "_publish_output", lambda paths, item, **kwargs: (
        {"rawSrt": str(published)} if item.stage == "raw-srt" else {}
    ))
    final = batch_main.run_batch_request(
        request, batch_id="batch-auto", batch_root=tmp_path / "batch",
        emit=events.append, build_item=build_item, run_batch=run_batch,
        default_pipeline_paths=lambda *_args, **_kwargs: SimpleNamespace(final_srt=output),
        claims=object(),
    )

    assert built[0]["stage"] == "raw-srt"
    assert final[0].state == "done"
    assert final[0].correction_skipped
    assert final[0].outputs == {"rawSrt": str(published)}
    assert final[0].skip_reason


def test_batch_exhausted_agent_keeps_raw_output(
    monkeypatch, tmp_path: Path
) -> None:
    from desktop.backend.settings.local_agents import COMMANDS_ENV

    config = tmp_path / "config.toml"
    config.write_text("[llm]\n", encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_DSH": ["dsh.exe"]}))
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "run" / "a.srt"
    output.parent.mkdir()
    output.with_name("a-raw.srt").write_text("raw", encoding="utf-8")
    request = BatchRequest.model_validate({"items": [{
        "input": str(source), "output": str(output),
        "stage": "final-srt", "llm_source": "agent",
    }]})
    events: list[BatchWorkerEvent] = []
    published = tmp_path / "published-raw.srt"
    published.write_text("raw", encoding="utf-8")

    def fail_agent(payload):
        error = RuntimeError("Agent quota exhausted")
        error._harness_route_decision = {"candidates": [
            {"decision": "attempted", "outcome": "failed", "failure_kind": "quota"},
        ]}
        raise error

    def build_item(options, *, claims):
        return BatchItem(
            label=source.name, stages={"llm": fail_agent},
            payload={"audio": source, "output": output},
        )

    def run_batch(items, **kwargs):
        payload = items[0].stages["llm"](items[0].payload)
        results = [ItemResult(label=items[0].label, status="done", payload=payload)]
        kwargs["publish"](items, results)
        return results

    monkeypatch.setattr(batch_main, "_publish_output", lambda paths, item, **kwargs: (
        {"rawSrt": str(published)} if item.stage == "raw-srt" else {}
    ))
    final = batch_main.run_batch_request(
        request, batch_id="batch-agent", batch_root=tmp_path / "batch",
        emit=events.append, build_item=build_item, run_batch=run_batch,
        default_pipeline_paths=lambda *_args, **_kwargs: SimpleNamespace(final_srt=output),
        claims=object(),
    )

    assert final[0].correction_skipped
    assert final[0].outputs == {"rawSrt": str(published)}
    assert any("Agent quota exhausted" in event.payload.get("message", "") for event in events)


def test_batch_successful_agent_fallback_reports_failed_target(
    monkeypatch, tmp_path: Path
) -> None:
    from desktop.backend.settings.local_agents import COMMANDS_ENV

    config = tmp_path / "config.toml"
    config.write_text("[llm]\n", encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_DSH": ["dsh.exe"]}))
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    output = tmp_path / "run" / "a.srt"
    artifact_log = output.parent / "a.llm-artifacts" / "task-artifacts.jsonl"
    request = BatchRequest.model_validate({"items": [{
        "input": str(source), "output": str(output),
        "stage": "final-srt", "llm_source": "agent",
    }]})
    events: list[BatchWorkerEvent] = []

    def succeed_after_fallback(payload):
        artifact_log.parent.mkdir(parents=True)
        artifact_log.write_text(json.dumps({"payload": {
            "route_decision": {"candidates": [
                {"target_id": "local-dsh-first", "outcome": "failed", "failure_kind": "quota"},
                {"target_id": "local-dsh-next", "outcome": "success"},
            ]},
            "execution_attempts": [{
                "target_id": "local-dsh-first", "vendor_error": "QUOTA: Insufficient Balance"
            }],
        }}) + "\n", encoding="utf-8")
        return payload

    def build_item(options, *, claims):
        return BatchItem(
            label=source.name, stages={"llm": succeed_after_fallback},
            payload={"audio": source, "output": output},
        )

    def run_batch(items, **kwargs):
        payload = items[0].stages["llm"](items[0].payload)
        results = [ItemResult(label=items[0].label, status="done", payload=payload)]
        kwargs["publish"](items, results)
        return results

    monkeypatch.setattr(batch_main, "_publish_output", lambda paths, item, **kwargs: (
        {"finalSrt": str(output)}
    ))
    final = batch_main.run_batch_request(
        request, batch_id="batch-fallback", batch_root=tmp_path / "batch",
        emit=events.append, build_item=build_item, run_batch=run_batch,
        default_pipeline_paths=lambda *_args, **_kwargs: SimpleNamespace(final_srt=output),
        claims=object(),
    )

    assert final[0].state == "done"
    assert not final[0].correction_skipped
    assert any("local-dsh-first" in event.payload.get("message", "")
               and "QUOTA: Insufficient Balance" in event.payload.get("message", "")
               for event in events)
