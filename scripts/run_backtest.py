"""
Multi-strategy, multi-symbol, multi-timeframe backtest report generator.

Usage:
    cd bingx-trading-bot
    backtest_venv/bin/python -m scripts.run_backtest

Output: reports/strategy_comparison.html

No API key needed — uses BingX public market data.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import math as _math
import time as _time

import ccxt  # noqa: E402

from src.backtest import BacktestResult, run_backtest  # noqa: E402
from src.models import Candle  # noqa: E402
from src.strategies import (  # noqa: E402
    AdaptiveStrategy, BBSqueezeStrategy, BollingerStrategy,
    EMAPullbackStrategy, EmaCrossStrategy, MacdStrategy, SRBreakoutStrategy,
)

# ---------------------------------------------------------------------------
# Config — edit these to change the backtest parameters
# ---------------------------------------------------------------------------

SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
]

# Short-term timeframes supported: 5m, 15m, 1h, 4h
# Use more candles for shorter timeframes to cover enough history
TIMEFRAME_CONFIGS = [
    {"timeframe": "15m", "candles": 4320, "label": "15-min scalp (~45 days)"},
    {"timeframe": "1h",  "candles": 2000, "label": "1-hour swing (~83 days)"},
    {"timeframe": "4h",  "candles": 720,  "label": "4-hour position (~120 days)"},
]

# Run report for this timeframe (change to compare different ones)
ACTIVE_TF = TIMEFRAME_CONFIGS[1]  # 1h swing
TIMEFRAME = ACTIVE_TF["timeframe"]
CANDLE_LIMIT = ACTIVE_TF["candles"]

# Set to a Unix ms timestamp to fetch a historical period instead of "most recent".
# None = fetch the most recent CANDLE_LIMIT candles (bear market, Apr-May 2025).
# Bull market example: 1730419200000 = 2024-11-01 00:00 UTC (BTC 67k→100k, 45 days).
SINCE_MS: int | None = None  # None = most recent 45 days; set to ms timestamp for historical

INITIAL_EQUITY   = 10_000.0
RISK_PER_TRADE   = 0.01      # 1% of equity risked per trade
LEVERAGE         = 20        # Used for liquidation guard + display
FEE_RATE         = 0.0005    # BingX taker: 0.05% per side
FUNDING_RATE_8H  = 0.0001    # BingX perpetual funding: ~0.01% per 8h (typical)

STRATEGIES = [
    EmaCrossStrategy(fast=9, slow=21, trend=50, rsi_period=14,
                     sl_atr_mult=1.5, rr=3.0),
    MacdStrategy(fast=12, slow=26, signal=9, trend=50, rsi_period=14,
                 sl_atr_mult=1.5, rr=3.0),
    BollingerStrategy(period=20, num_std=2.0, rsi_period=14,
                      sl_atr_mult=1.5, min_rr=1.8),
    SRBreakoutStrategy(pivot_window=5, sr_lookback=80, min_rr=2.0,
                       sl_atr_mult=1.0, breakout_pct=0.002),
    EMAPullbackStrategy(fast_period=21, trend_period=50, adx_min=22.0,
                        sl_atr_mult=1.5, rr=3.0),
    BBSqueezeStrategy(bb_period=20, squeeze_lookback=30, rr=3.0,
                      sl_atr_mult=1.5),
]

COLORS = ["#2980b9", "#e67e22", "#27ae60", "#8e44ad", "#16a085", "#d35400"]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

_TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
_API_MAX = 1440  # BingX hard limit per request


def fetch_candles(symbol: str, timeframe: str, limit: int,
                  since_ms: int | None = None) -> list[Candle]:
    """Fetch `limit` candles.  since_ms=None → most recent from BingX;
    since_ms set → fetch historical from Binance spot (same price, no auth needed)."""
    if since_ms is not None:
        # Binance spot symbol: "BTC/USDT:USDT" → "BTC/USDT"
        spot_sym = symbol.split(":")[0]
        exchange = ccxt.binance()
    else:
        spot_sym = symbol
        exchange = ccxt.bingx({"options": {"defaultType": "swap"}})
    tf_ms = _TF_MS.get(timeframe, 900_000)

    if since_ms is None and limit <= _API_MAX:
        raw = exchange.fetch_ohlcv(spot_sym, timeframe=timeframe, limit=limit)
        rows = raw
    else:
        pages = _math.ceil(limit / _API_MAX)
        if since_ms is not None:
            start_ms = since_ms
        else:
            now_ms = int(_time.time() * 1000)
            start_ms = now_ms - limit * tf_ms
        rows: list = []
        since = start_ms
        for _ in range(pages):
            chunk = exchange.fetch_ohlcv(spot_sym, timeframe=timeframe,
                                         since=since, limit=_API_MAX)
            if not chunk:
                break
            rows.extend(chunk)
            since = chunk[-1][0] + 1
            if len(rows) >= limit:
                break

        seen: set[int] = set()
        unique: list = []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                unique.append(r)
        unique.sort(key=lambda x: x[0])
        rows = unique[:limit] if since_ms is not None else unique[-limit:]

    return [
        Candle(
            timestamp_ms=int(r[0]), open=float(r[1]), high=float(r[2]),
            low=float(r[3]), close=float(r[4]), volume=float(r[5]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _pf(v: float) -> str:
    return "inf" if v == float("inf") else f"{v:.2f}"


def _style(v: float) -> str:
    color = "#27ae60" if v >= 0 else "#c0392b"
    return f'style="color:{color};font-weight:600"'


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def generate_html(
    results_by_symbol: dict[str, list[BacktestResult]],
    strategies: list,
    candles_by_symbol: dict[str, list[Candle]],
    timeframe: str,
) -> str:
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
        from plotly.subplots import make_subplots
        HAS_PLOTLY = True
    except ImportError:
        HAS_PLOTLY = False

    symbols = list(results_by_symbol.keys())
    strat_names = [s.name for s in strategies]
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    first_c = next(iter(candles_by_symbol.values()))
    period_start, period_end = _ts(first_c[0].timestamp_ms), _ts(first_c[-1].timestamp_ms)

    # Aggregate metrics across symbols per strategy
    agg = []
    for s_idx in range(len(strategies)):
        keys = ["num_trades","win_rate","profit_factor","total_return_pct",
                "max_drawdown_pct","sharpe_ratio","avg_rr_planned","expectancy_pct"]
        totals = {k: 0.0 for k in keys}
        fee_total = fund_total = 0.0
        n = len(symbols)
        for sym in symbols:
            m = results_by_symbol[sym][s_idx].metrics
            c = results_by_symbol[sym][s_idx].costs
            for k in keys:
                val = m.get(k, 0)
                totals[k] += min(val, 999) if val == float("inf") else val
            fee_total += c.total_fee_pct
            fund_total += c.total_funding_pct
        a = {k: v / n for k, v in totals.items()}
        a["name"] = strat_names[s_idx]
        a["avg_total_fee_pct"] = fee_total / n
        a["avg_funding_pct"] = fund_total / n
        a["avg_total_cost_pct"] = (fee_total + fund_total) / n
        agg.append(a)

    # Charts
    equity_chart = metrics_chart = heatmap = cost_chart = ""
    plotly_cdn = ""
    if HAS_PLOTLY:
        plotly_cdn = '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'

        # 1. Equity curves (BTC representative)
        btc_key = "BTC/USDT:USDT"
        fig1 = go.Figure()
        for s_idx, (name, color) in enumerate(zip(strat_names, COLORS)):
            result = results_by_symbol[btc_key][s_idx]
            times = [_ts(t) for t, _ in result.equity_curve]
            eqs = [eq for _, eq in result.equity_curve]
            fig1.add_trace(go.Scatter(x=times, y=eqs, mode="lines",
                                      name=name, line=dict(color=color, width=2)))
        fig1.update_layout(
            title=f"Equity Curve — BTC {timeframe} (1% risk/trade, {LEVERAGE}x leverage)",
            xaxis_title="Time (UTC)", yaxis_title="Equity (USDT)",
            template="plotly_white", height=400,
            legend=dict(orientation="h", y=1.02),
        )
        equity_chart = pio.to_html(fig1, full_html=False, include_plotlyjs=False)

        # 2. Metrics bar chart
        fig2 = make_subplots(1, 3, subplot_titles=["Win Rate (%)", "Avg Return (%)", "Max Drawdown (%)"])
        for s_idx, (a, color) in enumerate(zip(agg, COLORS)):
            kw = dict(name=a["name"], marker_color=color, showlegend=(s_idx == 0))
            fig2.add_trace(go.Bar(x=[a["name"]], y=[round(a["win_rate"]*100,1)], **kw), 1, 1)
            fig2.add_trace(go.Bar(x=[a["name"]], y=[round(a["total_return_pct"],2)], **kw), 1, 2)
            fig2.add_trace(go.Bar(x=[a["name"]], y=[round(a["max_drawdown_pct"],2)], **kw), 1, 3)
        fig2.update_layout(title="Strategy Metrics (avg across all symbols)",
                           template="plotly_white", height=380, showlegend=True)
        metrics_chart = pio.to_html(fig2, full_html=False, include_plotlyjs=False)

        # 3. Return heatmap
        z = []
        for s_idx in range(len(strategies)):
            z.append([round(results_by_symbol[sym][s_idx].metrics["total_return_pct"], 2)
                      for sym in symbols])
        short_syms = [s.split("/")[0] for s in symbols]
        fig3 = go.Figure(go.Heatmap(
            z=z, x=short_syms, y=strat_names, colorscale="RdYlGn", zmid=0,
            text=[[f"{v:+.1f}%" for v in row] for row in z],
            texttemplate="%{text}", textfont=dict(size=13),
        ))
        fig3.update_layout(title="Return (%) by Symbol", template="plotly_white", height=280)
        heatmap = pio.to_html(fig3, full_html=False, include_plotlyjs=False)

        # 4. Fee + funding cost comparison
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(
            name="Fees (open+close)", x=strat_names,
            y=[round(a["avg_total_fee_pct"], 3) for a in agg],
            marker_color="#e74c3c",
        ))
        fig4.add_trace(go.Bar(
            name="Funding rate", x=strat_names,
            y=[round(a["avg_funding_pct"], 4) for a in agg],
            marker_color="#f39c12",
        ))
        fig4.update_layout(
            title=f"Avg Total Cost per Symbol (fee={FEE_RATE*100:.2f}%/side, funding={FUNDING_RATE_8H*100:.3f}%/8h)",
            yaxis_title="% of equity", barmode="stack", template="plotly_white", height=340,
        )
        cost_chart = pio.to_html(fig4, full_html=False, include_plotlyjs=False)

    # Summary table
    agg_rows = ""
    for a in agg:
        ret = a["total_return_pct"]
        agg_rows += f"""
        <tr>
          <td><strong>{a['name']}</strong></td>
          <td>{int(a['num_trades'])}</td>
          <td>{a['win_rate']:.1%}</td>
          <td>{a['avg_rr_planned']:.1f}</td>
          <td>{_pf(a['profit_factor'])}</td>
          <td {_style(ret)}>{ret:+.2f}%</td>
          <td>{a['max_drawdown_pct']:.2f}%</td>
          <td>{a['sharpe_ratio']:.2f}</td>
          <td {_style(a['expectancy_pct'])}>{a['expectancy_pct']:+.3f}%</td>
          <td style="color:#c0392b">{a['avg_total_cost_pct']:.3f}%</td>
        </tr>"""

    # Cost breakdown table
    cost_header = f"""
    <table>
      <thead><tr>
        <th>Strategy</th>
        <th>Trades (avg)</th>
        <th>Taker Fee/trade</th>
        <th>Total Fees</th>
        <th>Funding/trade</th>
        <th>Total Funding</th>
        <th>Total Cost</th>
        <th>Return (gross)</th>
        <th>Return (net)</th>
      </tr></thead>
      <tbody>"""
    cost_rows = ""
    for s_idx, a in enumerate(agg):
        gross = a["total_return_pct"] + a["avg_total_cost_pct"]
        net = a["total_return_pct"]
        avg_fee_trade = a["avg_total_fee_pct"] / max(a["num_trades"], 1)
        avg_fund_trade = a["avg_funding_pct"] / max(a["num_trades"], 1)
        cost_rows += f"""
        <tr>
          <td><strong>{a['name']}</strong></td>
          <td>{int(a['num_trades'])}</td>
          <td>{avg_fee_trade:.4f}%</td>
          <td style="color:#c0392b">{a['avg_total_fee_pct']:.3f}%</td>
          <td>{avg_fund_trade:.5f}%</td>
          <td style="color:#e67e22">{a['avg_funding_pct']:.4f}%</td>
          <td style="color:#c0392b;font-weight:600">{a['avg_total_cost_pct']:.3f}%</td>
          <td {_style(gross)}>{gross:+.2f}%</td>
          <td {_style(net)}>{net:+.2f}%</td>
        </tr>"""

    # Per-symbol breakdown
    per_sym_html = ""
    for sym in symbols:
        short = sym.split("/")[0]
        rows = ""
        for s_idx, strat in enumerate(strategies):
            m = results_by_symbol[sym][s_idx].metrics
            c = results_by_symbol[sym][s_idx].costs
            ret = m["total_return_pct"]
            rows += f"""
            <tr>
              <td>{strat.name}</td>
              <td>{int(m['num_trades'])}</td>
              <td>{m['win_rate']:.1%}</td>
              <td>{m['avg_rr_planned']:.1f}</td>
              <td {_style(ret)}>{ret:+.2f}%</td>
              <td>{m['max_drawdown_pct']:.2f}%</td>
              <td style="color:#c0392b">{c.total_cost_pct:.3f}%</td>
            </tr>"""
        per_sym_html += f"""
        <details>
          <summary><strong>{short}</strong></summary>
          <table>
            <thead><tr><th>Strategy</th><th>Trades</th><th>Win Rate</th>
            <th>Avg RR</th><th>Return</th><th>Max DD</th><th>Total Cost</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </details>"""

    # Trade log
    trade_log_html = ""
    for s_idx, strat in enumerate(strategies):
        all_rows = ""
        total = 0
        for sym in symbols:
            short = sym.split("/")[0]
            for t in results_by_symbol[sym][s_idx].trades:
                total += 1
                pnl_color = "#27ae60" if t.pnl_equity_pct > 0 else "#c0392b"
                reason_label = {"tp": "TP hit", "sl": "SL hit", "end": "End"}.get(t.reason, t.reason)
                hold_h = (t.exit_time - t.entry_time) / 3_600_000
                all_rows += f"""
                <tr>
                  <td>{short}</td>
                  <td>{_ts(t.entry_time)}</td>
                  <td>{"Long" if t.side=="long" else "Short"}</td>
                  <td>{t.entry_price:.4f}</td>
                  <td>{t.sl_price:.4f}</td>
                  <td>{t.tp_price:.4f}</td>
                  <td>{t.rr_planned:.1f}</td>
                  <td>{t.exit_price:.4f}</td>
                  <td style="color:{pnl_color}">{t.pnl_equity_pct*100:+.3f}%</td>
                  <td style="color:#c0392b">{t.fee_equity_pct*100:.4f}%</td>
                  <td style="color:#e67e22">{t.funding_equity_pct*100:.5f}%</td>
                  <td>{hold_h:.1f}h</td>
                  <td>{reason_label}</td>
                </tr>"""
        trade_log_html += f"""
        <details>
          <summary><strong>{strat.name}</strong> — {total} total trades</summary>
          <table>
            <thead><tr>
              <th>Symbol</th><th>Entry Time</th><th>Side</th>
              <th>Entry</th><th>SL</th><th>TP</th><th>RR</th>
              <th>Exit</th><th>Net PnL</th><th>Fee</th><th>Funding</th>
              <th>Hold</th><th>Exit Reason</th>
            </tr></thead>
            <tbody>{all_rows}</tbody>
          </table>
        </details>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Trading Strategy Backtest — {timeframe}</title>
  {plotly_cdn}
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:"Segoe UI",Arial,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:24px;font-size:13.5px}}
    h1{{font-size:1.6rem;font-weight:700;margin-bottom:4px}}
    h2{{font-size:1.05rem;font-weight:600;color:#2c3e50;border-left:4px solid #2980b9;
        padding-left:10px;margin:24px 0 10px}}
    .meta{{color:#555;font-size:0.82rem;margin:5px 0}}
    .card{{background:#fff;border-radius:8px;padding:18px;margin-bottom:18px;
           box-shadow:0 1px 5px rgba(0,0,0,.08)}}
    table{{border-collapse:collapse;width:100%;font-size:.82rem}}
    th{{background:#2c3e50;color:#fff;padding:8px 12px;text-align:left;font-weight:500}}
    td{{padding:6px 12px;border-bottom:1px solid #eee}}
    tr:hover td{{background:#f8f9fc}}
    details{{border:1px solid #ddd;border-radius:6px;margin:6px 0;overflow:hidden}}
    details summary{{padding:9px 14px;cursor:pointer;background:#f8f9fc;font-size:.88rem}}
    details summary:hover{{background:#edf0f7}}
    .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
    .chart{{overflow-x:auto}}
    .note{{font-size:.78rem;color:#888;margin-top:8px;line-height:1.5}}
    .highlight{{background:#fffde7;border-left:3px solid #f39c12;padding:10px 14px;
                border-radius:4px;font-size:.85rem;margin:10px 0}}
    @media(max-width:800px){{.grid2{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>

<div class="card">
  <h1>Trading Strategy Backtest Report</h1>
  <p class="meta">Timeframe: <strong>{timeframe}</strong> &nbsp;|&nbsp;
    Symbols: <strong>{", ".join(s.split("/")[0] for s in symbols)}</strong> &nbsp;|&nbsp;
    Period: <strong>{period_start}</strong> to <strong>{period_end}</strong></p>
  <p class="meta">Initial equity: <strong>{INITIAL_EQUITY:,.0f} USDT</strong> &nbsp;|&nbsp;
    Risk/trade: <strong>{RISK_PER_TRADE*100:.0f}%</strong> &nbsp;|&nbsp;
    Leverage: <strong>{LEVERAGE}x</strong> &nbsp;|&nbsp;
    Taker fee: <strong>{FEE_RATE*100:.2f}%/side</strong> &nbsp;|&nbsp;
    Funding: <strong>{FUNDING_RATE_8H*100:.3f}%/8h</strong></p>
  <p class="meta">Generated: {generated}</p>
  <div class="highlight">
    Fee structure: each trade costs <strong>{FEE_RATE*2*100:.2f}% of notional</strong> in taker fees
    (open + close). At {RISK_PER_TRADE*100:.0f}% risk with 1% SL distance, position notional =
    {RISK_PER_TRADE/0.01:.0f}x equity → fee per trade ≈
    <strong>{FEE_RATE*2*(RISK_PER_TRADE/0.01)*100:.2f}% of equity</strong>.
    Funding adds ~{FUNDING_RATE_8H*100:.3f}% per 8h on full notional if position is held overnight.
  </div>
</div>

<div class="card">
  <h2>Aggregate Performance (avg across {len(symbols)} symbols)</h2>
  <table>
    <thead><tr>
      <th>Strategy</th><th>Avg Trades</th><th>Win Rate</th><th>Avg RR</th>
      <th>Profit Factor</th><th>Avg Return</th><th>Max Drawdown</th>
      <th>Sharpe</th><th>Expectancy/trade</th><th>Total Cost</th>
    </tr></thead>
    <tbody>{agg_rows}</tbody>
  </table>
  <p class="note">Expectancy = avg PnL per trade as % of equity. Positive expectancy = edge.
    All returns are net of fees and funding.</p>
</div>

<div class="card">
  <h2>Fee & Funding Cost Breakdown</h2>
  {cost_header}{cost_rows}</tbody></table>
  <p class="note">Gross return = what you would earn with zero fees.
    Difference shows exactly how much fees/funding erode each strategy.</p>
</div>

<div class="card chart">
  <h2>Equity Curves (BTC representative)</h2>
  {equity_chart or "<p>pip install plotly for charts</p>"}
</div>

<div class="grid2">
  <div class="card chart">
    <h2>Strategy Metrics</h2>
    {metrics_chart or ""}
  </div>
  <div class="card chart">
    <h2>Return Heatmap</h2>
    {heatmap or ""}
  </div>
</div>

<div class="card chart">
  <h2>Cost Comparison</h2>
  {cost_chart or ""}
</div>

<div class="card">
  <h2>Per-Symbol Breakdown (click to expand)</h2>
  {per_sym_html}
</div>

<div class="card">
  <h2>Full Trade Log (click to expand)</h2>
  {trade_log_html}
</div>

<div class="card">
  <h2>Strategy Logic Reference</h2>
  <table>
    <thead><tr><th>Strategy</th><th>Long Entry</th><th>Short Entry</th>
    <th>Stop Loss</th><th>Take Profit</th><th>Edge</th></tr></thead>
    <tbody>
      <tr><td>EMA(9,21)+Trend</td>
        <td>EMA9 crosses above EMA21 <b>AND</b> price &gt; EMA50 <b>AND</b> RSI 40–65</td>
        <td>EMA9 crosses below EMA21 <b>AND</b> price &lt; EMA50 <b>AND</b> RSI 35–60</td>
        <td>1.5 × ATR below entry</td><td>3× risk (3:1 R:R)</td>
        <td>Trend filter removes counter-trend losers</td></tr>
      <tr><td>MACD(12,26,9)+RSI</td>
        <td>MACD line crosses above signal <b>AND</b> price &gt; EMA50 <b>AND</b> RSI &lt; 65</td>
        <td>MACD line crosses below signal <b>AND</b> price &lt; EMA50 <b>AND</b> RSI &gt; 35</td>
        <td>1.5 × ATR below entry</td><td>3× risk (3:1 R:R)</td>
        <td>Slow confirmation + trend + RSI guards</td></tr>
      <tr><td>BB(20,2.0)+RSI</td>
        <td>Close crosses below lower band <b>AND</b> RSI &lt; 35</td>
        <td>Close crosses above upper band <b>AND</b> RSI &gt; 65</td>
        <td>1.5 × ATR below entry</td><td>Opposite band (1.8:1 R:R min)</td>
        <td>Both price extreme AND momentum confirm oversold/overbought</td></tr>
      <tr><td>SR+MACD (15m)</td>
        <td>Break above resistance + MACD histogram &gt; 0</td>
        <td>Break below support + MACD histogram &lt; 0</td>
        <td>1.0 × ATR below broken level</td>
        <td>Next S/R level or 2R synthetic</td>
        <td>Tuned for 15m: 3-bar pivots, 40-bar lookback</td></tr>
    </tbody>
  </table>
  <p class="note">SR+MACD places stop loss based on market structure (below the broken resistance level)
    rather than a fixed percentage. This adapts to each coin's volatility via ATR.
    Minimum R:R of 2.0 required before a trade is taken — low-quality setups are skipped.</p>
</div>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

BULL_SINCE_MS = 1730419200000  # 2024-11-01 00:00 UTC


def _run_period(label: str, since_ms: int | None, side_bias: str | None,
                two_stage_exit: bool = False, time_exit_bars: int = 0,
                vol_risk_adjust: bool = False,
                candle_limit: int = CANDLE_LIMIT) -> None:
    bias_label = f" [{side_bias}-only]" if side_bias else " [both sides]"
    opt_parts = []
    if two_stage_exit:
        opt_parts.append("2-stage")
    if time_exit_bars:
        opt_parts.append(f"time-exit={time_exit_bars}b")
    if vol_risk_adjust:
        opt_parts.append("vol-adj")
    opt_label = (" +" + ",".join(opt_parts)) if opt_parts else ""
    print(f"\n{'='*60}")
    print(f"  {label}{bias_label}{opt_label}")
    print(f"{'='*60}")

    candles_by_symbol: dict[str, list[Candle]] = {}
    for sym in SYMBOLS:
        print(f"Fetching {sym}...", end=" ", flush=True)
        candles_by_symbol[sym] = fetch_candles(sym, TIMEFRAME, candle_limit, since_ms=since_ms)
        print(f"({len(candles_by_symbol[sym])} candles)")

    print()
    results_by_symbol: dict[str, list[BacktestResult]] = {}
    for sym, candles in candles_by_symbol.items():
        results_by_symbol[sym] = []
        for strat in STRATEGIES:
            result = run_backtest(
                candles, strat,
                timeframe=TIMEFRAME,
                initial_equity=INITIAL_EQUITY,
                risk_per_trade_pct=RISK_PER_TRADE,
                leverage=LEVERAGE,
                fee_rate=FEE_RATE,
                funding_rate_per_8h=FUNDING_RATE_8H,
                side_bias=side_bias,
                trailing_stop=False,
                two_stage_exit=two_stage_exit,
                time_exit_bars=time_exit_bars,
                vol_risk_adjust=vol_risk_adjust,
            )
            m = result.metrics
            c = result.costs
            print(
                f"  {sym.split('/')[0]:>4}  {strat.name:<28} "
                f"trades={int(m['num_trades']):>3}  "
                f"win={m['win_rate']:.0%}  "
                f"rr={m['avg_rr_planned']:.1f}  "
                f"return={m['total_return_pct']:>+7.2f}%  "
                f"cost={c.total_cost_pct:.3f}%  "
                f"dd={m['max_drawdown_pct']:.1f}%"
            )
            results_by_symbol[sym].append(result)
        print()

    html = generate_html(results_by_symbol, STRATEGIES, candles_by_symbol, TIMEFRAME)
    os.makedirs("reports", exist_ok=True)
    period_tag = "full" if (since_ms is not None and candle_limit > 3000) else (
                 "bull" if since_ms is not None else "bear")
    bias_tag   = f"_{side_bias}only" if side_bias else ""
    opt_tag    = "_2stage" if two_stage_exit else ""
    output = f"reports/strategy_comparison_{TIMEFRAME}_{period_tag}{bias_tag}{opt_tag}.html"
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved: {output}")


FULL_CYCLE_CANDLES = 5040   # ~7 months of 1H bars  (Nov 2024 → late May 2025)


def main() -> None:
    kw = dict(two_stage_exit=True, time_exit_bars=24, vol_risk_adjust=True)
    print(f"Backtest: {len(SYMBOLS)} symbols | {TIMEFRAME} | {FULL_CYCLE_CANDLES} candles (~7 months) | "
          f"leverage={LEVERAGE}x | fee={FEE_RATE*100:.2f}%/side | "
          f"exit=2-stage+Chandelier | time-exit=24h | vol-risk-adj=ON")

    # Full bull→bear cycle: Nov 2024 → late May 2025
    _run_period("FULL CYCLE  Nov 2024→May 2025  [unfiltered]",
                since_ms=BULL_SINCE_MS, side_bias=None,
                candle_limit=FULL_CYCLE_CANDLES, **kw)
    _run_period("FULL CYCLE  Nov 2024→May 2025  [long-only]",
                since_ms=BULL_SINCE_MS, side_bias="long",
                candle_limit=FULL_CYCLE_CANDLES, **kw)
    _run_period("FULL CYCLE  Nov 2024→May 2025  [short-only]",
                since_ms=BULL_SINCE_MS, side_bias="short",
                candle_limit=FULL_CYCLE_CANDLES, **kw)


if __name__ == "__main__":
    main()
