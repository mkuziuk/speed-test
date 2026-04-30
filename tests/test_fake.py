"""Tests for the fake speed-test engine."""

import pytest

from speed_test_tui.fake import FakeSpeedTest
from speed_test_tui.interface import PingResult, SpeedResult, SpeedTestResult


@pytest.mark.asyncio
async def test_fake_full_test_without_upload_is_deterministic():
    engine = FakeSpeedTest(
        ping_delay=0,
        download_duration=0,
        upload_duration=0,
        ping_result=PingResult(10, 20, 15, 2, 3, 3),
        download_result=SpeedResult(1_250_000, 1, 10_000_000, 10),
    )

    events = [event async for event in engine.run_full_test(include_upload=False)]

    assert [phase for phase, _ in events] == [
        "ping",
        "download_progress",
        "download",
        "complete",
    ]
    assert isinstance(events[-1][1], SpeedTestResult)
    assert events[-1][1].upload is None
    assert events[-1][1].download.speed_mbps == 10


@pytest.mark.asyncio
async def test_fake_full_test_with_upload_includes_final_upload():
    engine = FakeSpeedTest(
        ping_delay=0,
        download_duration=0,
        upload_duration=0,
        upload_result=SpeedResult(500_000, 1, 4_000_000, 4),
    )

    events = [event async for event in engine.run_full_test(include_upload=True)]

    assert "upload_progress" in [phase for phase, _ in events]
    assert "upload" in [phase for phase, _ in events]
    final = events[-1][1]
    assert isinstance(final, SpeedTestResult)
    assert final.upload.speed_mbps == 4
