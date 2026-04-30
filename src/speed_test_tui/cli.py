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

DEFAULT_SERVER_URL = "https://speed.cloudflare.com"
DEFAULT_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=25000000"
DEFAULT_UPLOAD_URL = "https://speed.cloudflare.com/__up"


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="speed-test",
        description="Minimal terminal internet speed test.",
    )
    parser.add_argument(
        "--server",
        "-s",
        default=DEFAULT_SERVER_URL,
        help=f"Base server URL for ping checks (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--download-url",
        default=DEFAULT_DOWNLOAD_URL,
        help="Download endpoint URL.",
    )
    parser.add_argument(
        "--upload-url",
        default=DEFAULT_UPLOAD_URL,
        help="Upload endpoint URL.",
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
            server_url="fake://local-speed-test",
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
