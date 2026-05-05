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


def get_custom_presets() -> dict:
    """Return custom user-defined presets."""
    return load_config().get("custom_presets", {})


def add_custom_preset(name: str, server: str, download_url: str, upload_url: str) -> None:
    """Add or overwrite a custom preset."""
    cfg = load_config()
    if "custom_presets" not in cfg:
        cfg["custom_presets"] = {}
    cfg["custom_presets"][name] = {
        "server": server,
        "download_url": download_url,
        "upload_url": upload_url,
    }
    save_config(cfg)


def remove_custom_preset(name: str) -> None:
    """Remove a custom preset if it exists."""
    cfg = load_config()
    custom = cfg.get("custom_presets", {})
    if name in custom:
        del custom[name]
        save_config(cfg)
