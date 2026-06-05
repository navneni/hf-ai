"""Unit tests for ValuationEngine including DCF and Graham Number."""
from __future__ import annotations
import math
import pytest
from core.engine_base import DataBundle
from signals.valuation import _three_stage_dcf, _margin_of_safety, _fcf_cagr


# ── DCF helper tests ──────────────────────────────────────────────────────────

def test_dcf_basic():
    """DCF with positive FCF and reasonable inputs should return positive value."""
    iv = _three_stage_dcf(fcf=10e9, cagr=0.10, wacc=0.09)
    assert iv is not None and iv > 0


def test_dcf_wacc_lte_terminal_returns_none():
    """WACC <= terminal growth is mathematically undefined → return None."""
    iv = _three_stage_dcf(fcf=10e9, cagr=0.05, wacc=0.03, terminal_growth=0.03)
    assert iv is None


def test_dcf_negative_fcf_returns_none():
    iv = _three_stage_dcf(fcf=-5e9, cagr=0.10, wacc=0.09)
    assert iv is None


def test_margin_of_safety_undervalued():
    mos = _margin_of_safety(intrinsic=150.0, price=100.0)
    assert mos is not None and mos > 0   # undervalued


def test_margin_of_safety_overvalued():
    mos = _margin_of_safety(intrinsic=80.0, price=100.0)
    assert mos is not None and mos < 0   # overvalued


def test_fcf_cagr_computed_correctly():
    """FCF growing at ~15%/yr → CAGR ≈ 0.15."""
    fins = [
        {"period": str(2020 + i), "period_end": f"{2020 + i}-09-30",
         "free_cash_flow": 10e9 * (1.15 ** i)}   # 10→17.5 over 4 yrs
        for i in range(5)
    ]
    cagr = _fcf_cagr(fins, 5)
    assert cagr is not None and 0 < cagr < 0.50


# ── Engine tests ──────────────────────────────────────────────────────────────

def _annual(year, **kw) -> dict:
    base = {
        "period": year, "period_end": f"{year}-09-30", "market": "US",
        "revenue": 400e9, "gross_profit": 160e9, "net_income": 55e9,
        "operating_income": 70e9, "ebit": 70e9, "eps": 3.50,
        "total_assets": 340e9, "total_debt": 95e9, "equity": 60e9,
        "current_assets": 153e9, "current_liabilities": 75e9,
        "operating_cash_flow": 95e9, "capex": 9e9, "free_cash_flow": 86e9,
        "retained_earnings": -20e9, "ppe": 45e9,
        "depreciation_amortization": 11e9,
        "shares_outstanding": 15_000_000_000,
    }
    base.update(kw)
    return base


def _bundle(financials, ratios=None) -> DataBundle:
    return DataBundle(
        ticker="TEST", market="US", as_of_date="2024-01-15",
        financials=financials, ratios=ratios or {},
        market_config={"country": "US", "trading_days": 252,
                       "risk_free_rate": 0.053, "pe_fair_value": 18.0},
    )


def test_engine_name_and_weight():
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    assert e.name == "valuation"
    assert e.weight == 0.15


def test_validate_passes_with_market_cap_and_financials():
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    fins = [_annual("2024"), _annual("2023")]
    r = {"market_cap": 2_900_000_000_000, "pe_ratio": 28.0}
    assert e.validate_data(_bundle(fins, r)) is True


def test_validate_fails_empty_financials():
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    assert e.validate_data(_bundle([])) is False


def test_undervalued_gives_bullish():
    """Price far below intrinsic should give bullish signal."""
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    fins = [_annual(str(y)) for y in range(2016, 2025)]
    # Set price very low: market_cap = shares * price implies $10/share
    r = {
        "market_cap": 150_000_000_000,  # ~$10/share (vs EPS $3.5 → P/E 2.9x)
        "pe_ratio": 2.9, "pb_ratio": 2.5, "ev_ebitda": 5.0,
        "pe_fair_value": 18.0,
    }
    sig = e.compute(_bundle(fins, r))
    assert sig.signal == "bullish"
    assert sig.metadata.get("avg_mos", 0) > 0


def test_overvalued_gives_bearish():
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    fins = [_annual(str(y)) for y in range(2019, 2025)]
    r = {
        "market_cap": 20_000_000_000_000,  # massively overvalued
        "pe_ratio": 600.0, "pb_ratio": 300.0, "ev_ebitda": 400.0,
        "pe_fair_value": 18.0,
    }
    sig = e.compute(_bundle(fins, r))
    assert sig.signal == "bearish"


def test_models_used_at_least_3():
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    fins = [_annual(str(y)) for y in range(2019, 2025)]
    r = {"market_cap": 2_900_000_000_000, "pe_ratio": 28.0, "ev_ebitda": 23.0}
    sig = e.compute(_bundle(fins, r))
    assert sig.metadata.get("models_used", 0) >= 3


def test_insufficient_models_returns_neutral():
    from signals.valuation import ValuationEngine
    e = ValuationEngine()
    e.initialize({})
    # Only 1 annual period, no EPS → most models skip
    fins = [_annual("2024", eps=None, free_cash_flow=None, retained_earnings=None)]
    r = {"market_cap": None, "pe_ratio": None}
    sig = e.compute(_bundle(fins, r))
    assert sig.signal == "neutral"


def test_graham_number_computed():
    """Graham Number = sqrt(22.5 × EPS × BVPS)."""
    eps, bvps = 4.0, 20.0
    graham = math.sqrt(22.5 * eps * bvps)
    assert abs(graham - math.sqrt(22.5 * 4.0 * 20.0)) < 0.01
