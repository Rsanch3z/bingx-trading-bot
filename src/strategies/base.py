from typing import Protocol

from src.models import Candle, Signal


class Strategy(Protocol):
    """All strategies must implement this interface."""
    name: str

    def generate_signal(self, candles: list[Candle]) -> Signal: ...
