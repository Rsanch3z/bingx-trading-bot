import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import Candle


def ema(values: Sequence[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return []

    alpha = 2 / (period + 1)
    output = [float(values[0])]
    for value in values[1:]:
        output.append((float(value) * alpha) + (output[-1] * (1 - alpha)))
    return output


def sma(values: Sequence[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(math.nan)
        else:
            result.append(sum(float(v) for v in values[i - period + 1 : i + 1]) / period)
    return result


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = ema(macd_line, signal_period)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Average True Range — measures volatility; used for dynamic SL sizing."""
    if not highs or len(highs) < 2:
        return [0.0] * len(highs)
    trs = [float(highs[0]) - float(lows[0])]
    for i in range(1, len(highs)):
        trs.append(max(
            float(highs[i]) - float(lows[i]),
            abs(float(highs[i]) - float(closes[i - 1])),
            abs(float(lows[i]) - float(closes[i - 1])),
        ))
    return ema(trs, period)


def rsi(values: Sequence[float], period: int = 14) -> list[float]:
    """
    Relative Strength Index using Wilder smoothing.
    Returns NaN for the first `period` values (warmup).
    Range 0–100: >70 = overbought, <30 = oversold.
    """
    result = [math.nan] * len(values)
    if len(values) < period + 1:
        return result

    changes = [float(values[i]) - float(values[i - 1]) for i in range(1, len(values))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _to_rsi(ag: float, al: float) -> float:
        return 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)

    result[period] = _to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        result[i] = _to_rsi(avg_gain, avg_loss)

    return result


def bollinger_bands(
    values: Sequence[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    """Returns (upper, middle, lower) bands."""
    middle = sma(values, period)
    upper: list[float] = []
    lower: list[float] = []
    for i in range(len(values)):
        if i < period - 1:
            upper.append(math.nan)
            lower.append(math.nan)
        else:
            window = [float(v) for v in values[i - period + 1 : i + 1]]
            mean = sum(window) / period
            std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
            upper.append(middle[i] + num_std * std)
            lower.append(middle[i] - num_std * std)
    return upper, middle, lower


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Average Directional Index. Values 0-100; >25 = trending, <20 = ranging."""
    n = len(closes)
    if n < 2:
        return [math.nan] * n

    tr: list[float] = [float(highs[0]) - float(lows[0])]
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for i in range(1, n):
        up_move   = float(highs[i]) - float(highs[i - 1])
        down_move = float(lows[i - 1]) - float(lows[i])
        tr.append(max(
            float(highs[i]) - float(lows[i]),
            abs(float(highs[i]) - float(closes[i - 1])),
            abs(float(lows[i]) - float(closes[i - 1])),
        ))
        plus_dm.append(up_move   if up_move   > down_move and up_move   > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move   and down_move > 0 else 0.0)

    def _smooth(vals: list[float]) -> list[float]:
        out = [math.nan] * n
        if n < period:
            return out
        out[period - 1] = sum(vals[:period])
        for i in range(period, n):
            out[i] = out[i - 1] - out[i - 1] / period + vals[i]
        return out

    atr_s = _smooth(tr)
    pdm_s = _smooth(plus_dm)
    mdm_s = _smooth(minus_dm)

    dx = [math.nan] * n
    for i in range(period - 1, n):
        if math.isnan(atr_s[i]) or atr_s[i] == 0:
            continue
        pdi = 100 * pdm_s[i] / atr_s[i]
        mdi = 100 * mdm_s[i] / atr_s[i]
        di_sum = pdi + mdi
        if di_sum > 0:
            dx[i] = 100 * abs(pdi - mdi) / di_sum

    adx_vals = [math.nan] * n
    adx_start = 2 * period - 2
    if adx_start >= n:
        return adx_vals
    dx_window = [dx[j] for j in range(period - 1, 2 * period - 1) if not math.isnan(dx[j])]
    if len(dx_window) < period:
        return adx_vals
    adx_vals[adx_start] = sum(dx_window) / period
    for i in range(adx_start + 1, n):
        if not math.isnan(dx[i]) and not math.isnan(adx_vals[i - 1]):
            adx_vals[i] = (adx_vals[i - 1] * (period - 1) + dx[i]) / period
    return adx_vals
