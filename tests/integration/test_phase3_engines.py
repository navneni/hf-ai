"""
Phase 3 integration tests.
Verifies all 4 engines auto-discovered and run on AAPL data from MongoDB cache.
Requires MongoDB with AAPL data from Phase 2 (run --fetch-only first).
"""
from __future__ import annotations
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db():
    from db.client import MongoDBClient
    client = MongoDBClient()
    yield client
    client.close()


@pytest.fixture(scope="module")
def bus(db):
    from core.data_bus import DataBus
    return DataBus(db, force_refresh=False)


def test_all_four_engines_discovered():
    from core.engine_registry import EngineRegistry
    reg = EngineRegistry()
    reg.discover("signals")
    names = [e.name for e in reg.resolve("all")]
    for expected in ("technical", "fundamental", "valuation", "earnings_quality"):
        assert expected in names, f"Engine '{expected}' not discovered"


def test_technical_engine_on_cached_data(bus):
    from signals.technical import TechnicalEngine
    bundle = bus.fetch("AAPL")
    if len(bundle.prices) < 60:
        pytest.skip("Not enough price data cached — run --fetch-only first")
    e = TechnicalEngine()
    sig = e.compute(bundle)
    assert sig.signal in ("bullish", "bearish", "neutral")
    assert 0 <= sig.confidence <= 95
    assert "timeframes_used" in sig.metadata


def test_fundamental_engine_on_cached_data(bus):
    from signals.fundamental import FundamentalEngine
    bundle = bus.fetch("AAPL")
    if not bundle.financials:
        pytest.skip("No financials cached — run --fetch-only first")
    e = FundamentalEngine()
    e.initialize({})
    if not e.validate_data(bundle):
        pytest.skip("Insufficient fundamental data")
    sig = e.compute(bundle)
    assert sig.signal in ("bullish", "bearish", "neutral")
    assert "checks_passed" in sig.metadata


def test_valuation_engine_on_cached_data(bus):
    from signals.valuation import ValuationEngine
    bundle = bus.fetch("AAPL")
    e = ValuationEngine()
    e.initialize({})
    if not e.validate_data(bundle):
        pytest.skip("Insufficient valuation data")
    sig = e.compute(bundle)
    assert sig.signal in ("bullish", "bearish", "neutral")
    assert "models_used" in sig.metadata
    assert sig.metadata["models_used"] >= 1


def test_earnings_quality_engine_on_cached_data(bus):
    from signals.earnings_quality import EarningsQualityEngine
    bundle = bus.fetch("AAPL")
    e = EarningsQualityEngine()
    if not e.validate_data(bundle):
        pytest.skip("Need ≥2 annual periods cached")
    sig = e.compute(bundle)
    assert sig.signal in ("bullish", "bearish", "neutral")
    assert "piotroski_score" in sig.metadata


def test_signals_written_to_mongodb_via_write_engine():
    """Full run: WriteEngine discovers and runs all 4 engines, writes to DB."""
    from core.write_engine import WriteEngine
    engine = WriteEngine()
    result = engine.run(tickers=["AAPL"], as_of_date=None)
    assert result.status == "success"
    assert "AAPL" in result.signals
    assert len(result.signals["AAPL"]) >= 1   # at least 1 engine ran
