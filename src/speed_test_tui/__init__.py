"""speed-test-tui: Terminal-based internet speed test."""

from .interface import (
    SpeedTestProtocol,
    PingResult,
    SpeedResult,
    SpeedTestResult,
)
from .engine import SpeedTestEngine
from .fake import FakeSpeedTest
from .display import SpeedTestDisplay

__version__ = "0.1.0"
__all__ = [
    "SpeedTestProtocol",
    "PingResult",
    "SpeedResult",
    "SpeedTestResult",
    "SpeedTestEngine",
    "FakeSpeedTest",
    "SpeedTestDisplay",
]
