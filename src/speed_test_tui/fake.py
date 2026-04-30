"""Fake speed test engine for testing without network access."""

import asyncio
from datetime import datetime
from typing import AsyncIterator, Optional

from .interface import PingResult, SpeedResult, SpeedTestResult


class FakeSpeedTest:
    """Fake implementation for testing.

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
        server_url: str = "https://fake-server.example",
    ):
        self.ping_result = ping_result or self._default_ping()
        self.download_result = download_result or self._default_download()
        self.upload_result = upload_result or self._default_upload()
        self.ping_delay = ping_delay
        self.download_duration = download_duration
        self.upload_duration = upload_duration
        self.server_url = server_url

    async def measure_ping(self) -> PingResult:
        """Simulate ping measurement with configurable delay."""
        await asyncio.sleep(self.ping_delay)
        return self.ping_result

    async def measure_download(self) -> AsyncIterator[SpeedResult]:
        """Yield simulated download progress updates."""
        elapsed = 0.0
        interval = 0.5
        while elapsed < self.download_duration:
            await asyncio.sleep(interval)
            elapsed += interval
            progress = min(elapsed / self.download_duration, 1.0)
            yield SpeedResult(
                bytes_transferred=int(
                    self.download_result.bytes_transferred * progress
                ),
                duration_seconds=elapsed,
                speed_bps=self.download_result.speed_bps,
                speed_mbps=self.download_result.speed_mbps,
            )
        # Final yield with full result
        yield SpeedResult(
            bytes_transferred=self.download_result.bytes_transferred,
            duration_seconds=self.download_result.duration_seconds,
            speed_bps=self.download_result.speed_bps,
            speed_mbps=self.download_result.speed_mbps,
        )

    async def measure_upload(self) -> AsyncIterator[SpeedResult]:
        """Yield simulated upload progress updates."""
        elapsed = 0.0
        interval = 0.5
        while elapsed < self.upload_duration:
            await asyncio.sleep(interval)
            elapsed += interval
            progress = min(elapsed / self.upload_duration, 1.0)
            yield SpeedResult(
                bytes_transferred=int(
                    self.upload_result.bytes_transferred * progress
                ),
                duration_seconds=elapsed,
                speed_bps=self.upload_result.speed_bps,
                speed_mbps=self.upload_result.speed_mbps,
            )
        # Final yield with full result
        yield SpeedResult(
            bytes_transferred=self.upload_result.bytes_transferred,
            duration_seconds=self.upload_result.duration_seconds,
            speed_bps=self.upload_result.speed_bps,
            speed_mbps=self.upload_result.speed_mbps,
        )

    async def run_full_test(
        self,
        include_upload: bool = True,
    ) -> AsyncIterator[tuple[str, object]]:
        """Orchestrate full fake test sequence.

        Yields (phase, data) tuples just like the real engine.
        """
        yield ("ping", await self.measure_ping())

        download_result = None
        async for result in self.measure_download():
            yield ("download_progress", result)
            download_result = result
        if download_result is not None:
            yield ("download", download_result)

        upload_result = None
        if include_upload:
            async for result in self.measure_upload():
                yield ("upload_progress", result)
                upload_result = result
            if upload_result is not None:
                yield ("upload", upload_result)

        yield (
            "complete",
            SpeedTestResult(
                timestamp=datetime.now(),
                server_url=self.server_url,
                ping=self.ping_result,
                download=download_result,
                upload=upload_result,
            ),
        )

    @staticmethod
    def _default_ping() -> PingResult:
        return PingResult(
            min_ms=15.0,
            max_ms=25.0,
            avg_ms=18.5,
            jitter_ms=3.2,
            packets_sent=10,
            packets_received=10,
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
