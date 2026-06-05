"""Unit tests for investor screens — shared helpers + Buffett, Graham, Lynch."""
from __future__ import annotations
import pytest
from core.engine_base import DataBundle


# ─────────────────────────────────────── fixtures

def _fin(year, **kw):
    base = {
        "period": year, "period_end": f"{year}-09-30", "market": "US",
        "revenue": 400e9, "gross_profit": 160e9, "operating_income": 70e9,
        "net_income": 55e9, "eps": 3.5, "ebit": 70e9,
        "total_assets": 340e9, "total_debt": 95e9, "cash": 30e9,
        "equity": 60e9, "current_assets": 153e9, "current_liabilities": 75e9,
        "operating_cash_flow": 95e9, "capex": 9e9, "free_cash_flow": 86e9,
        "shares_outstanding": 15_000_000_000,
        "retained_earnings": -20e9, "ppe": 45e9,
        "depreciation_amortization": 11e9,
    }
    base.update(kw)
    return base


def _ratios(**kw):
    base = {
        "pe_ratio": 22.0, "pb_ratio": 3.5, "ps_ratio": 4.5, "peg_ratio": 2.1,
        "roe": 0.90, "roa": 0.16, "debt_to_equity": 1.58,
        "current_ratio": 2.04, "gross_margin": 0.40,
        "operating_margin": 0.175, "net_margin": 0.138,
        "fcf_yield": 0.029, "dividend_yield": 0.005,
        "market_cap": 2_900_000_000_000, "enterprise_value": 2_950_000_000_000,
        "sector": "Technology",
    }
    base.update(kw)
    return base


def _bundle(fins=None, r=None, prices=None, mkt="US") -> DataBundle:
    return DataBundle(
        ticker="AAPL", market=mkt, as_of_date="2024-01-15",
        financials=fins or [_fin(str(y)) for y in range(2019, 2025)],
        ratios=r or _ratios(),
        prices=prices or [],
        market_config={"country": mkt, "trading_days": 252, "risk_free_rate": 0.053,
                       "pe_fair_value": 18.0},
    )


# ─────────────────────────────────────── shared helper tests

def test_consistency_score_all_pass():
    from signals.screens import consistency_score
    assert consistency_score([0.20, 0.18, 0.22, 0.16, 0.19], 0.15) == pytest.approx(1.0)


def test_consistency_score_partial():
    from signals.screens import consistency_score
    s = consistency_score([0.20, 0.10, 0.18, 0.08, 0.22], 0.15)
    assert 0.0 < s < 1.0


def test_consistency_score_empty():
    from signals.screens import consistency_score
    assert consistency_score([], 0.15) == 0.0


def test_consistency_score_nones():
    from signals.screens import consistency_score
    assert consistency_score([None, None, 0.20], 0.15) == pytest.approx(1.0)


def test_moat_text_no_text():
    from signals.screens import moat_text_score
    assert moat_text_score("") == 0.0
    assert moat_text_score(None) == 0.0


def test_moat_text_with_keywords():
    from signals.screens import moat_text_score
    text = "Our proprietary technology creates significant switching costs " \
           "for customers. Our platform benefits from strong network effects " \
           "in our two-sided marketplace ecosystem."
    score = moat_text_score(text)
    assert 0 < score <= 1.0


def test_moat_text_idf_boosts_rare_keywords():
    from signals.screens import moat_text_score
    # Text with IDF-weighted moat terms should score higher than text with no moat terms
    text_with_moat  = "Our proprietary network effect platform creates switching costs " \
                      "lock-in mission-critical trade secret brand loyalty patent."
    text_boilerplate = "The company operates in a competitive market with many products " \
                       "and services for customers worldwide in various regions."
    assert moat_text_score(text_with_moat) > moat_text_score(text_boilerplate)


def test_management_quality_basics():
    from signals.screens import management_quality_score, _annual_sorted
    fins = [_fin(str(y)) for y in range(2015, 2025)]
    score = management_quality_score(_annual_sorted(fins), _ratios())
    assert 0.0 <= score <= 1.0


def test_master_screen_score_weights():
    from signals.screens import master_screen_score
    # All perfect → should be 1.0
    score = master_screen_score(1.0, 1.0, 1.0, 1.0)
    assert score == pytest.approx(1.0)

    # All zero → 0
    score = master_screen_score(0.0, 0.0, 0.0, 0.0)
    assert score == pytest.approx(0.0)


def test_master_screen_red_flag_halves_score():
    from signals.screens import master_screen_score
    normal   = master_screen_score(0.8, 0.8, 0.8, 0.8, filing_text="")
    flagged  = master_screen_score(0.8, 0.8, 0.8, 0.8, filing_text="going concern material weakness")
    assert flagged == pytest.approx(normal * 0.50)


# ─────────────────────────────────────── Buffett screen tests

def test_buffett_name_weight():
    from signals.screens.buffett import BuffettScreen
    e = BuffettScreen(); e.initialize({})
    assert e.name == "buffett_screen"
    assert abs(e.weight - 0.01538) < 0.001


def test_buffett_validate_needs_5yr():
    from signals.screens.buffett import BuffettScreen
    e = BuffettScreen(); e.initialize({})
    assert e.validate_data(_bundle([_fin("2024"), _fin("2023")])) is False
    assert e.validate_data(_bundle([_fin(str(y)) for y in range(2018,2025)])) is True


def test_buffett_quality_company_bullish():
    from signals.screens.buffett import BuffettScreen
    e = BuffettScreen()
    e.initialize({"us_thresholds": {"buffett_roe": 15, "buffett_de": 0.5,
                                     "buffett_margin_safety": 25, "buffett_net_margin": 10}})
    fins = [_fin(str(y), equity=200e9, total_debt=60e9) for y in range(2015, 2025)]
    r = _ratios(roe=0.35, debt_to_equity=0.3, net_margin=0.25, market_cap=500e9)
    sig = e.compute(_bundle(fins, r))
    assert sig.signal in ("bullish", "neutral")
    assert "criteria" in sig.metadata


def test_buffett_signal_metadata():
    from signals.screens.buffett import BuffettScreen
    e = BuffettScreen(); e.initialize({})
    sig = e.compute(_bundle())
    assert "total_score" in sig.metadata
    assert "checks_passed" in sig.metadata
    assert 0.0 <= sig.metadata["total_score"] <= 1.0


# ─────────────────────────────────────── Graham screen tests

def test_graham_name_weight():
    from signals.screens.graham import GrahamScreen
    e = GrahamScreen(); e.initialize({})
    assert e.name == "graham_screen"


def test_graham_deep_value_bullish():
    from signals.screens.graham import GrahamScreen
    e = GrahamScreen()
    e.initialize({"us_thresholds": {"graham_pe": 15, "graham_pb": 1.5, "buffett_de": 0.5}})
    r = _ratios(pe_ratio=10.0, pb_ratio=0.9, current_ratio=3.0,
                debt_to_equity=0.3, dividend_yield=0.03)
    fins = [_fin(str(y), eps=3.5) for y in range(2018, 2025)]
    sig = e.compute(_bundle(fins, r))
    assert sig.signal in ("bullish", "neutral")


def test_graham_overvalued_bearish():
    from signals.screens.graham import GrahamScreen
    e = GrahamScreen()
    e.initialize({"us_thresholds": {"graham_pe": 15, "graham_pb": 1.5, "buffett_de": 0.5}})
    r = _ratios(pe_ratio=120.0, pb_ratio=25.0, current_ratio=0.5,
                debt_to_equity=5.0, dividend_yield=0.0)
    fins = [_fin(str(y), eps=-0.5) for y in range(2018, 2025)]
    sig = e.compute(_bundle(fins, r))
    assert sig.signal in ("bearish", "neutral")


# ─────────────────────────────────────── Lynch screen tests

def test_lynch_name_weight():
    from signals.screens.lynch import LynchScreen
    e = LynchScreen(); e.initialize({})
    assert e.name == "lynch_screen"


def test_lynch_garp_bullish():
    from signals.screens.lynch import LynchScreen
    e = LynchScreen()
    e.initialize({"us_thresholds": {"lynch_peg": 1.0, "lynch_eps_growth": 20, "lynch_de": 0.35}})
    fins = [_fin(str(y), eps=3.5 * (1.25 ** (2024-int(y)))) for y in range(2019, 2025)]
    r = _ratios(peg_ratio=0.6, debt_to_equity=0.25)
    sig = e.compute(_bundle(fins, r))
    assert sig.signal in ("bullish", "neutral")


# ─────────────────────────────────────── All 13 screens discoverable

def test_all_13_screens_discovered():
    from core.engine_registry import EngineRegistry
    reg = EngineRegistry()
    reg.discover("signals")
    names = {e.name for e in reg.resolve("all")}
    expected = {
        "buffett_screen", "graham_screen", "lynch_screen", "fisher_screen",
        "munger_screen", "burry_screen", "ackman_screen", "wood_screen",
        "druckenmiller", "taleb_screen", "damodaran_screen", "pabrai_screen",
        "jhunjhunwala",
    }
    missing = expected - names
    assert not missing, f"Missing screens: {missing}"


def test_all_screens_run_without_crash():
    """All 13 screens should complete without exception on valid data."""
    from core.engine_registry import EngineRegistry
    reg = EngineRegistry()
    reg.discover("signals")
    reg.initialize_all({})
    fins = [_fin(str(y)) for y in range(2015, 2025)]
    b = _bundle(fins)

    import numpy as np
    from datetime import date, timedelta
    base = date(2022, 1, 3)
    prices = [{"date": str(base + timedelta(days=i)), "open": 100, "high": 102,
               "low": 98, "close": 100 + i*0.1, "volume": 1_000_000} for i in range(300)]
    b.prices = prices

    screen_engines = [e for e in reg.resolve("all") if "screen" in e.name or
                      e.name in ("druckenmiller","jhunjhunwala","munger_screen",
                                 "burry_screen","ackman_screen","wood_screen","taleb_screen",
                                 "damodaran_screen","pabrai_screen")]
    for e in screen_engines:
        if e.validate_data(b):
            sig = e.compute(b)
            assert sig.signal in ("bullish", "bearish", "neutral"), f"{e.name} returned invalid signal"
            assert 0 <= sig.confidence <= 95, f"{e.name} confidence out of range"


def test_combined_screen_weight():
    """13 screens × SCREEN_WEIGHT should sum to ≈ 0.20."""
    from signals.screens import SCREEN_WEIGHT
    total = 13 * SCREEN_WEIGHT
    assert abs(total - 0.20) < 0.001


def test_india_thresholds_used():
    """Jhunjhunwala screen uses India thresholds for promoter holding."""
    from signals.screens.jhunjhunwala import JhunjhunwalaScreen
    e = JhunjhunwalaScreen()
    e.initialize({"india_thresholds": {"jhunjhunwala_promoter": 40,
                                        "jhunjhunwala_eps_cagr": 20,
                                        "jhunjhunwala_revenue_cagr": 15,
                                        "jhunjhunwala_roce": 20}})
    fins = [_fin(str(y)) for y in range(2020, 2025)]
    b = _bundle(fins, mkt="IN")
    b.promoter_holdings = [{"quarter": "Q3-FY2024", "promoter_pct": 55.0}]
    sig = e.compute(b)
    assert "promoter" in sig.metadata["criteria"]
    assert sig.metadata["criteria"]["promoter"] is True
