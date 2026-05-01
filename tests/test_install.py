"""Tests for install helper."""

import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from speed_test_tui.install import _find_speed_test_binary, _is_on_path, install


def test_find_speed_test_binary_returns_path_or_none():
    result = _find_speed_test_binary()
    # In the venv the wrapper may exist; just assert it returns str or None
    assert result is None or isinstance(result, str)


def test_is_on_path_detects_directory():
    some_dir = Path("/usr/local/bin")
    with patch.dict(os.environ, {"PATH": str(some_dir)}):
        assert _is_on_path(some_dir) is True
    assert _is_on_path(Path("/unlikely/path/xyz")) is False


def test_install_dry_run_no_files_created(tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    status = install(bin_dir=bin_dir, source_path=None, dry_run=True)
    assert status == 0
    assert not bin_dir.exists()
    captured = capsys.readouterr().out
    assert "[dry-run]" in captured


def test_install_creates_wrapper_when_no_source(tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    with patch("speed_test_tui.install._find_speed_test_binary", return_value=None):
        status = install(bin_dir=bin_dir, source_path=None, dry_run=False)
    assert status == 0
    target = bin_dir / "speed-test"
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert sys.executable in text
    assert os.access(target, os.X_OK)
    captured = capsys.readouterr().out
    assert "Installed wrapper" in captured


def test_install_creates_symlink_when_source_given(tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    source = tmp_path / "fake_speed_test"
    source.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    source.chmod(0o755)
    status = install(bin_dir=bin_dir, source_path=str(source), dry_run=False)
    assert status == 0
    target = bin_dir / "speed-test"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()
    captured = capsys.readouterr().out
    assert "Installed:" in captured


def test_install_idempotent_symlink(tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    source = tmp_path / "fake_speed_test"
    source.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    source.chmod(0o755)
    install(bin_dir=bin_dir, source_path=str(source), dry_run=False)
    status = install(bin_dir=bin_dir, source_path=str(source), dry_run=False)
    assert status == 0
    captured = capsys.readouterr().out
    assert "Already installed" in captured


def test_install_warns_when_not_on_path(tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    with patch.dict(os.environ, {"PATH": "/usr/bin"}):
        status = install(bin_dir=bin_dir, source_path=None, dry_run=True)
    assert status == 0
    captured = capsys.readouterr().out
    assert "not on your PATH" in captured


def test_install_does_not_warn_when_on_path(tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    with patch.dict(os.environ, {"PATH": str(bin_dir)}):
        status = install(bin_dir=bin_dir, source_path=None, dry_run=True)
    assert status == 0
    captured = capsys.readouterr().out
    assert "already on PATH" in captured
