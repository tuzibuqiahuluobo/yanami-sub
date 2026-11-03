import json
from io import StringIO

import pytest
from finesub.scheduler import BatchItem, ItemResult

from desktop.backend.batches.manager import BatchManager
from desktop.backend.batches.protocol import BatchWorkerEvent
from desktop.backend.common.models import BatchRequest
from desktop.backend.worker.batch_main import run_batch_request


def test_append_is_durable_and_end_race_stays_resumable(tmp_path, monkeypatch):
    class Process:
        stdin = StringIO()
        stdout = StringIO()
        def poll(self): return None

    manager = BatchManager(python_executable="python", worker_env={}, history_path=tmp_path / "history.json",
        output_root=tmp_path / "tasks", process_factory=lambda *_args, **_kwargs: Process(), terminate_process_tree=lambda _: None)
    monkeypatch.setattr(manager, "_start_reader", lambda *_: None)
    started = manager.start(BatchRequest(items=[{"input": "a.wav", "llm_preset": "fast"}]))
    added = manager.append(started.batch_id, ["中文.wav"])
    assert len(added.request.items) == len(added.items) == 2
    assert added.request.items[-1].llm_preset == "fast"
    saved = json.loads(manager.history_path.read_text(encoding="utf-8"))[-1]
    assert saved["request"]["items"][-1]["input"] == "中文.wav"
    control = json.loads((tmp_path / "tasks" / started.batch_id / "control.jsonl").read_text(encoding="utf-8"))
    assert control["desktop_index"] == 1
    assert "/002-" in control["request"]["output"].replace("\\", "/")
    with pytest.raises(ValueError, match="twice"):
        manager.append(started.batch_id, ["中文.wav"])
    snapshot = manager._snapshot
    manager._apply_event(snapshot, BatchWorkerEvent(type="completed", batch_id=started.batch_id,
        payload={"items": [started.items[0].model_dump()]}))
    assert snapshot.state == "interrupted" and len(snapshot.items) == 2
    assert "resume" in snapshot.error
    for activity in manager._runtime_activities.values():
        activity.__exit__(None, None, None)


def test_worker_intake_uses_core_commit_and_restores_without_duplicate(tmp_path):
    request = BatchRequest(items=[{"input": "a.wav", "stage": "raw-srt"}])
    added = {**request.items[0].model_dump(), "input": "中文.wav"}
    control = {"source": "中文.wav", "desktop_index": 1, "request": added}
    (tmp_path / "control.jsonl").write_text(json.dumps(control, ensure_ascii=False) + "\n", encoding="utf-8")
    seen = []
    def build(options, **_):
        seen.append(options["source"])
        return BatchItem(label=options["source"], stages={})
    def run(items, **kwargs):
        initial = list(items)  # The real scheduler snapshots its starting items.
        poll = kwargs["intake"]()
        assert len(poll.items) == 1
        assert not (tmp_path / "control-cursor.txt").exists()
        admitted = [*initial, *poll.items]
        results = [ItemResult(label=item.label) for item in admitted]
        kwargs["publish"](admitted, results)
        poll.commit()
        assert (tmp_path / "control-cursor.txt").read_text() == "1"
        return results
    rows = run_batch_request(request, batch_id="intake", batch_root=tmp_path, emit=lambda _: None,
        build_item=build, run_batch=run, claims=object(), default_pipeline_paths=lambda *_: None)
    assert seen == ["a.wav", "中文.wav"] and len(rows) == 2
    seen.clear()
    def resumed(items, **kwargs):
        assert not kwargs["intake"]().items
        return [ItemResult(label=item.label) for item in items]
    run_batch_request(BatchRequest(items=[request.items[0].model_dump(), added]), batch_id="intake", batch_root=tmp_path,
        emit=lambda _: None, build_item=build, run_batch=resumed, claims=object(), default_pipeline_paths=lambda *_: None)
    assert seen == ["a.wav", "中文.wav"]
