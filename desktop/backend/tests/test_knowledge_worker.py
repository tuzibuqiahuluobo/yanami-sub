from __future__ import annotations

import json
from pathlib import Path

import pytest

from desktop.backend.worker.knowledge_main import _dispatch
from finesub.llm.knowledge.update import derive_task_paths


def test_knowledge_worker_creates_and_reads_an_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))

    empty = _dispatch({"action": "snapshot"})
    created = _dispatch(
        {
            "action": "maintenance",
            "command": "new",
            "args": [
                "common",
                "FineSub",
                "--intro",
                "字幕项目",
                "--type",
                "其他",
            ],
        }
    )
    snapshot = _dispatch({"action": "snapshot"})
    document = _dispatch(
        {"action": "entry", "name": "common/FineSub", "rev": None}
    )

    assert empty["revision"] == 0
    assert created["exit_code"] == 0
    assert "rev 1" in created["output"]
    assert snapshot["revision"] == 1
    assert snapshot["entries"][0]["qualified_name"] == "common/FineSub"
    assert "FineSub" in document["text"]


def test_knowledge_worker_aggregates_owned_task_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    final_srt = tmp_path / "episode.srt"
    final_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好\n", encoding="utf-8")
    artifact_dir = derive_task_paths(final_srt)["artifact_dir"]
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "task-artifacts.jsonl").write_text(
        json.dumps(
            {
                "kind": "research_task_feedback",
                "payload": {
                    "feedback": json.dumps(
                        {
                            "knowledge_hints": [
                                {
                                    "category": "common",
                                    "entry": "FineSub",
                                    "direction": "append_lines",
                                    "focus": "术语",
                                }
                            ],
                            "asr_corrections": ["Fine Sub → FineSub"],
                            "uncertainties": ["版本号"],
                        },
                        ensure_ascii=False,
                    )
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = _dispatch({"action": "feedback", "final_srt": str(final_srt)})

    assert result["merged_hints"][0]["entry"] == "FineSub"
    assert result["asr_corrections"] == ["Fine Sub → FineSub"]
    assert result["uncertainties"] == ["版本号"]


def test_knowledge_worker_rejects_commands_outside_the_core_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))

    with pytest.raises(ValueError, match="unsupported maintenance command"):
        _dispatch(
            {
                "action": "maintenance",
                "command": "shell",
                "args": ["calc.exe"],
            }
        )


def test_knowledge_snapshot_tolerates_a_non_numeric_push_queue_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    _dispatch(
        {
            "action": "maintenance",
            "command": "new",
            "args": [
                "common",
                "FineSub",
                "--intro",
                "字幕项目",
                "--type",
                "其他",
            ],
        }
    )
    (root / "share-pushes.jsonl").write_text(
        '{"remote":"https://example.test","queue_id":"manual"}\n',
        encoding="utf-8",
    )

    snapshot = _dispatch({"action": "snapshot"})

    assert snapshot["pushes"][0]["queue_id"] == "manual"
