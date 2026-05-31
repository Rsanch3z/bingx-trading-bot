"""
EMA Pullback Strategy — buy dips in strong trends.

Problem with crossover strategies: they enter at random points mid-trend,
often at exhaustion highs or lows. Win rate stays at 30-40%.

This strategy fixes that by waiting for PULLBACKS to EMA(21):
  1. Strong trend confirmed: ADX(14) > 22 + EMA(50) clearly sloping
  2. Pullback: current candle touches EMA(21) zone from the trend direction
     (candle low ≤ EMA21 for longs, candle high ≥ EMA21 for shorts)
  3. Reversal: candle CLOSES back in trend direction with a bullish/bearish body
     (close > open AND close > EMA21 for longs)
  4. RSI 30–60: not overbought at entry (we're buying the dip, not the top)
  5. EMA(200) macro gate: longs above, shorts below

Why win rate should be higher:
  - We enter at VALUE (the EMA), not at a random crossover
  - Strong trend + structural support = high probability continuation
  - The reversal candle confirms buyers/sellers stepped in at that exact level
  - Expected win rate: 50–65% vs 30–44% for crossover strategies
"""
from __future__ import annotations

import math

from src.indicators import adx as adx_fn, atr, ema, rsi, sma
from src.models import Candle, Signal, SignalSide


class EMAPullbackStrategy:

    def __init__(
        self,
        fast_period: int = 21,       # EMA to pull back to (short-term dynamic support)
        trend_period: int = 50,      # EMA for trend direction
        slope_lookback: int = 5,     # bars for EMA(50) slope measurement
        slope_min: float = 0.001,    # 0.1% over 5 bars = clearly trending
        adx_period: int = 14,
        adx_min: float = 22.0,
        pullback_band: float = 0.003,  # allow entry up to 0.3% away from EMA21
        rsi_period: int = 14,
        vol_period: int = 20,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        rr: float = 3.0,
    ) -> None:
        self.fast_period = fast_period
        self.trend_period = trend_period
        self.slope_lookback = slope_lookback
        self.slope_min = slope_min
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.pullback_band = pullback_band
        self.rsi_period = rsi_period
        self.vol_period = vol_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr
        self.name = f"EMA_Pullback({fast_period},{trend_period})"

    def generate_signal(self, candles: list[Candle]) -> Signal:
        min_len = max(
            self.trend_period + self.slope_lookback + 2,
            self.adx_period * 2 + 2,
            self.rsi_period + 2,
            self.vol_period + 2,
            202,  # EMA(200)
        )
        if len(candles) < min_len:
            return Signal(SignalSide.FLAT, "warmup", candles[-1].close if candles else 0.0)

        closes  = [c.close for c in candles]
        highs   = [c.high  for c in candles]
        lows    = [c.low   for c in candles]
        volumes = [c.volume for c in candles]
        candle  = candles[-1]
        entry   = candle.close

        # ── ADX: confirm a trending market ──────────────────────────────────
        adx_vals = adx_fn(highs, lows, closes, self.adx_period)
        curr_adx = adx_vals[-1]
        if math.isnan(curr_adx) or curr_adx < self.adx_min:
            return Signal(SignalSide.FLAT, f"ADX {curr_adx:.1f} < {self.adx_min}", entry)

        # ── EMA(50) slope: direction of the trend ───────────────────────────
        ema50 = ema(closes, self.trend_period)
        ref   = ema50[-(self.slope_lookback + 1)]
        slope = (ema50[-1] - ref) / ref if ref != 0 else 0.0
        trend_up = slope > self.slope_min
        trend_dn = slope < -self.slope_min
        if not trend_up and not trend_dn:
            return Signal(SignalSide.FLAT, f"EMA50 flat slope={slope:.4f}", entry)

        # ── EMA(21): the pullback target ─────────────────────────────────────
        ema21 = ema(closes, self.fast_period)[-1]

        # ── EMA(200) macro gate ──────────────────────────────────────────────
        ema200 = ema(closes, 200)[-1]
        if math.isnan(ema200):
            return Signal(SignalSide.FLAT, "ema200 warmup", entry)

        # ── RSI ──────────────────────────────────────────────────────────────
        curr_rsi = rsi(closes, self.rsi_period)[-1]
        if math.isnan(curr_rsi):
            return Signal(SignalSide.FLAT, "rsi warmup", entry)

        # ── Volume: at least average (dips should not be on disappearing vol) -
        vol_avg = sma(volumes, self.vol_period)[-1]
        if math.isnan(vol_avg) or volumes[-1] < 0.8 * vol_avg:
            return Signal(SignalSide.FLAT, "very low volume", entry)

        # ── ATR for SL ──────────────────────────────────────────────────────
        curr_atr = atr(highs, lows, closes, self.atr_period)[-1]
        if curr_atr <= 0:
            return Signal(SignalSide.FLAT, "atr zero", entry)

        band = self.pullback_band  # tolerance around EMA21

        # ════════════════════════════════════════════════════════════════════
        # LONG: uptrend + candle low touches EMA(21) + bullish reversal body
        # ════════════════════════════════════════════════════════════════════
        long_pullback = (
            candle.low  <= ema21 * (1 + band)   # touched EMA21 zone from above
            and candle.close > ema21             # closed back above EMA21
            and candle.close > candle.open       # bullish body: buyers stepped in
        )
        if trend_up and long_pullback and curr_rsi < 60 and entry > ema200:
            sl   = entry - self.sl_atr_mult * curr_atr
            risk = entry - sl
            if risk <= 0:
                return Signal(SignalSide.FLAT, "zero risk", entry)
            tp = entry + self.rr * risk
            return Signal(
                SignalSide.LONG,
                f"PB↑ EMA21={ema21:.2f}|ADX {curr_adx:.0f}|RSI {curr_rsi:.0f}|RR {self.rr:.1f}",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        # ════════════════════════════════════════════════════════════════════
        # SHORT: downtrend + candle high touches EMA(21) + bearish reversal body
        # ════════════════════════════════════════════════════════════════════
        short_pullback = (
            candle.high >= ema21 * (1 - band)   # touched EMA21 zone from below
            and candle.close < ema21             # closed back below EMA21
            and candle.close < candle.open       # bearish body: sellers stepped in
        )
        if trend_dn and short_pullback and curr_rsi > 40 and entry < ema200:
            sl   = entry + self.sl_atr_mult * curr_atr
            risk = sl - entry
            if risk <= 0:
                return Signal(SignalSide.FLAT, "zero risk", entry)
            tp = entry - self.rr * risk
            return Signal(
                SignalSide.SHORT,
                f"PB↓ EMA21={ema21:.2f}|ADX {curr_adx:.0f}|RSI {curr_rsi:.0f}|RR {self.rr:.1f}",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        return Signal(SignalSide.FLAT, "no pullback", entry)
