"""
Signal Aggregator — Phase 7: full weighted-vote + action determination + quantity sizing.

Flow per ticker:
  1. Extract MacroRegime from macro_context engine metadata.
  2. Apply regime multiplier to all bullish signal confidences.
  3. Weight-renormalize over voting engines (weight > 0, not macro_context).
  4. Coverage gate: total_weight < 0.30 → HOLD (insufficient signal coverage).
  5. Compute net_score = (bullish_weight − bearish_weight) / total_weight.
  6. Compute avg_confidence (weighted average over voting engines).
  7. Confidence gate: avg_conf < 40 → HOLD.
  8. Regime-adjusted threshold: bearish=0.25, neutral=0.15, bullish=0.10.
  9. Action: BUY / SELL / COVER / HOLD (SHORT deferred to Phase 8).
  10. Quantity: floor(max_shares × confidence/100), minimum 1.
"""
from __future__ import annotations
import logging
from typing import Optional

from core.engine_base import Signal, TradingDecision

logger = logging.getLogger(__name__)


class Aggregator:
    """Full signal aggregator with macro regime adjustment and risk-aware sizing."""

    def __init__(self, config: dict):
        agg  = config.get("aggregator", {})
        mac  = config.get("macro",      {})
        risk = config.get("risk",       {})

        self.buy_threshold: dict[str, float] = {
            "neutral": float(agg.get("buy_threshold_neutral", 0.15)),
            "bearish": float(agg.get("buy_threshold_bearish", 0.25)),
            "bullish": float(agg.get("buy_threshold_bullish", 0.10)),
        }
        self.regime_multiplier: dict[str, float] = {
            "bearish": float(mac.get("regime_multiplier_bearish", 0.80)),
            "neutral": 1.0,
            "bullish": float(mac.get("regime_multiplier_bullish", 1.10)),
        }
        self.min_confidence = float(risk.get("min_confidence_to_trade", 40.0))
        self.min_coverage   = float(risk.get("min_coverage_weight",      0.30))

    # ─────────────────────────────────── public API

    def get_macro_regime(self, signals: dict[str, Signal]) -> tuple[str, float]:
        """
        Extract regime and multiplier from macro_context signal metadata.
        Returns ("neutral", 1.0) when macro_context is absent.
        """
        macro_sig = signals.get("macro_context")
        if macro_sig is not None and macro_sig.metadata:
            regime     = macro_sig.metadata.get("regime",     "neutral")
            multiplier = macro_sig.metadata.get("multiplier", 1.0)
            return regime, float(multiplier)
        return "neutral", 1.0

    def apply_regime_multiplier(
        self,
        signals: dict[str, Signal],
        regime: str,
        multiplier: float,
    ) -> dict[str, Signal]:
        """
        Scale bullish signal confidences by the macro regime multiplier.
        macro_context is never modified (weight=0.0, metadata-only).
        """
        if multiplier == 1.0:
            return signals

        from dataclasses import replace
        adjusted: dict[str, Signal] = {}
        for name, sig in signals.items():
            if name == "macro_context" or sig.signal != "bullish":
                adjusted[name] = sig
            else:
                new_conf = min(100.0, sig.confidence * multiplier)
                adjusted[name] = replace(sig, confidence=round(new_conf, 2))
        return adjusted

    def aggregate_signals(
        self, signals: dict[str, Signal]
    ) -> tuple[float, float, float, float]:
        """
        Compute weighted vote statistics over voting engines.
        Returns: (net_score, avg_confidence, total_weight, bull_weight, bear_weight)
        Actually returns 5-tuple: (net_score, avg_conf, total_w, bull_w, bear_w).
        """
        voting = {
            k: v for k, v in signals.items()
            if k != "macro_context" and v.weight > 0
        }
        total_w = sum(v.weight for v in voting.values())
        if total_w == 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0

        bull_w   = sum(v.weight for v in voting.values() if v.signal == "bullish")
        bear_w   = sum(v.weight for v in voting.values() if v.signal == "bearish")
        net      = (bull_w - bear_w) / total_w
        avg_conf = sum(v.confidence * v.weight for v in voting.values()) / total_w
        return net, avg_conf, total_w, bull_w, bear_w

    def determine_action(
        self,
        net_score: float,
        confidence: float,
        regime: str,
        ticker: str,
        portfolio: Optional[dict] = None,
    ) -> str:
        """
        Map (net_score, confidence, regime) → action string.

        BUY   : net_score ≥ threshold AND no existing short position
        COVER : net_score ≥ threshold AND existing short position
        SELL  : net_score ≤ −threshold AND existing long position
        HOLD  : everything else (includes: low confidence, in the dead band,
                no long to sell, no short defined yet)

        SHORT is not generated in Phase 7; it requires Phase 8 portfolio state tracking.
        """
        if confidence < self.min_confidence:
            return "hold"

        threshold = self.buy_threshold.get(regime, self.buy_threshold["neutral"])
        pos = int((portfolio or {}).get(ticker, 0))

        if net_score >= threshold:
            return "cover" if pos < 0 else "buy"
        if net_score <= -threshold:
            return "sell" if pos > 0 else "hold"
        return "hold"

    def size_quantity(
        self,
        action: str,
        confidence: float,
        risk_limit,    # PositionLimit | None
        portfolio: Optional[dict] = None,
        ticker: str = "",
    ) -> int:
        """
        Quantity = floor(max_shares × confidence / 100), minimum 1.
        SELL/COVER quantity = existing position size (close in full).
        HOLD / no risk limit → 0.
        """
        if action == "hold":
            return 0
        if action in ("sell", "cover"):
            pos = abs(int((portfolio or {}).get(ticker, 0)))
            return pos if pos > 0 else 0
        if risk_limit is None or risk_limit.max_shares == 0:
            return 0
        qty = int(risk_limit.max_shares * confidence / 100.0)
        return max(1, min(qty, risk_limit.max_shares))

    def aggregate(
        self,
        ticker: str,
        signals: dict[str, Signal],
        risk_limit=None,           # PositionLimit | None
        portfolio: Optional[dict] = None,
    ) -> TradingDecision:
        """
        Full aggregation pipeline:
          macro multiplier → weighted vote → coverage gate → confidence gate
          → action → quantity → TradingDecision.
        """
        # Step 1: macro regime
        regime, multiplier = self.get_macro_regime(signals)
        adjusted = self.apply_regime_multiplier(signals, regime, multiplier)

        # Step 2: weighted vote
        net_score, avg_conf, total_w, bull_w, bear_w = self.aggregate_signals(adjusted)

        # Step 3: coverage gate
        if total_w < self.min_coverage:
            logger.warning(
                "Aggregator [%s]: low coverage %.2f < %.2f → HOLD",
                ticker, total_w, self.min_coverage,
            )
            return TradingDecision(
                ticker      = ticker,
                action      = "hold",
                quantity    = 0,
                confidence  = round(avg_conf, 1),
                price       = risk_limit.current_price if risk_limit else 0.0,
                reasoning   = (
                    f"Insufficient signal coverage (total_weight={total_w:.2f} "
                    f"< {self.min_coverage}). Macro: {regime}."
                ),
                signals     = adjusted,
                net_score   = round(net_score, 4),
                macro_regime = regime,
            )

        # Step 4: action + quantity
        action   = self.determine_action(net_score, avg_conf, regime, ticker, portfolio)
        quantity = self.size_quantity(action, avg_conf, risk_limit, portfolio, ticker)
        price    = risk_limit.current_price if risk_limit else 0.0

        # Step 5: reasoning summary
        threshold = self.buy_threshold.get(regime, self.buy_threshold["neutral"])
        reasoning = (
            f"Action={action.upper()} | "
            f"net_score={net_score:+.3f} (threshold={threshold}) | "
            f"conf={avg_conf:.1f}% | "
            f"bull_w={bull_w:.3f} bear_w={bear_w:.3f} total_w={total_w:.3f} | "
            f"macro={regime} (mult={multiplier})"
        )

        logger.info(
            "Aggregator [%s]: %s | net=%.3f conf=%.0f%% regime=%s",
            ticker, action.upper(), net_score, avg_conf, regime,
        )

        return TradingDecision(
            ticker       = ticker,
            action       = action,
            quantity     = quantity,
            confidence   = round(avg_conf, 1),
            price        = price,
            reasoning    = reasoning,
            signals      = adjusted,
            net_score    = round(net_score, 4),
            macro_regime = regime,
        )
