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
