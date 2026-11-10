import json
from pathlib import Path

import pytest

from desktop.backend.common.models import BatchItemRequest, BatchRequest, TaskRequest
from desktop.backend.common.core_compat import speech_call_options
from desktop.backend.settings import core_migration
from desktop.backend.worker.batch_main import _item_options
from desktop.backend.worker.main import WorkerReporter
from desktop.backend.worker.main import speech_model_provenance


@pytest.mark.parametrize("backend", ["local", "moss-local", "moss-pro", "mai2", "gemini-35t"])
def test_joint_asr_options_reach_single_and_batch_without_desktop_payment_flag(backend):
    row = BatchItemRequest(input="a.wav", asr=backend, asr_repair="quota", asr_aligner=True)
    batch = _item_options(row, {"download": 2, "asr": 1, "llm": 2}, task_id="t")
    assert all(batch[name] == value for name, value in speech_call_options(row).items())
    assert "moss_pro_paid" not in batch
    assert row.moss_pro_paid is False


def test_batch_cannot_mix_payment_consent():
    with pytest.raises(ValueError, match="payment"):
        BatchRequest(items=[BatchItemRequest(input="a", moss_pro_paid=False), BatchItemRequest(input="b", moss_pro_paid=True)])


def test_saved_speech_model_is_not_claimed_as_a_fresh_call(tmp_path):
    from types import SimpleNamespace
    path = tmp_path / "a-aligned.json"
    path.write_text(json.dumps({"metadata": {"joint_asr": {"model": "moss", "backend": "moss-pro"}}}), encoding="utf-8")
    assert "may be reused" in speech_model_provenance(SimpleNamespace(aligned_json=path))
    assert "moss" in speech_model_provenance(SimpleNamespace(aligned_json=path))


def test_actual_model_logging_has_stage_and_summary_without_key_or_candidate_claim():
    events = []
    report = WorkerReporter("t", events.append)
    report.stage_started("translated-srt")
    report.debug("llm api call", {"model": "actual-model", "tier": "GEMINI_FREE", "code": "200", "key": "label-not-a-secret"})
    report.debug("llm api call", {"model": "actual-model", "tier": "GEMINI_FREE", "code": "200"})
    report.completed("a.srt", 1)
    logs = [event.payload["message"] for event in events if event.type == "log"]
    assert sum("Model call:" in line for line in logs) == 1
    assert any("Responding model:" in line and "translated-srt" in line for line in logs)
    assert all("label-not-a-secret" not in line for line in logs)


def test_catalog_conversion_preview_and_apply_preserve_legacy_bytes(tmp_path, monkeypatch):
    from finesub.llm.routing.migrate_catalog import LEGACY_COLUMNS
    old = tmp_path / "model_catalog.psv"
    new = tmp_path / "model_catalog.toml"
    values = {"fact_id": "custom-model", "provider_tier": "CUSTOM", "provider_kind": "openai_compat",
              "base_url": "https://example.invalid/v1", "key_env": "CUSTOM_KEY", "api_model_id": "model",
              "max_input_tokens": "128000", "max_output_tokens": "64000", "capability": "70"}
    contents = ("|".join(LEGACY_COLUMNS) + "\n" + "|".join(values.get(key, "") for key in LEGACY_COLUMNS) + "\n").encode()
    old.write_bytes(contents)
    config = tmp_path / "config.toml"
    config.write_text('[llm]\nmedia="text"\n', encoding="utf-8")
    monkeypatch.delenv("FINESUB_MODEL_CATALOG", raising=False)
    monkeypatch.setattr("finesub.paths.resolve_model_catalog_override", lambda: old if old.exists() else new)
    plan = core_migration.preview_config_migration(config)
    assert plan["status"] == "ready", plan
    assert old.read_bytes() == contents and not new.exists()
    result = core_migration.apply_config_migration(config, plan["token"], confirmed=True)
    assert new.is_file() and not old.exists()
    assert old.with_name(old.name + ".bak").read_bytes() == contents
    assert (Path(result["backup_path"]) / "model_catalog.psv").read_bytes() == contents
    assert "custom-model" in new.read_text(encoding="utf-8")


def test_moss_paid_choice_is_worker_local(tmp_path, monkeypatch):
    from desktop.backend.worker.model_source import source_route
    from finesub.config import clear_config_cache, read_config_with_path
    config = tmp_path / "config.toml"
    config.write_text('[asr]\nmoss_pro_paid=true\n', encoding="utf-8")
    before = config.read_bytes()
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    clear_config_cache()
    try:
        with source_route(TaskRequest(input="a.wav", asr="moss-pro")):
            assert read_config_with_path()[0]["asr"]["moss_pro_paid"] is False
        assert config.read_bytes() == before
    finally:
        clear_config_cache()
