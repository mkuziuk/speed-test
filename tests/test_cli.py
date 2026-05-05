"""Tests for CLI orchestration and JSON output."""

import asyncio
import json
import sys
from unittest.mock import patch

import pytest
from rich.console import Console

from speed_test_tui.cli import (
    _extract_command,
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
async def test_run_with_display_shows_preset():
    engine = FakeSpeedTest(ping_delay=0, download_duration=0, upload_duration=0)
    console = Console(record=True, force_terminal=False, width=100)
    result = await run_with_display(engine, include_upload=True, console=console, preset="ru-moscow")
    exported = console.export_text()
    assert "ru-moscow" in exported
    assert result.preset == "ru-moscow"


@pytest.mark.asyncio
async def test_async_main_json_fake_outputs_valid_json(capsys):
    status = await async_main(["--fake", "--duration", "0.1", "--json", "--no-upload"])

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "https://speed.cloudflare.com"
    assert payload["download"]["speed_mbps"] == 100.0
    assert payload["upload"] is None
    assert payload["preset"] == "cloudflare"


def test_list_presets_output(capsys):
    """--list-presets prints known presets and exits cleanly."""
    status = asyncio.run(async_main(["--list-presets"]))
    assert status == 0
    captured = capsys.readouterr().out
    assert "cloudflare" in captured
    assert "ru-moscow" in captured
    assert "speed.cloudflare.com" in captured
    assert "mosoblcom.ru" in captured
    assert "(active)" in captured


@pytest.mark.asyncio
async def test_preset_ru_moscow_sets_urls(capsys):
    """--preset ru-moscow applies Moscow URLs and shows in JSON output."""
    status = await async_main(["--preset", "ru-moscow", "--fake", "--duration", "0.1", "--json", "--no-upload"])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "http://speedtest.mosoblcom.ru:8080"
    assert payload["preset"] == "ru-moscow"


@pytest.mark.asyncio
async def test_preset_default_is_cloudflare(capsys):
    """Default preset (no --preset) resolves to cloudflare."""
    status = await async_main(["--fake", "--duration", "0.1", "--json", "--no-upload"])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "https://speed.cloudflare.com"
    assert payload["preset"] == "cloudflare"


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
    assert "Preset set to 'ru-moscow'" in err
    assert "speedtest.mosoblcom.ru" in err


@pytest.mark.asyncio
async def test_interactive_presets_command(capsys):
    inputs = ["/presets", "1", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "/presets is deprecated" in err
    assert "cloudflare" in err
    assert "ru-moscow" in err
    assert "(active)" in err


@pytest.mark.asyncio
async def test_interactive_preset_menu_by_number(capsys):
    """Typing /preset shows the menu; choosing by number switches preset."""
    inputs = ["/preset", "2", "/server", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "Available presets:" in err
    assert "1) cloudflare" in err
    assert "2) ru-moscow" in err
    assert "Preset set to 'ru-moscow'" in err
    assert "speedtest.mosoblcom.ru" in err


@pytest.mark.asyncio
async def test_interactive_preset_menu_by_name(capsys):
    """Choosing preset by name in the menu switches successfully."""
    inputs = ["/preset", "ru-moscow", "/server", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "Preset set to 'ru-moscow'" in err


@pytest.mark.asyncio
async def test_interactive_preset_menu_unknown_choice(capsys):
    """Unknown preset choice shows error and keeps running."""
    inputs = ["/preset", "invalid", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "Unknown preset 'invalid'" in err


@pytest.mark.asyncio
async def test_interactive_preset_direct_with_arg(capsys):
    """/preset <name> directly switches without showing menu."""
    inputs = ["/preset ru-moscow", "/server", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "Preset set to 'ru-moscow'" in err
    assert "speedtest.mosoblcom.ru" in err


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
    assert payload["server_url"] == "https://speed.cloudflare.com"
    assert payload["download"]["speed_mbps"] == 100.0
    assert payload["preset"] == "cloudflare"


def test_extract_command_finds_first_non_option():
    assert _extract_command(["install", "--dry-run"]) == ("install", ["--dry-run"])
    assert _extract_command(["--dry-run", "update"]) == ("update", ["--dry-run"])
    assert _extract_command(["--fake"]) == (None, ["--fake"])
    assert _extract_command([]) == (None, [])


@pytest.mark.asyncio
async def test_async_main_none_uses_sys_argv(capsys):
    with patch.object(sys, "argv", ["speed-test", "--list-presets"]):
        status = await async_main(None)
    assert status == 0
    out = capsys.readouterr().out
    assert "cloudflare" in out


# --- Custom preset CLI tests ---


@pytest.mark.asyncio
async def test_custom_preset_add_command():
    from speed_test_tui.config import get_custom_presets

    status = await async_main([
        "preset", "add", "mytest",
        "--server", "http://s.com",
        "--download-url", "http://s.com/dl",
        "--upload-url", "http://s.com/ul",
    ])
    assert status == 0
    assert get_custom_presets()["mytest"]["server"] == "http://s.com"


@pytest.mark.asyncio
async def test_custom_preset_add_missing_fields_fails():
    from speed_test_tui.config import get_custom_presets

    # missing --server
    status = await async_main(["preset", "add", "bad", "--download-url", "x", "--upload-url", "x"])
    assert status != 0
    # missing --download-url
    status = await async_main(["preset", "add", "bad", "--server", "x", "--upload-url", "x"])
    assert status != 0
    # missing --upload-url
    status = await async_main(["preset", "add", "bad", "--server", "x", "--download-url", "x"])
    assert status != 0
    assert "bad" not in get_custom_presets()


@pytest.mark.asyncio
async def test_custom_preset_add_reserved_name_fails():
    from speed_test_tui.config import get_custom_presets

    for name in ("cloudflare", "ru-moscow"):
        status = await async_main([
            "preset", "add", name,
            "--server", "http://s.com",
            "--download-url", "http://s.com/dl",
            "--upload-url", "http://s.com/ul",
        ])
        assert status != 0
        assert name not in get_custom_presets()


@pytest.mark.asyncio
async def test_custom_preset_add_empty_name_fails():
    from speed_test_tui.config import get_custom_presets

    status = await async_main(["preset", "add", "", "--server", "x", "--download-url", "x", "--upload-url", "x"])
    assert status != 0
    status = await async_main(["preset", "add", "   ", "--server", "x", "--download-url", "x", "--upload-url", "x"])
    assert status != 0
    assert "" not in get_custom_presets()
    assert "   " not in get_custom_presets()


def test_custom_preset_list_presets_includes_custom(capsys):
    from speed_test_tui.config import add_custom_preset

    add_custom_preset("mytest", "http://x.com", "http://x.com/dl", "http://x.com/ul")
    status = asyncio.run(async_main(["--list-presets"]))
    assert status == 0
    captured = capsys.readouterr().out
    assert "cloudflare" in captured
    assert "ru-moscow" in captured
    assert "mytest" in captured


@pytest.mark.asyncio
async def test_custom_preset_usable_with_preset_flag(capsys):
    from speed_test_tui.config import add_custom_preset

    add_custom_preset("mytest", "http://fake.example.com", "http://fake.example.com/dl", "http://fake.example.com/ul")
    status = await async_main([
        "--preset", "mytest", "--fake", "--duration", "0.1", "--json", "--no-upload",
    ])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["server_url"] == "http://fake.example.com"
    assert payload["preset"] == "mytest"


@pytest.mark.asyncio
async def test_custom_preset_interactive_menu_shows_custom(capsys):
    from speed_test_tui.config import add_custom_preset

    add_custom_preset("mytest", "http://x.com", "http://x.com/dl", "http://x.com/ul")
    inputs = ["/preset", "1", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "cloudflare" in err
    assert "ru-moscow" in err
    assert "mytest" in err


@pytest.mark.asyncio
async def test_custom_preset_interactive_direct_switch(capsys):
    from speed_test_tui.config import add_custom_preset

    add_custom_preset("mytest", "http://x.com", "http://x.com/dl", "http://x.com/ul")
    inputs = ["/preset mytest", "/server", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "Preset set to 'mytest'" in err
    assert "http://x.com" in err


@pytest.mark.asyncio
async def test_custom_preset_interactive_menu_by_number(capsys):
    from speed_test_tui.config import add_custom_preset

    add_custom_preset("mytest", "http://x.com", "http://x.com/dl", "http://x.com/ul")
    inputs = ["/preset", "3", "/quit"]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])
    assert status == 0
    err = capsys.readouterr().err
    assert "Preset set to 'mytest'" in err


@pytest.mark.asyncio
async def test_interactive_preset_add_prompted_and_use_now(capsys):
    from speed_test_tui.config import get_custom_presets, get_saved_preset

    inputs = [
        "/preset add",
        "mytest",
        "http://x.com",
        "http://x.com/dl",
        "http://x.com/ul",
        "yes",
        "/server",
        "/quit",
    ]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])

    assert status == 0
    presets = get_custom_presets()
    assert presets["mytest"]["server"] == "http://x.com"
    assert get_saved_preset() == "mytest"
    err = capsys.readouterr().err
    assert "Preset 'mytest' added" in err
    assert "Preset set to 'mytest'" in err
    assert "http://x.com" in err


@pytest.mark.asyncio
async def test_interactive_preset_add_prompted_without_switching_shows_in_menu(capsys):
    from speed_test_tui.config import get_custom_presets, get_saved_preset

    inputs = [
        "/preset add",
        "mytest",
        "http://x.com",
        "http://x.com/dl",
        "http://x.com/ul",
        "n",
        "/preset",
        "1",
        "/quit",
    ]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])

    assert status == 0
    assert "mytest" in get_custom_presets()
    assert get_saved_preset() == "cloudflare"
    err = capsys.readouterr().err
    assert "Preset 'mytest' added" in err
    assert "mytest" in err


@pytest.mark.asyncio
async def test_interactive_preset_add_rejects_built_in_name(capsys):
    from speed_test_tui.config import get_custom_presets

    inputs = [
        "/preset add",
        "cloudflare",
        "http://x.com",
        "http://x.com/dl",
        "http://x.com/ul",
        "/quit",
    ]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])

    assert status == 0
    assert "cloudflare" not in get_custom_presets()
    assert "built-in preset" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_interactive_preset_add_rejects_blank_url(capsys):
    from speed_test_tui.config import get_custom_presets

    inputs = [
        "/preset add",
        "mytest",
        "http://x.com",
        "   ",
        "http://x.com/ul",
        "/quit",
    ]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])

    assert status == 0
    assert "mytest" not in get_custom_presets()
    assert "required" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_interactive_preset_add_one_line_and_use_now(capsys):
    from speed_test_tui.config import get_custom_presets, get_saved_preset

    inputs = [
        "/preset add mytest --server http://x.com --download-url http://x.com/dl --upload-url http://x.com/ul",
        "y",
        "/server",
        "/quit",
    ]
    with patch("rich.console.Console.input", side_effect=inputs):
        status = await async_main(["--fake", "--duration", "0.1"])

    assert status == 0
    assert get_custom_presets()["mytest"]["download_url"] == "http://x.com/dl"
    assert get_saved_preset() == "mytest"
    err = capsys.readouterr().err
    assert "Preset 'mytest' added" in err
    assert "Preset set to 'mytest'" in err
    assert "http://x.com" in err
