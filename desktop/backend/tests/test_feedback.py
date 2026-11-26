import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from PIL import Image
from desktop.backend.launcher import feedback_issue
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


def test_reviewed_issue_keeps_selected_artifacts_and_sanitizes_attachments(tmp_path):
    tasks = tmp_path / "tasks"
    task = tasks / "a-private-name"
    task.mkdir(parents=True)
    (task / "task-log.txt").write_text("RuntimeError: API call failed; token omitted", encoding="utf-8")
    (task / "task-diagnostics.log").write_text('{"action":"before_cleanup","artifact_bytes":{"vocal_audio":250}}\n', encoding="utf-8")
    (task / "subtitle.srt").write_text("PRIVATE TRANSCRIPT", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "session-unselected.log").write_text("private unrelated session", encoding="utf-8")
    image_buffer = BytesIO()
    exif = Image.Exif()
    exif[270] = "PRIVATE EXIF"
    Image.new("RGB", (32, 32), "red").save(image_buffer, format="JPEG", exif=exif)
    attachments = [
        {"name": "screenshot.jpg", "data": base64.b64encode(image_buffer.getvalue()).decode()},
        {"name": "provided.log", "data": base64.b64encode(b"TimeoutError: Authorization: unsafe-secret").decode()},
    ]
    result = collect_diagnostics(tasks=tasks, logs=logs, updates=tmp_path / "updates",
        destination=tmp_path / "reports", selected=[task.name], version="preview", secrets=["unsafe-secret"],
        private_roots=[tmp_path], fields={"language": "en", "actual": "Video import failed。More details", "steps": "Choose file"},
        attachments=attachments, include_system=False)
    assert result["issue_title"] == "Video import failed"
    assert "## Expected result" in result["issue_markdown"]
    assert "TimeoutError" in result["issue_markdown"] and "unsafe-secret" not in result["issue_markdown"]
    assert "a-private-name" not in result["issue_markdown"]
    with ZipFile(result["path"]) as archive:
        assert set(archive.namelist()) == {"issue.md", "report.md", "tasks/1.txt", "tasks/1-artifacts.txt",
            "screenshots/1.jpg", "attached-logs/2.txt"}
        assert b"vocal_audio" in archive.read("tasks/1-artifacts.txt")
        assert b"unsafe-secret" not in archive.read("attached-logs/2.txt")
        with Image.open(BytesIO(archive.read("screenshots/1.jpg"))) as prepared:
            assert not prepared.getexif()


@pytest.mark.parametrize("name,data", [("secret.toml", "YQ=="), ("bad.png", "YQ=="), ("log.txt", "AA==")])
def test_rejects_nonlogs_and_invalid_screenshots(name, data):
    with pytest.raises(ValueError):
        feedback_issue.attachment_files([{"name": name, "data": data}])


def test_cli_partial_attachment_failure_returns_created_issue_without_retry(tmp_path, monkeypatch):
    package = tmp_path / "review.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("screenshots/1.jpg", b"prepared JPEG")
    monkeypatch.setattr(feedback_issue, "cli_capability", lambda _cwd: "screenshots")
    monkeypatch.setattr(feedback_issue.shutil, "which", lambda _name: "gh")
    calls = []
    def gh(executable, args, *, cwd, timeout):
        calls.append(args)
        assert (cwd / "issue.md").read_text(encoding="utf-8") == "reviewed body"
        assert (cwd / "screenshot-1.jpg").read_bytes() == b"prepared JPEG"
        assert args[3] == feedback_issue.REPOSITORY and "--attach" in args
        return SimpleNamespace(stdout="https://github.com/tuzibuqiahuluobo/yanami-sub/issues/42\n", returncode=1)
    monkeypatch.setattr(feedback_issue, "_gh", gh)
    result = feedback_issue.publish_issue("title", "reviewed body", tmp_path, package.read_bytes(), ["screenshots/1.jpg"])
    assert result["url"].endswith("/42") and result["attachments_complete"] is False
    assert len(calls) == 1
