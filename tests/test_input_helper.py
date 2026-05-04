"""Tests for input helper fallback and suggestion matching."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from speed_test_tui.input_helper import (
    _COMMANDS,
    _COMMAND_HELP,
    _bottom_toolbar,
    _has_prompt_toolkit,
    prompt_input,
)


def test_has_prompt_toolkit_true():
    """_has_prompt_toolkit returns True when prompt_toolkit is importable."""
    assert _has_prompt_toolkit() is True


def test_has_prompt_toolkit_false_on_import_error():
    """_has_prompt_toolkit returns False when import raises."""
    with patch("builtins.__import__", side_effect=ImportError("nope")):
        assert _has_prompt_toolkit() is False


@pytest.mark.asyncio
async def test_prompt_input_fallback_when_not_tty():
    """When stdin is not a tty, prompt_input falls back to Console.input."""
    console = MagicMock(spec=Console)
    console.input.return_value = "  /run  "

    with patch.object(sys.stdin, "isatty", return_value=False):
        result = await prompt_input(console, "> ")

    console.input.assert_called_once_with("> ")
    assert result == "/run"


@pytest.mark.asyncio
async def test_prompt_input_fallback_when_no_prompt_toolkit():
    """When prompt_toolkit is unavailable, prompt_input falls back to Console.input."""
    console = MagicMock(spec=Console)
    console.input.return_value = "  /help  "

    with patch.object(sys.stdin, "isatty", return_value=True):
        with patch(
            "speed_test_tui.input_helper._has_prompt_toolkit", return_value=False
        ):
            result = await prompt_input(console, "> ")

    console.input.assert_called_once_with("> ")
    assert result == "/help"


@pytest.mark.asyncio
async def test_prompt_input_uses_prompt_toolkit_when_available():
    """When tty and prompt_toolkit are available, prompt_input uses PromptSession."""
    console = MagicMock(spec=Console)
    mock_session_cls = MagicMock()
    mock_session = MagicMock()
    mock_session.prompt_async = AsyncMock(return_value="  /quit  ")
    mock_session_cls.return_value = mock_session

    with patch.object(sys.stdin, "isatty", return_value=True):
        with patch(
            "speed_test_tui.input_helper._has_prompt_toolkit", return_value=True
        ):
            with patch("prompt_toolkit.PromptSession", mock_session_cls):
                result = await prompt_input(console, "> ")

    console.input.assert_not_called()
    mock_session_cls.assert_called_once()
    call_kwargs = mock_session_cls.call_args.kwargs
    assert "key_bindings" in call_kwargs
    assert "bottom_toolbar" in call_kwargs
    mock_session.prompt_async.assert_awaited_once_with("> ")
    assert result == "/quit"


@pytest.mark.asyncio
async def test_prompt_input_passes_custom_bottom_toolbar():
    """Custom bottom_toolbar callable is forwarded to PromptSession."""
    console = MagicMock(spec=Console)
    mock_session_cls = MagicMock()
    mock_session = MagicMock()
    mock_session.prompt_async = AsyncMock(return_value="/run")
    mock_session_cls.return_value = mock_session
    custom_toolbar = lambda: "custom"  # noqa: E731

    with patch.object(sys.stdin, "isatty", return_value=True):
        with patch(
            "speed_test_tui.input_helper._has_prompt_toolkit", return_value=True
        ):
            with patch("prompt_toolkit.PromptSession", mock_session_cls):
                result = await prompt_input(console, "> ", bottom_toolbar=custom_toolbar)

    call_kwargs = mock_session_cls.call_args.kwargs
    assert call_kwargs.get("bottom_toolbar") is custom_toolbar
    assert result == "/run"


def test_bottom_toolbar_contains_all_primary_commands():
    """Bottom toolbar includes every primary command and description."""
    toolbar = _bottom_toolbar()
    for cmd in _COMMANDS:
        if cmd in ("/q", "/exit"):
            continue
        assert cmd in toolbar
        assert _COMMAND_HELP[cmd] in toolbar


def test_bottom_toolbar_shows_preset():
    """Bottom toolbar includes the current preset when provided."""
    toolbar = _bottom_toolbar(preset="ru-moscow")
    assert "preset: ru-moscow" in toolbar


def test_command_list_has_all_slash_commands():
    """The exported command list covers the required slash commands."""
    expected = {"/run", "/preset", "/presets", "/server", "/help", "/quit", "/q", "/exit"}
    assert set(_COMMANDS) == expected
