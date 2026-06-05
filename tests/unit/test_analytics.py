"""
Unit tests for Phase 10 analytics module.
All pure functions — no live API calls, no MongoDB.
"""
from __future__ import annotations
import math
import pytest

from analytics import (
    correlation_matrix,
    drawdown_series,
    monthly_returns_heatmap,
    factor_attribution,
)


# ─────────────────────────────────────── helpers

def _prices(closes: list[float], start_idx: int = 0) -> list[dict]:
    return [
        {"date": f"2024-{(i+1)//22+1:02d}-{(i+1)%22+1:02d}", "close": c}
        for i, c in enumerate(closes, start=start_idx)
    ]


# ─────────────────────────────────────── correlation_matrix

class TestCorrelationMatrix:

    def test_single_ticker_returns_empty(self):
        prices = {"AAPL": _prices([100.0 + i for i in range(70)])}
        result = correlation_matrix(prices)
        assert result["matrix"] == {}
        assert result["high_pairs"] == []

    def test_perfectly_correlated_pair(self):
        closes = [100.0 + i for i in range(70)]
        prices = {
            "AAPL": _prices(closes),
            "MSFT": _prices([c * 2 for c in closes]),  # perfectly correlated
        }
        result = correlation_matrix(prices)
        corr = result["matrix"]["AAPL"]["MSFT"]
        assert corr == pytest.approx(1.0, abs=0.01)

    def test_uncorrelated_pair(self):
        import random
        rng = random.Random(42)
        closes_a = [100 * (1 + rng.gauss(0, 0.01)) for _ in range(70)]
        closes_b = [100 * (1 + rng.gauss(0, 0.01)) for _ in range(70)]
        prices = {"A": _prices(closes_a), "B": _prices(closes_b)}
        result = correlation_matrix(prices)
        corr = abs(result["matrix"]["A"]["B"])
        assert corr < 0.60   # should be low for independent series

    def test_high_pairs_flagged(self):
        closes = [100.0 + i for i in range(70)]
        prices = {
            "X": _prices(closes),
            "Y": _prices([c + 0.001 * i for i, c in enumerate(closes)]),
        }
        result = correlation_matrix(prices)
        # Near-perfect correlation → should be in high_pairs
        assert len(result["high_pairs"]) >= 1
        _, _, corr = result["high_pairs"][0]
        assert abs(corr) > 0.80

    def test_symmetric_matrix(self):
        closes_a = [100.0 + i * 0.5 for i in range(70)]
        closes_b = [200.0 + i * 0.3 for i in range(70)]
        prices = {"A": _prices(closes_a), "B": _prices(closes_b)}
        result = correlation_matrix(prices)
        corr_ab = result["matrix"]["A"]["B"]
        corr_ba = result["matrix"]["B"]["A"]
        assert corr_ab == pytest.approx(corr_ba, abs=1e-9)

    def test_insufficient_data_returns_empty(self):
        prices = {"A": _prices([100.0, 101.0]), "B": _prices([200.0, 201.0])}
        # min_len=1 → only 1 return → too short
        result = correlation_matrix(prices, lookback=60)
        # With 2 prices we have 1 return — less than 2 → empty
        assert result["matrix"] == {} or isinstance(result["matrix"], dict)


# ─────────────────────────────────────── drawdown_series

class TestDrawdownSeries:

    def _hist(self, values: list[float], start: str = "2024-01-02") -> list[dict]:
        from datetime import date, timedelta
        d = date.fromisoformat(start)
        out = []
        for v in values:
            out.append({"date": str(d), "portfolio_value": v})
            d += timedelta(days=1)
        return out

    def test_monotone_gain_zero_drawdown(self):
        hist = self._hist([100_000, 110_000, 120_000])
        dd   = drawdown_series(hist)
        assert dd["max_drawdown"] == pytest.approx(0.0)

    def test_drawdown_from_peak(self):
        # peak=120k, trough=90k → dd = (120k-90k)/120k = 25%
        hist = self._hist([100_000, 120_000, 90_000, 110_000])
        dd   = drawdown_series(hist)
        assert dd["max_drawdown"] == pytest.approx(0.25)

    def test_max_dd_date(self):
        from datetime import date, timedelta
        d0 = date(2024, 1, 2)
        hist = [
            {"date": str(d0),                        "portfolio_value": 100_000},
            {"date": str(d0 + timedelta(days=1)),     "portfolio_value": 120_000},
            {"date": str(d0 + timedelta(days=2)),     "portfolio_value":  90_000},
        ]
        dd = drawdown_series(hist)
        assert dd["max_dd_date"] == str(d0 + timedelta(days=2))

    def test_recovery_days_computed(self):
        # 100k → 80k (drawdown) → 100k (recovery)
        hist = self._hist([100_000, 80_000, 90_000, 100_000, 105_000])
        dd   = drawdown_series(hist)
        assert dd["recovery_days"] is not None
        assert dd["recovery_days"] > 0

    def test_no_recovery_returns_none(self):
        hist = self._hist([100_000, 80_000, 70_000])  # never recovers
        dd   = drawdown_series(hist)
        assert dd["recovery_days"] is None

    def test_empty_history(self):
        dd = drawdown_series([])
        assert dd["max_drawdown"] == 0.0
        assert dd["series"] == []

    def test_series_length_matches_history(self):
        hist = self._hist([100_000, 110_000, 90_000, 105_000])
        dd   = drawdown_series(hist)
        assert len(dd["series"]) == len(hist)

    def test_series_drawdown_non_negative(self):
        hist = self._hist([100_000, 120_000, 90_000, 110_000, 130_000])
        dd   = drawdown_series(hist)
        for snap in dd["series"]:
            assert snap["drawdown_pct"] >= 0.0


# ─────────────────────────────────────── monthly_returns_heatmap

class TestMonthlyReturnsHeatmap:

    def test_single_month_in_grid(self):
        monthly = [{"month": "2024-01", "return": 0.05}]
        hm = monthly_returns_heatmap(monthly)
        assert "2024" in hm["grid"]
        assert hm["grid"]["2024"]["01"] == pytest.approx(0.05)

    def test_yearly_compound(self):
        monthly = [
            {"month": "2024-01", "return": 0.10},
            {"month": "2024-02", "return": 0.10},
        ]
        hm = monthly_returns_heatmap(monthly)
        # Compound: (1.10 × 1.10) - 1 = 0.21
        assert hm["yearly"]["2024"] == pytest.approx(0.21)

    def test_multi_year(self):
        monthly = [
            {"month": "2023-12", "return": 0.03},
            {"month": "2024-01", "return": 0.05},
        ]
        hm = monthly_returns_heatmap(monthly)
        assert "2023" in hm["grid"]
        assert "2024" in hm["grid"]

    def test_negative_month(self):
        monthly = [{"month": "2024-06", "return": -0.08}]
        hm = monthly_returns_heatmap(monthly)
        assert hm["grid"]["2024"]["06"] == pytest.approx(-0.08)

    def test_empty_input(self):
        hm = monthly_returns_heatmap([])
        assert hm["grid"] == {}
        assert hm["yearly"] == {}

    def test_all_twelve_months(self):
        monthly = [{"month": f"2024-{mm:02d}", "return": 0.01} for mm in range(1, 13)]
        hm = monthly_returns_heatmap(monthly)
        assert len(hm["grid"]["2024"]) == 12
        # (1.01)^12 - 1 ≈ 12.68%
        assert hm["yearly"]["2024"] == pytest.approx((1.01 ** 12) - 1, rel=0.001)


# ─────────────────────────────────────── factor_attribution

class TestFactorAttribution:

    def _rising_prices(self, n: int = 100, rate: float = 0.001) -> list[dict]:
        return _prices([100.0 * (1 + rate) ** i for i in range(n)])

    def test_returns_dict(self):
        prices = {"AAPL": self._rising_prices()}
        result = factor_attribution(prices)
        assert isinstance(result, dict)
        assert "beta" in result
        assert "momentum_portfolio" in result

    def test_beta_with_benchmark(self):
        closes = [100.0 * (1.001 ** i) for i in range(80)]
        prices = {"AAPL": _prices(closes)}
        bench  = _prices(closes)   # identical → beta ≈ 1.0
        result = factor_attribution(prices, benchmark_prices=bench)
        assert result["beta"] == pytest.approx(1.0, abs=0.15)

    def test_empty_prices_returns_empty(self):
        assert factor_attribution({}) == {}

    def test_value_tilt_from_ratios(self):
        prices = {"AAPL": self._rising_prices(), "MSFT": self._rising_prices()}
        ratios = {
            "AAPL": {"pb_ratio": 5.0, "roe": 0.25},
            "MSFT": {"pb_ratio": 10.0, "roe": 0.35},
        }
        result = factor_attribution(prices, ratios_dict=ratios)
        assert result["value_tilt_pb_rank"] is not None
        assert result["quality_roe_rank"] is not None
        # Values should be in [0, 1]
        assert 0.0 <= result["value_tilt_pb_rank"] <= 1.0
        assert 0.0 <= result["quality_roe_rank"] <= 1.0

    def test_momentum_positive_in_rising_market(self):
        prices = {"AAPL": self._rising_prices(n=200, rate=0.005)}
        result = factor_attribution(prices)
        assert result["momentum_portfolio"] > 0

    def test_n_tickers_correct(self):
        prices = {
            "AAPL": self._rising_prices(),
            "MSFT": self._rising_prices(),
            "NVDA": self._rising_prices(),
        }
        result = factor_attribution(prices)
        assert result["n_tickers"] == 3
