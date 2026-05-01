"""Safe local update for speed-test-tui."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


def _find_git_root() -> Path | None:
    """Find the git repository root for the installed package."""
    try:
        import speed_test_tui

        pkg_dir = Path(speed_test_tui.__file__).resolve().parent
    except Exception:
        return None
    for path in [pkg_dir, *pkg_dir.parents]:
        if (path / ".git").is_dir():
            return path
    return None


def _default_runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, **kwargs)


def update(
    dry_run: bool = False,
    git_root: Path | None = None,
    _runner: Callable[..., subprocess.CompletedProcess[str]] = _default_runner,
) -> int:
    """Update speed-test-tui from its git source.

    Args:
        dry_run: If True, print commands instead of running them.
        git_root: Override auto-discovered git repository root.
        _runner: Subprocess runner (for testing).
    """
    if git_root is None:
        git_root = _find_git_root()
    if git_root is None:
        print("Update is only supported when installed from a git repository.")
        print("You can reinstall manually with: pip install --upgrade <path-or-url>")
        return 1

    commands = [
        ["git", "-C", str(git_root), "pull", "--ff-only"],
        [sys.executable, "-m", "pip", "install", "--upgrade", "-e", str(git_root)],
    ]

    for cmd in commands:
        cmd_str = " ".join(cmd)
        if dry_run:
            print(f"[dry-run] Would run: {cmd_str}")
        else:
            print(f"Running: {cmd_str}")
            result = _runner(cmd, capture_output=False, text=True)
            if result.returncode != 0:
                print(
                    f"Command failed with exit code {result.returncode}: {cmd_str}"
                )
                return result.returncode

    print("Update complete.")
    return 0
