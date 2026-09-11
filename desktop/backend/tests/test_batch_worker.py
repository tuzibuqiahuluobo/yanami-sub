from __future__ import annotations

from pathlib import Path
import sys
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
