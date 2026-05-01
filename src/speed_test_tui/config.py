"""Local configuration persistence for speed-test-tui."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _config_dir() -> Path:
    env = os.environ.get("SPEED_TEST_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "speed-test-tui"


def _config_path() -> Path:
    return _config_dir() / "config.json"


def load_config() -> dict:
    """Load user config as a dict. Returns empty dict if missing or invalid."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_config(data: dict) -> None:
    """Persist user config."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_saved_preset() -> str | None:
    """Return the saved preset name, if any."""
    return load_config().get("preset")


def set_saved_preset(preset: str) -> None:
    """Save the chosen preset name."""
    cfg = load_config()
    cfg["preset"] = preset
    save_config(cfg)
