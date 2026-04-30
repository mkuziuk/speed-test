# Speed Test TUI Implementation Plan

A minimalistic terminal-based internet speed test application built in Python.

---

## Overview

**speed-test-tui** is a command-line application that measures internet connection performance directly from the terminal. It provides real-time feedback during testing and displays results in a clean, readable format using the `rich` library.

### Goals

- **Minimal dependencies**: Only `httpx` and `rich` at runtime
- **Testable by design**: Interface-based architecture enables full test coverage without network access
- **Async-first**: Leverages Python's async capabilities for concurrent network operations
- **User-friendly**: Live progress updates, clear results, optional JSON output for automation

### Non-Goals

- Server discovery/benchmarking (user specifies server URL)
- Historical data storage
- GUI or web interface
- Multi-platform binary distribution (Python package only)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI Layer                              │
│                    (cli.py, __main__.py)                         │
│         argparse → Engine Selection → Display Context            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SpeedTestProtocol                           │
│                        (interface.py)                            │
│     measure_ping() │ measure_download() │ measure_upload()       │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│    SpeedTestEngine        │   │      FakeSpeedTest        │
│      (engine.py)          │   │       (fake.py)           │
│   Real network operations │   │   Configurable mock data  │
│   httpx.AsyncClient       │   │   Simulated delays        │
└───────────────────────────┘   └───────────────────────────┘
                │                               │
                └───────────────┬───────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SpeedTestDisplay                            │
│                       (display.py)                               │
│              rich.live.Live │ Progress bars │ Summary table      │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Dependency Inversion**: High-level CLI depends on abstract `SpeedTestProtocol`, not concrete implementations
2. **Single Responsibility**: Each module has one clear purpose
3. **Async Throughout**: All I/O operations are non-blocking
4. **Progressive Disclosure**: Display updates incrementally as test phases complete

---

## Component Details

### 1. Interface Layer (`interface.py`)

Defines the contract between the CLI/display and the testing engine.

```python
from dataclasses import dataclass
from typing import Protocol, AsyncIterator, Optional
from datetime import datetime

@dataclass
class PingResult:
    """Results from ping measurement."""
    min_ms: float
    max_ms: float
    avg_ms: float
    jitter_ms: float
    packets_sent: int
    packets_received: int

@dataclass
class SpeedResult:
    """Results from download/upload measurement."""
    bytes_transferred: int
    duration_seconds: float
    speed_bps: float  # Bits per second
    speed_mbps: float  # Megabits per second (derived)

@dataclass
class SpeedTestResult:
    """Complete test results."""
    timestamp: datetime
    server_url: str
    ping: Optional[PingResult]
    download: Optional[SpeedResult]
    upload: Optional[SpeedResult]

class SpeedTestProtocol(Protocol):
    """Abstract interface for speed test implementations."""

    async def measure_ping(self) -> PingResult:
        """Measure latency to the server."""
        ...

    async def measure_download(self) -> AsyncIterator[SpeedResult]:
        """Measure download speed, yielding progress updates."""
        ...

    async def measure_upload(self) -> AsyncIterator[SpeedResult]:
        """Measure upload speed, yielding progress updates."""
        ...

    async def run_full_test(
        self,
        include_upload: bool = True
    ) -> AsyncIterator[tuple[str, object]]:
        """
        Run complete test suite, yielding (phase, result) tuples.
        Phases: 'ping', 'download', 'upload', 'complete'
        """
        ...
```

**Key Design Decisions:**
- `Protocol` instead of `ABC` for structural subtyping (no inheritance required)
- `AsyncIterator` for progress updates during long-running operations
- Dataclasses for immutable, hashable result objects
- Optional results allow skipping phases (e.g., `--no-upload`)

---

### 2. Real Engine (`engine.py`)

Production implementation using actual network operations.

```python
import httpx
import asyncio
import time
from typing import AsyncIterator, Optional

class SpeedTestEngine:
    """Real speed test implementation using httpx."""

    DEFAULT_PING_COUNT = 10
    DEFAULT_TEST_DURATION = 10.0  # seconds
    DEFAULT_CONCURRENCY = 4

    def __init__(
        self,
        server_url: str,
        download_url: Optional[str] = None,
        upload_url: Optional[str] = None,
        ping_count: int = DEFAULT_PING_COUNT,
        test_duration: float = DEFAULT_TEST_DURATION,
        concurrency: int = DEFAULT_CONCURRENCY,
        timeout: float = 30.0,
    ):
        self.server_url = server_url
        self.download_url = download_url or f"{server_url}/download"
        self.upload_url = upload_url or f"{server_url}/upload"
        self.ping_count = ping_count
        self.test_duration = test_duration
        self.concurrency = concurrency
        self.timeout = timeout

    async def measure_ping(self) -> PingResult:
        """
        Measure latency using sequential HTTP HEAD requests.

        Implementation:
        - Send HEAD requests sequentially (not concurrent)
        - Record round-trip time for each request
        - Calculate min, max, avg, and jitter (standard deviation)
        - Handle timeouts as packet loss
        """
        latencies: list[float] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for _ in range(self.ping_count):
                start = time.perf_counter()
                try:
                    response = await client.head(self.server_url)
                    elapsed = (time.perf_counter() - start) * 1000  # ms
                    if response.status_code < 400:
                        latencies.append(elapsed)
                except httpx.RequestError:
                    pass  # Count as lost packet
                await asyncio.sleep(0.1)  # Brief pause between pings

        if not latencies:
            return PingResult(
                min_ms=0, max_ms=0, avg_ms=0, jitter_ms=0,
                packets_sent=self.ping_count, packets_received=0
            )

        # Calculate statistics
        min_ms = min(latencies)
        max_ms = max(latencies)
        avg_ms = sum(latencies) / len(latencies)
        jitter_ms = self._calculate_jitter(latencies)

        return PingResult(
            min_ms=min_ms,
            max_ms=max_ms,
            avg_ms=avg_ms,
            jitter_ms=jitter_ms,
            packets_sent=self.ping_count,
            packets_received=len(latencies)
        )

    async def measure_download(self) -> AsyncIterator[SpeedResult]:
        """
        Measure download speed using concurrent GET requests.

        Implementation:
        - Spawn concurrent tasks downloading from CDN endpoint
        - Track total bytes and elapsed time
        - Yield progress updates every 500ms
        - Cancel all tasks when duration expires
        """
        start_time = time.perf_counter()
        total_bytes = 0
        semaphore = asyncio.Semaphore(self.concurrency)

        async def download_chunk() -> int:
            async with semaphore:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    try:
                        async with client.stream('GET', self.download_url) as resp:
                            resp.raise_for_status()
                            chunk_bytes = 0
                            async for chunk in resp.aiter_bytes(chunk_size=8192):
                                chunk_bytes += len(chunk)
                            return chunk_bytes
                    except httpx.RequestError:
                        return 0

        # Launch concurrent download tasks
        tasks = [asyncio.create_task(download_chunk()) for _ in range(self.concurrency)]

        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= self.test_duration:
                break

            # Yield progress update
            yield SpeedResult(
                bytes_transferred=total_bytes,
                duration_seconds=elapsed,
                speed_bps=0,
                speed_mbps=0
            )
            await asyncio.sleep(0.5)

        # Cancel remaining tasks and collect results
        for task in tasks:
            task.cancel()

        # Final result with actual speed calculation
        final_elapsed = time.perf_counter() - start_time
        final_bytes = sum(t.result() for t in tasks if t.done() and not t.cancelled())

        yield SpeedResult(
            bytes_transferred=final_bytes,
            duration_seconds=final_elapsed,
            speed_bps=(final_bytes * 8) / final_elapsed,
            speed_mbps=((final_bytes * 8) / final_elapsed) / 1_000_000
        )

    async def measure_upload(self) -> AsyncIterator[SpeedResult]:
        """
        Measure upload speed using concurrent POST requests.

        Implementation:
        - Generate random payload (or use deterministic pattern)
        - POST to upload endpoint concurrently
        - Track bytes sent and elapsed time
        - Yield progress updates every 500ms
        """
        # Similar structure to download, but with POST and payload generation
        ...

    async def run_full_test(
        self,
        include_upload: bool = True
    ) -> AsyncIterator[tuple[str, object]]:
        """
        Orchestrate full test sequence.

        Yields:
            ('ping', PingResult)
            ('download_progress', SpeedResult) ... multiple times
            ('download', SpeedResult)  # final
            ('upload_progress', SpeedResult) ... multiple times (if enabled)
            ('upload', SpeedResult)  # final (if enabled)
            ('complete', SpeedTestResult)
        """
        from datetime import datetime

        ping_result = await self.measure_ping()
        yield ('ping', ping_result)

        download_result = None
        async for result in self.measure_download():
            yield ('download_progress', result)
            download_result = result

        upload_result = None
        if include_upload:
            async for result in self.measure_upload():
                yield ('upload_progress', result)
                upload_result = result

        final_result = SpeedTestResult(
            timestamp=datetime.now(),
            server_url=self.server_url,
            ping=ping_result,
            download=download_result,
            upload=upload_result
        )
        yield ('complete', final_result)

    @staticmethod
    def _calculate_jitter(latencies: list[float]) -> float:
        """Calculate jitter as standard deviation of latencies."""
        if len(latencies) < 2:
            return 0.0
        avg = sum(latencies) / len(latencies)
        variance = sum((x - avg) ** 2 for x in latencies) / len(latencies)
        return variance ** 0.5
```

---

### 3. Fake Engine (`fake.py`)

Test double for unit testing without network access.

```python
import asyncio
from typing import AsyncIterator, Optional
from .interface import (
    SpeedTestProtocol,
    PingResult,
    SpeedResult,
    SpeedTestResult,
)

class FakeSpeedTest:
    """
    Fake implementation for testing.

    Configurable results with simulated delays to mimic real behavior.
    """

    def __init__(
        self,
        ping_result: Optional[PingResult] = None,
        download_result: Optional[SpeedResult] = None,
        upload_result: Optional[SpeedResult] = None,
        ping_delay: float = 0.1,
        download_duration: float = 2.0,
        upload_duration: float = 2.0,
    ):
        self.ping_result = ping_result or self._default_ping()
        self.download_result = download_result or self._default_download()
        self.upload_result = upload_result or self._default_upload()
        self.ping_delay = ping_delay
        self.download_duration = download_duration
        self.upload_duration = upload_duration

    async def measure_ping(self) -> PingResult:
        await asyncio.sleep(self.ping_delay)
        return self.ping_result

    async def measure_download(self) -> AsyncIterator[SpeedResult]:
        """Yield progress updates at intervals."""
        elapsed = 0.0
        interval = 0.5
        while elapsed < self.download_duration:
            await asyncio.sleep(interval)
            elapsed += interval
            progress = elapsed / self.download_duration
            yield SpeedResult(
                bytes_transferred=int(self.download_result.bytes_transferred * progress),
                duration_seconds=elapsed,
                speed_bps=self.download_result.speed_bps,
                speed_mbps=self.download_result.speed_mbps,
            )
        yield self.download_result

    async def measure_upload(self) -> AsyncIterator[SpeedResult]:
        elapsed = 0.0
        interval = 0.5
        while elapsed < self.upload_duration:
            await asyncio.sleep(interval)
            elapsed += interval
            progress = elapsed / self.upload_duration
            yield SpeedResult(
                bytes_transferred=int(self.upload_result.bytes_transferred * progress),
                duration_seconds=elapsed,
                speed_bps=self.upload_result.speed_bps,
                speed_mbps=self.upload_result.speed_mbps,
            )
        yield self.upload_result

    async def run_full_test(
        self,
        include_upload: bool = True
    ) -> AsyncIterator[tuple[str, object]]:
        from datetime import datetime

        yield ('ping', await self.measure_ping())

        download_result = None
        async for result in self.measure_download():
            yield ('download_progress', result)
            download_result = result

        upload_result = None
        if include_upload:
            async for result in self.measure_upload():
                yield ('upload_progress', result)
                upload_result = result

        yield ('complete', SpeedTestResult(
            timestamp=datetime.now(),
            server_url='https://fake-server.example',
            ping=self.ping_result,
            download=download_result,
            upload=upload_result,
        ))

    @staticmethod
    def _default_ping() -> PingResult:
        return PingResult(
            min_ms=15.0, max_ms=25.0, avg_ms=18.5, jitter_ms=3.2,
            packets_sent=10, packets_received=10
        )

    @staticmethod
    def _default_download() -> SpeedResult:
        mbps = 100.0
        duration = 10.0
        bytes_transferred = int((mbps * 1_000_000 / 8) * duration)
        return SpeedResult(
            bytes_transferred=bytes_transferred,
            duration_seconds=duration,
            speed_bps=mbps * 1_000_000,
            speed_mbps=mbps,
        )

    @staticmethod
    def _default_upload() -> SpeedResult:
        mbps = 50.0
        duration = 10.0
        bytes_transferred = int((mbps * 1_000_000 / 8) * duration)
        return SpeedResult(
            bytes_transferred=bytes_transferred,
            duration_seconds=duration,
            speed_bps=mbps * 1_000_000,
            speed_mbps=mbps,
        )
```

---

### 4. Display Layer (`display.py`)

Terminal UI using `rich` for live updates.

```python
from contextlib import contextmanager
from typing import Optional
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.layout import Layout

from .interface import PingResult, SpeedResult, SpeedTestResult

class SpeedTestDisplay:
    """
    Manages terminal display for speed test.

    Uses rich.Live for real-time updates without screen flicker.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._current_phase: str = "Initializing"
        self._ping_result: Optional[PingResult] = None
        self._download_result: Optional[SpeedResult] = None
        self._upload_result: Optional[SpeedResult] = None
        self._progress: float = 0.0

    @contextmanager
    def live_display(self):
        """Context manager for live display."""
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        with Live(layout, console=self.console, refresh_per_second=4) as live:
            self._live = live
            self._update_layout(layout)
            yield
            self._live = None

    def update_phase(self, phase: str, progress: float = 0.0):
        """Update current test phase."""
        self._current_phase = phase
        self._progress = progress
        if self._live:
            self._update_layout(self._live.layout)

    def update_ping(self, result: PingResult):
        """Update ping results."""
        self._ping_result = result
        if self._live:
            self._update_layout(self._live.layout)

    def update_download(self, result: SpeedResult):
        """Update download progress/result."""
        self._download_result = result
        if self._live:
            self._update_layout(self._live.layout)

    def update_upload(self, result: SpeedResult):
        """Update upload progress/result."""
        self._upload_result = result
        if self._live:
            self._update_layout(self._live.layout)

    def show_summary(self, result: SpeedTestResult):
        """Display final summary table."""
        table = Table(title="Speed Test Results", box="ROUNDED")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        # Ping section
        if result.ping:
            table.add_row("Ping (Avg)", f"{result.ping.avg_ms:.1f} ms")
            table.add_row("Ping (Min)", f"{result.ping.min_ms:.1f} ms")
            table.add_row("Ping (Max)", f"{result.ping.max_ms:.1f} ms")
            table.add_row("Jitter", f"{result.ping.jitter_ms:.1f} ms")

        # Download section
        if result.download:
            table.add_row("", "")  # Spacer
            table.add_row("Download", f"{result.download.speed_mbps:.1f} Mbps")
            table.add_row("", f"{self._format_bytes(result.download.bytes_transferred)}")

        # Upload section
        if result.upload:
            table.add_row("", "")  # Spacer
            table.add_row("Upload", f"{result.upload.speed_mbps:.1f} Mbps")
            table.add_row("", f"{self._format_bytes(result.upload.bytes_transferred)}")

        self.console.print(table)

    def _update_layout(self, layout: Layout):
        """Update the live layout with current state."""
        # Header
        layout["header"].update(Panel(
            "[bold blue]Speed Test TUI[/bold blue]",
            box="NONE"
        ))

        # Body - current operation
        body_content = self._render_body()
        layout["body"].update(Panel(body_content, title=self._current_phase))

        # Footer - progress
        layout["footer"].update(
            f"[dim]Progress: {self._progress:.0%}[/dim]"
        )

    def _render_body(self) -> str:
        """Render body content based on current state."""
        lines = []

        if self._ping_result:
            lines.append(f"[green]✓[/green] Ping: {self._ping_result.avg_ms:.1f} ms")

        if self._download_result:
            speed = self._download_result.speed_mbps
            if speed > 0:
                lines.append(f"[green]{'✓' if self._current_phase != 'download' else '↓'}[/green] Download: {speed:.1f} Mbps")

        if self._upload_result:
            speed = self._upload_result.speed_mbps
            if speed > 0:
                lines.append(f"[green]{'✓' if self._current_phase != 'upload' else '↑'}[/green] Upload: {speed:.1f} Mbps")

        if not lines:
            lines.append("[dim]Starting test...[/dim]")

        return "\n".join(lines)

    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} TB"
```

---

### 5. CLI Layer (`cli.py`, `__main__.py`)

Command-line interface and entry points.

```python
# cli.py
import argparse
import asyncio
import json
import sys
from typing import Optional

from .interface import SpeedTestProtocol, SpeedTestResult
from .engine import SpeedTestEngine
from .fake import FakeSpeedTest
from .display import SpeedTestDisplay


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="speed-test",
        description="Measure your internet connection speed"
    )

    parser.add_argument(
        "--server", "-s",
        type=str,
        default="https://speedtest.example.com",
        help="Speed test server URL (default: https://speedtest.example.com)"
    )

    parser.add_argument(
        "--download-url",
        type=str,
        help="Custom download endpoint URL"
    )

    parser.add_argument(
        "--upload-url",
        type=str,
        help="Custom upload endpoint URL"
    )

    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip upload test"
    )

    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=10.0,
        help="Test duration in seconds per phase (default: 10)"
    )

    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=4,
        help="Number of concurrent connections (default: 4)"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use fake engine for testing (no network)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )

    return parser


async def run_test(args: argparse.Namespace) -> SpeedTestResult:
    """Run speed test with given arguments."""
    # Select engine
    if args.fake:
        engine: SpeedTestProtocol = FakeSpeedTest()
    else:
        engine = SpeedTestEngine(
            server_url=args.server,
            download_url=args.download_url,
            upload_url=args.upload_url,
            test_duration=args.duration,
            concurrency=args.concurrency,
        )

    # Create display (unless JSON output)
    display = SpeedTestDisplay()

    final_result = None

    if args.json:
        # Silent mode for JSON output
        async for phase, data in engine.run_full_test(include_upload=not args.no_upload):
            if phase == 'complete':
                final_result = data
    else:
        # Live display mode
        with display.live_display():
            async for phase, data in engine.run_full_test(include_upload=not args.no_upload):
                if phase == 'ping':
                    display.update_phase("Measuring Ping", 0.25)
                    display.update_ping(data)
                elif phase == 'download_progress':
                    display.update_phase("Testing Download", 0.50)
                    display.update_download(data)
                elif phase == 'download':
                    display.update_download(data)
                elif phase == 'upload_progress':
                    display.update_phase("Testing Upload", 0.75)
                    display.update_upload(data)
                elif phase == 'upload':
                    display.update_upload(data)
                elif phase == 'complete':
                    display.update_phase("Complete", 1.0)
                    final_result = data

        # Show final summary
        display.show_summary(final_result)

    return final_result


def result_to_json(result: SpeedTestResult) -> dict:
    """Convert result to JSON-serializable dict."""
    return {
        "timestamp": result.timestamp.isoformat(),
        "server_url": result.server_url,
        "ping": {
            "min_ms": result.ping.min_ms if result.ping else None,
            "max_ms": result.ping.max_ms if result.ping else None,
            "avg_ms": result.ping.avg_ms if result.ping else None,
            "jitter_ms": result.ping.jitter_ms if result.ping else None,
        } if result.ping else None,
        "download": {
            "speed_mbps": result.download.speed_mbps if result.download else None,
            "bytes_transferred": result.download.bytes_transferred if result.download else None,
        } if result.download else None,
        "upload": {
            "speed_mbps": result.upload.speed_mbps if result.upload else None,
            "bytes_transferred": result.upload.bytes_transferred if result.upload else None,
        } if result.upload else None,
    }


def main():
    """CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        result = asyncio.run(run_test(args))

        if args.json:
            print(json.dumps(result_to_json(result), indent=2))
        elif args.debug:
            print(f"\n[Debug] Full result object: {result}")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\nTest cancelled by user")
        sys.exit(130)
    except Exception as e:
        if args.debug:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

```python
# __main__.py
"""Allow running as: python -m speed_test_tui"""
from .cli import main

if __name__ == "__main__":
    main()
```

---

## Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   User      │     │    CLI       │     │   Display       │
│  (terminal) │────▶│  (cli.py)    │────▶│  (display.py)   │
└─────────────┘     └──────────────┘     └─────────────────┘
                           │                      │
                           ▼                      │
                    ┌──────────────┐              │
                    │   Engine     │──────────────┘
                    │ (engine.py   │  Progress
                    │  or fake.py) │  callbacks
                    └──────────────┘
```

### Sequence

1. **CLI Initialization**
   - Parse command-line arguments
   - Instantiate `SpeedTestEngine` or `FakeSpeedTest` based on `--fake` flag
   - Create `SpeedTestDisplay` (unless `--json` mode)

2. **Test Execution**
   - Enter `display.live_display()` context (creates `rich.Live`)
   - Call `engine.run_full_test(include_upload=...)`
   - Engine yields `(phase, data)` tuples asynchronously

3. **Progress Updates**
   - CLI receives each yield from engine
   - Calls appropriate `display.update_*()` method
   - Display refreshes `Live` layout automatically

4. **Completion**
   - Engine yields `('complete', SpeedTestResult)`
   - CLI exits `live_display()` context
   - Calls `display.show_summary()` for final table
   - Optionally outputs JSON

5. **Exit**
   - Return exit code 0 on success, non-zero on error
   - Handle `KeyboardInterrupt` gracefully

---

## Testing Strategy

### Test Pyramid

```
         ┌───────────┐
         │  E2E/CLI  │  Few tests - verify integration
         └───────────┘
        ┌─────────────┐
        │  Component  │  Moderate - display formatting,
        │   Tests     │  engine orchestration
        └─────────────┘
       ┌───────────────┐
       │    Unit       │  Many - interface contract,
       │    Tests      │  fake behavior, data classes
       └───────────────┘
```

### Test Files

| File | Purpose |
|------|---------|
| `test_interface.py` | Verify Protocol contract, dataclass behavior |
| `test_fake.py` | Verify fake returns configured results with delays |
| `test_display.py` | Verify output formatting (capture console output) |
| `test_cli.py` | Verify argument parsing, engine selection, JSON output |
| `test_engine.py` | Integration tests (may require network or mocks) |

### Key Test Patterns

#### 1. Interface Contract Tests

```python
# test_interface.py
import pytest
from speed_test_tui.interface import (
    SpeedTestProtocol,
    PingResult, SpeedResult, SpeedTestResult,
)

def test_ping_result_dataclass():
    result = PingResult(min_ms=10, max_ms=20, avg_ms=15, jitter_ms=2,
                        packets_sent=10, packets_received=10)
    assert result.avg_ms == 15
    assert result.jitter_ms == 2

def test_speed_result_mbps_calculation():
    # 100 Mbps = 100,000,000 bits/sec
    result = SpeedResult(
        bytes_transferred=12_500_000,  # 100 megabits in bytes
        duration_seconds=1.0,
        speed_bps=100_000_000,
        speed_mbps=100.0,
    )
    assert result.speed_mbps == 100.0
```

#### 2. Fake Engine Tests

```python
# test_fake.py
import pytest
import asyncio
from speed_test_tui.fake import FakeSpeedTest
from speed_test_tui.interface import PingResult

@pytest.mark.asyncio
async def test_fake_ping_returns_configured_result():
    expected = PingResult(min_ms=5, max_ms=10, avg_ms=7, jitter_ms=1,
                          packets_sent=10, packets_received=10)
    fake = FakeSpeedTest(ping_result=expected)

    result = await fake.measure_ping()
    assert result.avg_ms == expected.avg_ms

@pytest.mark.asyncio
async def test_fake_ping_has_delay():
    fake = FakeSpeedTest(ping_delay=0.2)

    start = asyncio.get_event_loop().time()
    await fake.measure_ping()
    elapsed = asyncio.get_event_loop().time() - start

    assert elapsed >= 0.2
```

#### 3. Display Tests

```python
# test_display.py
import pytest
from io import StringIO
from rich.console import Console
from speed_test_tui.display import SpeedTestDisplay
from speed_test_tui.interface import PingResult, SpeedResult, SpeedTestResult
from datetime import datetime

def test_summary_table_formatting():
    console = Console(file=StringIO(), force_terminal=True)
    display = SpeedTestDisplay(console=console)

    result = SpeedTestResult(
        timestamp=datetime.now(),
        server_url="https://test.example",
        ping=PingResult(min_ms=10, max_ms=20, avg_ms=15, jitter_ms=2,
                        packets_sent=10, packets_received=10),
        download=SpeedResult(bytes_transferred=1000000, duration_seconds=10,
                             speed_bps=800000, speed_mbps=0.8),
        upload=None,
    )

    display.show_summary(result)
    output = console.file.getvalue()

    assert "Ping (Avg)" in output
    assert "15.0 ms" in output
    assert "Download" in output
    assert "0.8 Mbps" in output
```

#### 4. CLI Tests

```python
# test_cli.py
import pytest
from speed_test_tui.cli import create_parser, result_to_json

def test_parser_default_values():
    parser = create_parser()
    args = parser.parse_args([])

    assert args.server == "https://speedtest.example.com"
    assert args.duration == 10.0
    assert args.concurrency == 4
    assert args.no_upload is False
    assert args.json is False

def test_parser_custom_server():
    parser = create_parser()
    args = parser.parse_args(["--server", "https://custom.example"])

    assert args.server == "https://custom.example"

def test_parser_no_upload():
    parser = create_parser()
    args = parser.parse_args(["--no-upload"])

    assert args.no_upload is True

def test_json_output_serializable():
    from datetime import datetime
    from speed_test_tui.interface import SpeedTestResult, PingResult, SpeedResult

    result = SpeedTestResult(
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        server_url="https://test.example",
        ping=PingResult(min_ms=10, max_ms=20, avg_ms=15, jitter_ms=2,
                        packets_sent=10, packets_received=10),
        download=SpeedResult(bytes_transferred=1000, duration_seconds=1,
                             speed_bps=8000, speed_mbps=0.008),
        upload=None,
    )

    json_data = result_to_json(result)

    assert json_data["timestamp"] == "2024-01-15T10:30:00"
    assert json_data["ping"]["avg_ms"] == 15
    assert json_data["upload"] is None
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=speed_test_tui --cov-report=term-missing

# Specific test file
pytest tests/test_fake.py

# Async tests with verbose output
pytest -v -s --asyncio-mode=auto
```

### Test Requirements

- ✅ All tests pass without network access
- ✅ 80%+ code coverage on core modules
- ✅ No flaky tests (use fixed delays in fakes)
- ✅ CI-compatible (no interactive prompts)

---

## Dependencies

### Runtime (`pyproject.toml`)

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "speed-test-tui"
version = "0.1.0"
description = "Terminal-based internet speed test"
readme = "README.md"
requires-python = ">=3.9"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "httpx>=0.24.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
speed-test = "speed_test_tui.cli:main"

[project.urls]
Homepage = "https://github.com/yourusername/speed-test-tui"
Repository = "https://github.com/yourusername/speed-test-tui"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py39"

[tool.mypy]
python_version = "3.9"
strict = true
```

### Dependency Rationale

| Package | Version | Purpose |
|---------|---------|---------|
| `httpx` | >=0.24 | Async HTTP client with HTTP/2 support |
| `rich` | >=13.0 | Terminal formatting, Live display, tables |
| `pytest` | >=7.0 | Test framework |
| `pytest-asyncio` | >=0.21 | Async test support |
| `pytest-cov` | >=4.0 | Coverage reporting |

### Why These Dependencies?

- **httpx over aiohttp**: Modern API, built-in HTTP/2, better type hints, actively maintained
- **rich over textual**: Lighter weight, no TUI framework overhead, sufficient for this use case
- **No click/typer**: argparse is in stdlib, sufficient for simple CLI

---

## Implementation Order

### Phase 1: Foundation (Day 1)

1. ✅ Create project structure
   - `pyproject.toml` with dependencies
   - Package directory `src/speed_test_tui/`
   - Test directory `tests/`

2. ✅ Implement `interface.py`
   - Data classes: `PingResult`, `SpeedResult`, `SpeedTestResult`
   - Protocol: `SpeedTestProtocol`

3. ✅ Implement `fake.py`
   - `FakeSpeedTest` class
   - Configurable results and delays

4. ✅ Write initial tests
   - `test_interface.py`
   - `test_fake.py`

### Phase 2: Core Engine (Day 2)

5. ✅ Implement `engine.py`
   - `SpeedTestEngine` class
   - `measure_ping()` with sequential HEAD requests
   - `measure_download()` with concurrent GET
   - `measure_upload()` with concurrent POST
   - `run_full_test()` orchestration

6. ✅ Write engine tests
   - Mock httpx responses
   - Verify concurrency behavior
   - Test error handling

### Phase 3: Display (Day 3)

7. ✅ Implement `display.py`
   - `SpeedTestDisplay` class
   - Live layout with rich
   - Summary table formatting

8. ✅ Write display tests
   - Capture console output
   - Verify table structure

### Phase 4: CLI (Day 4)

9. ✅ Implement `cli.py` and `__main__.py`
   - Argument parser
   - Engine selection logic
   - JSON output mode
   - Error handling

10. ✅ Write CLI tests
    - Argument parsing
    - JSON serialization
    - Integration with fake engine

### Phase 5: Polish (Day 5)

11. ✅ Add type checking
    - Run mypy, fix issues
    - Add any missing type hints

12. ✅ Add linting
    - Configure ruff
    - Fix style issues

13. ✅ Write README
    - Installation instructions
    - Usage examples
    - Development setup

14. ✅ Final verification
    - All tests pass
    - Coverage >= 80%
    - Manual testing with real server

---

## Trade-offs & Alternatives

### Considered Alternatives

#### 1. TUI Framework: textual vs rich

| Aspect | textual | rich (chosen) |
|--------|---------|---------------|
| Learning curve | Steeper | Gentle |
| Dependencies | More (asyncio app framework) | Fewer |
| Flexibility | High (full app framework) | Moderate |
| Suitability | Complex interactive apps | Simple progress display |

**Decision**: rich is sufficient for displaying progress and results. textual would be overkill.

#### 2. HTTP Client: aiohttp vs httpx

| Aspect | aiohttp | httpx (chosen) |
|--------|---------|----------------|
| API style | Lower-level | Higher-level, requests-like |
| HTTP/2 | Requires extra setup | Built-in |
| Type hints | Good | Excellent |
| Maintenance | Mature | Active |

**Decision**: httpx has better developer experience and modern defaults.

#### 3. CLI Framework: argparse vs click vs typer

| Aspect | argparse (chosen) | click | typer |
|--------|-------------------|-------|-------|
| Dependencies | stdlib | External | External |
| Complexity | Low | Medium | Low |
| Type hints | Manual | Decorator-based | Type-based |

**Decision**: argparse keeps dependencies minimal. typer would be nice but adds a dependency.

#### 4. Test Double: Mock vs Fake

| Aspect | unittest.mock | Fake (chosen) |
|--------|---------------|---------------|
| Realism | Low (stubbed methods) | High (real async flow) |
| Test speed | Fast | Fast |
| Maintenance | Brittle to interface changes | Stable |

**Decision**: Fake engine tests the actual async flow, catching integration issues mocks would miss.

#### 5. Concurrency: threading vs asyncio

| Aspect | threading | asyncio (chosen) |
|--------|-----------|-----------------|
| I/O performance | Good (GIL released) | Excellent |
| Complexity | Lock management | Async/await |
| Network I/O | Fine | Optimal |

**Decision**: asyncio is the modern Python approach for network I/O.

### Known Limitations

1. **No server discovery**: User must know server URL. Adding server benchmarking would require:
   - Server list endpoint
   - Latency screening
   - Geographic selection logic

2. **No HTTP/2 multiplexing**: httpx supports it, but current implementation doesn't leverage connection reuse optimally.

3. **No adaptive test duration**: Fixed duration may be too short for slow connections, too long for fast ones.

4. **Single-threaded display**: rich.Live runs in main thread; heavy computation could cause flicker (not an issue for this app).

### Future Enhancements

- [ ] Server discovery and selection
- [ ] Historical results storage (SQLite)
- [ ] Config file support (~/.config/speed-test-tui/config.toml)
- [ ] WebSocket-based testing for lower overhead
- [ ] Graphical gauge display using braille characters
- [ ] CI integration for network quality monitoring

---

## Appendix: Example Output

### Live Display (during test)

```
╭──────────────────────────────────────────────────────────────╮
│                  Speed Test TUI                               │
╰──────────────────────────────────────────────────────────────╯
╭──────────────────────────────────────────────────────────────╮
│ Testing Download                                             │
│                                                              │
│ ✓ Ping: 18.5 ms                                              │
│ ↓ Download: 94.2 Mbps                                        │
│                                                              │
╰──────────────────────────────────────────────────────────────╯
Progress: 50%
```

### Final Summary

```
╭──────────────────────────────────────────────────────────────╮
│                    Speed Test Results                         │
├────────────────────┬─────────────────────────────────────────┤
│ Metric             │                                   Value │
├────────────────────┼─────────────────────────────────────────┤
│ Ping (Avg)         │                                  18.5 ms│
│ Ping (Min)         │                                  15.2 ms│
│ Ping (Max)         │                                  24.8 ms│
│ Jitter             │                                   3.2 ms│
│                    │                                         │
│ Download           │                                 95.3 Mbps│
│                    │                               119.1 MB  │
│                    │                                         │
│ Upload             │                                 48.7 Mbps│
│                    │                                60.9 MB  │
╰────────────────────┴─────────────────────────────────────────╯
```

### JSON Output

```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "server_url": "https://speedtest.example.com",
  "ping": {
    "min_ms": 15.2,
    "max_ms": 24.8,
    "avg_ms": 18.5,
    "jitter_ms": 3.2
  },
  "download": {
    "speed_mbps": 95.3,
    "bytes_transferred": 124678912
  },
  "upload": {
    "speed_mbps": 48.7,
    "bytes_transferred": 63897600
  }
}
```
