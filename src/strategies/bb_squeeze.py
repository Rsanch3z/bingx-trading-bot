"""
BB Squeeze Breakout Strategy.

Detects low-volatility compression via Bollinger Band width hitting a
multi-period minimum (the "squeeze"), then enters on the first expansion
candle in the direction confirmed by MACD momentum histogram.

Classic TTM Squeeze concept (John Carter, 2005):
  1. Squeeze  = BB width at N-period low → market coiling, big move coming
  2. Fire     = width expands above minimum → coil releases, enter immediately
  3. Direction = MACD histogram sign (positive = long, negative = short)

Edge: compressed volatility reliably precedes large directional moves.
Catching the first expansion candle gives maximum RR on the full impulse.
Cost advantage: fewer, longer-duration trades = lower total fees and funding.
"""
from __future__ import annotations

import math

from src.indicators import atr, bollinger_bands, ema, macd, rsi
from src.models import Candle, Signal, SignalSide


class BBSqueezeStrategy:

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_lookback: int = 30,      # bars to scan for width minimum
        squeeze_threshold: float = 1.15, # ≤ threshold × min = "in squeeze"
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        rsi_period: int = 14,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        rr: float = 3.0,
    ) -> None:
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_threshold = squeeze_threshold
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr
        self.name = f"BB_Squeeze(sq={squeeze_lookback},rr={rr:.0f})"

    def generate_signal(self, candles: list[Candle]) -> Signal:
        min_len = max(
            self.bb_period + self.squeeze_lookback + 5,
            self.macd_slow + self.macd_signal + 2,
            self.rsi_period + 2,
            202,  # EMA(200) warmup
        )
        if len(candles) < min_len:
            return Signal(SignalSide.FLAT, "warmup", candles[-1].close if candles else 0.0)

        closes = [c.close for c in candles]
        highs  = [c.high  for c in candles]
        lows   = [c.low   for c in candles]
        entry  = closes[-1]

        # ── BB width history ─────────────────────────────────────────────────
        upper, middle, lower = bollinger_bands(closes, self.bb_period, self.bb_std)
        if math.isnan(upper[-1]) or middle[-1] == 0:
            return Signal(SignalSide.FLAT, "bb warmup", entry)

        lb = self.squeeze_lookback
        width_history: list[float] = []
        for i in range(-lb - 2, 0):
            if not math.isnan(upper[i]) and middle[i] != 0:
                width_history.append((upper[i] - lower[i]) / middle[i])

        if len(width_history) < lb:
            return Signal(SignalSide.FLAT, "squeeze warmup", entry)

        curr_width = width_history[-1]
        prev_width = width_history[-2]
        window_min = min(width_history[:-1])  # min over history, excluding current

        # Previous candle was "in squeeze": width ≤ threshold × window minimum
        was_in_squeeze = prev_width <= window_min * self.squeeze_threshold

        # Squeeze "fires": was compressed, now expanding
        fired = was_in_squeeze and curr_width > prev_width
        if not fired:
            return Signal(SignalSide.FLAT, "no squeeze fire", entry)

        # ── MACD histogram direction ─────────────────────────────────────────
        _, _, hist = macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
        if math.isnan(hist[-1]) or math.isnan(hist[-2]):
            return Signal(SignalSide.FLAT, "macd warmup", entry)

        macd_bull = hist[-1] > 0 and hist[-1] > hist[-2]
        macd_bear = hist[-1] < 0 and hist[-1] < hist[-2]
        if not macd_bull and not macd_bear:
            return Signal(SignalSide.FLAT, "macd direction unclear", entry)

        # ── EMA(200) macro gate ──────────────────────────────────────────────
        ema200 = ema(closes, 200)[-1]
        if math.isnan(ema200):
            return Signal(SignalSide.FLAT, "ema200 warmup", entry)

        # ── RSI guard: avoid entering into exhaustion ───────────────────────
        curr_rsi = rsi(closes, self.rsi_period)[-1]
        if math.isnan(curr_rsi):
            return Signal(SignalSide.FLAT, "rsi warmup", entry)

        # ── ATR for SL sizing ────────────────────────────────────────────────
        curr_atr = atr(highs, lows, closes, self.atr_period)[-1]
        if curr_atr <= 0:
            return Signal(SignalSide.FLAT, "atr zero", entry)

        squeeze_pct = round(window_min * 100, 3)  # for signal label

        # ── Long entry ───────────────────────────────────────────────────────
        if macd_bull and entry > ema200 and curr_rsi < 70:
            sl   = entry - self.sl_atr_mult * curr_atr
            risk = entry - sl
            if risk <= 0:
                return Signal(SignalSide.FLAT, "zero risk", entry)
            tp = entry + self.rr * risk
            return Signal(
                SignalSide.LONG,
                f"Squeeze↑ w={squeeze_pct}%|hist={hist[-1]:.4f}|RSI {curr_rsi:.0f}|RR {self.rr:.1f}",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        # ── Short entry ──────────────────────────────────────────────────────
        if macd_bear and entry < ema200 and curr_rsi > 30:
            sl   = entry + self.sl_atr_mult * curr_atr
            risk = sl - entry
            if risk <= 0:
                return Signal(SignalSide.FLAT, "zero risk", entry)
            tp = entry - self.rr * risk
            return Signal(
                SignalSide.SHORT,
                f"Squeeze↓ w={squeeze_pct}%|hist={hist[-1]:.4f}|RSI {curr_rsi:.0f}|RR {self.rr:.1f}",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        return Signal(SignalSide.FLAT, "macro gate blocked", entry)
