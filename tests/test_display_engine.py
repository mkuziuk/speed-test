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
    import re

    # Very low speed → hex gradient, mostly empty with dim styling
    low = SpeedTestDisplay._render_gauge(10.0, width=10)
    assert re.search(r"#[0-9a-f]{6}", low)  # Has hex color
    assert "[dim]░[/dim]" in low
    # 10 Mbps / 200 Mbps = 0.05, width=10 → 1 filled (min for positive), 9 empty
    assert low.count("█") == 1
    assert low.count("░") == 9

    # Medium speed → hex gradient, partial fill
    mid = SpeedTestDisplay._render_gauge(50.0, width=10)
    assert re.search(r"#[0-9a-f]{6}", mid)  # Has hex color
    assert "[dim]░[/dim]" in mid
    assert "█" in mid
    # 50 Mbps / 200 Mbps = 0.25, width=10 → 2 filled, 8 empty
    assert mid.count("█") == 2
    assert mid.count("░") == 8

    # High speed → hex gradient, mostly full
    high = SpeedTestDisplay._render_gauge(150.0, width=10)
    assert re.search(r"#[0-9a-f]{6}", high)  # Has hex color
    # 150 Mbps / 200 Mbps = 0.75, width=10 → 7 filled, 3 empty
    assert high.count("█") == 7
    assert high.count("░") == 3

    # Capped at max - no empty blocks
    capped = SpeedTestDisplay._render_gauge(500.0, width=10)
    assert re.search(r"#[0-9a-f]{6}", capped)  # Has hex color
    assert "[dim]" not in capped  # No dim styling when fully filled
    assert "░" not in capped
    assert capped.count("█") == 10
    # Also verify colors are green-ish (not purple/magenta)
    cap_pattern = r"\[(#[0-9a-f]{6})\]█\[\/\1\]"
    cap_colors = re.findall(cap_pattern, capped)
    for c in cap_colors:
        r_val = int(c[1:3], 16)
        g_val = int(c[3:5], 16)
        assert r_val < 20, f"Expected green-ish color (low red), got {c}"
        assert g_val > 80, f"Expected green-ish color (high green), got {c}"


def test_render_gauge_absolute_color_positions():
    """Colors are based on absolute position, not fill count."""
    import re

    # Render low and high gauges
    low = SpeedTestDisplay._render_gauge(10.0, width=20)   # 1 filled
    high = SpeedTestDisplay._render_gauge(180.0, width=20)  # 18 filled

    # Extract hex colors from filled blocks pattern [#rrggbb]█[/#rrggbb]
    pattern = r"\[(#[0-9a-f]{6})\]█\[\/\1\]"

    low_colors = re.findall(pattern, low)
    high_colors = re.findall(pattern, high)

    # Position 0 should have same color in both
    assert low_colors[0] == high_colors[0], "Position 0 colors should match"

    # Position 1 should have same color in both (if both have at least 2 filled)
    # Low has 1 filled, high has 18 - so we can only compare position 0
    # Let's use a different test: compare position 0 and 1 of two medium gauges
    mid1 = SpeedTestDisplay._render_gauge(50.0, width=20)   # ~5 filled
    mid2 = SpeedTestDisplay._render_gauge(100.0, width=20)  # ~10 filled

    mid1_colors = re.findall(pattern, mid1)
    mid2_colors = re.findall(pattern, mid2)

    # Positions 0 and 1 should match between mid1 and mid2
    assert mid1_colors[0] == mid2_colors[0], "Position 0 colors should match"
    assert mid1_colors[1] == mid2_colors[1], "Position 1 colors should match"


def test_render_gauge_smooth_gradient_full_width():
    """Full gauge should have smooth gradient with many distinct colors."""
    import re

    # Render full gauge
    full = SpeedTestDisplay._render_gauge(300.0, width=20)

    # All 20 cells should be filled
    assert full.count("█") == 20
    assert "░" not in full

    # Extract all hex colors
    pattern = r"\[(#[0-9a-f]{6})\]█\[\/\1\]"
    colors = re.findall(pattern, full)

    # Should have at least 8 distinct colors (smooth gradient, not chunky)
    distinct_colors = set(colors)
    assert len(distinct_colors) >= 8, f"Expected >= 8 distinct colors, got {len(distinct_colors)}"

    # First color should be near dark green (#008000)
    first_r, first_g, first_b = int(colors[0][1:3], 16), int(colors[0][3:5], 16), int(colors[0][5:7], 16)
    assert first_r < 20, "First color should be green-ish (very low red)"
    assert first_g > 100, "First color should be green-ish (medium-high green)"
    assert first_b < 20, "First color should be green-ish (very low blue)"

    # Last color should be near spring green (#00ff80)
    last_r, last_g, last_b = int(colors[-1][1:3], 16), int(colors[-1][3:5], 16), int(colors[-1][5:7], 16)
    assert last_r < 20, "Last color should be spring green (very low red)"
    assert last_g > 200, "Last color should be spring green (high green)"
    assert last_b > 100, "Last color should be spring green (high blue)"


def test_render_gauge_each_cell_is_one_char():
    """Each cell renders as exactly one visible character."""
    import re

    for width in [10, 20, 30]:
        for speed in [0.0, 10.0, 100.0, 300.0]:
            gauge = SpeedTestDisplay._render_gauge(speed, width=width)

            # Strip all Rich markup tags
            visible = re.sub(r"\[.*?\]", "", gauge)

            # Should have exactly `width` visible characters
            assert len(visible) == width, f"Width {width}, speed {speed}: expected {width} chars, got {len(visible)}"

            # All visible chars should be █ or ░
            assert all(c in "█░" for c in visible), f"Unexpected chars in: {visible}"


def test_render_gauge_zero_speed_all_empty_dim():
    """Zero speed should show all empty blocks with dim styling."""
    gauge = SpeedTestDisplay._render_gauge(0.0, width=10)
    assert gauge.count("█") == 0
    assert gauge.count("░") == 10
    assert "[dim]░[/dim]" in gauge


def test_display_body_contains_mbps():
    from speed_test_tui.interface import SpeedResult

    display = SpeedTestDisplay()
    display.update_download(SpeedResult(1_000_000, 1.0, 10_000_000, 10.0))
    panel = display._render_body()
    text = str(panel.renderable)
    assert "Mbps" in text
    assert "MB/s" not in text
