"""
Backtesting engine with realistic cost modelling.

Fee model (BingX perpetual futures):
  - Taker fee:  0.05% per side (open + close = 0.10% round trip)
  - Maker fee:  0.02% per side (limit orders, not used in bot)
  - Funding:    charged every 8 hours on full notional (longs pay, typically ~0.01%/8h)

Position sizing:
  - Risk per trade is fixed at risk_per_trade_pct of current equity
  - Position notional = risk / SL_distance_pct  (this is the leveraged notional)
  - Actual margin used = notional / leverage
  - Liquidation price checked: SL must be placed before liquidation

Exit modes (mutually exclusive preference: two_stage_exit > trailing_stop):
  - trailing_stop:    1R trail — once price moves +1R, trail SL 1R behind peak
  - two_stage_exit:   50% exit at +2R → move SL to breakeven → Chandelier trail remaining 50%
  - time_exit_bars:   force-close after N candles regardless of SL/TP
  - vol_risk_adjust:  halve position size when ATR% > 1.5× rolling 50-bar mean
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.indicators import atr as _atr_fn
from src.models import Candle, Signal, SignalSide

WARMUP_CANDLES = 100
_CHANDELIER_MULT = 2.5


@dataclass
class Trade:
    entry_time: int
    exit_time: int
    side: str
    entry_price: float
    tp_price: float
    sl_price: float
    exit_price: float
    pnl_equity_pct: float
    fee_equity_pct: float
    funding_equity_pct: float
    reason: str       # "tp" | "sl" | "time" | "end"
    rr_planned: float


@dataclass
class CostSummary:
    total_fee_pct: float
    total_funding_pct: float
    total_cost_pct: float
    avg_fee_per_trade_pct: float
    avg_funding_per_trade_pct: float


@dataclass
class BacktestResult:
    strategy_name: str
    timeframe: str
    leverage: int
    trades: list[Trade]
    equity_curve: list[tuple[int, float]]
    metrics: dict[str, float]
    costs: CostSummary


def _timeframe_to_ms(tf: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    try:
        return int(tf[:-1]) * units[tf[-1]]
    except (ValueError, KeyError):
        return 3_600_000


def run_backtest(
    candles: list[Candle],
    strategy,
    timeframe: str = "4h",
    initial_equity: float = 10_000.0,
    risk_per_trade_pct: float = 0.01,
    leverage: int = 10,
    fee_rate: float = 0.0005,
    funding_rate_per_8h: float = 0.0001,
    side_bias: str | None = None,
    trailing_stop: bool = False,
    two_stage_exit: bool = False,
    time_exit_bars: int = 0,
    vol_risk_adjust: bool = False,
) -> BacktestResult:
    """
    Simulate strategy on historical candles with full cost modelling.

    Parameters
    ----------
    leverage            Used for liquidation price check and display.
    fee_rate            Taker fee per side (BingX default: 0.0005 = 0.05%).
    funding_rate_per_8h Funding rate per 8h period (default 0.0001 = 0.01%).
    trailing_stop       Classic 1R trail: once +1R, trail SL 1R below peak.
    two_stage_exit      50% exit at +2R, breakeven SL, Chandelier trail rest.
    time_exit_bars      Force-close after this many candles (0 = disabled).
    vol_risk_adjust     Cut risk to 0.5% when current ATR% > 1.5× 50-bar mean.
    """
    equity = initial_equity
    equity_curve: list[tuple[int, float]] = [(candles[0].timestamp_ms, equity)]
    trades: list[Trade] = []

    # Pre-compute ATR series (used for Chandelier and vol-risk-adjust)
    _h = [c.high  for c in candles]
    _l = [c.low   for c in candles]
    _c = [c.close for c in candles]
    _atr_series = _atr_fn(_h, _l, _c, 14)

    _atr_pct: list[float] = [
        _atr_series[i] / _c[i] if _c[i] > 0 else 0.0 for i in range(len(_c))
    ]
    _vol_period = 50
    _atr_pct_mean: list[float] = [math.nan] * len(_c)
    for idx in range(_vol_period - 1, len(_c)):
        window = _atr_pct[idx - _vol_period + 1 : idx + 1]
        _atr_pct_mean[idx] = sum(window) / len(window)

    in_position  = False
    active_signal = None
    entry_time:   int   = 0
    current_sl:   float = 0.0
    peak_price:   float = 0.0
    stage1_done:  bool  = False
    stage1_price: float = 0.0
    bars_in_trade: int  = 0
    active_risk:  float = risk_per_trade_pct

    for i in range(WARMUP_CANDLES, len(candles)):
        if in_position and active_signal is not None:
            candle = candles[i]
            sig    = active_signal
            bars_in_trade += 1

            if sig.side == SignalSide.LONG:
                peak_price = max(peak_price, candle.high)
            else:
                peak_price = min(peak_price, candle.low)

            # ── Two-stage exit: partial at +2R → Chandelier trail ────────────
            if two_stage_exit:
                risk_price = abs(sig.entry_price - sig.stop_loss_price)
                if not stage1_done and risk_price > 0:
                    if sig.side == SignalSide.LONG:
                        s1_target = sig.entry_price + 2.0 * risk_price
                        if candle.high >= s1_target:
                            stage1_done  = True
                            stage1_price = s1_target
                            current_sl   = sig.entry_price  # move to breakeven
                    else:
                        s1_target = sig.entry_price - 2.0 * risk_price
                        if candle.low <= s1_target:
                            stage1_done  = True
                            stage1_price = s1_target
                            current_sl   = sig.entry_price  # move to breakeven

                if stage1_done:
                    c_atr = _atr_series[i]
                    if not math.isnan(c_atr) and c_atr > 0:
                        if sig.side == SignalSide.LONG:
                            current_sl = max(current_sl, peak_price - _CHANDELIER_MULT * c_atr)
                        else:
                            current_sl = min(current_sl, peak_price + _CHANDELIER_MULT * c_atr)

            # ── Classic 1R trailing stop ─────────────────────────────────────
            if trailing_stop:
                risk = abs(sig.entry_price - sig.stop_loss_price)
                if risk > 0:
                    if sig.side == SignalSide.LONG:
                        r_moved = (peak_price - sig.entry_price) / risk
                        if r_moved >= 1.0:
                            current_sl = max(current_sl, sig.entry_price + (r_moved - 1.0) * risk)
                    else:
                        r_moved = (sig.entry_price - peak_price) / risk
                        if r_moved >= 1.0:
                            current_sl = min(current_sl, sig.entry_price - (r_moved - 1.0) * risk)

            # ── Exit conditions ──────────────────────────────────────────────
            if sig.side == SignalSide.LONG:
                sl_hit = candle.low  <= current_sl
                tp_hit = candle.high >= sig.take_profit_price
            else:
                sl_hit = candle.high >= current_sl
                tp_hit = candle.low  <= sig.take_profit_price

            if sl_hit and tp_hit:
                tp_hit = False  # conservative: assume SL first

            time_exit = time_exit_bars > 0 and bars_in_trade >= time_exit_bars

            if sl_hit or tp_hit or time_exit:
                if time_exit and not sl_hit and not tp_hit:
                    exit_price = candle.close
                    reason = "time"
                elif sl_hit:
                    exit_price = current_sl
                    reason = "sl"
                else:
                    exit_price = sig.take_profit_price
                    reason = "tp"
                exit_time = candle.timestamp_ms

                eff_exit = (
                    0.5 * stage1_price + 0.5 * exit_price
                    if (two_stage_exit and stage1_done)
                    else exit_price
                )

                sl_dist = abs(sig.entry_price - sig.stop_loss_price) / sig.entry_price
                position_size = min(
                    active_risk / sl_dist if sl_dist > 0 else 0.0,
                    float(leverage),
                )

                if sig.side == SignalSide.LONG:
                    move = (eff_exit - sig.entry_price) / sig.entry_price
                else:
                    move = (sig.entry_price - eff_exit) / sig.entry_price
                gross_pnl = position_size * move

                fee_cost = 2 * fee_rate * position_size
                hold_ms  = exit_time - entry_time
                funding_cost = (hold_ms / (8 * 3_600_000)) * funding_rate_per_8h * position_size
                if sig.side == SignalSide.SHORT:
                    funding_cost = -funding_cost

                net_pnl = gross_pnl - fee_cost - funding_cost
                equity *= 1 + net_pnl

                if sig.side == SignalSide.LONG:
                    rr = (sig.take_profit_price - sig.entry_price) / (sig.entry_price - sig.stop_loss_price)
                else:
                    rr = (sig.entry_price - sig.take_profit_price) / (sig.stop_loss_price - sig.entry_price)

                trades.append(Trade(
                    entry_time=entry_time, exit_time=exit_time,
                    side=sig.side.value, entry_price=sig.entry_price,
                    tp_price=sig.take_profit_price, sl_price=sig.stop_loss_price,
                    exit_price=eff_exit, pnl_equity_pct=net_pnl,
                    fee_equity_pct=fee_cost, funding_equity_pct=funding_cost,
                    reason=reason, rr_planned=round(rr, 2),
                ))
                equity_curve.append((exit_time, equity))
                in_position  = False
                active_signal = None

        if not in_position:
            sig = strategy.generate_signal(candles[:i + 1])
            if side_bias == "long" and sig.side == SignalSide.SHORT:
                sig = Signal(SignalSide.FLAT, "bias:long-only", sig.entry_price)
            elif side_bias == "short" and sig.side == SignalSide.LONG:
                sig = Signal(SignalSide.FLAT, "bias:short-only", sig.entry_price)

            if (
                sig.side != SignalSide.FLAT
                and sig.stop_loss_price is not None
                and sig.take_profit_price is not None
            ):
                sl_dist_pct = abs(sig.entry_price - sig.stop_loss_price) / sig.entry_price
                if sl_dist_pct > 0:
                    eff_lev = min(risk_per_trade_pct / sl_dist_pct, leverage)
                    liq_dist_pct = 1.0 / eff_lev if eff_lev > 0 else 1.0
                    if sl_dist_pct < liq_dist_pct:
                        active_risk = risk_per_trade_pct
                        if vol_risk_adjust:
                            am = _atr_pct_mean[i]
                            if not math.isnan(am) and am > 0 and _atr_pct[i] > 1.5 * am:
                                active_risk = risk_per_trade_pct * 0.5

                        in_position   = True
                        active_signal = sig
                        entry_time    = candles[i].timestamp_ms
                        current_sl    = sig.stop_loss_price
                        peak_price    = sig.entry_price
                        stage1_done   = False
                        stage1_price  = 0.0
                        bars_in_trade = 0

    # Close any open position at end of data
    if in_position and active_signal is not None:
        exit_price = candles[-1].close
        exit_time  = candles[-1].timestamp_ms
        sig        = active_signal
        eff_exit   = (
            0.5 * stage1_price + 0.5 * exit_price
            if (two_stage_exit and stage1_done)
            else exit_price
        )
        sl_dist = abs(sig.entry_price - sig.stop_loss_price) / sig.entry_price
        position_size = min(active_risk / sl_dist if sl_dist > 0 else 0.0, float(leverage))
        if sig.side == SignalSide.LONG:
            move = (eff_exit - sig.entry_price) / sig.entry_price
        else:
            move = (sig.entry_price - eff_exit) / sig.entry_price
        gross_pnl    = position_size * move
        fee_cost     = 2 * fee_rate * position_size
        hold_8h      = (exit_time - entry_time) / (8 * 3_600_000)
        funding_cost = hold_8h * funding_rate_per_8h * position_size
        if sig.side == SignalSide.SHORT:
            funding_cost = -funding_cost
        net_pnl = gross_pnl - fee_cost - funding_cost
        equity *= 1 + net_pnl
        trades.append(Trade(
            entry_time=entry_time, exit_time=exit_time,
            side=sig.side.value, entry_price=sig.entry_price,
            tp_price=sig.take_profit_price, sl_price=sig.stop_loss_price,
            exit_price=eff_exit, pnl_equity_pct=net_pnl,
            fee_equity_pct=fee_cost, funding_equity_pct=funding_cost,
            reason="end", rr_planned=0.0,
        ))
        equity_curve.append((exit_time, equity))

    metrics = _compute_metrics(trades, initial_equity, equity, equity_curve)
    costs   = _compute_costs(trades)
    return BacktestResult(
        strategy_name=strategy.name, timeframe=timeframe, leverage=leverage,
        trades=trades, equity_curve=equity_curve, metrics=metrics, costs=costs,
    )


def _compute_metrics(
    trades: list[Trade],
    initial_equity: float,
    final_equity: float,
    equity_curve: list[tuple[int, float]],
) -> dict[str, float]:
    if not trades:
        return {
            "num_trades": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_return_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0,
            "avg_rr_planned": 0.0, "expectancy_pct": 0.0,
        }

    wins        = [t for t in trades if t.pnl_equity_pct > 0]
    losses      = [t for t in trades if t.pnl_equity_pct <= 0]
    gross_profit = sum(t.pnl_equity_pct for t in wins)
    gross_loss   = abs(sum(t.pnl_equity_pct for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else math.inf
    win_rate      = len(wins) / len(trades)
    total_return  = (final_equity - initial_equity) / initial_equity * 100
    avg_rr        = sum(t.rr_planned for t in trades) / len(trades)

    avg_win  = (gross_profit / len(wins))   if wins   else 0.0
    avg_loss = (gross_loss   / len(losses)) if losses else 0.0
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    peak   = initial_equity
    max_dd = 0.0
    for _, eq in equity_curve:
        peak  = max(peak, eq)
        dd    = (peak - eq) / peak * 100
        max_dd = max(max_dd, dd)

    pnls     = [t.pnl_equity_pct for t in trades]
    mean_pnl = sum(pnls) / len(pnls)
    sharpe   = 0.0
    if len(pnls) > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std_pnl  = math.sqrt(variance) if variance > 0 else 0.0
        sharpe   = (mean_pnl / std_pnl * math.sqrt(252)) if std_pnl > 0 else 0.0

    return {
        "num_trades":       float(len(trades)),
        "win_rate":         win_rate,
        "profit_factor":    profit_factor,
        "total_return_pct": total_return,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio":     sharpe,
        "avg_rr_planned":   avg_rr,
        "expectancy_pct":   expectancy * 100,
    }


def _compute_costs(trades: list[Trade]) -> CostSummary:
    if not trades:
        return CostSummary(0, 0, 0, 0, 0)
    total_fee     = sum(t.fee_equity_pct for t in trades)
    total_funding = sum(abs(t.funding_equity_pct) for t in trades)
    n = len(trades)
    return CostSummary(
        total_fee_pct=total_fee * 100,
        total_funding_pct=total_funding * 100,
        total_cost_pct=(total_fee + total_funding) * 100,
        avg_fee_per_trade_pct=total_fee / n * 100,
        avg_funding_per_trade_pct=total_funding / n * 100,
    )
