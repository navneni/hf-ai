"""
Unit tests for Phase 8 backtesting:
  - Portfolio trade execution (buy, sell, short, cover)
  - P&L correctness with commissions and slippage
  - Performance metric computation (return, Sharpe, max drawdown, etc.)
  - Monthly return aggregation
"""
from __future__ import annotations
import math
import pytest
from dataclasses import dataclass

from core.backtest import (
    Portfolio,
    BacktestConfig,
    compute_metrics,
    monthly_returns,
)


# ─────────────────────────────────────── helpers

@dataclass
class _FakeDecision:
    ticker: str
    action: str
    quantity: int
    price: float
    confidence: float = 70.0
    reasoning: str = ""
    signals: dict = None
    net_score: float = 0.0
    macro_regime: str = "neutral"
    narrative: str = None

    def __post_init__(self):
        if self.signals is None:
            self.signals = {}


def _config(commission: float = 0.001, slippage: float = 0.001,
            margin: float = 0.50) -> BacktestConfig:
    return BacktestConfig(
        tickers=["AAPL"],
        start_date="2024-01-01",
        end_date="2024-12-31",
        initial_cash=100_000.0,
        commission_pct=commission,
        slippage_pct=slippage,
        margin_req=margin,
    )


def _portfolio(cash: float = 100_000.0) -> Portfolio:
    return Portfolio(cash)


def _decide(action: str, qty: int, price: float, ticker: str = "AAPL") -> _FakeDecision:
    return _FakeDecision(ticker=ticker, action=action, quantity=qty, price=price)


# ─────────────────────────────────────── Portfolio.execute — BUY

class TestBuy:

    def test_buy_reduces_cash(self):
        p = _portfolio(10_000)
        p.execute(_decide("buy", 10, 100.0), _config(), "2024-01-02")
        # cost ≈ 10 × 100 × 1.001_slippage × 1.001_commission ≈ 1002.00
        assert p.cash < 10_000

    def test_buy_adds_shares(self):
        p = _portfolio(10_000)
        p.execute(_decide("buy", 10, 100.0), _config(), "2024-01-02")
        assert p.long.get("AAPL", 0) == 10

    def test_buy_no_commission_no_slippage(self):
        p = _portfolio(10_000)
        p.execute(_decide("buy", 10, 100.0), _config(commission=0.0, slippage=0.0), "2024-01-02")
        assert p.cash == pytest.approx(9_000.0)
        assert p.long["AAPL"] == 10

    def test_buy_records_trade(self):
        p = _portfolio(10_000)
        p.execute(_decide("buy", 5, 100.0), _config(), "2024-01-02")
        assert len(p.trades) == 1
        assert p.trades[0]["action"] == "buy"
        assert p.trades[0]["pnl"] is None

    def test_buy_avg_cost_updated(self):
        p = _portfolio(50_000)
        p.execute(_decide("buy", 10, 100.0), _config(commission=0.0, slippage=0.0), "2024-01-02")
        p.execute(_decide("buy", 10, 200.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        assert p.avg_cost["AAPL"] == pytest.approx(150.0)

    def test_buy_reduces_qty_if_insufficient_cash(self):
        p = _portfolio(500)  # only $500
        p.execute(_decide("buy", 100, 100.0), _config(commission=0.0, slippage=0.0), "2024-01-02")
        # can only afford 5 shares at $100
        assert p.long.get("AAPL", 0) == 5

    def test_buy_skipped_if_zero_cash(self):
        p = _portfolio(0)
        p.execute(_decide("buy", 10, 100.0), _config(), "2024-01-02")
        assert not p.trades

    def test_hold_does_nothing(self):
        p = _portfolio(10_000)
        p.execute(_decide("hold", 10, 100.0), _config(), "2024-01-02")
        assert not p.trades
        assert p.cash == pytest.approx(10_000.0)


# ─────────────────────────────────────── Portfolio.execute — SELL

class TestSell:

    def _buy_first(self, qty: int = 10, price: float = 100.0) -> Portfolio:
        p = _portfolio(10_000)
        p.execute(_decide("buy", qty, price), _config(commission=0.0, slippage=0.0), "2024-01-02")
        return p

    def test_sell_restores_cash(self):
        p = self._buy_first(10, 100.0)
        pre_cash = p.cash
        p._prices["AAPL"] = 100.0
        p.execute(_decide("sell", 10, 120.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        # Sold 10 @ 120 → proceeds 1200
        assert p.cash == pytest.approx(pre_cash + 1_200.0)

    def test_sell_removes_shares(self):
        p = self._buy_first(10, 100.0)
        p.execute(_decide("sell", 10, 120.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        assert p.long.get("AAPL", 0) == 0

    def test_sell_records_pnl(self):
        p = self._buy_first(10, 100.0)   # basis = 100
        p.execute(_decide("sell", 10, 150.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        trade = p.trades[-1]
        assert trade["pnl"] == pytest.approx(500.0)  # (150-100) × 10

    def test_sell_loss_pnl(self):
        p = self._buy_first(10, 100.0)
        p.execute(_decide("sell", 10, 80.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        trade = p.trades[-1]
        assert trade["pnl"] == pytest.approx(-200.0)  # (80-100) × 10

    def test_sell_capped_at_held_shares(self):
        p = self._buy_first(5, 100.0)
        p.execute(_decide("sell", 100, 120.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        assert p.long.get("AAPL", 0) == 0
        assert p.trades[-1]["qty"] == 5

    def test_sell_skipped_if_no_position(self):
        p = _portfolio(10_000)
        p.execute(_decide("sell", 10, 100.0), _config(), "2024-01-02")
        assert not p.trades

    def test_partial_sell(self):
        p = self._buy_first(10, 100.0)
        p.execute(_decide("sell", 5, 120.0), _config(commission=0.0, slippage=0.0), "2024-01-03")
        assert p.long["AAPL"] == 5


# ─────────────────────────────────────── Portfolio.execute — SHORT / COVER

class TestShortCover:

    def test_short_blocks_margin(self):
        p = _portfolio(10_000)
        p.execute(_decide("short", 10, 100.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-02")
        # margin = 10 × 100 × 0.5 = $500
        assert p.cash == pytest.approx(9_500.0)
        assert p.short.get("AAPL", 0) == 10

    def test_cover_profitable(self):
        p = _portfolio(10_000)
        p.execute(_decide("short", 10, 100.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-02")
        # Price drops to 80 → profitable cover
        p.execute(_decide("cover", 10, 80.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-03")
        trade = p.trades[-1]
        assert trade["pnl"] == pytest.approx(200.0)  # (100-80) × 10
        assert p.short.get("AAPL", 0) == 0

    def test_cover_unprofitable(self):
        p = _portfolio(10_000)
        p.execute(_decide("short", 10, 100.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-02")
        p.execute(_decide("cover", 10, 120.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-03")
        trade = p.trades[-1]
        assert trade["pnl"] == pytest.approx(-200.0)  # (100-120) × 10

    def test_cover_returns_margin(self):
        p = _portfolio(10_000)
        p.execute(_decide("short", 10, 100.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-02")
        cash_after_short = p.cash
        p.execute(_decide("cover", 10, 100.0), _config(commission=0.0, slippage=0.0, margin=0.5), "2024-01-03")
        # Cover at same price → PnL=0, margin returned → cash back to original
        assert p.cash == pytest.approx(10_000.0)


# ─────────────────────────────────────── portfolio_value

class TestPortfolioValue:

    def test_cash_only(self):
        p = _portfolio(50_000)
        assert p.portfolio_value() == pytest.approx(50_000.0)

    def test_long_position_mark_to_market(self):
        p = _portfolio(90_000)
        p.long["AAPL"] = 10
        p._prices["AAPL"] = 150.0
        assert p.portfolio_value() == pytest.approx(91_500.0)

    def test_short_position_unrealized_gain(self):
        p = _portfolio(9_500)
        p.short["AAPL"] = 10
        p.avg_short["AAPL"] = 100.0
        p._prices["AAPL"] = 80.0   # price fell → gain
        assert p.portfolio_value() == pytest.approx(9_700.0)  # 9500 + (100-80)*10

    def test_short_position_unrealized_loss(self):
        p = _portfolio(9_500)
        p.short["AAPL"] = 10
        p.avg_short["AAPL"] = 100.0
        p._prices["AAPL"] = 120.0   # price rose → loss
        assert p.portfolio_value() == pytest.approx(9_300.0)  # 9500 + (100-120)*10


# ─────────────────────────────────────── compute_metrics

def _history(values: list[float], start: str = "2024-01-02") -> list[dict]:
    from datetime import date, timedelta
    d = date.fromisoformat(start)
    out = []
    for v in values:
        out.append({"date": str(d), "portfolio_value": v})
        d += timedelta(days=1)
    return out


class TestComputeMetrics:

    def test_total_return(self):
        hist = _history([100_000, 110_000])
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["total_return"] == pytest.approx(0.10)

    def test_total_return_loss(self):
        hist = _history([100_000, 90_000])
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["total_return"] == pytest.approx(-0.10)

    def test_max_drawdown_zero_on_monotone_gain(self):
        hist = _history([100_000, 110_000, 120_000, 130_000])
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["max_drawdown"] == pytest.approx(0.0)

    def test_max_drawdown_correct(self):
        # 100k → 120k → 90k → 110k — drawdown from peak 120k to trough 90k = 25%
        hist = _history([100_000, 120_000, 90_000, 110_000])
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["max_drawdown"] == pytest.approx(0.25)

    def test_sharpe_positive_for_good_returns(self):
        # Daily return of 0.05% → ~12.7% annualized, well above 5.3% risk-free rate
        values = [100_000 * (1.0005 ** i) for i in range(252)]
        hist = _history(values)
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["sharpe_ratio"] > 0

    def test_win_rate(self):
        trades = [
            {"pnl": 100.0},
            {"pnl": 200.0},
            {"pnl": -50.0},
            {"pnl": None},  # open trade — excluded
        ]
        m = compute_metrics(_history([100_000, 100_000]), trades, 100_000, [], 252)
        assert m["win_rate"] == pytest.approx(2 / 3)
        assert m["total_trades"] == 3

    def test_profit_factor(self):
        trades = [{"pnl": 300.0}, {"pnl": 200.0}, {"pnl": -100.0}]
        m = compute_metrics(_history([100_000, 100_000]), trades, 100_000, [], 252)
        assert m["profit_factor"] == pytest.approx(5.0)  # 500 / 100

    def test_alpha_positive_when_outperforms(self):
        # Portfolio doubles, benchmark flat
        hist = _history([100_000, 200_000])
        bench = [100.0, 100.0]  # flat benchmark
        m = compute_metrics(hist, [], 100_000, bench, 252)
        assert m["alpha"] > 0

    def test_empty_history_returns_empty(self):
        m = compute_metrics([], [], 100_000, [], 252)
        assert m == {}

    def test_final_value_matches_last_snapshot(self):
        hist = _history([100_000, 105_000, 103_000])
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["final_value"] == pytest.approx(103_000.0)

    def test_calmar_none_when_no_drawdown(self):
        hist = _history([100_000, 120_000])
        m = compute_metrics(hist, [], 100_000, [], 252)
        # max_drawdown = 0 → calmar = None (avoid division by zero)
        assert m["calmar_ratio"] is None

    def test_n_trading_days(self):
        hist = _history([100_000] * 50)
        m = compute_metrics(hist, [], 100_000, [], 252)
        assert m["n_trading_days"] == 50


# ─────────────────────────────────────── monthly_returns

class TestMonthlyReturns:

    def test_single_month(self):
        hist = [
            {"date": "2024-01-02", "portfolio_value": 100_000},
            {"date": "2024-01-31", "portfolio_value": 105_000},
        ]
        rows = monthly_returns(hist)
        assert len(rows) == 1
        assert rows[0]["month"] == "2024-01"
        assert rows[0]["return"] == pytest.approx(0.05)

    def test_two_months(self):
        hist = [
            {"date": "2024-01-02", "portfolio_value": 100_000},
            {"date": "2024-01-31", "portfolio_value": 110_000},
            {"date": "2024-02-01", "portfolio_value": 110_000},
            {"date": "2024-02-29", "portfolio_value": 99_000},
        ]
        rows = monthly_returns(hist)
        assert len(rows) == 2
        assert rows[0]["return"] == pytest.approx(0.10)
        assert rows[1]["return"] == pytest.approx(-0.10, rel=1e-3)

    def test_negative_month(self):
        hist = [
            {"date": "2024-03-01", "portfolio_value": 100_000},
            {"date": "2024-03-31", "portfolio_value": 90_000},
        ]
        rows = monthly_returns(hist)
        assert rows[0]["return"] == pytest.approx(-0.10)

    def test_empty_history(self):
        assert monthly_returns([]) == []
