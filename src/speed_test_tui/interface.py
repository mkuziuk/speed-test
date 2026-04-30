"""Core interfaces and data types for speed test."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


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
    speed_mbps: float  # Megabits per second


@dataclass
class SpeedTestResult:
    """Complete test results."""

    timestamp: datetime = field(default_factory=datetime.now)
    server_url: str = ""
    ping: Optional[PingResult] = None
    download: Optional[SpeedResult] = None
    upload: Optional[SpeedResult] = None


@runtime_checkable
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
        include_upload: bool = True,
    ) -> AsyncIterator[tuple[str, object]]:
        """
        Run complete test suite, yielding (phase, result) tuples.

        Phases: 'ping', 'download_progress', 'download',
                'upload_progress', 'upload', 'complete'
        """
        ...
