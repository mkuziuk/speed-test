"""Terminal display using Rich for live speed test updates."""

from contextlib import contextmanager
from typing import Optional

from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .interface import PingResult, SpeedResult, SpeedTestResult


class SpeedTestDisplay:
    """Manages terminal display for speed test.

    Uses rich.Live for real-time updates without screen flicker.
    """

    def __init__(self, console: Optional[Console] = None, preset: Optional[str] = None):
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._current_phase: str = "Initializing"
        self._ping_result: Optional[PingResult] = None
        self._download_result: Optional[SpeedResult] = None
        self._upload_result: Optional[SpeedResult] = None
        self._progress: float = 0.0
        self._preset = preset

    @contextmanager
    def live_display(self):
        """Context manager for live display updates."""
        renderable = Panel("Starting...", title="Speed Test TUI")

        with Live(renderable, console=self.console, refresh_per_second=4) as live:
            self._live = live
            self._refresh()
            yield
            self._live = None

    def update_phase(self, phase: str, progress: float = 0.0) -> None:
        """Update current test phase and progress."""
        self._current_phase = phase
        self._progress = progress
        self._refresh()

    def update_ping(self, result: PingResult) -> None:
        """Update ping results."""
        self._ping_result = result
        self._refresh()

    def update_download(self, result: SpeedResult) -> None:
        """Update download progress/result."""
        self._download_result = result
        self._refresh()

    def update_upload(self, result: SpeedResult) -> None:
        """Update upload progress/result."""
        self._upload_result = result
        self._refresh()

    def show_summary(self, result: SpeedTestResult) -> None:
        """Display final summary table."""
        table = Table(title="Speed Test Results", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        table.add_column("Gauge")

        if result.preset:
            table.add_row("Preset", f"[yellow]{result.preset}[/yellow]", "")

        # Ping section
        if result.ping:
            table.add_row("Ping (Avg)", f"{result.ping.avg_ms:.1f} ms")
            table.add_row("Ping (Min)", f"{result.ping.min_ms:.1f} ms")
            table.add_row("Ping (Max)", f"{result.ping.max_ms:.1f} ms")
            table.add_row("Jitter", f"{result.ping.jitter_ms:.1f} ms")

        # Download section
        if result.download:
            table.add_row("", "", "")  # Spacer
            table.add_row(
                "Download",
                f"{result.download.speed_mbps:.1f} Mbps",
                self._render_gauge(result.download.speed_mbps),
            )
            table.add_row(
                "",
                self._format_bytes(result.download.bytes_transferred),
                "",
            )

        # Upload section
        if result.upload:
            table.add_row("", "", "")  # Spacer
            table.add_row(
                "Upload",
                f"{result.upload.speed_mbps:.1f} Mbps",
                self._render_gauge(result.upload.speed_mbps),
            )
            table.add_row(
                "",
                self._format_bytes(result.upload.bytes_transferred),
                "",
            )

        self.console.print(table)

    def _refresh(self) -> None:
        """Refresh the live display with current state."""
        if self._live is None:
            return
        self._live.update(self._render_body())

    def _render_body(self) -> Panel:
        """Render body content based on current state."""
        lines = []

        if self._ping_result:
            lines.append(
                f"[green]✓[/green] Ping: {self._ping_result.avg_ms:.1f} ms "
                f"(min: {self._ping_result.min_ms:.1f}, max: {self._ping_result.max_ms:.1f}, "
                f"jitter: {self._ping_result.jitter_ms:.1f})"
            )

        if self._download_result:
            speed = self._download_result.speed_mbps
            if speed > 0:
                indicator = (
                    "✓" if self._current_phase not in ("Testing Download",)
                    else "↓"
                )
                lines.append(
                    f"[green]{indicator}[/green] Download: {speed:.1f} Mbps "
                    f"({self._format_bytes(self._download_result.bytes_transferred)})"
                )
                lines.append(f"  {self._render_gauge(speed)}")

        if self._upload_result:
            speed = self._upload_result.speed_mbps
            if speed > 0:
                indicator = (
                    "✓" if self._current_phase not in ("Testing Upload",)
                    else "↑"
                )
                lines.append(
                    f"[green]{indicator}[/green] Upload: {speed:.1f} Mbps "
                    f"({self._format_bytes(self._upload_result.bytes_transferred)})"
                )
                lines.append(f"  {self._render_gauge(speed)}")

        if not lines:
            lines.append("[dim]Starting test...[/dim]")

        body_text = "\n".join(lines)
        footer = f"[dim]Phase: {self._current_phase} | Progress: {self._progress:.0%}[/dim]"
        content = f"{body_text}\n\n{footer}"

        title = "Speed Test TUI"
        if self._preset:
            title = f"Speed Test TUI — {self._preset}"

        return Panel(content, title=title, border_style="blue")

    @staticmethod
    def _render_gauge(speed_mbps: float, width: int = 20) -> str:
        """Return a Rich-formatted colored gauge bar string."""
        max_speed = 200.0
        filled = min(speed_mbps / max_speed, 1.0)
        filled_chars = int(filled * width)
        # Ensure any positive speed shows at least one filled block
        if speed_mbps > 0 and filled_chars == 0:
            filled_chars = 1
        empty_chars = width - filled_chars

        # Dark green (#008000) to spring-green (#00ff80) gradient via hex interpolation
        start_color = (0, 128, 0)    # dark green
        end_color = (0, 255, 128)    # spring green (green with hint of cyan)

        # Build gauge with gradient based on absolute position
        gauge = ""
        for i in range(width):
            if i < filled_chars:
                # Compute t based on absolute position in full width
                t = i / (width - 1) if width > 1 else 0.0
                # Interpolate RGB channels
                r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
                g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
                b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                gauge += f"[{hex_color}]█[/{hex_color}]"
            else:
                gauge += "[dim]░[/dim]"

        return gauge

    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} TB"
