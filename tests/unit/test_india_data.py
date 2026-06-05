"""
Unit tests for Phase 9 — India Data Layer.
Tests engine routing, signal computation with India DataBundles,
and India-specific signal logic. All tests are offline (no live API calls).
"""
from __future__ import annotations
import pytest
from datetime import date

from core.engine_base import DataBundle, Signal
from signals.macro_context import MacroContextEngine
from signals.institutional_flow import InstitutionalFlowEngine
from signals.insider_sentiment import InsiderSentimentEngine


# ─────────────────────────────────────── helpers

def _india_bundle(
    macro: dict | None = None,
    inst_flow_india: dict | None = None,
    promoter_holdings: list | None = None,
    bulk_deals: list | None = None,
    prices: list | None = None,
    financials: list | None = None,
    insider_trades: list | None = None,
) -> DataBundle:
    return DataBundle(
        ticker="TCS.NS",
        market="IN",
        as_of_date="2025-01-15",
        prices=prices or [],
        financials=financials or [],
        macro=macro or {},
        inst_flow_india=inst_flow_india,
        promoter_holdings=promoter_holdings,
        bulk_deals=bulk_deals or [],
        insider_trades=insider_trades,
    )


def _macro_engine() -> MacroContextEngine:
    eng = MacroContextEngine()
    eng.initialize({"macro": {}})
    return eng


def _inst_engine() -> InstitutionalFlowEngine:
    eng = InstitutionalFlowEngine()
    eng.initialize({})
    return eng


def _insider_engine() -> InsiderSentimentEngine:
    eng = InsiderSentimentEngine()
    eng.initialize({})
    return eng


# ─────────────────────────────────────── MacroContextEngine — India path

class TestIndiaMacroContext:

    def test_india_bearish_regime(self):
        macro = {
            "india_vix": 25.0,        # > 20 → bearish
            "nifty_vs_200ma": -0.08,  # below 200d → bearish
            "usdinr_30d_change": 0.03, # INR weakening → bearish
            "net_fii_5d": -5000,      # FII selling → bearish
        }
        sig = _macro_engine().compute(_india_bundle(macro))
        assert sig.signal == "bearish"
        assert sig.metadata["regime"] == "bearish"
        assert sig.metadata["multiplier"] < 1.0

    def test_india_bullish_regime(self):
        macro = {
            "india_vix": 11.0,        # < 13 → bullish
            "nifty_vs_200ma": 0.08,   # above 200d → bullish
            "usdinr_30d_change": -0.015,  # INR strengthening → bullish
            "net_fii_5d": 4000,       # FII buying → bullish
        }
        sig = _macro_engine().compute(_india_bundle(macro))
        assert sig.signal == "bullish"
        assert sig.metadata["multiplier"] > 1.0

    def test_india_neutral_mixed(self):
        macro = {
            "india_vix": 16.0,       # neutral (13–20)
            "nifty_vs_200ma": 0.02,  # neutral
            "usdinr_30d_change": 0.005,  # neutral
        }
        sig = _macro_engine().compute(_india_bundle(macro))
        assert sig.signal == "neutral"

    def test_india_high_vix_bearish(self):
        macro = {"india_vix": 28.0, "nifty_vs_200ma": -0.07}
        sig = _macro_engine().compute(_india_bundle(macro))
        assert sig.signal == "bearish"

    def test_india_macro_metadata_has_india_vix(self):
        macro = {"india_vix": 16.0, "nifty_vs_200ma": 0.04}
        sig = _macro_engine().compute(_india_bundle(macro))
        assert "india_vix" in sig.metadata

    def test_india_validate_empty_macro(self):
        eng = _macro_engine()
        assert eng.validate_data(_india_bundle({})) is False

    def test_india_validate_with_macro(self):
        eng = _macro_engine()
        assert eng.validate_data(_india_bundle({"india_vix": 15.0})) is True

    def test_india_path_triggered_for_in_market(self):
        macro = {"india_vix": 28.0, "nifty_vs_200ma": -0.10}
        sig = _macro_engine().compute(_india_bundle(macro))
        # India VIX > 20 and Nifty below 200MA → bearish
        assert sig.signal == "bearish"

    def test_us_path_still_works(self):
        """Confirm US path not broken by India addition."""
        us_bundle = DataBundle(
            ticker="AAPL", market="US", as_of_date="2025-01-15",
            macro={"vix": 35.0, "yield_spread": -0.005, "sp500_vs_200ma": -0.08},
        )
        sig = _macro_engine().compute(us_bundle)
        assert sig.signal == "bearish"


# ─────────────────────────────────────── InstitutionalFlowEngine — India path

class TestIndiaInstitutionalFlow:

    def test_fii_buying_bullish(self):
        flow = {
            "net_fii_5d": 6000,   # large FII net buy (Cr)
            "net_dii_5d": 1000,
        }
        sig = _inst_engine().compute(_india_bundle(inst_flow_india=flow))
        assert sig.signal == "bullish"

    def test_fii_selling_bearish(self):
        flow = {"net_fii_5d": -7000, "net_dii_5d": 500}
        sig = _inst_engine().compute(_india_bundle(inst_flow_india=flow))
        assert sig.signal == "bearish"

    def test_fii_neutral_range(self):
        flow = {"net_fii_5d": 500, "net_dii_5d": -200}
        sig = _inst_engine().compute(_india_bundle(inst_flow_india=flow))
        assert sig.signal == "neutral"

    def test_no_india_data_returns_neutral(self):
        sig = _inst_engine().compute(_india_bundle(inst_flow_india={}))
        assert sig.signal == "neutral"

    def test_india_validate_returns_true(self):
        assert _inst_engine().validate_data(_india_bundle()) is True

    def test_india_metadata_has_path(self):
        flow = {"net_fii_5d": 3000}
        sig = _inst_engine().compute(_india_bundle(inst_flow_india=flow))
        assert sig.metadata.get("path") == "IN"

    def test_bulk_deals_buy_bullish_contribution(self):
        bulk = [
            {"date": "2025-01-10", "buy_sell": "buy", "quantity": 1_000_000, "price": 3500.0},
            {"date": "2025-01-11", "buy_sell": "buy", "quantity": 500_000,   "price": 3520.0},
        ]
        sig = _inst_engine().compute(_india_bundle(
            inst_flow_india={"net_fii_5d": 3000},
            bulk_deals=bulk,
        ))
        assert sig.signal in ("bullish", "neutral")  # FII buying + bulk buys = bullish

    def test_us_path_unchanged(self):
        """US path still works after India path added."""
        us_bundle = DataBundle(
            ticker="AAPL", market="US", as_of_date="2025-01-15",
            inst_flow_us={"si_pct": 0.20, "si_biweekly_change": -0.08, "pc_ratio": None},
        )
        sig = _inst_engine().compute(us_bundle)
        assert sig.signal == "bullish"   # short squeeze setup


# ─────────────────────────────────────── InsiderSentimentEngine

class TestInsiderSentimentEngine:

    # ── US path

    def _us_bundle(self, trades: list) -> DataBundle:
        return DataBundle(
            ticker="AAPL", market="US", as_of_date="2025-01-15",
            insider_trades=trades,
        )

    def test_us_net_buyers_bullish(self):
        trades = [
            {"transaction_date": "2025-01-10", "transaction_type": "buy",
             "value": 500_000, "is_open_market": True},
            {"transaction_date": "2025-01-05", "transaction_type": "buy",
             "value": 300_000, "is_open_market": True},
        ]
        sig = _insider_engine().compute(self._us_bundle(trades))
        assert sig.signal == "bullish"

    def test_us_net_sellers_bearish(self):
        trades = [
            {"transaction_date": "2025-01-10", "transaction_type": "sell",
             "value": 1_000_000, "is_open_market": True},
            {"transaction_date": "2025-01-05", "transaction_type": "sell",
             "value": 800_000, "is_open_market": True},
        ]
        sig = _insider_engine().compute(self._us_bundle(trades))
        assert sig.signal == "bearish"

    def test_us_mixed_neutral(self):
        trades = [
            {"transaction_date": "2025-01-10", "transaction_type": "buy",
             "value": 100_000, "is_open_market": True},
            {"transaction_date": "2025-01-05", "transaction_type": "sell",
             "value": 90_000, "is_open_market": True},
        ]
        sig = _insider_engine().compute(self._us_bundle(trades))
        assert sig.signal == "neutral"

    def test_us_no_trades_neutral(self):
        sig = _insider_engine().compute(self._us_bundle([]))
        assert sig.signal == "neutral"

    def test_us_validate_true_with_trades(self):
        trades = [{"transaction_date": "2025-01-10", "transaction_type": "buy",
                   "value": 100_000, "is_open_market": True}]
        assert _insider_engine().validate_data(self._us_bundle(trades)) is True

    def test_us_validate_false_no_trades(self):
        assert _insider_engine().validate_data(self._us_bundle([])) is False

    # ── India path

    def test_india_promoter_increasing_bullish(self):
        holdings = [
            {"quarter": "2024-12", "promoter_pct": 72.5},
            {"quarter": "2024-09", "promoter_pct": 71.8},
        ]
        sig = _insider_engine().compute(_india_bundle(promoter_holdings=holdings))
        assert sig.signal == "bullish"

    def test_india_promoter_decreasing_bearish(self):
        holdings = [
            {"quarter": "2024-12", "promoter_pct": 65.0},
            {"quarter": "2024-09", "promoter_pct": 66.5},
        ]
        sig = _insider_engine().compute(_india_bundle(promoter_holdings=holdings))
        assert sig.signal == "bearish"

    def test_india_promoter_stable_neutral(self):
        holdings = [
            {"quarter": "2024-12", "promoter_pct": 60.2},
            {"quarter": "2024-09", "promoter_pct": 60.1},
        ]
        sig = _insider_engine().compute(_india_bundle(promoter_holdings=holdings))
        assert sig.signal == "neutral"

    def test_india_high_promoter_holding_bullish(self):
        """Promoter >70% with stable holding → slight bullish bias."""
        holdings = [
            {"quarter": "2024-12", "promoter_pct": 72.3},
            {"quarter": "2024-09", "promoter_pct": 72.1},
        ]
        sig = _insider_engine().compute(_india_bundle(promoter_holdings=holdings))
        assert sig.signal == "bullish"   # stable but >70% → bullish tilt

    def test_india_no_holdings_neutral(self):
        sig = _insider_engine().compute(_india_bundle(promoter_holdings=[]))
        assert sig.signal == "neutral"

    def test_india_validate_with_holdings(self):
        holdings = [{"quarter": "2024-12", "promoter_pct": 65.0}]
        assert _insider_engine().validate_data(_india_bundle(promoter_holdings=holdings)) is True

    def test_india_validate_false_no_holdings(self):
        assert _insider_engine().validate_data(_india_bundle(promoter_holdings=[])) is False

    def test_india_metadata_has_path(self):
        holdings = [
            {"quarter": "2024-12", "promoter_pct": 68.0},
            {"quarter": "2024-09", "promoter_pct": 67.0},
        ]
        sig = _insider_engine().compute(_india_bundle(promoter_holdings=holdings))
        assert sig.metadata.get("path") == "IN"


# ─────────────────────────────────────── market routing

class TestMarketRouting:

    def test_india_ticker_detected(self):
        from data.market_config import get_market_config
        assert get_market_config("TCS.NS").country == "IN"
        assert get_market_config("RELIANCE.BO").country == "IN"
        assert get_market_config("AAPL").country == "US"
        assert get_market_config("MSFT").country == "US"

    def test_india_config_fields(self):
        from data.market_config import get_market_config
        mc = get_market_config("TCS.NS")
        assert mc.currency == "INR"
        assert mc.risk_free_rate > 0.06   # India rate higher than US
        assert mc.vix_ticker == "INDIAVIX.NS"
        assert mc.benchmark_ticker == "^NSEI"
