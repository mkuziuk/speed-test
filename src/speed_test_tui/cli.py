"""Command-line entry point for speed-test-tui."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Sequence

from rich.console import Console

from .display import SpeedTestDisplay
from .engine import SpeedTestEngine
from .fake import FakeSpeedTest
from .input_helper import prompt_input, _bottom_toolbar
from .interface import PingResult, SpeedResult, SpeedTestProtocol, SpeedTestResult

from .config import get_custom_presets, add_custom_preset, get_saved_preset, set_saved_preset
from .install import install as _run_install
from .update import update as _run_update

PRESETS: dict[str, dict[str, str]] = {
    "cloudflare": {
        "server": "https://speed.cloudflare.com",
        "download_url": "https://speed.cloudflare.com/__down?bytes=25000000",
        "upload_url": "https://speed.cloudflare.com/__up",
    },
    "ru-moscow": {
        "server": "http://speedtest.mosoblcom.ru:8080",
        "download_url": "http://speedtest.mosoblcom.ru:8080/speedtest/random4000x4000.jpg",
        "upload_url": "http://speedtest.mosoblcom.ru:8080/speedtest/upload.php",
    },
}


def _all_presets() -> dict[str, dict[str, str]]:
    return {**PRESETS, **get_custom_presets()}


_HELP_TEXT = """\
Available commands:
  /run              Run a speed test with current settings
  /preset           Switch to or choose a preset
  /preset add       Add a custom preset (prompts for details or one-line args)
  /server           Show current server URL
  /help             Show this help message
  /quit, /q, /exit  Exit the session
"""


def _extract_command(argv: Sequence[str]) -> tuple[str | None, list[str]]:
    """Return the first non-option token as a command and the remaining argv."""
    for i, arg in enumerate(argv):
        if not arg.startswith("-"):
            return arg, list(argv[:i]) + list(argv[i + 1 :])
    return None, list(argv)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="speed-test",
        description="Minimal terminal internet speed test.",
        epilog="Additional commands: install, update (both support --dry-run).",
    )
    parser.add_argument(
        "--server",
        "-s",
        default=None,
        help="Base server URL for ping checks (default: from preset).",
    )
    parser.add_argument(
        "--download-url",
        default=None,
        help="Download endpoint URL (default: from preset).",
    )
    parser.add_argument(
        "--upload-url",
        default=None,
        help="Upload endpoint URL (default: from preset).",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help="Speed-test server preset (default: saved preset or cloudflare).",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit.",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip upload measurement.",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=10.0,
        help="Download/upload test duration in seconds per phase (default: 10).",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=4,
        help="Concurrent connections for download/upload phases (default: 4).",
    )
    parser.add_argument(
        "--ping-count",
        type=int,
        default=10,
        help="Number of ping requests (default: 10).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print final results as JSON instead of the live TUI.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one test and exit (default: start interactive session).",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use deterministic fake results without network calls.",
    )
    return parser


def resolve_preset(args: argparse.Namespace) -> None:
    """Choose effective preset: explicit CLI > saved config > built-in default."""
    if getattr(args, "_explicit_preset", False):
        return
    saved = get_saved_preset()
    args.preset = saved if saved else "cloudflare"


def resolve_args(args: argparse.Namespace) -> None:
    """Apply preset defaults when the user did not provide explicit URLs."""
    all_presets = _all_presets()
    if args.preset not in all_presets:
        raise ValueError(f"Unknown preset '{args.preset}'")
    preset = all_presets[args.preset]
    if not getattr(args, "_explicit_server", False):
        args.server = preset["server"]
    if not getattr(args, "_explicit_download", False):
        args.download_url = preset["download_url"]
    if not getattr(args, "_explicit_upload", False):
        args.upload_url = preset["upload_url"]


def make_engine(args: argparse.Namespace) -> SpeedTestProtocol:
    """Create the selected speed-test implementation."""
    if args.duration <= 0:
        raise ValueError("--duration must be greater than 0")
    if args.concurrency <= 0:
        raise ValueError("--concurrency must be greater than 0")
    if args.ping_count <= 0:
        raise ValueError("--ping-count must be greater than 0")

    if args.fake:
        return FakeSpeedTest(
            ping_delay=0.05,
            download_duration=min(args.duration, 1.0),
            upload_duration=min(args.duration, 1.0),
            server_url=args.server,
        )

    return SpeedTestEngine(
        server_url=args.server,
        download_url=args.download_url,
        upload_url=args.upload_url,
        ping_count=args.ping_count,
        test_duration=args.duration,
        concurrency=args.concurrency,
    )


async def collect_results(
    engine: SpeedTestProtocol,
    *,
    include_upload: bool = True,
) -> SpeedTestResult:
    """Run a speed test and return the final result without rendering a TUI."""
    final: SpeedTestResult | None = None
    async for phase, payload in engine.run_full_test(include_upload=include_upload):
        if phase == "complete" and isinstance(payload, SpeedTestResult):
            final = payload
    if final is None:
        raise RuntimeError("speed test did not produce a final result")
    return final


async def run_with_display(
    engine: SpeedTestProtocol,
    *,
    include_upload: bool = True,
    console: Console | None = None,
    preset: str | None = None,
) -> SpeedTestResult:
    """Run a speed test while updating the Rich display."""
    display = SpeedTestDisplay(console=console, preset=preset)
    final: SpeedTestResult | None = None
    latest_download: SpeedResult | None = None
    latest_upload: SpeedResult | None = None

    with display.live_display():
        async for phase, payload in engine.run_full_test(include_upload=include_upload):
            if phase == "ping" and isinstance(payload, PingResult):
                display.update_phase("Testing Download", 0.10)
                display.update_ping(payload)
            elif phase == "download_progress" and isinstance(payload, SpeedResult):
                latest_download = payload
                display.update_phase("Testing Download", 0.45)
                display.update_download(payload)
            elif phase == "download" and isinstance(payload, SpeedResult):
                latest_download = payload
                display.update_phase(
                    "Testing Upload" if include_upload else "Complete", 0.70
                )
                display.update_download(payload)
            elif phase == "upload_progress" and isinstance(payload, SpeedResult):
                latest_upload = payload
                display.update_phase("Testing Upload", 0.85)
                display.update_upload(payload)
            elif phase == "upload" and isinstance(payload, SpeedResult):
                latest_upload = payload
                display.update_phase("Complete", 1.0)
                display.update_upload(payload)
            elif phase == "complete" and isinstance(payload, SpeedTestResult):
                # Preserve the latest displayed progress values if the engine's
                # final object is missing one for any reason.
                if payload.download is None:
                    payload.download = latest_download
                if include_upload and payload.upload is None:
                    payload.upload = latest_upload
                final = payload
                display.update_phase("Complete", 1.0)

    if final is None:
        raise RuntimeError("speed test did not produce a final result")
    final.preset = preset
    display.show_summary(final)
    return final


def result_to_json(result: SpeedTestResult) -> str:
    """Serialize speed-test results to stable, pretty JSON."""

    def convert(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            return {key: convert(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return json.dumps(convert(result), indent=2, sort_keys=True)


async def _run_single(
    args: argparse.Namespace,
    console: Console,
) -> int:
    """Run one speed test and return exit code."""
    try:
        engine = make_engine(args)
        include_upload = not args.no_upload
        if args.json:
            result = await collect_results(engine, include_upload=include_upload)
            result.preset = args.preset
            print(result_to_json(result))
        else:
            result = await run_with_display(
                engine, include_upload=include_upload, preset=args.preset
            )
            result.preset = args.preset
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        return 130
    except Exception as exc:  # pragma: no cover - defensive user-facing path
        console.print(f"[red]Error:[/red] {exc}")
        return 1


async def _interactive_session(
    args: argparse.Namespace,
    console: Console,
) -> int:
    """Run the interactive command session."""
    console.print(
        f"[bold green]Speed Test TUI[/bold green] — Interactive session "
        f"(preset: [yellow]{args.preset}[/yellow])"
    )
    console.print("Type /help for available commands.\n")

    while True:
        try:
            prompt_text = f"[{args.preset}] > "
            toolbar = lambda: _bottom_toolbar(args.preset)  # noqa: E731
            cmd = await prompt_input(console, prompt_text, bottom_toolbar=toolbar)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye.[/yellow]")
            return 0

        if not cmd:
            continue

        if cmd in ("/quit", "/q", "/exit"):
            console.print("[yellow]Goodbye.[/yellow]")
            return 0
        elif cmd == "/help":
            console.print(_HELP_TEXT)
        elif cmd == "/run":
            await _run_single(args, console)
        elif cmd in ("/preset", "/presets"):
            if cmd == "/presets":
                console.print("[yellow]/presets is deprecated, use /preset to choose a preset[/yellow]")
            console.print("Available presets:")
            preset_names = list(_all_presets().keys())
            for i, name in enumerate(preset_names, 1):
                marker = " (active)" if args.preset == name else ""
                console.print(f"  {i}) {name}{marker}")
            choice = console.input("[bold]Choose preset (number or name):[/bold] ").strip()
            selected = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(preset_names):
                    selected = preset_names[idx]
            else:
                for name in preset_names:
                    if name.lower() == choice.lower():
                        selected = name
                        break
            if selected is None:
                console.print(f"[red]Unknown preset '{choice}'[/red]")
                continue
            args.preset = selected
            resolve_args(args)
            set_saved_preset(selected)
            console.print(f"[green]Preset set to '{selected}'[/green]")
        elif cmd == "/preset add" or cmd.startswith("/preset add "):
            rest = cmd[len("/preset add"):].strip()
            if rest:
                try:
                    name, server, download_url, upload_url = _parse_preset_add_args(
                        shlex.split(rest)
                    )
                except ValueError as exc:
                    console.print(f"[red]Invalid preset arguments:[/red] {exc}")
                    continue
            else:
                name = console.input("[bold]Preset name:[/bold] ").strip()
                server = console.input("[bold]Server URL:[/bold] ").strip()
                download_url = console.input("[bold]Download URL:[/bold] ").strip()
                upload_url = console.input("[bold]Upload URL:[/bold] ").strip()

            name = (name or "").strip()
            server = (server or "").strip()
            download_url = (download_url or "").strip()
            upload_url = (upload_url or "").strip()

            if not name:
                console.print("[red]Preset name is required[/red]")
                continue
            if name in PRESETS:
                console.print(f"[red]'{name}' is a built-in preset and cannot be overwritten[/red]")
                continue
            if not server or not download_url or not upload_url:
                console.print("[red]Server, download URL, and upload URL are required[/red]")
                continue

            add_custom_preset(name, server, download_url, upload_url)
            console.print(f"[green]Preset '{name}' added[/green]")

            use_now = console.input("[bold]Use it now? [y/N]:[/bold] ").strip().lower()
            if use_now in ("y", "yes"):
                args.preset = name
                resolve_args(args)
                set_saved_preset(name)
                console.print(f"[green]Preset set to '{name}'[/green]")
        elif cmd.startswith("/preset "):
            name = cmd[len("/preset "):].strip()
            all_presets = _all_presets()
            if name in all_presets:
                args.preset = name
                resolve_args(args)
                set_saved_preset(name)
                console.print(f"[green]Preset set to '{name}'[/green]")
            else:
                console.print(f"[red]Unknown preset '{name}'[/red]")
        elif cmd == "/server":
            console.print(f"  Current server: {args.server}")
        else:
            console.print(f"[yellow]Unknown command: {cmd}[/yellow]")


def _parse_preset_add_args(rest_argv: list[str]) -> tuple[str | None, str | None, str | None, str | None]:
    if not rest_argv:
        return None, None, None, None
    name = rest_argv[0]
    server = None
    download_url = None
    upload_url = None
    i = 1
    while i < len(rest_argv):
        if rest_argv[i] == "--server" and i + 1 < len(rest_argv):
            server = rest_argv[i + 1]
            i += 2
        elif rest_argv[i] == "--download-url" and i + 1 < len(rest_argv):
            download_url = rest_argv[i + 1]
            i += 2
        elif rest_argv[i] == "--upload-url" and i + 1 < len(rest_argv):
            upload_url = rest_argv[i + 1]
            i += 2
        else:
            i += 1
    return name, server, download_url, upload_url


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Async CLI body."""
    if argv is None:
        argv = sys.argv[1:]

    cmd, rest_argv = _extract_command(argv)
    if cmd == "install":
        dry_run = "--dry-run" in rest_argv
        return _run_install(dry_run=dry_run)
    if cmd == "update":
        dry_run = "--dry-run" in rest_argv
        return _run_update(dry_run=dry_run)
    if cmd == "preset" and len(rest_argv) >= 1 and rest_argv[0] == "add":
        name, server, download_url, upload_url = _parse_preset_add_args(rest_argv[1:])
        if not name or not name.strip():
            return 1
        if name in PRESETS:
            return 1
        if not server or not download_url or not upload_url:
            return 1
        add_custom_preset(name, server, download_url, upload_url)
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(stderr=True)

    args._explicit_server = args.server is not None
    args._explicit_download = args.download_url is not None
    args._explicit_upload = args.upload_url is not None
    args._explicit_preset = args.preset is not None

    resolve_preset(args)

    if args.list_presets:
        all_presets = _all_presets()
        for name, urls in all_presets.items():
            marker = " (active)" if args.preset == name else ""
            print(f"{name}{marker}  →  {urls['server']}")
        return 0

    resolve_args(args)

    if args.json or args.run_once:
        return await _run_single(args, console)

    return await _interactive_session(args, console)


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous console-script entry point."""
    return asyncio.run(async_main(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
