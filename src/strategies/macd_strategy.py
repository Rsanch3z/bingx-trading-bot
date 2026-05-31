"""
MACD Cross with Trend Filter + RSI Guard.

Improvements over the original:
  - EMA(50) trend filter: don't fight the trend
  - RSI guard: skip signals when price is already too extended
  - ATR-based SL/TP: volatility-adaptive instead of fixed %
  - 3:1 R:R target: edges compound faster with fewer but higher-quality trades

MACD's natural advantage: the histogram smoothing means it reacts slower
than raw EMA cross, which filters out many short-lived fake signals.
Adding the trend filter and RSI guard further tightens the entry criteria.
"""
import math

from src.indicators import atr, ema, macd, rsi
from src.models import Candle, Signal, SignalSide


class MacdStrategy:

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        trend: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        rr: float = 3.0,
    ) -> None:
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.trend = trend
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr
        self.name = f"MACD({fast},{slow},{signal})+RSI"

    def generate_signal(self, candles: list[Candle]) -> Signal:
        min_len = max(
            self.slow + self.signal_period + 2,
            self.trend + 2,
            self.rsi_period + 2,
        )
        if len(candles) < min_len:
            return Signal(SignalSide.FLAT, "warmup", candles[-1].close if candles else 0.0)

        closes = [c.close for c in candles]
        highs  = [c.high  for c in candles]
        lows   = [c.low   for c in candles]

        # ── MACD cross ───────────────────────────────────────────────────────
        macd_line, signal_line, _ = macd(closes, self.fast, self.slow, self.signal_period)
        cross_up = macd_line[-2] <= signal_line[-2] and macd_line[-1] > signal_line[-1]
        cross_dn = macd_line[-2] >= signal_line[-2] and macd_line[-1] < signal_line[-1]

        if not cross_up and not cross_dn:
            return Signal(SignalSide.FLAT, "no MACD cross", closes[-1])

        # ── Trend filter via EMA(50) ─────────────────────────────────────────
        trend_vals = ema(closes, self.trend)
        trend_up   = closes[-1] > trend_vals[-1]

        # ── RSI guard ────────────────────────────────────────────────────────
        rsi_vals = rsi(closes, self.rsi_period)
        curr_rsi = rsi_vals[-1]
        if math.isnan(curr_rsi):
            return Signal(SignalSide.FLAT, "rsi warmup", closes[-1])

        # ── ATR-based position sizing ────────────────────────────────────────
        curr_atr = atr(highs, lows, closes, self.atr_period)[-1]
        if curr_atr <= 0:
            return Signal(SignalSide.FLAT, "atr zero", closes[-1])

        entry = closes[-1]

        # LONG: MACD crosses up + above EMA(50) + RSI not yet overbought
        if cross_up and trend_up and curr_rsi < 65:
            sl   = entry - self.sl_atr_mult * curr_atr
            risk = entry - sl
            tp   = entry + self.rr * risk
            return Signal(
                SignalSide.LONG,
                f"MACD cross ↑ | trend ↑ | RSI {curr_rsi:.0f} | ATR-SL",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        # SHORT: MACD crosses down + below EMA(50) + RSI not yet oversold
        if cross_dn and not trend_up and curr_rsi > 35:
            sl   = entry + self.sl_atr_mult * curr_atr
            risk = sl - entry
            tp   = entry - self.rr * risk
            return Signal(
                SignalSide.SHORT,
                f"MACD cross ↓ | trend ↓ | RSI {curr_rsi:.0f} | ATR-SL",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        return Signal(SignalSide.FLAT, "cross filtered by trend/RSI", closes[-1])
