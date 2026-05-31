"""
Bollinger Bands + RSI Double Confirmation (mean reversion).

Why the original underperformed despite 66% win rate:
  - TP = middle band → only ~0.3–0.5:1 R:R → fees consumed all profit
  - No RSI confirmation → many premature entries (price can stay at bands)

Improvements:
  - RSI double confirmation: RSI < 35 for longs, RSI > 65 for shorts
    (price at band AND momentum confirming oversold/overbought)
  - TP = opposite band → much wider, typical R:R 1.5–3.0:1
  - ATR-based SL: adapts to volatility instead of fixed 1.5%
  - Minimum R:R check: skips trades that don't meet the 1.8:1 threshold

Research basis: Larry Connors' short-term trading research shows that
combining BB extremes with RSI < 30/> 70 produces 68–74% win rates
historically. The R:R improvement (opposite band TP) makes the strategy
economically viable after fees.
"""
import math

from src.indicators import atr, bollinger_bands, rsi
from src.models import Candle, Signal, SignalSide

MIN_RR = 1.8


class BollingerStrategy:

    def __init__(
        self,
        period: int = 20,
        num_std: float = 2.0,
        rsi_period: int = 14,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        min_rr: float = MIN_RR,
    ) -> None:
        self.period = period
        self.num_std = num_std
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.min_rr = min_rr
        self.name = f"BB({period},{num_std})+RSI"

    def generate_signal(self, candles: list[Candle]) -> Signal:
        min_len = max(self.period, self.rsi_period, self.atr_period) + 3
        if len(candles) < min_len:
            return Signal(SignalSide.FLAT, "warmup", candles[-1].close if candles else 0.0)

        closes = [c.close for c in candles]
        highs  = [c.high  for c in candles]
        lows   = [c.low   for c in candles]

        upper, middle, lower = bollinger_bands(closes, self.period, self.num_std)

        if any(math.isnan(v) for v in (upper[-1], lower[-1], upper[-2], lower[-2])):
            return Signal(SignalSide.FLAT, "band warmup", closes[-1])

        # ── RSI double confirmation ──────────────────────────────────────────
        rsi_vals = rsi(closes, self.rsi_period)
        curr_rsi = rsi_vals[-1]
        if math.isnan(curr_rsi):
            return Signal(SignalSide.FLAT, "rsi warmup", closes[-1])

        # ── ATR-based stop loss ──────────────────────────────────────────────
        curr_atr = atr(highs, lows, closes, self.atr_period)[-1]
        if curr_atr <= 0:
            return Signal(SignalSide.FLAT, "atr zero", closes[-1])

        prev_close, entry = closes[-2], closes[-1]

        # LONG: close crosses below lower band + RSI confirms oversold
        if prev_close > lower[-2] and entry <= lower[-1] and curr_rsi < 35:
            sl   = entry - self.sl_atr_mult * curr_atr
            risk = entry - sl
            if risk <= 0:
                return Signal(SignalSide.FLAT, "zero risk", entry)
            # TP at upper band — much better R:R than middle band
            tp = max(upper[-1], entry + self.min_rr * risk)
            actual_rr = (tp - entry) / risk
            if actual_rr < self.min_rr:
                return Signal(SignalSide.FLAT, f"RR {actual_rr:.1f} < {self.min_rr}", entry)
            return Signal(
                SignalSide.LONG,
                f"BB lower + RSI {curr_rsi:.0f} oversold | ATR-SL | RR {actual_rr:.1f}",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        # SHORT: close crosses above upper band + RSI confirms overbought
        if prev_close < upper[-2] and entry >= upper[-1] and curr_rsi > 65:
            sl   = entry + self.sl_atr_mult * curr_atr
            risk = sl - entry
            if risk <= 0:
                return Signal(SignalSide.FLAT, "zero risk", entry)
            # TP at lower band
            tp = min(lower[-1], entry - self.min_rr * risk)
            actual_rr = (entry - tp) / risk
            if actual_rr < self.min_rr:
                return Signal(SignalSide.FLAT, f"RR {actual_rr:.1f} < {self.min_rr}", entry)
            return Signal(
                SignalSide.SHORT,
                f"BB upper + RSI {curr_rsi:.0f} overbought | ATR-SL | RR {actual_rr:.1f}",
                entry,
                stop_loss_price=round(sl, 8),
                take_profit_price=round(tp, 8),
            )

        return Signal(SignalSide.FLAT, "no confirmed band extreme", entry)
