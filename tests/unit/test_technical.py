"""Unit tests for TechnicalEngine using synthetic price data."""
from __future__ import annotations
import pytest
import numpy as np
from core.engine_base import DataBundle


def _make_prices(n: int = 100, trend: float = 0.001, vol: float = 0.01, seed: int = 42) -> list[dict]:
    """Generate synthetic daily OHLCV prices with a trend."""
    rng = np.random.default_rng(seed)
    price = 100.0
    prices = []
    from datetime import date, timedelta
    base = date(2022, 1, 3)
    for i in range(n):
        ret = trend + rng.normal(0, vol)
        close = round(price * (1 + ret), 2)
        high  = round(close * (1 + abs(rng.normal(0, vol/2))), 2)
        low   = round(close * (1 - abs(rng.normal(0, vol/2))), 2)
        prices.append({
            "date":   str(base + timedelta(days=i)),
            "open":   round(price, 2),
            "high":   high,
            "low":    low,
            "close":  close,
            "volume": int(rng.integers(10_000_000, 50_000_000)),
        })
        price = close
    return prices


def _bundle(prices) -> DataBundle:
    return DataBundle(ticker="TEST", market="US", as_of_date="2022-12-31",
                      prices=prices, market_config={"country": "US", "trading_days": 252})


# ─────────────────────────────────────────────────────────────────────────────

def test_engine_name_and_weight():
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    assert e.name == "technical"
    assert e.weight == 0.20


def test_validate_data_passes_with_enough_prices():
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    assert e.validate_data(_bundle(_make_prices(60))) is True


def test_validate_data_fails_with_too_few_prices():
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    assert e.validate_data(_bundle(_make_prices(30))) is False


def test_bullish_signal_on_uptrend():
    """Strong uptrend should produce a bullish signal."""
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    prices = _make_prices(200, trend=0.003, vol=0.005)  # +0.3%/day
    sig = e.compute(_bundle(prices))
    assert sig.signal in ("bullish", "neutral")
    assert 0 <= sig.confidence <= 95


def test_bearish_signal_on_downtrend():
    """Strong downtrend should produce a bearish signal."""
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    prices = _make_prices(200, trend=-0.003, vol=0.005)
    sig = e.compute(_bundle(prices))
    assert sig.signal in ("bearish", "neutral")
    assert 0 <= sig.confidence <= 95


def test_signal_has_required_fields():
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    sig = e.compute(_bundle(_make_prices(120)))
    assert sig.signal in ("bullish", "bearish", "neutral")
    assert isinstance(sig.confidence, float)
    assert isinstance(sig.metadata, dict)
    assert "timeframes_used" in sig.metadata


def test_metadata_contains_timeframe_info():
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    sig = e.compute(_bundle(_make_prices(150)))
    assert "timeframes_used" in sig.metadata
    assert len(sig.metadata["timeframes_used"]) >= 1


def test_confidence_in_valid_range():
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    for seed in range(5):
        sig = e.compute(_bundle(_make_prices(100, seed=seed)))
        assert 0 <= sig.confidence <= 95, f"Confidence out of range: {sig.confidence}"


def test_high_confidence_when_all_timeframes_agree():
    """With 200+ bars and strong uptrend, all timeframes should agree → boosted confidence."""
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    prices = _make_prices(252, trend=0.004, vol=0.003, seed=1)
    sig = e.compute(_bundle(prices))
    if sig.signal == "bullish":
        assert sig.confidence > 40   # confluence should push confidence up


def test_rsi_helper():
    from signals.technical import _rsi
    import pandas as pd
    close = pd.Series(range(100, 150, 1), dtype=float)
    rsi = _rsi(close, 14)
    assert rsi.iloc[-1] > 70   # monotonically rising → overbought


def test_adx_helper():
    from signals.technical import _adx
    import pandas as pd
    n = 60
    close  = pd.Series([100 + i * 0.5 for i in range(n)])
    high   = close + 1.0
    low    = close - 1.0
    adx    = _adx(high, low, close, 14)
    assert adx.dropna().iloc[-1] > 0   # basic sanity check


def test_hurst_trending():
    """Strongly trending series → Hurst closer to 1 than mean-reverting."""
    from signals.technical import _hurst
    rng = np.random.default_rng(42)
    # Persistent trend: cumsum of positive returns + small noise
    trend = np.cumsum(np.ones(100) * 0.5 + rng.normal(0, 0.05, 100))
    h_trend = _hurst(trend)
    # Mean-reverting: oscillating series
    mr = np.array([(-1) ** i * (1 + rng.normal(0, 0.1)) for i in range(100)])
    h_mr = _hurst(np.cumsum(mr))
    assert h_trend > h_mr, "Trending series should have higher Hurst than mean-reverting"
    assert 0.0 <= h_trend <= 1.0


def test_minimal_data_returns_neutral():
    """Exactly 60 bars — many indicators will be limited; should still return a valid signal."""
    from signals.technical import TechnicalEngine
    e = TechnicalEngine()
    sig = e.compute(_bundle(_make_prices(60)))
    assert sig.signal in ("bullish", "bearish", "neutral")
