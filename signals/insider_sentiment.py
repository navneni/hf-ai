"""
Insider Sentiment Engine — Phase 9.

US path:  SEC Form 4 open-market transactions (data.insider_trades).
India path: Promoter quarterly holding changes (data.promoter_holdings).

Both paths produce a -1..+1 score based on directional conviction of the
insiders/promoters most likely to have edge over retail investors.

Engine weight: 0.10 (configurable in engine.yaml).
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Optional

from core.engine_base import BaseSignalEngine, DataBundle, Signal

logger = logging.getLogger(__name__)


class InsiderSentimentEngine(BaseSignalEngine):
    """Insider/promoter sentiment signal — dual-market aware."""

    name    = "insider_sentiment"
    version = "1.0.0"
    weight  = 0.10

    def initialize(self, config: dict) -> None:
        w = config.get("engines", {}).get("insider_sentiment", {}).get("weight")
        if w is not None:
            self.weight = float(w)

    def validate_data(self, data: DataBundle) -> bool:
        if data.market == "US":
            return bool(data.insider_trades)
        return bool(data.promoter_holdings)

    def compute(self, data: DataBundle) -> Signal:
        if data.market == "IN":
            return self._compute_india(data)
        return self._compute_us(data)

    # ─────────────────────────────────── US path

    def _compute_us(self, data: DataBundle) -> Signal:
        trades = data.insider_trades or []
        if not trades:
            return Signal("neutral", 30.0, self.weight,
                          "No insider trade data", {})

        as_of  = data.as_of_date
        cutoff = str(date.fromisoformat(as_of) - timedelta(days=180))

        recent = [
            t for t in trades
            if t.get("transaction_date", "") >= cutoff
            and t.get("is_open_market", True)
        ]

        if not recent:
            return Signal("neutral", 30.0, self.weight,
                          "No recent insider trades (180d)", {})

        buy_val  = sum(t.get("value", 0) or 0 for t in recent if t.get("transaction_type") == "buy")
        sell_val = sum(t.get("value", 0) or 0 for t in recent if t.get("transaction_type") == "sell")
        total    = buy_val + sell_val

        if total == 0:
            return Signal("neutral", 30.0, self.weight, "No buy/sell value data", {})

        # Value-weighted buy ratio: +1 = all buys, -1 = all sells
        ratio    = (buy_val - sell_val) / total
        n_buys   = sum(1 for t in recent if t.get("transaction_type") == "buy")
        n_sells  = sum(1 for t in recent if t.get("transaction_type") == "sell")

        if ratio > 0.30:
            signal, confidence = "bullish", min(88.0, 50 + ratio * 50)
        elif ratio < -0.30:
            signal, confidence = "bearish", min(88.0, 50 + abs(ratio) * 50)
        else:
            signal, confidence = "neutral", 40.0

        return Signal(
            signal=signal,
            confidence=round(confidence, 1),
            weight=self.weight,
            reasoning=(
                f"US insider: ratio={ratio:+.2f} | "
                f"buy_val=${buy_val:,.0f} sell_val=${sell_val:,.0f} | "
                f"n_buys={n_buys} n_sells={n_sells}"
            ),
            metadata={
                "path":      "US",
                "ratio":     round(ratio, 4),
                "buy_val":   buy_val,
                "sell_val":  sell_val,
                "n_trades":  len(recent),
                "n_buys":    n_buys,
                "n_sells":   n_sells,
            },
        )

    # ─────────────────────────────────── India path

    def _compute_india(self, data: DataBundle) -> Signal:
        holdings = data.promoter_holdings or []
        if not holdings:
            return Signal("neutral", 30.0, self.weight,
                          "No promoter holding data", {"path": "IN"})

        # Sort by quarter descending; take last 2 to compute change
        sorted_h = sorted(holdings, key=lambda h: h.get("quarter", ""), reverse=True)
        if len(sorted_h) < 2:
            return Signal("neutral", 30.0, self.weight,
                          "Insufficient promoter history (need ≥2 quarters)", {"path": "IN"})

        latest   = sorted_h[0]
        previous = sorted_h[1]

        curr_pct = latest.get("promoter_pct")
        prev_pct = previous.get("promoter_pct")

        if curr_pct is None or prev_pct is None:
            return Signal("neutral", 30.0, self.weight,
                          "Promoter pct unavailable", {"path": "IN"})

        change = curr_pct - prev_pct   # percentage-point change

        # > +0.5pp increase → bullish (promoters buying)
        # < -0.5pp decrease → bearish (promoters selling / diluting)
        if change > 0.5:
            signal     = "bullish"
            confidence = min(88.0, 50 + change * 10)
        elif change < -0.5:
            signal     = "bearish"
            confidence = min(88.0, 50 + abs(change) * 10)
        else:
            signal     = "neutral"
            confidence = 40.0

        # Apply absolute level bonus: very high promoter holding (>70%) → slightly bullish tilt
        if curr_pct > 70 and signal == "neutral":
            signal     = "bullish"
            confidence = 45.0

        return Signal(
            signal=signal,
            confidence=round(confidence, 1),
            weight=self.weight,
            reasoning=(
                f"India promoter: {prev_pct:.1f}% → {curr_pct:.1f}% "
                f"({change:+.2f}pp change, Q={latest.get('quarter')})"
            ),
            metadata={
                "path":         "IN",
                "curr_pct":     curr_pct,
                "prev_pct":     prev_pct,
                "change_pp":    round(change, 2),
                "latest_quarter": latest.get("quarter"),
                "fii_pct":      latest.get("fii_pct"),
                "public_pct":   latest.get("public_pct"),
            },
        )

    def required_data_types(self) -> list[str]:
        return ["insider_trades", "promoter_holdings"]
