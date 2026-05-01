"""Tests for CLI orchestration and JSON output."""

import asyncio
import json
from unittest.mock import patch

import pytest
from rich.console import Console

from speed_test_tui.cli import (
    async_main,
    collect_results,
    make_engine,
    result_to_json,
    run_with_display,
)
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
    assert payload["server_url"] == "http://speedtest.mosoblcom.ru:8080"
    assert payload["download"]["speed_mbps"] == 100.0
    assert payload["upload"] is None


def test_list_presets_output(capsys):
    """--list-presets prints known presets and exits cleanly."""
    status = asyncio.run(async_main(["--list-presets"]))
    assert status == 0
    captured = capsys.readouterr().out
    assert "cloudflare" in captured
    assert "ru-moscow" in captured
    assert "speed.cloudflare.com" in captured
    assert "mosoblcom.ru" in captured


@pytest.mark.asyncio
async def test_preset_ru_moscow_sets_urls(capsys):
    """--preset ru-moscow applies Moscow URLs and shows in JSON output."""
    status = await async_main(["--preset", "ru-moscow", "--fake", "--duration", "0.1", "--json", "--no-upload"])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "http://speedtest.mosoblcom.ru:8080"


@pytest.mark.asyncio
async def test_preset_default_is_ru_moscow(capsys):
    """Default preset (no --preset) resolves to ru-moscow."""
    status = await async_main(["--fake", "--duration", "0.1", "--json", "--no-upload"])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "http://speedtest.mosoblcom.ru:8080"


@pytest.mark.asyncio
async def test_preset_override_with_explicit_server(capsys):
    """--server overrides the preset's server URL."""
    status = await async_main([
        "--preset", "ru-moscow", "--server", "https://custom.example.com",
        "--fake", "--duration", "0.1", "--json", "--no-upload",
    ])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "https://custom.example.com"


# --- Interactive session tests ---


@pytest.mark.asyncio
async def test_interactive_run_and_quit(capsys):
    inputs = ["/run", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1", "--no-upload"])
    assert status == 0
    assert "Speed Test Results" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_interactive_preset_command(capsys):
    inputs = ["/preset ru-moscow", "/server", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    captured = capsys.readouterr()
    out = captured.out
    err = captured.err
    assert "Preset switched to ru-moscow" in err
    assert "speedtest.mosoblcom.ru" in err


@pytest.mark.asyncio
async def test_interactive_presets_command(capsys):
    inputs = ["/presets", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "cloudflare" in err
    assert "ru-moscow" in err


@pytest.mark.asyncio
async def test_interactive_help_command(capsys):
    inputs = ["/help", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "/run" in err
    assert "/quit" in err


@pytest.mark.asyncio
async def test_interactive_quit_aliases():
    for cmd in ["/q", "/exit"]:
        with patch("rich.console.Console.input", side_effect=[cmd]):
            status = await async_main(["--fake", "--duration", "0.1"])
            assert status == 0


@pytest.mark.asyncio
async def test_interactive_keyboard_interrupt():
    with patch("rich.console.Console.input", side_effect=KeyboardInterrupt):
        status = await async_main(["--fake", "--duration", "0.1"])
        assert status == 0


@pytest.mark.asyncio
async def test_interactive_unknown_command(capsys):
    with patch("rich.console.Console.input", side_effect=["/foo", "/quit"]):
        status = await async_main(["--fake", "--duration", "0.1"])
        assert status == 0
        assert "Unknown command" in capsys.readouterr().err


# --- --run-once tests ---


@pytest.mark.asyncio
async def test_run_once_flag_exits_after_test(capsys):
    status = await async_main(["--fake", "--duration", "0.1", "--run-once", "--no-upload"])
    assert status == 0
    assert "Speed Test Results" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_once_with_json_outputs_json(capsys):
    status = await async_main(["--fake", "--duration", "0.1", "--run-once", "--json", "--no-upload"])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "http://speedtest.mosoblcom.ru:8080"
    assert payload["download"]["speed_mbps"] == 100.0
