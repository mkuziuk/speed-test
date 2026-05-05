"""Tests for config persistence."""

import json

import pytest

from speed_test_tui.config import (
    _config_path,
    get_saved_preset,
    load_config,
    save_config,
    set_saved_preset,
)


def test_load_config_missing_returns_empty(isolated_speed_test_config):
    assert load_config() == {}


def test_load_config_invalid_json_returns_empty(isolated_speed_test_config):
    path = _config_path()
    path.write_text("not json", encoding="utf-8")
    assert load_config() == {}


def test_load_config_non_dict_returns_empty(isolated_speed_test_config):
    path = _config_path()
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_config() == {}


def test_save_config_round_trip(isolated_speed_test_config):
    save_config({"preset": "ru-moscow", "foo": "bar"})
    assert load_config() == {"preset": "ru-moscow", "foo": "bar"}


def test_get_saved_preset_none_when_empty(isolated_speed_test_config):
    assert get_saved_preset() is None


def test_set_saved_preset_persists(isolated_speed_test_config):
    set_saved_preset("cloudflare")
    assert get_saved_preset() == "cloudflare"
    set_saved_preset("ru-moscow")
    assert get_saved_preset() == "ru-moscow"


def test_config_file_created_in_isolated_dir(isolated_speed_test_config):
    set_saved_preset("cloudflare")
    path = _config_path()
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["preset"] == "cloudflare"


# --- Custom preset tests ---


def test_add_custom_preset_persists():
    from speed_test_tui.config import add_custom_preset, get_custom_presets, load_config

    add_custom_preset("mytest", "http://s.com", "http://s.com/dl", "http://s.com/ul")
    expected = {"server": "http://s.com", "download_url": "http://s.com/dl", "upload_url": "http://s.com/ul"}
    assert load_config()["custom_presets"]["mytest"] == expected
    assert get_custom_presets() == {"mytest": expected}


def test_get_custom_presets_empty_default():
    from speed_test_tui.config import get_custom_presets

    assert get_custom_presets() == {}


def test_add_custom_preset_overwrites():
    from speed_test_tui.config import add_custom_preset, get_custom_presets

    add_custom_preset("mytest", "http://s.com", "http://s.com/dl", "http://s.com/ul")
    add_custom_preset("mytest", "http://other.com", "http://other.com/dl", "http://other.com/ul")
    expected = {"server": "http://other.com", "download_url": "http://other.com/dl", "upload_url": "http://other.com/ul"}
    assert get_custom_presets()["mytest"] == expected


def test_remove_custom_preset_removes():
    from speed_test_tui.config import add_custom_preset, get_custom_presets, load_config, remove_custom_preset

    add_custom_preset("mytest", "http://s.com", "http://s.com/dl", "http://s.com/ul")
    remove_custom_preset("mytest")
    assert "mytest" not in get_custom_presets()
    assert "mytest" not in load_config().get("custom_presets", {})


def test_add_custom_preset_preserves_saved_preset():
    from speed_test_tui.config import add_custom_preset, get_saved_preset, set_saved_preset

    set_saved_preset("cloudflare")
    add_custom_preset("mytest", "http://s.com", "http://s.com/dl", "http://s.com/ul")
    assert get_saved_preset() == "cloudflare"


def test_add_custom_preset_different_names_independent():
    from speed_test_tui.config import add_custom_preset, get_custom_presets

    add_custom_preset("a", "http://a.com", "http://a.com/dl", "http://a.com/ul")
    add_custom_preset("b", "http://b.com", "http://b.com/dl", "http://b.com/ul")
    presets = get_custom_presets()
    assert "a" in presets
    assert "b" in presets
    assert presets["a"]["server"] == "http://a.com"
    assert presets["b"]["server"] == "http://b.com"
