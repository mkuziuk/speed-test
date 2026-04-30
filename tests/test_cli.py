"""Tests for CLI orchestration and JSON output."""

import json

import pytest
from rich.console import Console

from speed_test_tui.cli import async_main, collect_results, make_engine, result_to_json, run_with_display
from speed_test_tui.fake import FakeSpeedTest
from speed_test_tui.interface import SpeedTestResult


@pytest.mark.asyncio
async def test_collect_results_returns_final_result_without_upload():
    engine = FakeSpeedTest(ping_delay=0, download_duration=0, upload_duration=0)

    result = await collect_results(engine, include_upload=False)

    assert isinstance(result, SpeedTestResult)
    assert result.ping.avg_ms == 18.5
    assert result.download.speed_mbps == 100.0
    assert result.upload is None


@pytest.mark.asyncio
async def test_run_with_display_uses_fake_engine_without_network():
    engine = FakeSpeedTest(ping_delay=0, download_duration=0, upload_duration=0)
    console = Console(record=True, force_terminal=False, width=100)

    result = await run_with_display(engine, include_upload=True, console=console)

    exported = console.export_text()
    assert result.download.speed_mbps == 100.0
    assert result.upload.speed_mbps == 50.0
    assert "Speed Test Results" in exported
    assert "Download" in exported
    assert "Upload" in exported


def test_result_to_json_serializes_dataclasses_and_datetime():
    result = FakeSpeedTest(ping_delay=0, download_duration=0, upload_duration=0)._default_ping()
    # Build a full result through the public async path in a tiny nested run would
    # be redundant; this verifies the serializer's nested dataclass handling.
    full = SpeedTestResult(server_url="fake://test", ping=result)

    payload = json.loads(result_to_json(full))

    assert payload["server_url"] == "fake://test"
    assert payload["ping"]["avg_ms"] == 18.5
    assert "timestamp" in payload


def test_make_engine_rejects_invalid_duration():
    parser_args = type(
        "Args",
        (),
        {
            "duration": 0,
            "concurrency": 1,
            "ping_count": 1,
            "fake": True,
            "server": "unused",
            "download_url": None,
            "upload_url": None,
        },
    )()

    with pytest.raises(ValueError, match="duration"):
        make_engine(parser_args)


@pytest.mark.asyncio
async def test_run_with_display_shows_gauge_and_mbps():
    engine = FakeSpeedTest(ping_delay=0, download_duration=0, upload_duration=0)
    console = Console(record=True, force_terminal=False, width=100)
    result = await run_with_display(engine, include_upload=True, console=console)
    exported = console.export_text()
    assert "Mbps" in exported
    assert "MB/s" not in exported
    # Gauge characters should appear
    assert "█" in exported or "░" in exported


@pytest.mark.asyncio
async def test_async_main_json_fake_outputs_valid_json(capsys):
    status = await async_main(["--fake", "--duration", "0.1", "--json", "--no-upload"])

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "fake://local-speed-test"
    assert payload["download"]["speed_mbps"] == 100.0
    assert payload["upload"] is None
