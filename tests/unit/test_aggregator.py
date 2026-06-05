"""
Unit tests for Phase 7 Aggregator:
  - aggregate_signals() weighted vote
  - determine_action() regime-adjusted thresholds + confidence gate
  - size_quantity() proportional sizing
  - Full aggregate() pipeline
"""
from __future__ import annotations
import pytest

from core.engine_base import Signal, TradingDecision
from core.aggregator import Aggregator
from core.risk_engine import PositionLimit


# ─────────────────────────────────────── helpers

_CFG = {
    "aggregator": {
        "buy_threshold_neutral": 0.15,
        "buy_threshold_bearish": 0.25,
        "buy_threshold_bullish": 0.10,
    },
    "macro": {
        "regime_multiplier_bearish": 0.80,
        "regime_multiplier_bullish": 1.10,
    },
    "risk": {
        "min_confidence_to_trade": 40.0,
        "min_coverage_weight":     0.30,
    },
}


def _agg() -> Aggregator:
    return Aggregator(_CFG)


def _sig(signal: str, conf: float, weight: float) -> Signal:
    return Signal(signal=signal, confidence=conf, weight=weight, reasoning="", metadata={})


def _macro_sig(regime: str) -> Signal:
    mult = {"bearish": 0.80, "neutral": 1.0, "bullish": 1.10}[regime]
    return Signal(
        signal=regime, confidence=50.0, weight=0.0,
        reasoning="", metadata={"regime": regime, "multiplier": mult},
    )


def _limit(max_shares: int = 500, price: float = 100.0) -> PositionLimit:
    return PositionLimit(
        ticker="TEST", annualized_vol=0.20, vol_tier="medium_low",
        max_alloc_pct=0.20, corr_multiplier=1.0,
        max_position_usd=20_000.0, max_shares=max_shares,
        current_price=price,
    )


# ─────────────────────────────────────── aggregate_signals

class TestAggregateSignals:

    def test_all_bullish(self):
        sigs = {
            "technical":   _sig("bullish", 70.0, 0.20),
            "fundamental": _sig("bullish", 60.0, 0.15),
        }
        net, conf, total_w, bull_w, bear_w = _agg().aggregate_signals(sigs)
        assert total_w == pytest.approx(0.35)
        assert bull_w  == pytest.approx(0.35)
        assert bear_w  == pytest.approx(0.0)
        assert net     == pytest.approx(1.0)

    def test_all_bearish(self):
        sigs = {
            "technical":   _sig("bearish", 80.0, 0.20),
            "fundamental": _sig("bearish", 70.0, 0.15),
        }
        net, conf, total_w, bull_w, bear_w = _agg().aggregate_signals(sigs)
        assert net == pytest.approx(-1.0)

    def test_mixed_signals(self):
        sigs = {
            "technical":   _sig("bullish", 70.0, 0.20),
            "fundamental": _sig("bearish", 60.0, 0.20),
            "valuation":   _sig("neutral", 50.0, 0.15),
        }
        net, conf, total_w, bull_w, bear_w = _agg().aggregate_signals(sigs)
        # bull=0.20, bear=0.20, neutral=0.15 → total=0.55
        assert total_w == pytest.approx(0.55)
        assert net     == pytest.approx(0.0, abs=0.01)

    def test_macro_context_excluded_from_vote(self):
        sigs = {
            "macro_context": _macro_sig("bullish"),    # weight=0 → excluded
            "technical":     _sig("bullish", 70.0, 0.20),
        }
        net, conf, total_w, bull_w, bear_w = _agg().aggregate_signals(sigs)
        assert total_w == pytest.approx(0.20)
        assert net     == pytest.approx(1.0)

    def test_weight_zero_excluded(self):
        sigs = {
            "macro_context": _macro_sig("neutral"),  # weight=0
            "technical":     _sig("bearish", 75.0, 0.20),
        }
        net, conf, total_w, bull_w, bear_w = _agg().aggregate_signals(sigs)
        assert total_w == pytest.approx(0.20)

    def test_weighted_confidence(self):
        sigs = {
            "technical":   _sig("bullish", 80.0, 0.20),
            "fundamental": _sig("neutral", 50.0, 0.10),
        }
        _, avg_conf, total_w, _, _ = _agg().aggregate_signals(sigs)
        # (80*0.20 + 50*0.10) / 0.30 = (16+5)/0.30 = 70.0
        assert avg_conf == pytest.approx(70.0)

    def test_empty_signals_returns_zeros(self):
        net, conf, total_w, bull_w, bear_w = _agg().aggregate_signals({})
        assert total_w == 0.0
        assert net     == 0.0


# ─────────────────────────────────────── determine_action

class TestDetermineAction:

    def test_buy_when_above_neutral_threshold(self):
        action = _agg().determine_action(0.20, 60.0, "neutral", "TEST")
        assert action == "buy"

    def test_buy_when_above_bullish_threshold(self):
        action = _agg().determine_action(0.12, 60.0, "bullish", "TEST")
        assert action == "buy"

    def test_hold_below_bullish_threshold(self):
        action = _agg().determine_action(0.08, 60.0, "bullish", "TEST")
        assert action == "hold"

    def test_sell_when_below_neutral_threshold_with_long(self):
        portfolio = {"TEST": 100}   # existing long
        action = _agg().determine_action(-0.20, 60.0, "neutral", "TEST", portfolio)
        assert action == "sell"

    def test_hold_when_below_threshold_no_position(self):
        """No long position → no SELL, no SHORT in Phase 7 → HOLD."""
        action = _agg().determine_action(-0.20, 60.0, "neutral", "TEST")
        assert action == "hold"

    def test_hold_when_confidence_below_minimum(self):
        action = _agg().determine_action(0.50, 35.0, "neutral", "TEST")
        assert action == "hold"

    def test_cover_when_above_threshold_with_short(self):
        portfolio = {"TEST": -50}   # existing short
        action = _agg().determine_action(0.20, 60.0, "neutral", "TEST", portfolio)
        assert action == "cover"

    def test_bearish_regime_requires_higher_threshold(self):
        # 0.20 net_score: above neutral(0.15) but below bearish(0.25) threshold
        action = _agg().determine_action(0.20, 60.0, "bearish", "TEST")
        assert action == "hold"

    def test_bullish_regime_lower_threshold(self):
        # 0.11 net_score: above bullish(0.10) threshold
        action = _agg().determine_action(0.11, 60.0, "bullish", "TEST")
        assert action == "buy"


# ─────────────────────────────────────── size_quantity

class TestSizeQuantity:

    def test_hold_returns_zero(self):
        q = _agg().size_quantity("hold", 80.0, _limit())
        assert q == 0

    def test_buy_proportional_to_confidence(self):
        q = _agg().size_quantity("buy", 80.0, _limit(max_shares=500))
        assert q == 400   # 500 * 0.80

    def test_buy_minimum_one(self):
        q = _agg().size_quantity("buy", 1.0, _limit(max_shares=50))
        assert q >= 1

    def test_buy_capped_at_max_shares(self):
        q = _agg().size_quantity("buy", 100.0, _limit(max_shares=300))
        assert q == 300

    def test_sell_returns_existing_position(self):
        portfolio = {"TEST": 150}
        q = _agg().size_quantity("sell", 80.0, _limit(), portfolio, "TEST")
        assert q == 150

    def test_cover_returns_short_size(self):
        portfolio = {"TEST": -80}
        q = _agg().size_quantity("cover", 60.0, _limit(), portfolio, "TEST")
        assert q == 80

    def test_no_risk_limit_returns_zero(self):
        q = _agg().size_quantity("buy", 80.0, None)
        assert q == 0


# ─────────────────────────────────────── full aggregate pipeline

class TestAggregatePipeline:

    def _signals_high_coverage_bullish(self, regime: str = "neutral") -> dict:
        return {
            "macro_context": _macro_sig(regime),
            "technical":     _sig("bullish", 75.0, 0.20),
            "fundamental":   _sig("bullish", 65.0, 0.15),
            "valuation":     _sig("bullish", 70.0, 0.15),
            "earnings_quality": _sig("neutral", 50.0, 0.10),
        }

    def test_buy_decision_sufficient_coverage(self):
        sigs = self._signals_high_coverage_bullish()
        dec = _agg().aggregate("AAPL", sigs, risk_limit=_limit(500))
        assert dec.action == "buy"
        assert dec.ticker == "AAPL"
        assert dec.quantity > 0

    def test_hold_due_to_low_coverage(self):
        sigs = {
            "macro_context": _macro_sig("neutral"),
            "technical":     _sig("bullish", 80.0, 0.20),  # only 0.20 weight
        }
        dec = _agg().aggregate("TST", sigs, risk_limit=_limit(500))
        assert dec.action == "hold"
        assert "coverage" in dec.reasoning.lower()

    def test_hold_due_to_low_confidence(self):
        sigs = {
            "technical":   _sig("bullish", 30.0, 0.20),
            "fundamental": _sig("bullish", 25.0, 0.20),
            "valuation":   _sig("neutral", 20.0, 0.15),
        }
        dec = _agg().aggregate("TST", sigs, risk_limit=_limit(500))
        # avg confidence will be < 40 → HOLD
        assert dec.action == "hold"

    def test_macro_regime_in_decision(self):
        sigs = self._signals_high_coverage_bullish("bearish")
        dec = _agg().aggregate("AAPL", sigs, risk_limit=_limit(500))
        assert dec.macro_regime == "bearish"

    def test_bearish_regime_reduces_buy_confidence(self):
        # With bearish regime, bullish confidences are ×0.80 before vote
        sigs_neutral = self._signals_high_coverage_bullish("neutral")
        sigs_bearish = self._signals_high_coverage_bullish("bearish")
        dec_n = _agg().aggregate("X", sigs_neutral, risk_limit=_limit(500))
        dec_b = _agg().aggregate("X", sigs_bearish, risk_limit=_limit(500))
        # Bearish regime should result in equal or lower confidence
        assert dec_b.confidence <= dec_n.confidence + 1.0  # allow tiny rounding

    def test_net_score_stored_in_decision(self):
        sigs = self._signals_high_coverage_bullish()
        dec = _agg().aggregate("AAPL", sigs, risk_limit=_limit(500))
        assert dec.net_score > 0

    def test_sell_with_existing_long_position(self):
        portfolio = {"AAPL": 200}  # existing long
        sigs = {
            "macro_context": _macro_sig("neutral"),
            "technical":   _sig("bearish", 75.0, 0.20),
            "fundamental": _sig("bearish", 70.0, 0.20),
            "valuation":   _sig("bearish", 65.0, 0.15),
        }
        dec = _agg().aggregate("AAPL", sigs, risk_limit=_limit(500), portfolio=portfolio)
        assert dec.action == "sell"
        assert dec.quantity == 200   # close full position

    def test_reasoning_contains_net_score(self):
        sigs = self._signals_high_coverage_bullish()
        dec = _agg().aggregate("AAPL", sigs, risk_limit=_limit(500))
        assert "net_score" in dec.reasoning

    def test_signals_dict_contains_adjusted_confidences(self):
        """Bullish regime boost is visible in the decision.signals dict."""
        sigs = {
            "macro_context": _macro_sig("bullish"),   # mult=1.10
            "technical":     _sig("bullish", 80.0, 0.20),
            "fundamental":   _sig("bullish", 70.0, 0.15),
            "valuation":     _sig("bullish", 60.0, 0.15),
        }
        dec = _agg().aggregate("X", sigs, risk_limit=_limit(500))
        # Technical confidence should be 80 * 1.10 = 88 (capped at 100)
        assert dec.signals["technical"].confidence == pytest.approx(88.0)

    def test_price_from_risk_limit(self):
        sigs = self._signals_high_coverage_bullish()
        dec = _agg().aggregate("AAPL", sigs, risk_limit=_limit(500, price=175.0))
        assert dec.price == pytest.approx(175.0)
