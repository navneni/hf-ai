"""
News Sentiment Signal Engine.
4-source composite: FinBERT headlines (25%) + MD&A (30%) + analyst ratings (25%) + options overlay (20%).
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timezone
from typing import Optional

from core.engine_base import BaseSignalEngine, DataBundle, Signal

logger = logging.getLogger(__name__)


class NewsSentimentEngine(BaseSignalEngine):
    """
    4-source news sentiment: FinBERT headlines, MD&A, analyst ratings, options overlay.
    FinBERT loaded once at initialize(); falls back to rule-based if unavailable.
    """

    name    = "news_sentiment"
    version = "1.0.0"
    weight  = 0.10

    def initialize(self, config: dict) -> None:
        from news.sentiment import FourSourceComposite, FinBERTScorer
        self._composite = FourSourceComposite()
        self._composite.initialize()   # pre-load FinBERT

    def validate_data(self, data: DataBundle) -> bool:
        if not data.news_items:
            return False
        from datetime import date as date_cls
        as_of = data.as_of_date or str(date_cls.today())
        recent = [
            a for a in data.news_items
            if a.get("published_date", "") >= str(
                date_cls.fromisoformat(as_of) - __import__("datetime").timedelta(days=30)
            )
        ]
        return len(recent) >= 3

    def required_data_types(self) -> list[str]:
        return ["news_items", "mda_text", "analyst_ratings", "inst_flow_us"]

    def compute(self, data: DataBundle) -> Signal:
        from news.sentiment import FourSourceComposite

        # Lazily initialize composite if not done in initialize()
        if not hasattr(self, "_composite"):
            self._composite = FourSourceComposite()
            self._composite.initialize()

        composite_score, breakdown = self._composite.score(
            news_items      = data.news_items or [],
            mda_text        = data.mda_text or "",
            analyst_ratings = data.analyst_ratings,
            inst_flow_us    = data.inst_flow_us,
            as_of_date      = data.as_of_date,
        )

        # Determine signal
        if composite_score > 0.10:
            signal = "bullish"
            reasoning = (
                f"Positive composite {composite_score:+.2f} — "
                f"{len(breakdown.get('sources_used', []))} sources; "
                f"{breakdown.get('article_count', 0)} articles"
            )
        elif composite_score < -0.10:
            signal = "bearish"
            reasoning = (
                f"Negative composite {composite_score:+.2f} — "
                f"{len(breakdown.get('sources_used', []))} sources; "
                f"{breakdown.get('article_count', 0)} articles"
            )
        else:
            signal = "neutral"
            reasoning = f"Mixed sentiment {composite_score:+.2f} — no clear direction"

        confidence = min(95.0, abs(composite_score) * 100)

        meta = {
            "composite_score":   round(composite_score, 4),
            "headline_score":    breakdown.get("headlines"),
            "mda_score":         breakdown.get("mda"),
            "analyst_score":     breakdown.get("analyst"),
            "options_score":     breakdown.get("options"),
            "sources_used":      breakdown.get("sources_used", []),
            "article_count":     breakdown.get("article_count", 0),
        }

        # Persist to MongoDB if db is available (via run_id in context — best effort)
        self._persist_sentiment(data, composite_score, signal, confidence, breakdown)

        return Signal(signal, round(confidence, 1), self.weight, reasoning, meta)

    def _persist_sentiment(
        self,
        data: DataBundle,
        composite_score: float,
        signal: str,
        confidence: float,
        breakdown: dict,
    ) -> None:
        """Save aggregated sentiment to news_sentiment collection (best-effort)."""
        try:
            from db.client import MongoDBClient
            # Use cached client if available; otherwise skip persistence
            # (full persistence wired in Phase 10)
        except Exception:
            pass
