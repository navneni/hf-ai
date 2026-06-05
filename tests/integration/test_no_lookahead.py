"""
Integration tests for no-lookahead enforcement.
Uses synthetic data injected directly into MongoDB — no network calls.
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    from db.client import MongoDBClient
    client = MongoDBClient()
    yield client
    # Clean up test documents
    client.prices_us.delete_many({"ticker": "TEST_NOLOOK"})
    client.financials.delete_many({"ticker": "TEST_NOLOOK"})
    client.data_cache_meta.delete_many({"ticker": "TEST_NOLOOK"})
    client.close()


@pytest.fixture
def bus(db):
    from core.data_bus import DataBus
    return DataBus(db, force_refresh=False)


def _insert_prices(db, ticker, dates):
    now = datetime.now(tz=timezone.utc)
    for d in dates:
        db.prices_us.update_one(
            {"ticker": ticker, "date": d},
            {"$set": {"ticker": ticker, "date": d, "close": 100.0,
                      "open": 100.0, "high": 101.0, "low": 99.0, "volume": 1000000,
                      "is_historical": True, "fetched_at": now}},
            upsert=True,
        )


def _insert_financials(db, ticker, periods):
    now = datetime.now(tz=timezone.utc)
    for period, period_end in periods:
        db.financials.update_one(
            {"ticker": ticker, "period": period, "period_end": period_end},
            {"$set": {"ticker": ticker, "market": "US", "period": period,
                      "period_end": period_end, "revenue": 1e9,
                      "is_historical": True, "fetched_at": now}},
            upsert=True,
        )


def test_prices_respect_as_of_date(db, bus):
    """Prices after as_of_date must not appear in the bundle."""
    ticker = "TEST_NOLOOK"
    _insert_prices(db, ticker, ["2023-06-10", "2023-06-14", "2023-06-15", "2023-06-16", "2023-06-20"])

    # Mark cache as fresh so DataBus reads from DB (not live API)
    from datetime import datetime, timezone
    db.data_cache_meta.update_one(
        {"ticker": ticker, "data_type": "prices", "market": "US"},
        {"$set": {"ticker": ticker, "data_type": "prices", "market": "US",
                  "last_fetched": datetime.now(tz=timezone.utc), "ttl_seconds": 86400,
                  "is_stale": False, "record_count": 5}},
        upsert=True,
    )
    db.data_cache_meta.update_one(
        {"ticker": ticker, "data_type": "financials", "market": "US"},
        {"$set": {"ticker": ticker, "data_type": "financials", "market": "US",
                  "last_fetched": datetime.now(tz=timezone.utc), "ttl_seconds": 86400,
                  "is_stale": False, "record_count": 1}},
        upsert=True,
    )
    db.data_cache_meta.update_one(
        {"ticker": ticker, "data_type": "ratios", "market": "US"},
        {"$set": {"ticker": ticker, "data_type": "ratios", "market": "US",
                  "last_fetched": datetime.now(tz=timezone.utc), "ttl_seconds": 86400,
                  "is_stale": False, "record_count": 1}},
        upsert=True,
    )

    bundle = bus._load_from_db(ticker, "2023-06-15")
    price_dates = [p["date"] for p in (bundle.prices if bundle else [])]

    assert "2023-06-16" not in price_dates, "Date after as_of_date must not appear"
    assert "2023-06-20" not in price_dates, "Date after as_of_date must not appear"
    assert "2023-06-15" in price_dates, "as_of_date itself must be included"
    assert "2023-06-14" in price_dates


def test_financials_respect_as_of_date(db):
    """Financial periods with period_end after as_of_date must not appear."""
    ticker = "TEST_NOLOOK"
    _insert_financials(db, ticker, [
        ("2021", "2021-09-30"),
        ("2022", "2022-09-30"),
        ("2023", "2023-09-30"),
        ("2024", "2024-09-30"),
    ])

    from datetime import datetime, timezone
    db.data_cache_meta.update_one(
        {"ticker": ticker, "data_type": "financials", "market": "US"},
        {"$set": {"ticker": ticker, "data_type": "financials", "market": "US",
                  "last_fetched": datetime.now(tz=timezone.utc), "ttl_seconds": 86400,
                  "is_stale": False, "record_count": 4}},
        upsert=True,
    )

    fin_filter = {"ticker": ticker, "market": "US", "period_end": {"$lte": "2023-06-15"}}
    results = list(db.financials.find(fin_filter, {"_id": 0}))
    periods = [r["period"] for r in results]

    assert "2024" not in periods, "Future fiscal year must not appear"
    assert "2023" not in periods, "FY2023 ends 2023-09-30 > 2023-06-15, must not appear"
    assert "2022" in periods
    assert "2021" in periods
