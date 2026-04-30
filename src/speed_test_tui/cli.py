"""Command-line entry point for speed-test-tui."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Sequence

from rich.console import Console

from .display import SpeedTestDisplay
from .engine import SpeedTestEngine
from .fake import FakeSpeedTest
from .interface import PingResult, SpeedResult, SpeedTestProtocol, SpeedTestResult

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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="speed-test",
        description="Minimal terminal internet speed test.",
    )
    parser.add_argument(
        "--server",
        "-s",
        default=None,
        help="Base server URL for ping checks (default: cloudflare preset).",
    )
    parser.add_argument(
        "--download-url",
        default=None,
        help="Download endpoint URL (default: cloudflare preset).",
    )
    parser.add_argument(
        "--upload-url",
        default=None,
        help="Upload endpoint URL (default: cloudflare preset).",
    )
    parser.add_argument(
        "--preset",
        default="cloudflare",
        choices=list(PRESETS.keys()),
        help="Speed-test server preset (default: cloudflare).",
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
        "--fake",
        action="store_true",
        help="Use deterministic fake results without network calls.",
    )
    return parser


def resolve_args(args: argparse.Namespace) -> None:
    """Apply preset defaults when the user did not provide explicit URLs."""
    preset = PRESETS[args.preset]
    args.server = args.server or preset["server"]
    args.download_url = args.download_url or preset["download_url"]
    args.upload_url = args.upload_url or preset["upload_url"]


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
) -> SpeedTestResult:
    """Run a speed test while updating the Rich display."""
    display = SpeedTestDisplay(console=console)
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
                display.update_phase("Testing Upload" if include_upload else "Complete", 0.70)
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


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Async CLI body."""
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(stderr=True)

    if args.list_presets:
        for name, urls in PRESETS.items():
            print(f"{name}  →  {urls['server']}")
        return 0

    resolve_args(args)

    try:
        engine = make_engine(args)
        include_upload = not args.no_upload
        if args.json:
            result = await collect_results(engine, include_upload=include_upload)
            print(result_to_json(result))
        else:
            await run_with_display(engine, include_upload=include_upload)
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        return 130
    except Exception as exc:  # pragma: no cover - defensive user-facing path
        console.print(f"[red]Error:[/red] {exc}")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous console-script entry point."""
    return asyncio.run(async_main(argv))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
