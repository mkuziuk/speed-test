"""CLI installation helper."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _default_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def _find_speed_test_binary() -> str | None:
    """Find the 'speed-test' executable in PATH."""
    path = shutil.which("speed-test")
    if path:
        return path
    return None


def _is_on_path(directory: Path) -> bool:
    path_env = os.environ.get("PATH", "")
    dirs = [Path(p).resolve() for p in path_env.split(os.pathsep) if p]
    return directory.resolve() in dirs


def install(
    bin_dir: Path | None = None,
    source_path: str | None = None,
    dry_run: bool = False,
) -> int:
    """Idempotently install the speed-test CLI into a user-local bin directory.

    Args:
        bin_dir: Target directory (default: ~/.local/bin).
        source_path: Path to the existing speed-test binary to link.
            If None, auto-detect or create a wrapper script.
        dry_run: If True, print actions instead of performing them.
    """
    target_dir = bin_dir or _default_bin_dir()
    bin_name = "speed-test"
    target_path = target_dir / bin_name

    source = source_path or _find_speed_test_binary()

    if source is None:
        # Create a wrapper script invoking the current interpreter
        wrapper = (
            f"#!/bin/sh\n"
            f'exec "{sys.executable}" -m speed_test_tui.cli "$@"\n'
        )
        if dry_run:
            print(f"[dry-run] Would create directory {target_dir}")
            print(f"[dry-run] Would write wrapper script to {target_path}")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target_path.exists() or target_path.is_symlink():
                target_path.unlink()
            target_path.write_text(wrapper, encoding="utf-8")
            target_path.chmod(0o755)
            print(f"Installed wrapper script to {target_path}")
    else:
        source_resolved = Path(source).resolve()
        if dry_run:
            print(f"[dry-run] Would ensure directory {target_dir}")
            if target_path.exists() or target_path.is_symlink():
                if target_path.is_symlink() and target_path.resolve() == source_resolved:
                    print(f"[dry-run] Symlink already correct.")
                else:
                    print(
                        f"[dry-run] Would replace {target_path} with symlink to {source_resolved}"
                    )
            else:
                print(
                    f"[dry-run] Would create symlink {target_path} -> {source_resolved}"
                )
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target_path.exists() or target_path.is_symlink():
                if target_path.is_symlink() and target_path.resolve() == source_resolved:
                    print(f"Already installed: {target_path} -> {source_resolved}")
                else:
                    target_path.unlink()
                    target_path.symlink_to(source_resolved)
                    print(f"Updated symlink: {target_path} -> {source_resolved}")
            else:
                target_path.symlink_to(source_resolved)
                print(f"Installed: {target_path} -> {source_resolved}")

    if not _is_on_path(target_dir):
        print(
            f"\nNote: {target_dir} is not on your PATH."
            f"\nAdd it to your shell profile, e.g.:"
            f'\n  export PATH="$HOME/.local/bin:$PATH"'
        )
    else:
        print(f"{target_dir} is already on PATH.")

    return 0
