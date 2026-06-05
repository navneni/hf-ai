"""
Unit tests for Phase 6:
  - MacroContextEngine regime classification
  - InstitutionalFlowEngine signal computation
  - Aggregator macro multiplier application
"""
from __future__ import annotations
import pytest
from dataclasses import replace

from core.engine_base import DataBundle, Signal
from signals.macro_context import MacroContextEngine
from signals.institutional_flow import InstitutionalFlowEngine
from core.aggregator import Aggregator


# ─────────────────────────────────────── fixtures

def _bundle(macro: dict, inst_flow_us: dict | None = None, market: str = "US") -> DataBundle:
    return DataBundle(
        ticker="TEST",
        market=market,
        as_of_date="2025-01-15",
        macro=macro,
        inst_flow_us=inst_flow_us,
    )


def _macro_engine(thresholds: dict | None = None) -> MacroContextEngine:
    eng = MacroContextEngine()
    cfg = {"macro": thresholds or {}}
    eng.initialize(cfg)
    return eng


def _inst_engine() -> InstitutionalFlowEngine:
    eng = InstitutionalFlowEngine()
    eng.initialize({})
    return eng


# ─────────────────────────────────────── MacroContextEngine

class TestMacroContextEngine:

    def test_bearish_regime_all_factors(self):
        macro = {
            "vix": 38.0,             # > 30 → bearish
            "yield_spread": -0.005,  # inverted → bearish
            "sp500_vs_200ma": -0.08, # -8% → bearish
            "market_breadth": 0.20,  # 20% → bearish
        }
        sig = _macro_engine().compute(_bundle(macro))
        assert sig.signal == "bearish"
        assert sig.metadata["regime"] == "bearish"
        assert sig.metadata["multiplier"] < 1.0

    def test_bullish_regime_all_factors(self):
        macro = {
            "vix": 14.0,             # < 20 → bullish
            "yield_spread": 0.010,   # normal → bullish
            "sp500_vs_200ma": 0.08,  # +8% → bullish
            "market_breadth": 0.80,  # 80% → bullish
        }
        sig = _macro_engine().compute(_bundle(macro))
        assert sig.signal == "bullish"
        assert sig.metadata["regime"] == "bullish"
        assert sig.metadata["multiplier"] > 1.0

    def test_neutral_regime_mixed_factors(self):
        macro = {
            "vix": 25.0,             # neutral (20–30)
            "yield_spread": 0.005,   # neutral (slight positive)
            "sp500_vs_200ma": 0.01,  # neutral (-5% to +5%)
            "market_breadth": 0.50,  # neutral
        }
        sig = _macro_engine().compute(_bundle(macro))
        assert sig.signal == "neutral"
        assert sig.metadata["multiplier"] == 1.0

    def test_bearish_with_only_two_factors(self):
        # 2 bearish + 1 neutral (no bullish → bearish regime)
        macro = {
            "vix": 35.0,             # bearish
            "yield_spread": -0.008,  # bearish
            "sp500_vs_200ma": 0.02,  # neutral
        }
        sig = _macro_engine().compute(_bundle(macro))
        assert sig.signal == "bearish"

    def test_neutral_when_one_bearish_one_bullish(self):
        macro = {
            "vix": 38.0,            # bearish
            "yield_spread": 0.015,  # bullish
            "sp500_vs_200ma": 0.02, # neutral
        }
        sig = _macro_engine().compute(_bundle(macro))
        assert sig.signal == "neutral"

    def test_validate_data_empty_macro(self):
        eng = _macro_engine()
        bundle = _bundle({})
        assert eng.validate_data(bundle) is False

    def test_validate_data_with_macro(self):
        eng = _macro_engine()
        bundle = _bundle({"vix": 20.0})
        assert eng.validate_data(bundle) is True

    def test_weight_is_zero(self):
        assert MacroContextEngine.weight == 0.0

    def test_metadata_contains_factor_votes(self):
        macro = {
            "vix": 35.0,
            "yield_spread": -0.010,
            "sp500_vs_200ma": -0.07,
        }
        sig = _macro_engine().compute(_bundle(macro))
        assert "factor_votes" in sig.metadata
        assert len(sig.metadata["factor_votes"]) == 3
        assert sig.metadata["factor_votes"].count("bearish") >= 2

    def test_custom_thresholds_respected(self):
        # Override: bearish only if VIX > 40
        thresholds = {"vix_bearish_threshold": 40}
        macro = {"vix": 35.0, "yield_spread": 0.005}  # VIX < 40 custom threshold
        sig = _macro_engine(thresholds).compute(_bundle(macro))
        # VIX 35 should be neutral with custom threshold of 40
        votes = sig.metadata["factor_votes"]
        assert votes[0] == "neutral"


# ─────────────────────────────────────── InstitutionalFlowEngine

class TestInstitutionalFlowEngine:

    def test_squeeze_setup_bullish(self):
        flow = {
            "si_pct": 0.18,           # > 15%
            "si_biweekly_change": -0.06,  # covering → squeeze
            "pc_ratio": None,
            "iv_rank": None,
        }
        sig = _inst_engine().compute(_bundle({}, inst_flow_us=flow))
        assert sig.signal == "bullish"

    def test_high_pc_ratio_contrarian_bullish(self):
        flow = {"pc_ratio": 2.0, "si_pct": 0.05}  # extreme put buying
        sig = _inst_engine().compute(_bundle({}, inst_flow_us=flow))
        assert sig.signal == "bullish"

    def test_low_pc_ratio_caution(self):
        flow = {"pc_ratio": 0.30, "si_pct": 0.25}  # extreme call buying + high SI
        sig = _inst_engine().compute(_bundle({}, inst_flow_us=flow))
        assert sig.signal in ("bearish", "neutral")

    def test_high_iv_rank_caution(self):
        flow = {"iv_rank": 90.0, "pc_ratio": None, "si_pct": 0.05}
        sig = _inst_engine().compute(_bundle({}, inst_flow_us=flow))
        # High IV alone may not be enough for bearish but should drag confidence
        assert sig.signal in ("bearish", "neutral")

    def test_no_data_returns_neutral(self):
        sig = _inst_engine().compute(_bundle({}, inst_flow_us={}))
        assert sig.signal == "neutral"
        assert sig.confidence <= 35.0

    def test_india_market_skipped(self):
        sig = _inst_engine().compute(_bundle({}, market="IN"))
        assert sig.signal == "neutral"

    def test_validate_india_returns_true(self):
        # India path implemented in Phase 9 — validate returns True
        eng = _inst_engine()
        assert eng.validate_data(_bundle({}, market="IN")) is True

    def test_validate_us_returns_true(self):
        eng = _inst_engine()
        assert eng.validate_data(_bundle({})) is True

    def test_metadata_contains_net_score(self):
        flow = {"si_pct": 0.20, "si_biweekly_change": -0.08, "pc_ratio": 1.8}
        sig = _inst_engine().compute(_bundle({}, inst_flow_us=flow))
        assert "net_score" in sig.metadata

    def test_high_inst_ownership_bullish_contribution(self):
        flow = {"inst_ownership_pct": 0.80}
        sig = _inst_engine().compute(_bundle({}, inst_flow_us=flow))
        assert sig.metadata["net_score"] > 0


# ─────────────────────────────────────── Aggregator

class TestAggregator:

    _CFG = {
        "aggregator": {"buy_threshold_neutral": 0.15, "buy_threshold_bearish": 0.25,
                       "buy_threshold_bullish": 0.10},
        "macro": {"regime_multiplier_bearish": 0.80, "regime_multiplier_bullish": 1.10},
        "risk": {"min_confidence_to_trade": 40.0, "min_coverage_weight": 0.30},
    }

    def _agg(self):
        return Aggregator(self._CFG)

    def _macro_signal(self, regime: str) -> Signal:
        mult = {"bearish": 0.80, "neutral": 1.0, "bullish": 1.10}[regime]
        return Signal(
            signal=regime, confidence=50.0, weight=0.0,
            reasoning="macro test",
            metadata={"regime": regime, "multiplier": mult},
        )

    def test_get_macro_regime_bullish(self):
        sigs = {"macro_context": self._macro_signal("bullish")}
        regime, mult = self._agg().get_macro_regime(sigs)
        assert regime == "bullish"
        assert mult == pytest.approx(1.10)

    def test_get_macro_regime_bearish(self):
        sigs = {"macro_context": self._macro_signal("bearish")}
        regime, mult = self._agg().get_macro_regime(sigs)
        assert regime == "bearish"
        assert mult == pytest.approx(0.80)

    def test_get_macro_regime_absent(self):
        regime, mult = self._agg().get_macro_regime({})
        assert regime == "neutral"
        assert mult == 1.0

    def test_apply_multiplier_reduces_bullish_confidence(self):
        bullish_sig = Signal("bullish", 80.0, 0.15, "", {})
        sigs = {"technical": bullish_sig}
        adjusted = self._agg().apply_regime_multiplier(sigs, "bearish", 0.80)
        assert adjusted["technical"].confidence == pytest.approx(64.0)  # 80 * 0.80

    def test_apply_multiplier_boosts_bullish_confidence(self):
        bullish_sig = Signal("bullish", 80.0, 0.15, "", {})
        sigs = {"technical": bullish_sig}
        adjusted = self._agg().apply_regime_multiplier(sigs, "bullish", 1.10)
        assert adjusted["technical"].confidence == pytest.approx(88.0)  # 80 * 1.10

    def test_apply_multiplier_caps_at_100(self):
        bullish_sig = Signal("bullish", 95.0, 0.15, "", {})
        sigs = {"technical": bullish_sig}
        adjusted = self._agg().apply_regime_multiplier(sigs, "bullish", 1.10)
        assert adjusted["technical"].confidence <= 100.0

    def test_apply_multiplier_does_not_change_bearish_signals(self):
        bearish_sig = Signal("bearish", 75.0, 0.15, "", {})
        sigs = {"technical": bearish_sig}
        adjusted = self._agg().apply_regime_multiplier(sigs, "bearish", 0.80)
        assert adjusted["technical"].confidence == pytest.approx(75.0)

    def test_apply_multiplier_neutral_no_change(self):
        bullish_sig = Signal("bullish", 70.0, 0.15, "", {})
        sigs = {"technical": bullish_sig}
        adjusted = self._agg().apply_regime_multiplier(sigs, "neutral", 1.0)
        assert adjusted["technical"].confidence == pytest.approx(70.0)

    def test_macro_context_unchanged_by_multiplier(self):
        sigs = {"macro_context": self._macro_signal("bearish")}
        adjusted = self._agg().apply_regime_multiplier(sigs, "bearish", 0.80)
        assert adjusted["macro_context"].confidence == pytest.approx(50.0)

    def test_aggregate_returns_macro_regime_in_decision(self):
        sigs = {
            "macro_context": self._macro_signal("bearish"),
            "technical": Signal("bullish", 70.0, 0.20, "", {}),
        }
        decision = self._agg().aggregate("AAPL", sigs)
        assert decision.macro_regime == "bearish"
        assert decision.ticker == "AAPL"
        # Phase 6 stub — still returns hold
        assert decision.action == "hold"

    def test_aggregate_with_bullish_macro_adjusts_signals(self):
        sigs = {
            "macro_context": self._macro_signal("bullish"),
            "technical": Signal("bullish", 80.0, 0.20, "", {}),
        }
        decision = self._agg().aggregate("MSFT", sigs)
        adjusted_conf = decision.signals["technical"].confidence
        assert adjusted_conf == pytest.approx(88.0)  # 80 * 1.10
