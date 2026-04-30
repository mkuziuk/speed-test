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
