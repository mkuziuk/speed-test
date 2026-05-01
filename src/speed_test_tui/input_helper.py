"""Input helper with prompt_toolkit completion or Rich fallback."""

import sys

from rich.console import Console

_COMMANDS = [
    "/run",
    "/preset",
    "/presets",
    "/server",
    "/help",
    "/quit",
    "/q",
    "/exit",
]

_COMMAND_HELP = {
    "/run": "Run a speed test",
    "/preset": "Switch to a preset",
    "/presets": "List available presets",
    "/server": "Show current server URL",
    "/help": "Show help",
    "/quit": "Exit the session",
    "/q": "Exit the session",
    "/exit": "Exit the session",
}


def _bottom_toolbar() -> str:
    pieces = []
    for cmd in _COMMANDS:
        if cmd in ("/q", "/exit"):
            continue
        pieces.append(f"{cmd} — {_COMMAND_HELP[cmd]}")
    return " | ".join(pieces)


def _has_prompt_toolkit() -> bool:
    try:
        import prompt_toolkit  # noqa: F401

        return True
    except Exception:
        return False


async def prompt_input(console: Console, text: str = "> ") -> str:
    """Read a line of input with completion when available and TTY attached."""
    if not sys.stdin.isatty() or not _has_prompt_toolkit():
        return console.input(text).strip()

    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter

    completer = WordCompleter(
        _COMMANDS,
        meta_dict=_COMMAND_HELP,
        ignore_case=False,
        sentence=True,
        match_middle=False,
    )

    session: PromptSession[str] = PromptSession(
        completer=completer,
        complete_while_typing=True,
        bottom_toolbar=_bottom_toolbar,
    )

    try:
        result = await session.prompt_async(text)
        return result.strip()
    except (EOFError, KeyboardInterrupt):
        raise
