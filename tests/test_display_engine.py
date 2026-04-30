"""Tests for small pure functions in the display and engine layers."""

import pytest

from speed_test_tui.display import SpeedTestDisplay
from speed_test_tui.engine import SpeedTestEngine


def test_format_bytes_scales_units():
    assert SpeedTestDisplay._format_bytes(512) == "512.0 B"
    assert SpeedTestDisplay._format_bytes(2048) == "2.0 KB"
    assert SpeedTestDisplay._format_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_calculate_jitter_is_zero_for_single_latency():
    assert SpeedTestEngine._calculate_jitter([10.0]) == 0.0


def test_calculate_jitter_uses_population_standard_deviation():
    assert SpeedTestEngine._calculate_jitter([10.0, 20.0, 30.0]) == pytest.approx(8.1649658)


def test_render_gauge_colors_and_fill():
    # Very low speed → red, mostly empty
    low = SpeedTestDisplay._render_gauge(10.0, width=10)
    assert "red" in low
    assert "░" in low

    # Medium speed → yellow, partial fill
    mid = SpeedTestDisplay._render_gauge(50.0, width=10)
    assert "yellow" in mid
    assert "█" in mid
    assert "░" in mid

    # High speed → bright_green, mostly full
    high = SpeedTestDisplay._render_gauge(150.0, width=10)
    assert "bright_green" in high
    assert high.count("█") > high.count("░")

    # Capped at max
    capped = SpeedTestDisplay._render_gauge(500.0, width=10)
    assert "bright_green" in capped
    assert "░" not in capped


def test_display_body_contains_mbps():
    from speed_test_tui.interface import SpeedResult

    display = SpeedTestDisplay()
    display.update_download(SpeedResult(1_000_000, 1.0, 10_000_000, 10.0))
    panel = display._render_body()
    text = str(panel.renderable)
    assert "Mbps" in text
    assert "MB/s" not in text
