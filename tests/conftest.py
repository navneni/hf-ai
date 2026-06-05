"""Shared pytest fixtures for unit and integration tests."""
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_prices():
    with open(FIXTURES_DIR / "sample_prices.json") as f:
        return json.load(f)


@pytest.fixture
def sample_financials():
    with open(FIXTURES_DIR / "sample_financials.json") as f:
        return json.load(f)


@pytest.fixture
def sample_ratios():
    with open(FIXTURES_DIR / "sample_ratios.json") as f:
        return json.load(f)


@pytest.fixture
def sample_data_bundle(sample_prices, sample_financials, sample_ratios):
    from core.engine_base import DataBundle
    return DataBundle(
        ticker="AAPL",
        market="US",
        as_of_date="2024-01-15",
        prices=sample_prices,
        financials=sample_financials,
        ratios=sample_ratios,
        market_config={"country": "US", "trading_days": 252, "risk_free_rate": 0.053},
    )


@pytest.fixture
def config_file(tmp_path):
    """Write a minimal engine.yaml to a temp dir and return its path."""
    yaml_content = """
mongodb:
  uri: "mongodb://localhost:27017"
  db_name: "hf_ai_engine_test"
markets:
  US:
    trading_days: 252
    benchmark: "^GSPC"
    vix_ticker: "^VIX"
    risk_free_rate: 0.053
    currency: "USD"
engines:
  technical: {enabled: true, weight: 0.20}
risk:
  min_confidence_to_trade: 40.0
  min_coverage_weight: 0.30
monitoring:
  log_level: WARNING
  log_file: "logs/test.log"
"""
    p = tmp_path / "engine.yaml"
    p.write_text(yaml_content)
    return str(p)
