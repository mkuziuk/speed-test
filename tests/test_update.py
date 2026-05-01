"""Tests for update helper."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from speed_test_tui.update import _find_git_root, update


def test_find_git_root_returns_real_repo():
    root = _find_git_root()
    assert root is not None
    assert (root / ".git").is_dir()


def test_update_dry_run_prints_commands(tmp_path, capsys):
    status = update(dry_run=True, git_root=tmp_path)
    assert status == 0
    captured = capsys.readouterr().out
    assert "[dry-run] Would run: git" in captured
    assert "[dry-run] Would run:" in captured
    assert "pip" in captured


def test_update_runs_commands_successfully(tmp_path, capsys):
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0)

    status = update(dry_run=False, git_root=tmp_path, _runner=fake_runner)
    assert status == 0
    assert len(calls) == 2
    assert calls[0][0] == "git"
    assert calls[1][0] == sys.executable
    captured = capsys.readouterr().out
    assert "Update complete" in captured


def test_update_fails_when_git_root_none(capsys):
    with patch("speed_test_tui.update._find_git_root", return_value=None):
        status = update(dry_run=False)
    assert status == 1
    captured = capsys.readouterr().out
    assert "only supported when installed from a git repository" in captured


def test_update_fails_on_command_failure(tmp_path, capsys):
    def fake_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1)

    status = update(dry_run=False, git_root=tmp_path, _runner=fake_runner)
    assert status == 1
    captured = capsys.readouterr().out
    assert "Command failed with exit code 1" in captured


def test_update_dry_run_no_subprocess_calls(tmp_path):
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0)

    status = update(dry_run=True, git_root=tmp_path, _runner=fake_runner)
    assert status == 0
    assert calls == []
