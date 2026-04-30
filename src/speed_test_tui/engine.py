"""Real speed test engine using httpx."""

import asyncio
import os
import time
from typing import AsyncIterator, Optional

import httpx

from .interface import PingResult, SpeedResult, SpeedTestResult


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
        self.server_url = server_url.rstrip("/")
        self.download_url = download_url or f"{self.server_url}/download"
        self.upload_url = upload_url or f"{self.server_url}/upload"
        self.ping_count = ping_count
        self.test_duration = test_duration
        self.concurrency = concurrency
        self.timeout = timeout

    async def measure_ping(self) -> PingResult:
        """Measure latency using sequential HTTP HEAD requests."""
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
                await asyncio.sleep(0.1)

        if not latencies:
            return PingResult(
                min_ms=0,
                max_ms=0,
                avg_ms=0,
                jitter_ms=0,
                packets_sent=self.ping_count,
                packets_received=0,
            )

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
            packets_received=len(latencies),
        )

    async def measure_download(self) -> AsyncIterator[SpeedResult]:
        """Measure download speed using concurrent GET requests."""
        start_time = time.perf_counter()
        total_bytes = 0
        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(self.concurrency)

        async def download_loop() -> None:
            nonlocal total_bytes
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                while True:
                    async with semaphore:
                        try:
                            async with client.stream(
                                "GET", self.download_url
                            ) as resp:
                                resp.raise_for_status()
                                async for chunk in resp.aiter_bytes(chunk_size=65536):
                                    async with lock:
                                        total_bytes += len(chunk)
                        except (httpx.RequestError, asyncio.CancelledError):
                            break

        tasks = [
            asyncio.create_task(download_loop())
            for _ in range(self.concurrency)
        ]

        try:
            while True:
                elapsed = time.perf_counter() - start_time
                if elapsed >= self.test_duration:
                    break

                async with lock:
                    current_bytes = total_bytes

                safe_elapsed = max(elapsed, 0.001)
                speed_bps = (current_bytes * 8) / safe_elapsed
                yield SpeedResult(
                    bytes_transferred=current_bytes,
                    duration_seconds=elapsed,
                    speed_bps=speed_bps,
                    speed_mbps=speed_bps / 1_000_000,
                )
                await asyncio.sleep(0.5)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        final_elapsed = time.perf_counter() - start_time
        final_bytes = total_bytes

        safe_elapsed = max(final_elapsed, 0.001)
        final_speed_bps = (final_bytes * 8) / safe_elapsed
        yield SpeedResult(
            bytes_transferred=final_bytes,
            duration_seconds=final_elapsed,
            speed_bps=final_speed_bps,
            speed_mbps=final_speed_bps / 1_000_000,
        )

    async def measure_upload(self) -> AsyncIterator[SpeedResult]:
        """Measure upload speed using concurrent POST requests."""
        start_time = time.perf_counter()
        total_bytes = 0
        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(self.concurrency)

        # Pre-generate payload data
        payload = os.urandom(65536)  # 64KB chunks

        async def upload_loop() -> None:
            nonlocal total_bytes
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                while True:
                    async with semaphore:
                        try:
                            response = await client.post(
                                self.upload_url,
                                content=payload,
                                headers={
                                    "Content-Type": "application/octet-stream"
                                },
                            )
                            response.raise_for_status()
                            async with lock:
                                total_bytes += len(payload)
                        except (httpx.RequestError, asyncio.CancelledError):
                            break

        tasks = [
            asyncio.create_task(upload_loop())
            for _ in range(self.concurrency)
        ]

        try:
            while True:
                elapsed = time.perf_counter() - start_time
                if elapsed >= self.test_duration:
                    break

                async with lock:
                    current_bytes = total_bytes

                safe_elapsed = max(elapsed, 0.001)
                speed_bps = (current_bytes * 8) / safe_elapsed
                yield SpeedResult(
                    bytes_transferred=current_bytes,
                    duration_seconds=elapsed,
                    speed_bps=speed_bps,
                    speed_mbps=speed_bps / 1_000_000,
                )
                await asyncio.sleep(0.5)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        final_elapsed = time.perf_counter() - start_time
        final_bytes = total_bytes

        safe_elapsed = max(final_elapsed, 0.001)
        final_speed_bps = (final_bytes * 8) / safe_elapsed
        yield SpeedResult(
            bytes_transferred=final_bytes,
            duration_seconds=final_elapsed,
            speed_bps=final_speed_bps,
            speed_mbps=final_speed_bps / 1_000_000,
        )

    async def run_full_test(
        self,
        include_upload: bool = True,
    ) -> AsyncIterator[tuple[str, object]]:
        """Orchestrate full test sequence.

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
        yield ("ping", ping_result)

        download_result = None
        async for result in self.measure_download():
            yield ("download_progress", result)
            download_result = result
        # Yield final download separately
        if download_result is not None:
            yield ("download", download_result)

        upload_result = None
        if include_upload:
            async for result in self.measure_upload():
                yield ("upload_progress", result)
                upload_result = result
            if upload_result is not None:
                yield ("upload", upload_result)

        final_result = SpeedTestResult(
            timestamp=datetime.now(),
            server_url=self.server_url,
            ping=ping_result,
            download=download_result,
            upload=upload_result,
        )
        yield ("complete", final_result)

    @staticmethod
    def _calculate_jitter(latencies: list[float]) -> float:
        """Calculate jitter as standard deviation of latencies."""
        if len(latencies) < 2:
            return 0.0
        avg = sum(latencies) / len(latencies)
        variance = sum((x - avg) ** 2 for x in latencies) / len(latencies)
        return variance**0.5
