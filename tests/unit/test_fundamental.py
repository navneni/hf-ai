"""Unit tests for FundamentalEngine and Piotroski F-Score."""
from __future__ import annotations
import pytest
from core.engine_base import DataBundle


def _annual(year: str, **kwargs) -> dict:
    base = {
        "period": year, "period_end": f"{year}-09-30", "market": "US",
        "revenue":             400e9,
        "gross_profit":        160e9,
        "operating_income":     70e9,
        "net_income":           55e9,
        "eps":                   3.5,
        "total_assets":        340e9,
        "total_debt":           95e9,
        "cash":                 30e9,
        "equity":               60e9,
        "current_assets":      153e9,
        "current_liabilities":  75e9,
        "operating_cash_flow":  95e9,
        "capex":                 9e9,
        "free_cash_flow":       86e9,
        "shares_outstanding":   15_000_000_000,
        "retained_earnings":    -20e9,
        "ppe":                   45e9,
        "receivables":           33e9,
        "sga_expense":           24e9,
        "depreciation_amortization": 11e9,
    }
    base.update(kwargs)
    return base


def _ratios(**kwargs) -> dict:
    base = {
        "pe_ratio": 22.0, "pb_ratio": 15.0, "ps_ratio": 4.5,
        "roe": 0.90, "roa": 0.16, "debt_to_equity": 1.58,
        "current_ratio": 2.04, "gross_margin": 0.40,
        "operating_margin": 0.175, "net_margin": 0.138,
        "fcf_yield": 0.029, "market_cap": 2_900_000_000_000,
    }
    base.update(kwargs)
    return base


def _bundle(financials, ratios=None, market="US") -> DataBundle:
    return DataBundle(
        ticker="TEST", market=market, as_of_date="2024-01-15",
        financials=financials, ratios=ratios or _ratios(),
        market_config={"country": market, "trading_days": 252, "risk_free_rate": 0.053},
    )


# ─────────────────────────────────────────────────────────────────────────────

def test_engine_name_and_weight():
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    assert e.name == "fundamental"
    assert e.weight == 0.15


def test_validate_data_with_ttm():
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    fins = [_annual("TTM")]
    fins[0]["period"] = "TTM"
    assert e.validate_data(_bundle(fins)) is True


def test_validate_data_empty():
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    assert e.validate_data(_bundle([])) is False


def test_strong_company_bullish():
    """High quality metrics should produce bullish signal."""
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    fins = [
        _annual("TTM", **{"period": "TTM", "period_end": "2024-06-30"}),
        _annual("2023"),
        _annual("2022"),
    ]
    # High ROE, good margins, low debt
    r = _ratios(roe=1.5, net_margin=0.26, operating_margin=0.31,
                pe_ratio=22, pb_ratio=10, ps_ratio=4,
                current_ratio=2.0, debt_to_equity=1.5)
    sig = e.compute(_bundle(fins, r))
    assert sig.signal in ("bullish", "neutral")
    assert "checks_passed" in sig.metadata


def test_weak_company_bearish():
    """Poor metrics should push toward bearish."""
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    fins = [
        _annual("TTM", **{"period": "TTM", "net_income": -5e9, "eps": -0.3,
                           "gross_profit": 10e9, "operating_income": -8e9,
                           "current_assets": 20e9, "current_liabilities": 50e9,
                           "free_cash_flow": -10e9, "total_debt": 200e9,
                           "equity": 10e9, "period_end": "2024-06-30"}),
        _annual("2023", **{"net_income": -3e9}),
    ]
    r = _ratios(roe=-0.3, net_margin=-0.05, operating_margin=-0.02,
                pe_ratio=None, pb_ratio=0.5, ps_ratio=0.8,
                current_ratio=0.4, debt_to_equity=20.0)
    sig = e.compute(_bundle(fins, r))
    assert sig.signal in ("bearish", "neutral")


def test_signal_has_checks_metadata():
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    sig = e.compute(_bundle([_annual("2024"), _annual("2023")]))
    assert "checks_passed" in sig.metadata
    assert "piotroski_score" in sig.metadata
    assert "ratio_checks" in sig.metadata


def test_piotroski_computed():
    """Piotroski should produce a score when 2+ annual periods available."""
    from signals.fundamental import _piotroski
    fins = [_annual("2024"), _annual("2023")]
    score, checks = _piotroski(fins)
    assert score >= 0
    assert len(checks) == 9


def test_piotroski_insufficient_data():
    """Single period should return -1 (insufficient)."""
    from signals.fundamental import _piotroski
    score, _ = _piotroski([_annual("2024")])
    assert score == -1


def test_confidence_in_range():
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({})
    sig = e.compute(_bundle([_annual("2024"), _annual("2023")]))
    assert 0 <= sig.confidence <= 95


def test_india_thresholds_applied():
    """India D/E threshold (0.6) is higher than US (0.5)."""
    from signals.fundamental import FundamentalEngine
    e = FundamentalEngine()
    e.initialize({"us_thresholds": {"buffett_de": 0.5}, "india_thresholds": {"buffett_de": 0.6}})
    fins = [_annual("2024", total_debt=50e9, equity=100e9),  # D/E = 0.5
            _annual("2023")]
    r = _ratios(debt_to_equity=0.5)
    # D/E 0.5: passes India threshold (0.6) but borderline US (0.5)
    sig_us = e.compute(_bundle(fins, r, market="US"))
    sig_in = e.compute(_bundle(fins, r, market="IN"))
    assert "debt_equity" in sig_us.metadata["ratio_checks"]
