"""Unit tests for DataBus caching logic using mocks (no network, no MongoDB)."""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from core.engine_base import DataBundle


# ── helpers ──────────────────────────────────────────────────────────────────

def _chainable_cursor(rows=None):
    """Return a mock cursor supporting .find().sort().limit() chaining."""
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = iter(rows or [])
    return cursor


def _make_db(prices=None, financials=None, ratios=None, meta_stale=True):
    """Build a mock db where MongoDB returns no usable cached data by default."""
    db = MagicMock()

    # data_cache_meta: return None by default → stale
    db.data_cache_meta.find_one.return_value = None if meta_stale else {
        "last_fetched": datetime.now(tz=timezone.utc),
        "ttl_seconds":  21600,
    }

    # Chainable cursors for collection.find().sort().limit()
    db.prices_us.find.return_value  = _chainable_cursor(prices)
    db.financials.find.return_value = _chainable_cursor(financials)
    db.insider_trades.find.return_value = _chainable_cursor([])

    db.ratios.find_one.return_value        = ratios or {}
    db.filing_texts.find_one.return_value  = None
    db.audit_log.insert_one.return_value   = None

    # db.db["prices_us"] → db.prices_us  (used in _load_from_db)
    def _getitem(name):
        return getattr(db, name, MagicMock())
    db.db.__getitem__ = MagicMock(side_effect=_getitem)

    return db


def _fake_bundle(ticker="AAPL") -> DataBundle:
    return DataBundle(
        ticker=ticker, market="US", as_of_date="2024-01-15",
        prices=[{"date": "2024-01-15", "close": 185.0}],
        financials=[{"period": "2023", "revenue": 400e9}],
        ratios={"pe_ratio": 30.0},
        market_config={"country": "US"},
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_memory_cache_hit():
    """Second call for same ticker+date returns from memory without hitting DB or live."""
    from core.data_bus import DataBus

    db = _make_db()
    bus = DataBus(db)

    bundle = _fake_bundle()
    bus._mem["AAPL:2024-01-15"] = bundle

    result = bus.fetch("AAPL", "2024-01-15")

    assert result is bundle
    db.data_cache_meta.find_one.assert_not_called()


def test_live_fetch_called_on_cache_miss():
    """When MongoDB has no data, _live_fetch is called."""
    from core.data_bus import DataBus

    db = _make_db(meta_stale=True)
    bus = DataBus(db)
    expected = _fake_bundle()

    with patch.object(bus, "_live_fetch", return_value=expected) as mock_lf, \
         patch.object(bus, "_save_to_db"):
        result = bus.fetch("AAPL", "2024-01-15")

    mock_lf.assert_called_once_with("AAPL", "2024-01-15")
    assert result is expected


def test_result_cached_in_memory_after_live_fetch():
    """After a live fetch, the result is stored in the memory cache."""
    from core.data_bus import DataBus

    db = _make_db()
    bus = DataBus(db)
    bundle = _fake_bundle()

    with patch.object(bus, "_live_fetch", return_value=bundle), \
         patch.object(bus, "_save_to_db"):
        bus.fetch("AAPL", "2024-01-15")

    assert "AAPL:2024-01-15" in bus._mem


def test_force_refresh_bypasses_memory_cache():
    """force_refresh=True ignores the memory cache."""
    from core.data_bus import DataBus

    db = _make_db()
    bus = DataBus(db, force_refresh=True)
    bundle = _fake_bundle()
    bus._mem["AAPL:2024-01-15"] = bundle   # pre-populate memory cache

    with patch.object(bus, "_live_fetch", return_value=bundle) as mock_lf, \
         patch.object(bus, "_save_to_db"):
        bus.fetch("AAPL", "2024-01-15")

    mock_lf.assert_called_once()


def test_historical_data_never_stale():
    """Data fetched for a past date (backtest) is always considered fresh."""
    from core.data_bus import _is_stale
    from datetime import datetime, timezone, timedelta

    old_fetch = datetime.now(tz=timezone.utc) - timedelta(days=30)
    # Historical date → never stale regardless of TTL
    assert _is_stale(old_fetch, "prices", "2020-01-15") is False


def test_live_data_stale_when_old():
    """Live data is stale when fetched_at exceeds TTL."""
    from core.data_bus import _is_stale
    from datetime import datetime, timezone, timedelta

    old_fetch = datetime.now(tz=timezone.utc) - timedelta(hours=8)
    # prices TTL = 6h → 8h old → stale
    assert _is_stale(old_fetch, "prices", None) is True


def test_live_data_fresh_when_recent():
    """Live data is fresh when fetched within TTL."""
    from core.data_bus import _is_stale
    from datetime import datetime, timezone, timedelta

    recent_fetch = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    assert _is_stale(recent_fetch, "prices", None) is False


def test_prefetch_parallel(monkeypatch):
    """prefetch() calls fetch() for each ticker."""
    from core.data_bus import DataBus

    db = _make_db()
    bus = DataBus(db)
    fetched = []

    def fake_fetch(ticker, as_of_date=None):
        fetched.append(ticker)
        return _fake_bundle(ticker)

    monkeypatch.setattr(bus, "fetch", fake_fetch)
    bus.prefetch(["AAPL", "MSFT", "NVDA"], "2024-01-15")

    assert sorted(fetched) == ["AAPL", "MSFT", "NVDA"]
