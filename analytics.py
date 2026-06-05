"""
Portfolio Analytics — Phase 10.
Pure functions: no MongoDB writes, no side effects. Input → output only.
Displayed via --show-analytics after a backtest run.

Functions:
  sector_exposure(tickers)              — concentration by GICS sector
  correlation_matrix(prices_dict)       — 60-day pairwise correlation
  factor_attribution(prices_dict, ...)  — OLS: beta, value, momentum, quality
  drawdown_series(history)              — daily drawdown from peak + recovery
  monthly_returns_heatmap(monthly_returns) — {YYYY: {MM: return}} grid
"""
from __future__ import annotations
import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────── sector exposure

def sector_exposure(
    tickers: list[str],
    weights: Optional[dict[str, float]] = None,
) -> dict:
    """
    Compute portfolio sector concentration using yfinance sector tags.
    weights: {ticker: position_value} — defaults to equal-weight.
    Returns:
      {
        "sectors":          {sector_name: pct},
        "concentrated":     [sector_names where pct > 40%],
        "unknown":          [tickers without sector data],
      }
    """
    import yfinance as yf

    ticker_sectors: dict[str, str] = {}
    unknown: list[str] = []

    for ticker in tickers:
        try:
            info   = yf.Ticker(ticker).info
            sector = info.get("sector") or info.get("sectorKey")
            if sector:
                ticker_sectors[ticker] = sector
            else:
                unknown.append(ticker)
        except Exception:
            unknown.append(ticker)

    if not ticker_sectors:
        return {"sectors": {}, "concentrated": [], "unknown": unknown}

    total_weight = sum((weights or {}).get(t, 1.0) for t in ticker_sectors)
    if total_weight <= 0:
        total_weight = len(ticker_sectors)

    sector_totals: dict[str, float] = {}
    for ticker, sector in ticker_sectors.items():
        w = (weights or {}).get(ticker, 1.0)
        sector_totals[sector] = sector_totals.get(sector, 0.0) + w

    sectors = {s: round(v / total_weight, 4) for s, v in sector_totals.items()}
    concentrated = [s for s, pct in sectors.items() if pct > 0.40]

    return {
        "sectors":      sectors,
        "concentrated": concentrated,
        "unknown":      unknown,
    }


# ─────────────────────────────────────────────── correlation matrix

def correlation_matrix(
    prices_dict: dict[str, list[dict]],
    lookback: int = 60,
) -> dict:
    """
    Compute pairwise 60-day return correlation.
    prices_dict: {ticker: [{"date": ..., "close": float}, ...]}
    Returns:
      {
        "matrix":   {tickerA: {tickerB: corr}},
        "high_pairs": [(tickerA, tickerB, corr)] where abs(corr) > 0.80,
      }
    """
    tickers = list(prices_dict.keys())
    if len(tickers) < 2:
        return {"matrix": {}, "high_pairs": []}

    returns_map: dict[str, list[float]] = {}
    for ticker, prices in prices_dict.items():
        closes = [float(p["close"]) for p in sorted(prices, key=lambda x: x["date"])]
        if len(closes) < 2:
            continue
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
        returns_map[ticker] = rets[-lookback:] if len(rets) > lookback else rets

    valid = [t for t in tickers if t in returns_map and len(returns_map[t]) >= 2]
    if len(valid) < 2:
        return {"matrix": {}, "high_pairs": []}

    min_len = min(len(returns_map[t]) for t in valid)
    matrix  = np.array([returns_map[t][-min_len:] for t in valid])

    try:
        corr = np.corrcoef(matrix)
    except Exception as e:
        logger.debug("Correlation computation failed: %s", e)
        return {"matrix": {}, "high_pairs": []}

    result_matrix: dict[str, dict[str, float]] = {}
    high_pairs: list[tuple[str, str, float]] = []

    for i, t1 in enumerate(valid):
        result_matrix[t1] = {}
        for j, t2 in enumerate(valid):
            if i == j:
                continue
            c = round(float(corr[i, j]), 4)
            result_matrix[t1][t2] = c
            if i < j and abs(c) > 0.80:
                high_pairs.append((t1, t2, c))

    return {"matrix": result_matrix, "high_pairs": high_pairs}


# ─────────────────────────────────────────────── factor attribution

def factor_attribution(
    prices_dict: dict[str, list[dict]],
    ratios_dict: Optional[dict[str, dict]] = None,
    benchmark_prices: Optional[list[dict]] = None,
) -> dict:
    """
    OLS factor attribution for the portfolio (equal-weighted across tickers).

    Factors:
      beta            — regression of portfolio vs benchmark (60d)
      value_tilt      — average P/B ratio rank (0=cheapest … 1=most expensive)
      momentum        — 6-month portfolio return vs 6-month benchmark return
      quality         — average ROE rank (0=worst … 1=best)

    Returns dict with each factor + annualized alpha.
    """
    if not prices_dict:
        return {}

    # Equal-weighted portfolio daily returns
    all_returns: list[list[float]] = []
    for ticker, prices in prices_dict.items():
        closes = [float(p["close"]) for p in sorted(prices, key=lambda x: x["date"])]
        if len(closes) < 2:
            continue
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
        all_returns.append(rets)

    if not all_returns:
        return {}

    min_len  = min(len(r) for r in all_returns)
    lb_rets  = min(min_len, 60)
    port_rets = [
        sum(r[-lb_rets:][i] for r in all_returns) / len(all_returns)
        for i in range(lb_rets)
    ]

    # Benchmark returns
    beta = alpha_ann = 0.0
    if benchmark_prices and len(benchmark_prices) >= 2:
        bench_closes = [float(p["close"]) for p in sorted(benchmark_prices, key=lambda x: x["date"])]
        bench_rets   = [bench_closes[i] / bench_closes[i - 1] - 1.0 for i in range(1, len(bench_closes))]
        lb = min(len(port_rets), len(bench_rets), 60)
        p  = np.array(port_rets[-lb:])
        b  = np.array(bench_rets[-lb:])
        if np.var(b) > 0:
            beta = float(np.cov(p, b)[0, 1] / np.var(b))
        residuals = p - beta * b
        alpha_ann = float(np.mean(residuals) * 252)

    # Momentum: 6-month (126 trading days) portfolio return vs benchmark
    momentum_port = 0.0
    momentum_bench = 0.0
    for rets_list in all_returns:
        lb126 = min(len(rets_list), 126)
        momentum_port += math.prod(1 + r for r in rets_list[-lb126:]) - 1.0
    momentum_port /= len(all_returns)

    if benchmark_prices and len(benchmark_prices) > 2:
        bench_closes = [float(p["close"]) for p in sorted(benchmark_prices, key=lambda x: x["date"])]
        lb_b = min(len(bench_closes) - 1, 126)
        momentum_bench = bench_closes[-1] / bench_closes[-(lb_b + 1)] - 1.0

    # Value and Quality from ratios
    pb_vals: list[float] = []
    roe_vals: list[float] = []
    if ratios_dict:
        for ticker, ratios in ratios_dict.items():
            pb = ratios.get("pb_ratio")
            if pb is not None and pb > 0:
                pb_vals.append(float(pb))
            roe = ratios.get("roe")
            if roe is not None:
                roe_vals.append(float(roe))

    value_tilt = None
    quality    = None
    if pb_vals:
        sorted_pb = sorted(pb_vals)
        port_pb   = sum(pb_vals) / len(pb_vals)
        value_tilt = round(sorted_pb.index(min(sorted_pb, key=lambda x: abs(x - port_pb))) / max(1, len(pb_vals) - 1), 4)
    if roe_vals:
        sorted_roe = sorted(roe_vals)
        port_roe   = sum(roe_vals) / len(roe_vals)
        quality    = round(sorted_roe.index(min(sorted_roe, key=lambda x: abs(x - port_roe))) / max(1, len(roe_vals) - 1), 4)

    return {
        "beta":           round(beta, 4),
        "alpha_annualized": round(alpha_ann, 4),
        "momentum_portfolio":  round(momentum_port, 4),
        "momentum_benchmark":  round(momentum_bench, 4),
        "momentum_excess":     round(momentum_port - momentum_bench, 4),
        "value_tilt_pb_rank":  value_tilt,   # 0=cheapest, 1=most expensive
        "quality_roe_rank":    quality,      # 0=worst, 1=best
        "n_tickers":           len(prices_dict),
    }


# ─────────────────────────────────────────────── drawdown series

def drawdown_series(history: list[dict]) -> dict:
    """
    Compute daily drawdown from running peak.
    history: [{date, portfolio_value}, ...]
    Returns:
      {
        "series":        [{date, drawdown_pct}, ...],
        "max_drawdown":  float,
        "max_dd_date":   str,
        "recovery_days": int | None,
      }
    """
    if not history:
        return {"series": [], "max_drawdown": 0.0, "max_dd_date": None, "recovery_days": None}

    sorted_h = sorted(history, key=lambda h: h["date"])
    peak     = sorted_h[0]["portfolio_value"]
    series   = []
    max_dd   = 0.0
    max_dd_date = sorted_h[0]["date"]
    max_dd_peak = peak
    recovery_days = None

    for snap in sorted_h:
        val  = snap["portfolio_value"]
        peak = max(peak, val)
        dd   = (peak - val) / peak if peak > 0 else 0.0
        series.append({"date": snap["date"], "drawdown_pct": round(dd, 6)})
        if dd > max_dd:
            max_dd      = dd
            max_dd_date = snap["date"]
            max_dd_peak = peak

    # Estimate recovery: days from max_dd_date until portfolio recovers to peak
    in_recovery = False
    dd_end_idx  = next((i for i, s in enumerate(series) if s["date"] == max_dd_date), None)
    if dd_end_idx is not None:
        for s in series[dd_end_idx:]:
            if s["drawdown_pct"] == 0.0:
                # Recovered
                start  = series[dd_end_idx]["date"]
                end    = s["date"]
                start_d = __import__("datetime").date.fromisoformat(start)
                end_d   = __import__("datetime").date.fromisoformat(end)
                recovery_days = (end_d - start_d).days
                break

    return {
        "series":        series,
        "max_drawdown":  round(max_dd, 6),
        "max_dd_date":   max_dd_date,
        "recovery_days": recovery_days,
    }


# ─────────────────────────────────────────────── monthly returns heatmap

def monthly_returns_heatmap(monthly_returns: list[dict]) -> dict:
    """
    Reshape monthly returns into {YYYY: {MM: return}} grid for display.
    monthly_returns: [{month: "YYYY-MM", return: float}, ...]
    Also returns yearly aggregates.
    """
    grid: dict[str, dict[str, float]] = {}
    yearly: dict[str, float] = {}

    for row in monthly_returns:
        month = row.get("month", "")
        ret   = row.get("return", 0.0)
        if not month or len(month) < 7:
            continue
        year, mm = month[:4], month[5:7]
        grid.setdefault(year, {})[mm] = round(ret, 6)

    # Compound monthly returns → yearly return
    for year, months in grid.items():
        compound = math.prod(1 + v for v in months.values()) - 1.0
        yearly[year] = round(compound, 6)

    return {"grid": grid, "yearly": yearly}
