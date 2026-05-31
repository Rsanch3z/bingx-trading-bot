"""
Support/Resistance Breakout + MACD Confirmation strategy.

Entry logic (professional trader style):
  Long:  previous close <= resistance, current close breaks above by breakout_pct
         AND MACD histogram is positive (momentum confirms direction)
  Short: previous close >= support, current close breaks below by breakout_pct
         AND MACD histogram is negative

Stop loss — placed using market structure, NOT a fixed percentage:
  Long:  resistance level (now acting as support) - sl_atr_mult × ATR
  Short: support level (now acting as resistance) + sl_atr_mult × ATR
  → If that puts SL above entry (level too close), fall back to 1.5× ATR below entry

Take profit — next structural level:
  Long:  next resistance above entry (if RR >= min_rr), else entry + min_rr × risk
  Short: next support below entry (if RR >= min_rr), else entry - min_rr × risk

The trade is skipped entirely if calculated R:R < min_rr.
This means fewer trades but higher-quality setups.
"""
from src.indicators import atr, macd
from src.models import Candle, Signal, SignalSide
from src.structure import find_sr_levels


class SRBreakoutStrategy:

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        atr_period: int = 14,
        sl_atr_mult: float = 1.0,
        min_rr: float = 2.0,
        breakout_pct: float = 0.002,
        pivot_window: int = 5,
        sr_lookback: int = 80,
    ) -> None:
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.min_rr = min_rr
        self.breakout_pct = breakout_pct
        self.pivot_window = pivot_window
        self.sr_lookback = sr_lookback
        self.name = f"SR+MACD(piv={pivot_window},RR>={min_rr})"

    def generate_signal(self, candles: list[Candle]) -> Signal:
        min_len = max(
            self.macd_slow + self.macd_signal + 2,
            self.sr_lookback + self.pivot_window * 2 + 5,
        )
        if len(candles) < min_len:
            return Signal(SignalSide.FLAT, "warmup", candles[-1].close if candles else 0.0)

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        # MACD histogram — positive = bullish momentum, negative = bearish
        _, _, histogram = macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
        hist = histogram[-1]

        # ATR — current market volatility (used for dynamic SL sizing)
        atr_values = atr(highs, lows, closes, self.atr_period)
        current_atr = atr_values[-1]
        if current_atr <= 0:
            return Signal(SignalSide.FLAT, "atr zero", closes[-1])

        # S/R levels as of the PREVIOUS candle — used to detect just-happened breakouts.
        # find_sr_levels classifies levels relative to current price, so we must look
        # at prev-candle context to find levels that were resistance/support before
        # the current candle moved through them.
        supports_prev, resistances_prev = find_sr_levels(
            candles[:-1], self.pivot_window, self.sr_lookback
        )
        # Current levels used only for TP target selection.
        supports_curr, resistances_curr = find_sr_levels(
            candles, self.pivot_window, self.sr_lookback
        )

        entry = closes[-1]
        prev_close = closes[-2]

        # --- LONG: breakout above a level that was resistance at the prev candle ---
        if resistances_prev and hist > 0:
            nearest_r = resistances_prev[0]
            broke_above = (
                prev_close <= nearest_r
                and entry > nearest_r * (1 + self.breakout_pct)
            )
            if broke_above:
                sl = self._long_sl(entry, nearest_r, current_atr)
                risk = entry - sl
                if risk <= 0:
                    return Signal(SignalSide.FLAT, "sl above entry", entry)

                tp = self._long_tp(entry, risk, resistances_curr)
                actual_rr = (tp - entry) / risk
                if actual_rr < self.min_rr:
                    return Signal(SignalSide.FLAT,
                                  f"RR {actual_rr:.1f} < {self.min_rr}", entry)

                return Signal(
                    SignalSide.LONG,
                    f"breakout {nearest_r:.4f} | ATR-SL | RR {actual_rr:.1f}",
                    entry,
                    stop_loss_price=round(sl, 8),
                    take_profit_price=round(tp, 8),
                )

        # --- SHORT: breakdown below a level that was support at the prev candle ---
        if supports_prev and hist < 0:
            nearest_s = supports_prev[-1]
            broke_below = (
                prev_close >= nearest_s
                and entry < nearest_s * (1 - self.breakout_pct)
            )
            if broke_below:
                sl = self._short_sl(entry, nearest_s, current_atr)
                risk = sl - entry
                if risk <= 0:
                    return Signal(SignalSide.FLAT, "sl below entry", entry)

                tp = self._short_tp(entry, risk, supports_curr)
                actual_rr = (entry - tp) / risk
                if actual_rr < self.min_rr:
                    return Signal(SignalSide.FLAT,
                                  f"RR {actual_rr:.1f} < {self.min_rr}", entry)

                return Signal(
                    SignalSide.SHORT,
                    f"breakdown {nearest_s:.4f} | ATR-SL | RR {actual_rr:.1f}",
                    entry,
                    stop_loss_price=round(sl, 8),
                    take_profit_price=round(tp, 8),
                )

        return Signal(SignalSide.FLAT, "no structural breakout", entry)

    def _long_sl(self, entry: float, broken_resistance: float, current_atr: float) -> float:
        # SL just below the broken resistance (resistance → support after breakout)
        sl = broken_resistance - self.sl_atr_mult * current_atr
        if sl >= entry:
            # Level too close to entry — use ATR from entry instead
            sl = entry - 1.5 * current_atr
        return sl

    def _short_sl(self, entry: float, broken_support: float, current_atr: float) -> float:
        sl = broken_support + self.sl_atr_mult * current_atr
        if sl <= entry:
            sl = entry + 1.5 * current_atr
        return sl

    def _long_tp(self, entry: float, risk: float, resistances: list[float]) -> float:
        if len(resistances) > 1:
            return resistances[1]
        return entry + self.min_rr * risk

    def _short_tp(self, entry: float, risk: float, supports: list[float]) -> float:
        if len(supports) > 1:
            return supports[-2]
        return entry - self.min_rr * risk
