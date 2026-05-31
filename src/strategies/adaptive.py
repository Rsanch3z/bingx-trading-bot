"""
Adaptive Regime-Switching Strategy — v2 with ADX + MTF + Session filter.

Improvements over v1:
  - ADX(14) regime detection: >22 trending, <20 ranging, 20-22 neutral skip
  - Session / calendar gate for MACD: 08:00–20:00 UTC on weekdays only
  - EMA(200) macro gate with ±0.5% buffer zone (avoids choppy zone at EMA)
  - 4H MTF confirmation: EMA(50) slope on aggregated 4H bars
  - Volume 1.5× average for MACD trending entries, 1.0× for BB ranging
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from src.indicators import adx as adx_fn, atr, bollinger_bands, ema, macd, rsi, sma
from src.models import Candle, Signal, SignalSide


def _aggregate_to_4h(candles: list[Candle]) -> list[Candle]:
    """Group consecutive 1H candles into 4H bars (every 4 → 1)."""
    result = []
    for i in range(0, len(candles) - 3, 4):
        chunk = candles[i:i + 4]
        result.append(Candle(
            timestamp_ms=chunk[0].timestamp_ms,
            open=chunk[0].open,
            high=max(c.high for c in chunk),
            low=min(c.low for c in chunk),
            close=chunk[-1].close,
            volume=sum(c.volume for c in chunk),
        ))
    return result


class AdaptiveStrategy:

    def __init__(
        self,
        trend_period: int = 50,
        slope_lookback: int = 12,
        adx_period: int = 14,
        adx_trend_min: float = 22.0,
        adx_range_max: float = 20.0,
        vol_period: int = 20,
        vol_mult: float = 1.0,          # BB ranging vol threshold (MACD uses 1.5× internally)
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        rr: float = 3.0,
        min_rr_mean_rev: float = 1.8,
    ) -> None:
        self.trend_period = trend_period
        self.slope_lookback = slope_lookback
        self.adx_period = adx_period
        self.adx_trend_min = adx_trend_min
        self.adx_range_max = adx_range_max
        self.vol_period = vol_period
        self.vol_mult = vol_mult
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr
        self.min_rr_mean_rev = min_rr_mean_rev
        self.name = "Adaptive(BB↔MACD)+Vol"

    def generate_signal(self, candles: list[Candle]) -> Signal:
        min_len = max(
            self.macd_slow + self.macd_signal + 2,
            self.trend_period + self.slope_lookback + 2,
            self.bb_period + 3,
            self.rsi_period + 2,
            self.vol_period + 2,
            202,                          # EMA(200) warmup
            4 * (self.trend_period + 5),  # 4H MTF: ~55 4H bars
        )
        if len(candles) < min_len:
            return Signal(SignalSide.FLAT, "warmup", candles[-1].close if candles else 0.0)

        closes  = [c.close  for c in candles]
        highs   = [c.high   for c in candles]
        lows    = [c.low    for c in candles]
        volumes = [c.volume for c in candles]
        entry   = closes[-1]

        # ── Session / calendar filter ────────────────────────────────────────
        dt_utc   = datetime.fromtimestamp(candles[-1].timestamp_ms / 1000, tz=timezone.utc)
        hour_utc = dt_utc.hour
        weekday  = dt_utc.weekday()  # 0=Mon … 6=Sun
        in_active_session = 8 <= hour_utc < 20
        is_weekend = weekday >= 5 or (weekday == 4 and hour_utc >= 20)

        # ── ADX regime detection ─────────────────────────────────────────────
        adx_vals = adx_fn(highs, lows, closes, self.adx_period)
        curr_adx = adx_vals[-1]
        if math.isnan(curr_adx):
            return Signal(SignalSide.FLAT, "adx warmup", entry)

        if curr_adx > self.adx_trend_min:
            regime = "trending"
        elif curr_adx < self.adx_range_max:
            regime = "ranging"
        else:
            return Signal(SignalSide.FLAT, f"ADX {curr_adx:.1f} neutral", entry)

        # ── EMA(50) slope for directional bias ──────────────────────────────
        trend_ema = ema(closes, self.trend_period)
        ref_ema   = trend_ema[-(self.slope_lookback + 1)]
        slope     = (trend_ema[-1] - ref_ema) / ref_ema if ref_ema != 0 else 0.0
        trend_up  = slope > 0

        # ── EMA(200) macro gate with ±0.5% buffer ───────────────────────────
        ema200_vals = ema(closes, 200)
        ema200 = ema200_vals[-1]
        if math.isnan(ema200):
            return Signal(SignalSide.FLAT, "ema200 warmup", entry)
        macro_long_ok  = entry > ema200 * 1.005
        macro_short_ok = entry < ema200 * 0.995

        # ── 4H MTF confirmation via EMA(50) slope ───────────────────────────
        candles_4h = _aggregate_to_4h(candles)
        htf_long_ok = htf_short_ok = False
        if len(candles_4h) >= self.trend_period + 3:
            closes_4h = [c.close for c in candles_4h]
            ema50_4h  = ema(closes_4h, self.trend_period)
            if (not math.isnan(ema50_4h[-1]) and not math.isnan(ema50_4h[-3])
                    and ema50_4h[-3] != 0):
                htf_slope    = (ema50_4h[-1] - ema50_4h[-3]) / ema50_4h[-3]
                htf_long_ok  = htf_slope > 0
                htf_short_ok = htf_slope < 0

        # ── Shared indicators ────────────────────────────────────────────────
        rsi_vals = rsi(closes, self.rsi_period)
        curr_rsi = rsi_vals[-1]
        if math.isnan(curr_rsi):
            return Signal(SignalSide.FLAT, "rsi warmup", entry)

        curr_atr = atr(highs, lows, closes, self.atr_period)[-1]
        if curr_atr <= 0:
            return Signal(SignalSide.FLAT, "atr zero", entry)

        # ════════════════════════════════════════════════════════════════════
        # TRENDING REGIME → MACD  (session-gated, 1.5× volume)
        # ════════════════════════════════════════════════════════════════════
        if regime == "trending":
            if not in_active_session or is_weekend:
                return Signal(SignalSide.FLAT, "outside session", entry)

            vol_avg = sma(volumes, self.vol_period)[-1]
            if math.isnan(vol_avg) or volumes[-1] < 1.5 * vol_avg:
                return Signal(SignalSide.FLAT, "low volume", entry)

            ml, sl_line, _ = macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
            cross_up = ml[-2] <= sl_line[-2] and ml[-1] > sl_line[-1]
            cross_dn = ml[-2] >= sl_line[-2] and ml[-1] < sl_line[-1]

            if cross_up and trend_up and curr_rsi < 65 and macro_long_ok and htf_long_ok:
                sl   = entry - self.sl_atr_mult * curr_atr
                risk = entry - sl
                tp   = entry + self.rr * risk
                return Signal(
                    SignalSide.LONG,
                    f"Trend↑ MACD|ADX {curr_adx:.0f}|RSI {curr_rsi:.0f}|RR {self.rr:.1f}",
                    entry,
                    stop_loss_price=round(sl, 8),
                    take_profit_price=round(tp, 8),
                )

            if cross_dn and not trend_up and curr_rsi > 35 and macro_short_ok and htf_short_ok:
                sl   = entry + self.sl_atr_mult * curr_atr
                risk = sl - entry
                tp   = entry - self.rr * risk
                return Signal(
                    SignalSide.SHORT,
                    f"Trend↓ MACD|ADX {curr_adx:.0f}|RSI {curr_rsi:.0f}|RR {self.rr:.1f}",
                    entry,
                    stop_loss_price=round(sl, 8),
                    take_profit_price=round(tp, 8),
                )

        # ════════════════════════════════════════════════════════════════════
        # RANGING REGIME → BB mean-reversion  (no session restriction, 1.0× vol)
        # ════════════════════════════════════════════════════════════════════
        else:
            vol_avg = sma(volumes, self.vol_period)[-1]
            if math.isnan(vol_avg) or volumes[-1] < self.vol_mult * vol_avg:
                return Signal(SignalSide.FLAT, "low volume", entry)

            upper, _mid, lower = bollinger_bands(closes, self.bb_period, self.bb_std)
            if math.isnan(upper[-1]) or math.isnan(lower[-1]):
                return Signal(SignalSide.FLAT, "band warmup", entry)

            prev_close = closes[-2]
            is_bullish = candles[-1].close > candles[-1].open
            is_bearish = candles[-1].close < candles[-1].open

            if (prev_close > lower[-2] and entry <= lower[-1]
                    and curr_rsi < 35 and is_bullish
                    and macro_long_ok and htf_long_ok):
                sl   = entry - self.sl_atr_mult * curr_atr
                risk = entry - sl
                if risk <= 0:
                    return Signal(SignalSide.FLAT, "zero risk", entry)
                tp        = max(upper[-1], entry + self.min_rr_mean_rev * risk)
                actual_rr = (tp - entry) / risk
                if actual_rr < self.min_rr_mean_rev:
                    return Signal(SignalSide.FLAT, f"RR {actual_rr:.1f}<min", entry)
                return Signal(
                    SignalSide.LONG,
                    f"Range BB↓|ADX {curr_adx:.0f}|RSI {curr_rsi:.0f}|RR {actual_rr:.1f}",
                    entry,
                    stop_loss_price=round(sl, 8),
                    take_profit_price=round(tp, 8),
                )

            if (prev_close < upper[-2] and entry >= upper[-1]
                    and curr_rsi > 65 and is_bearish
                    and macro_short_ok and htf_short_ok):
                sl   = entry + self.sl_atr_mult * curr_atr
                risk = sl - entry
                if risk <= 0:
                    return Signal(SignalSide.FLAT, "zero risk", entry)
                tp        = min(lower[-1], entry - self.min_rr_mean_rev * risk)
                actual_rr = (entry - tp) / risk
                if actual_rr < self.min_rr_mean_rev:
                    return Signal(SignalSide.FLAT, f"RR {actual_rr:.1f}<min", entry)
                return Signal(
                    SignalSide.SHORT,
                    f"Range BB↑|ADX {curr_adx:.0f}|RSI {curr_rsi:.0f}|RR {actual_rr:.1f}",
                    entry,
                    stop_loss_price=round(sl, 8),
                    take_profit_price=round(tp, 8),
                )

        return Signal(SignalSide.FLAT, "no qualified signal", entry)
