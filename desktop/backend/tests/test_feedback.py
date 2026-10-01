from pathlib import Path
from zipfile import ZipFile

import pytest
from desktop.backend.launcher.feedback import collect_diagnostics, log_catalog, redact, safe_path, issue_url


def test_diagnostic_snapshots_are_bounded_redacted_and_local(tmp_path):
    tasks, logs, updates = (tmp_path / name for name in ("tasks", "logs", "updates"))
    task = tasks / "中文 ピロリン"
    task.mkdir(parents=True)
    source = task / "task-log.txt.part"
    source.write_text("x" * 600_000 + "\n识别完成 12345678901\nAuthorization: Bearer private\n?token=private\n",
                      encoding="utf-8")
    (task / "subtitle.srt").write_text("PRIVATE SUBTITLE", encoding="utf-8")
    logs.mkdir()
    (logs / "session-test.log").write_text("C:\\Users\\Alice\\private\n", encoding="utf-8")
    (logs / ".env").write_text("PRIVATE ENV", encoding="utf-8")
    result = collect_diagnostics(tasks=tasks, logs=logs, updates=updates,
                                destination=tmp_path / "reports", selected=["中文 ピロリン"],
                                version="test", secrets=["12345678901"], private_roots=[tmp_path])
    assert result["size"] < 20 * 1024 * 1024
    with ZipFile(result["path"]) as archive:
        assert set(archive.namelist()) == {"report.md", "tasks/1.txt", "application/1.txt"}
        combined = b"\n".join(archive.read(name) for name in archive.namelist()).decode("utf-8")
        assert "识别完成" in combined and "TRUNCATED" in combined
        for secret in ("12345678901", "Bearer private", "?token=private", "Alice", "PRIVATE SUBTITLE", "PRIVATE ENV"):
            assert secret not in combined
    assert "12345678901" in source.read_text(encoding="utf-8")  # Original untouched.


def test_catalog_includes_unindexed_tasks_and_shared_batches(tmp_path):
    (tmp_path / "old-unindexed").mkdir()
    batch = tmp_path / "batches" / "batch-one"
    batch.mkdir(parents=True)
    (batch / "batch-log.txt").write_text("batch", encoding="utf-8")
    rows = log_catalog(tmp_path)
    assert {row["id"] for row in rows} == {"old-unindexed", "batches/batch-one"}
    assert next(row for row in rows if row["batch"])["log_path"].endswith("batch-log.txt")


@pytest.mark.parametrize("identifier", ["../secret", "/absolute", "C:/secret", "task\\secret", "task/../secret"])
def test_log_selectors_reject_paths(tmp_path, identifier):
    with pytest.raises(ValueError):
        safe_path(tmp_path, identifier)


def test_reparse_points_are_not_collected(tmp_path):
    source, tasks = tmp_path / "outside", tmp_path / "tasks"
    source.mkdir()
    tasks.mkdir()
    try:
        (tasks / "linked").symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks require Windows permission")
    assert log_catalog(tasks) == []
    with pytest.raises(ValueError):
        safe_path(tasks, "linked")


def test_redacts_custom_formats_and_proxy_passwords():
    text = redact("api_key=987654321 https://alice:pwd@host ?key=secret hf_" + "a" * 30,
                  ["987654321"], [])
    assert "987654321" not in text and "alice:pwd" not in text and "?key=secret" not in text
    assert len(issue_url("x" * 1000, "中文" * 10000, "0.1.2-rc.7.post7")) < 6000
