"""
Backtesting Framework — Phase 8.

Architecture:
  BacktestFramework.run() drives the engine over every trading day in [start, end].
  Portfolio tracks cash, long/short positions, P&L, and daily snapshots.
  Metrics are computed from the daily history and persisted to MongoDB.

Key constraints (from PHASES.md):
  - All backtests run daily — no rebalance_freq field.
  - Data stored with is_historical=True, never auto-deleted.
  - No lookahead: DataBus.fetch(as_of_date=date) enforces the cutoff.
  - KeyboardInterrupt saves partial results and exits cleanly.
"""
from __future__ import annotations
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────── config / result

@dataclass
class BacktestConfig:
    tickers:         list[str]
    start_date:      str            # YYYY-MM-DD
    end_date:        str            # YYYY-MM-DD
    initial_cash:    float = 100_000.0
    commission_pct:  float = 0.001  # 0.1% per side
    slippage_pct:    float = 0.001  # 0.1% market impact
    margin_req:      float = 0.50   # short margin requirement
    market:          str   = "US"
    engines:         Optional[list[str]] = None
    benchmark:       str   = "^GSPC"
    # NOTE: no rebalance_freq — all backtests run daily (v1)


@dataclass
class BacktestResult:
    run_id:          str
    config:          BacktestConfig
    metrics:         dict
    monthly_returns: list[dict]
    trades:          list[dict]
    history:         list[dict] = field(default_factory=list)  # daily {date, portfolio_value, ...}


# ─────────────────────────────────────────────────────── portfolio

class Portfolio:
    """
    Simulated portfolio with long, short, cash tracking.
    All prices are execution prices (post-slippage).
    """

    def __init__(self, initial_cash: float):
        self.cash          = initial_cash
        self.initial_cash  = initial_cash
        self.long:         dict[str, int]   = {}  # ticker → shares held
        self.short:        dict[str, int]   = {}  # ticker → shares short
        self.avg_cost:     dict[str, float] = {}  # ticker → avg cost basis (long)
        self.avg_short:    dict[str, float] = {}  # ticker → avg entry price (short)
        self.history:      list[dict]       = []  # daily snapshots
        self.trades:       list[dict]       = []  # all executed trades
        self._prices:      dict[str, float] = {}  # latest known prices

    # ── price update

    def update_prices(self, prices: dict[str, float]) -> None:
        self._prices.update(prices)

    # ── portfolio valuation

    def portfolio_value(self) -> float:
        long_val   = sum(s * self._prices.get(t, 0.0) for t, s in self.long.items())
        short_pnl  = sum(
            (self.avg_short.get(t, self._prices.get(t, 0.0)) - self._prices.get(t, 0.0)) * s
            for t, s in self.short.items()
        )
        return self.cash + long_val + short_pnl

    # ── portfolio state dict (passed to WriteEngine.run)

    def state(self) -> dict:
        result: dict = {}
        for t, s in self.long.items():
            result[t] = s
        for t, s in self.short.items():
            result[t] = result.get(t, 0) - s
        result["portfolio_value"] = self.portfolio_value()
        result["cash"] = self.cash
        return result

    # ── daily snapshot

    def snapshot(self, date_str: str) -> dict:
        return {
            "date":            date_str,
            "portfolio_value": round(self.portfolio_value(), 2),
            "cash":            round(self.cash, 2),
            "positions": {
                t: {
                    "shares": s,
                    "price":  round(self._prices.get(t, 0.0), 4),
                    "value":  round(s * self._prices.get(t, 0.0), 2),
                }
                for t, s in self.long.items() if s > 0
            },
            "short_positions": {
                t: {"shares": s, "avg_entry": round(self.avg_short.get(t, 0.0), 4)}
                for t, s in self.short.items() if s > 0
            },
        }

    # ── trade execution

    def execute(self, decision, config: BacktestConfig, date_str: str) -> None:
        """Execute one TradingDecision against the portfolio."""
        from core.engine_base import TradingDecision
        action = decision.action
        qty    = decision.quantity
        price  = decision.price
        ticker = decision.ticker

        if action == "hold" or qty <= 0 or price <= 0:
            return

        if action == "buy":
            self._execute_buy(ticker, qty, price, config, date_str)
        elif action == "sell":
            self._execute_sell(ticker, qty, price, config, date_str)
        elif action == "short":
            self._execute_short(ticker, qty, price, config, date_str)
        elif action == "cover":
            self._execute_cover(ticker, qty, price, config, date_str)

    def _execute_buy(self, ticker: str, qty: int, price: float,
                     config: BacktestConfig, date_str: str) -> None:
        eff = price * (1 + config.slippage_pct)
        total_cost = qty * eff * (1 + config.commission_pct)

        # Reduce qty if insufficient cash
        if total_cost > self.cash:
            unit_cost = eff * (1 + config.commission_pct)
            qty = int(self.cash / unit_cost)
            if qty <= 0:
                return
            total_cost = qty * unit_cost

        prev_shares = self.long.get(ticker, 0)
        prev_basis  = self.avg_cost.get(ticker, 0.0)
        new_shares  = prev_shares + qty

        self.avg_cost[ticker] = (prev_basis * prev_shares + eff * qty) / new_shares
        self.long[ticker]     = new_shares
        self.cash            -= total_cost
        self._prices[ticker]  = price

        self.trades.append({
            "date": date_str, "ticker": ticker, "action": "buy",
            "qty": qty, "price": round(eff, 4),
            "cost": round(total_cost, 2), "pnl": None,
        })

    def _execute_sell(self, ticker: str, qty: int, price: float,
                      config: BacktestConfig, date_str: str) -> None:
        held = self.long.get(ticker, 0)
        if held <= 0:
            return
        qty      = min(qty, held)
        eff      = price * (1 - config.slippage_pct)
        proceeds = qty * eff
        comm     = proceeds * config.commission_pct
        net      = proceeds - comm
        basis    = self.avg_cost.get(ticker, 0.0)
        pnl      = (eff - basis) * qty - comm

        self.cash            += net
        self.long[ticker]     = held - qty
        self._prices[ticker]  = price
        if self.long[ticker] <= 0:
            self.long.pop(ticker, None)
            self.avg_cost.pop(ticker, None)

        self.trades.append({
            "date": date_str, "ticker": ticker, "action": "sell",
            "qty": qty, "price": round(eff, 4),
            "proceeds": round(net, 2), "pnl": round(pnl, 2),
        })

    def _execute_short(self, ticker: str, qty: int, price: float,
                       config: BacktestConfig, date_str: str) -> None:
        eff    = price * (1 - config.slippage_pct)
        margin = qty * eff * config.margin_req
        comm   = qty * eff * config.commission_pct
        total  = margin + comm

        if total > self.cash:
            unit = eff * (config.margin_req + config.commission_pct)
            qty  = int(self.cash / unit)
            if qty <= 0:
                return
            margin = qty * eff * config.margin_req
            comm   = qty * eff * config.commission_pct
            total  = margin + comm

        self.cash           -= total
        self.short[ticker]   = self.short.get(ticker, 0) + qty
        self.avg_short[ticker] = eff
        self._prices[ticker] = price

        self.trades.append({
            "date": date_str, "ticker": ticker, "action": "short",
            "qty": qty, "price": round(eff, 4),
            "margin_blocked": round(margin, 2), "pnl": None,
        })

    def _execute_cover(self, ticker: str, qty: int, price: float,
                       config: BacktestConfig, date_str: str) -> None:
        held_short = self.short.get(ticker, 0)
        if held_short <= 0:
            return
        qty          = min(qty, held_short)
        eff          = price * (1 + config.slippage_pct)
        short_entry  = self.avg_short.get(ticker, eff)
        margin_ret   = qty * short_entry * config.margin_req
        pnl          = (short_entry - eff) * qty
        comm         = qty * eff * config.commission_pct
        net          = margin_ret + pnl - comm

        self.cash            += net
        self.short[ticker]    = held_short - qty
        self._prices[ticker]  = price
        if self.short[ticker] <= 0:
            self.short.pop(ticker, None)
            self.avg_short.pop(ticker, None)

        self.trades.append({
            "date": date_str, "ticker": ticker, "action": "cover",
            "qty": qty, "price": round(eff, 4),
            "pnl": round(pnl, 2),
        })


# ─────────────────────────────────────────────────────── metrics

def compute_metrics(
    history: list[dict],
    trades: list[dict],
    initial_cash: float,
    bench_prices: list[float],
    trading_days_per_year: int = 252,
) -> dict:
    """Pure function — no I/O. Compute all performance metrics."""
    if not history:
        return {}

    values = [h["portfolio_value"] for h in history]
    n      = len(values)

    total_return = (values[-1] - initial_cash) / initial_cash if initial_cash > 0 else 0.0
    ann_return   = (values[-1] / initial_cash) ** (trading_days_per_year / n) - 1.0 \
                   if n > 0 and initial_cash > 0 else 0.0

    daily_rets = [values[i] / values[i - 1] - 1.0 for i in range(1, n)]

    ann_vol = sharpe = sortino = 0.0
    if len(daily_rets) >= 2:
        ann_vol  = float(np.std(daily_rets, ddof=1)) * math.sqrt(trading_days_per_year)
        rf_ann   = 0.053
        sharpe   = (ann_return - rf_ann) / ann_vol if ann_vol > 0 else 0.0
        downside = [r for r in daily_rets if r < 0]
        if downside and len(downside) >= 2:
            ds_vol  = float(np.std(downside, ddof=1)) * math.sqrt(trading_days_per_year)
            sortino = (ann_return - rf_ann) / ds_vol if ds_vol > 0 else 0.0
        else:
            sortino = float("inf") if ann_return > rf_ann else 0.0

    # Max drawdown
    peak   = values[0]
    max_dd = 0.0
    for v in values:
        peak   = max(peak, v)
        dd     = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    calmar = ann_return / max_dd if max_dd > 0 else None

    # Benchmark alpha
    alpha = 0.0
    if len(bench_prices) >= 2:
        bench_total = bench_prices[-1] / bench_prices[0] - 1.0
        bench_ann   = (1.0 + bench_total) ** (trading_days_per_year / len(bench_prices)) - 1.0
        alpha       = ann_return - bench_ann

    # Trade statistics
    completed   = [t for t in trades if t.get("pnl") is not None]
    wins        = [t for t in completed if t["pnl"] > 0]
    losses      = [t for t in completed if t["pnl"] <= 0]
    total_win   = sum(t["pnl"] for t in wins)
    total_loss  = abs(sum(t["pnl"] for t in losses))

    return {
        "total_return":      round(total_return, 6),
        "annualized_return": round(ann_return, 6),
        "annualized_vol":    round(ann_vol, 6),
        "alpha":             round(alpha, 6),
        "max_drawdown":      round(max_dd, 6),
        "sharpe_ratio":      round(sharpe, 4),
        "sortino_ratio":     round(sortino, 4) if not math.isinf(sortino) else None,
        "calmar_ratio":      round(calmar, 4) if calmar is not None else None,
        "win_rate":          round(len(wins) / len(completed), 6) if completed else 0.0,
        "avg_win":           round(total_win / len(wins), 2) if wins else 0.0,
        "avg_loss":          round(total_loss / len(losses), 2) if losses else 0.0,
        "profit_factor":     round(total_win / total_loss, 4) if total_loss > 0 else None,
        "total_trades":      len(completed),
        "total_wins":        len(wins),
        "total_losses":      len(losses),
        "final_value":       round(values[-1], 2),
        "initial_cash":      initial_cash,
        "n_trading_days":    n,
    }


def monthly_returns(history: list[dict]) -> list[dict]:
    """Aggregate daily history into monthly return rows."""
    if not history:
        return []
    grouped: dict[str, list[float]] = {}
    for snap in history:
        ym = snap["date"][:7]
        grouped.setdefault(ym, []).append(snap["portfolio_value"])

    result  = []
    prev_v  = None
    for ym in sorted(grouped):
        vals = grouped[ym]
        if prev_v is None:
            prev_v = vals[0]
        end_v  = vals[-1]
        ret    = (end_v - prev_v) / prev_v if prev_v > 0 else 0.0
        result.append({"month": ym, "return": round(ret, 6), "end_value": round(end_v, 2)})
        prev_v = end_v
    return result


# ─────────────────────────────────────────────────────── framework

class BacktestFramework:
    """
    Runs the full WriteEngine stack over every trading day in [start, end].
    Pre-warms the data cache before the loop for efficiency.
    Handles KeyboardInterrupt gracefully — partial results are saved.
    """

    def __init__(self, write_engine, store, config: BacktestConfig):
        self.write_engine = write_engine
        self.store        = store
        self.config       = config

    def run(self) -> BacktestResult:
        cfg = self.config

        logger.info(
            "Backtest %s → %s | %s | cash=$%.0f",
            cfg.start_date, cfg.end_date, cfg.tickers, cfg.initial_cash,
        )

        # 1. Trading calendar (benchmark dates — correct for holidays)
        dates = self._trading_calendar()
        if not dates:
            raise ValueError(
                f"No trading days found between {cfg.start_date} and {cfg.end_date}"
            )
        logger.info("Trading calendar: %d days", len(dates))

        # 2. Benchmark prices for alpha computation
        bench_prices = self._fetch_benchmark()

        # 3. Pre-warm data cache for entire date range (avoids per-day live fetches)
        logger.info("Pre-warming data cache for %s ...", cfg.tickers)
        self.write_engine.fetch_only(cfg.tickers, cfg.end_date)

        # 4. Portfolio + run state
        portfolio = Portfolio(cfg.initial_cash)
        run_id    = None

        try:
            for i, date_str in enumerate(dates):
                port_val = portfolio.portfolio_value()
                print(
                    f"\rDay {i+1}/{len(dates)} | {date_str} | "
                    f"portfolio: ${port_val:,.0f}  ",
                    end="", flush=True,
                )

                port_state = portfolio.state()
                result = self.write_engine.run(
                    tickers=cfg.tickers,
                    engines=cfg.engines,
                    as_of_date=date_str,
                    portfolio=port_state,
                )
                if run_id is None:
                    run_id = result.run_id

                # Update portfolio prices from decisions
                prices_today: dict[str, float] = {
                    ticker: dec.price
                    for ticker, dec in result.decisions.items()
                    if dec.price > 0
                }
                portfolio.update_prices(prices_today)

                # Execute decisions
                for ticker, decision in result.decisions.items():
                    portfolio.execute(decision, cfg, date_str)

                # Daily snapshot + persist
                snap = portfolio.snapshot(date_str)
                portfolio.history.append(snap)
                day_trades = [t for t in portfolio.trades if t["date"] == date_str]
                self.store.save_backtest_snapshot(
                    run_id=run_id,
                    date=date_str,
                    portfolio_value=snap["portfolio_value"],
                    cash=snap["cash"],
                    positions=snap["positions"],
                    trades=day_trades,
                )

        except KeyboardInterrupt:
            print("\n\n[interrupted] Computing partial metrics...")
            logger.warning("Backtest interrupted after %d/%d days", i + 1, len(dates))

        else:
            print()  # newline after progress bar

        # 5. Compute and persist metrics
        trading_days_yr = 252 if cfg.market == "US" else 250
        metrics = compute_metrics(
            history=portfolio.history,
            trades=portfolio.trades,
            initial_cash=cfg.initial_cash,
            bench_prices=bench_prices,
            trading_days_per_year=trading_days_yr,
        )
        m_returns = monthly_returns(portfolio.history)

        config_dict = {
            "tickers":        cfg.tickers,
            "start_date":     cfg.start_date,
            "end_date":       cfg.end_date,
            "initial_cash":   cfg.initial_cash,
            "commission_pct": cfg.commission_pct,
            "slippage_pct":   cfg.slippage_pct,
            "market":         cfg.market,
            "engines":        cfg.engines,
            "benchmark":      cfg.benchmark,
        }
        self.store.save_backtest_metrics(run_id or "backtest", config_dict, {
            **metrics,
            "monthly_returns": m_returns,
        })

        logger.info(
            "Backtest complete: ret=%.1f%% sharpe=%.2f max_dd=%.1f%% trades=%d",
            metrics.get("total_return", 0) * 100,
            metrics.get("sharpe_ratio", 0),
            metrics.get("max_drawdown", 0) * 100,
            metrics.get("total_trades", 0),
        )

        return BacktestResult(
            run_id=run_id or "backtest",
            config=cfg,
            metrics=metrics,
            monthly_returns=m_returns,
            trades=portfolio.trades,
            history=portfolio.history,
        )

    # ── helpers

    def _trading_calendar(self) -> list[str]:
        """Use benchmark index prices as the trading calendar (auto-handles holidays)."""
        import yfinance as yf
        cfg = self.config
        benchmark = cfg.benchmark if cfg.market == "US" else "^NSEI"
        try:
            end_dt = date.fromisoformat(cfg.end_date) + timedelta(days=1)
            hist = yf.Ticker(benchmark).history(
                start=cfg.start_date,
                end=str(end_dt),
                auto_adjust=False,
                actions=False,
            )
            if hist is None or hist.empty:
                return self._weekday_calendar()
            return sorted(
                str(dt.date())
                for dt in hist.index
                if cfg.start_date <= str(dt.date()) <= cfg.end_date
            )
        except Exception as e:
            logger.warning("Trading calendar fetch failed (%s) — falling back to weekdays", e)
            return self._weekday_calendar()

    def _weekday_calendar(self) -> list[str]:
        """Fallback calendar: Mon–Fri only (no holiday exclusion)."""
        cfg    = self.config
        dates  = []
        d      = date.fromisoformat(cfg.start_date)
        end    = date.fromisoformat(cfg.end_date)
        while d <= end:
            if d.weekday() < 5:
                dates.append(str(d))
            d += timedelta(days=1)
        return dates

    def _fetch_benchmark(self) -> list[float]:
        """Fetch benchmark closing prices for the backtest period (for alpha)."""
        import yfinance as yf
        cfg = self.config
        try:
            end_dt = date.fromisoformat(cfg.end_date) + timedelta(days=1)
            hist   = yf.Ticker(cfg.benchmark).history(
                start=cfg.start_date,
                end=str(end_dt),
                auto_adjust=True,
                actions=False,
            )
            if hist is None or hist.empty:
                return []
            return [
                float(hist.loc[dt, "Close"])
                for dt in hist.index
                if cfg.start_date <= str(dt.date()) <= cfg.end_date
            ]
        except Exception as e:
            logger.warning("Benchmark fetch failed: %s", e)
            return []
