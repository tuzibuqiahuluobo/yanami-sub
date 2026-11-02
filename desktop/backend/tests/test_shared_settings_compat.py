import pytest

from desktop.backend.common.models import SharedSettings
from desktop.backend.settings.store import SettingsStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    return SettingsStore(tmp_path)


def test_unset_scale_stays_unset_without_creating_a_config(store):
    assert store.shared_settings().split_length_scale is None
    assert not store.config_path.exists()


def test_shared_scale_round_trips_without_overwriting_other_settings(store):
    store.config_path.write_text('# 用户注释\n[llm]\nstyle = "字幕组"\n', encoding="utf-8")
    assert store.save_shared_settings(SharedSettings(split_length_scale=0.8)).split_length_scale == 0.8
    assert '[llm]\nstyle = "字幕组"' in store.config_path.read_text(encoding="utf-8")
    assert store.save_shared_settings(SharedSettings()).split_length_scale is None
    assert '# 用户注释' in store.config_path.read_text(encoding="utf-8")
    assert 'length_scale' not in store.config_path.read_text(encoding="utf-8")


def test_invalid_shared_scale_is_refused_before_config_write(store):
    with pytest.raises(ValueError):
        store.save_shared_settings(SharedSettings(split_length_scale=4.0))
    assert not store.config_path.exists()


@pytest.mark.parametrize("value", ["true", '"0.8"', '"not a number"'])
def test_hand_edited_wrong_types_are_not_silently_coerced(store, value):
    store.config_path.write_text(f"[segmentation]\nlength_scale = {value}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        store.shared_settings()
