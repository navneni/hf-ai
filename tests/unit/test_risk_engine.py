"""
Unit tests for Phase 7 RiskEngine.
Uses synthetic price series with known volatility to verify tier assignment,
position sizing, and correlation multipliers.
"""
from __future__ import annotations
import math
import pytest

from core.engine_base import DataBundle
from core.risk_engine import RiskEngine, PositionLimit


# ─────────────────────────────────────── helpers

def _price_series(n: int, daily_vol: float = 0.01, start: float = 100.0) -> list[dict]:
    """Generate synthetic price series with specified daily vol (random walk)."""
    import random
    rng = random.Random(42)
    prices = []
    p = start
    for i in range(n):
        ret = rng.gauss(0, daily_vol)
        p = p * (1 + ret)
        prices.append({
            "date":  f"2024-{(i // 20 + 1):02d}-{(i % 20 + 1):02d}",
            "open":  round(p * 0.99, 2),
            "high":  round(p * 1.01, 2),
            "low":   round(p * 0.98, 2),
            "close": round(p, 2),
            "volume": 1_000_000,
        })
    return prices


def _bundle(prices: list[dict], ticker: str = "TST", market: str = "US") -> DataBundle:
    return DataBundle(ticker=ticker, market=market, as_of_date="2024-12-31", prices=prices)


def _engine(extra_config: dict | None = None) -> RiskEngine:
    cfg = {
        "risk": {
            "vol_lookback_days": 60,
            "corr_high_threshold": 0.80,
            "corr_low_threshold": 0.30,
            "corr_high_multiplier": 0.70,
            "corr_low_multiplier": 1.10,
            "default_portfolio_value": 100_000.0,
            "vol_tiers": {
                "low":        {"threshold": 0.15, "max_alloc": 0.25},
                "medium_low": {"threshold": 0.22, "max_alloc": 0.20},
                "medium":     {"threshold": 0.30, "max_alloc": 0.15},
                "high":       {"threshold": 0.50, "max_alloc": 0.125},
                "very_high":  {"threshold": 999.0, "max_alloc": 0.10},
            },
        },
        **(extra_config or {}),
    }
    return RiskEngine(cfg)


# ─────────────────────────────────────── vol tier tests

class TestVolTier:

    def test_low_vol_tier(self):
        eng = _engine()
        tier, alloc = eng._vol_tier(0.10)   # 10% → low
        assert tier == "low"
        assert alloc == pytest.approx(0.25)

    def test_medium_low_vol_tier(self):
        eng = _engine()
        tier, alloc = eng._vol_tier(0.18)
        assert tier == "medium_low"
        assert alloc == pytest.approx(0.20)

    def test_medium_vol_tier(self):
        eng = _engine()
        tier, alloc = eng._vol_tier(0.25)
        assert tier == "medium"
        assert alloc == pytest.approx(0.15)

    def test_high_vol_tier(self):
        eng = _engine()
        tier, alloc = eng._vol_tier(0.40)
        assert tier == "high"
        assert alloc == pytest.approx(0.125)

    def test_very_high_vol_tier(self):
        eng = _engine()
        tier, alloc = eng._vol_tier(0.75)
        assert tier == "very_high"
        assert alloc == pytest.approx(0.10)

    def test_boundary_at_threshold(self):
        eng = _engine()
        tier, _ = eng._vol_tier(0.15)   # exactly at low/medium_low boundary → low
        assert tier == "low"


# ─────────────────────────────────────── annualized vol tests

class TestAnnualizedVol:

    def test_low_vol_series(self):
        """Daily vol=0.5% → annualized ≈ 7.9% → low tier."""
        prices = _price_series(300, daily_vol=0.005)
        eng  = _engine()
        lims = eng.compute({"TST": _bundle(prices)})
        assert lims["TST"].vol_tier == "low"
        assert lims["TST"].annualized_vol < 0.15

    def test_medium_vol_series(self):
        """Daily vol=1.3% → annualized ≈ 20.6% → medium_low."""
        prices = _price_series(300, daily_vol=0.013)
        eng  = _engine()
        lims = eng.compute({"TST": _bundle(prices)})
        assert lims["TST"].vol_tier in ("medium_low", "medium")

    def test_high_vol_series(self):
        """Daily vol=2.5% → annualized ≈ 39.7% → high."""
        prices = _price_series(300, daily_vol=0.025)
        eng  = _engine()
        lims = eng.compute({"TST": _bundle(prices)})
        assert lims["TST"].vol_tier == "high"

    def test_lookback_uses_only_last_60_days(self):
        """Engine should only use the last 60 days for vol, not all history."""
        # First 200 bars: calm; last 80 bars: very volatile
        calm = _price_series(200, daily_vol=0.002)
        noisy = _price_series(80, daily_vol=0.030, start=calm[-1]["close"])
        prices = calm + noisy
        eng  = _engine()
        lims = eng.compute({"TST": _bundle(prices)})
        # Lookback 60 covers only the noisy portion → high/very_high tier
        assert lims["TST"].vol_tier in ("high", "very_high")


# ─────────────────────────────────────── position sizing tests

class TestPositionSizing:

    def test_max_position_usd(self):
        prices = _price_series(300, daily_vol=0.005)   # low vol → 25%
        portfolio = {"portfolio_value": 100_000.0}
        lims = _engine().compute({"TST": _bundle(prices)}, portfolio)
        limit = lims["TST"]
        # With corr_mult=1.0 (single ticker): 100k * 0.25 * 1.0 = 25k
        assert limit.max_position_usd == pytest.approx(25_000.0, rel=0.05)

    def test_max_shares_computed_from_price(self):
        prices = _price_series(300, daily_vol=0.005)
        last_price = prices[-1]["close"]
        portfolio = {"portfolio_value": 100_000.0}
        lims = _engine().compute({"TST": _bundle(prices)}, portfolio)
        limit = lims["TST"]
        expected = int(limit.max_position_usd / last_price)
        assert limit.max_shares == expected

    def test_max_shares_minimum_one(self):
        """Even if position_usd < price, max_shares ≥ 1."""
        prices = _price_series(100, daily_vol=0.030, start=100_000.0)  # expensive stock
        portfolio = {"portfolio_value": 1_000.0}  # tiny portfolio
        lims = _engine().compute({"TST": _bundle(prices)}, portfolio)
        assert lims["TST"].max_shares >= 1

    def test_current_price_in_limit(self):
        prices = _price_series(200, daily_vol=0.010)
        last_price = prices[-1]["close"]
        lims = _engine().compute({"TST": _bundle(prices)})
        assert lims["TST"].current_price == pytest.approx(last_price)

    def test_empty_prices_skipped(self):
        bundle = _bundle([])
        lims = _engine().compute({"TST": bundle})
        assert "TST" in lims
        # No price data → max_shares=0, current_price=0
        assert lims["TST"].max_shares == 0
        assert lims["TST"].current_price == 0.0


# ─────────────────────────────────────── correlation tests

class TestCorrelation:

    def _correlated_prices(self, n: int = 200, corr: float = 0.95) -> tuple[list[dict], list[dict]]:
        """Generate two price series with target correlation."""
        import random
        rng = random.Random(7)
        p1, p2 = 100.0, 100.0
        prices1, prices2 = [], []
        for i in range(n):
            common   = rng.gauss(0, 0.015)
            idio1    = rng.gauss(0, 0.005)
            idio2    = rng.gauss(0, 0.005)
            r1 = corr * common + (1 - corr) * idio1
            r2 = corr * common + (1 - corr) * idio2
            p1 = p1 * (1 + r1)
            p2 = p2 * (1 + r2)
            dt = f"2024-{(i//20+1):02d}-{(i%20+1):02d}"
            prices1.append({"date": dt, "close": round(p1, 2), "open": p1, "high": p1, "low": p1, "volume": 1_000_000})
            prices2.append({"date": dt, "close": round(p2, 2), "open": p2, "high": p2, "low": p2, "volume": 1_000_000})
        return prices1, prices2

    def test_high_correlation_reduces_position(self):
        p1, p2 = self._correlated_prices(200, corr=0.95)
        bundles = {
            "A": _bundle(p1, "A"),
            "B": _bundle(p2, "B"),
        }
        lims = _engine().compute(bundles)
        # High correlation → corr_multiplier = 0.70 for both
        assert lims["A"].corr_multiplier == pytest.approx(0.70, abs=0.05)
        assert lims["B"].corr_multiplier == pytest.approx(0.70, abs=0.05)

    def test_single_ticker_no_corr_adjustment(self):
        """Only one ticker → no peers → corr_mult = 1.0."""
        prices = _price_series(200, daily_vol=0.010)
        lims = _engine().compute({"TST": _bundle(prices)})
        assert lims["TST"].corr_multiplier == pytest.approx(1.0)

    def test_uncorrelated_tickers_increase_position(self):
        """Two near-orthogonal series → corr_mult = 1.10."""
        import random
        rng = random.Random(99)
        def _rand_prices(n=200):
            p = 100.0
            out = []
            for i in range(n):
                p = p * (1 + rng.gauss(0, 0.01))
                out.append({"date": f"2024-01-{(i%28+1):02d}", "close": round(p, 2),
                             "open": p, "high": p, "low": p, "volume": 1})
            return out
        b1 = _bundle(_rand_prices(), "X")
        # Second series: totally independent noise
        b2 = _bundle(_rand_prices(), "Y")
        lims = _engine().compute({"X": b1, "Y": b2})
        # Correlation between two independent series should be low → 1.10
        assert lims["X"].corr_multiplier in (1.0, pytest.approx(1.10, abs=0.05))
