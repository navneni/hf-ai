from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from core.engine_base import Signal, TradingDecision

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ResultStore:
    """Writes signals, decisions, and backtest results to MongoDB."""

    def __init__(self, db):
        self._db = db

    def save_signal(self, run_id: str, ticker: str, engine_name: str, signal: Signal) -> None:
        doc = {
            "run_id":      run_id,
            "ticker":      ticker,
            "engine":      engine_name,
            "as_of_date":  None,   # set by caller if available
            "signal":      signal.signal,
            "confidence":  signal.confidence,
            "weight":      signal.weight,
            "reasoning":   signal.reasoning,
            "metadata":    signal.metadata,
            "computed_at": _now(),
        }
        self._db.signals.update_one(
            {"run_id": run_id, "ticker": ticker, "engine": engine_name},
            {"$set": doc},
            upsert=True,
        )

    def save_signals_bulk(self, run_id: str, ticker: str, signals: dict[str, Signal], as_of_date: Optional[str] = None) -> None:
        now = _now()
        for engine_name, signal in signals.items():
            doc = {
                "run_id":      run_id,
                "ticker":      ticker,
                "engine":      engine_name,
                "as_of_date":  as_of_date,
                "signal":      signal.signal,
                "confidence":  signal.confidence,
                "weight":      signal.weight,
                "reasoning":   signal.reasoning,
                "metadata":    signal.metadata,
                "computed_at": now,
            }
            self._db.signals.update_one(
                {"run_id": run_id, "ticker": ticker, "engine": engine_name},
                {"$set": doc},
                upsert=True,
            )
            # Auto-save clean screen result if this is a screen engine
            if signal.metadata and "criteria" in signal.metadata:
                self._save_screen_result(ticker, engine_name, signal, as_of_date, run_id, now)

    def _save_screen_result(
        self, ticker: str, screen: str, signal: Signal,
        as_of_date: Optional[str], run_id: str, now
    ) -> None:
        """Upsert a clean screen result document to hf_ai_engine.screen_results."""
        meta = signal.metadata
        doc = {
            "ticker":         ticker,
            "screen":         screen,
            "as_of_date":     as_of_date,
            "run_id":         run_id,
            # Decision
            "signal":         signal.signal,
            "confidence":     signal.confidence,
            # Scores (0.0–1.0)
            "total_score":    meta.get("total_score"),
            "criteria_score": meta.get("criteria_score"),
            "consistency":    meta.get("consistency"),
            "moat_score":     meta.get("moat_score"),
            "mgmt_score":     meta.get("mgmt_score"),
            # Counts
            "checks_passed":  meta.get("checks_passed"),
            "checks_total":   meta.get("checks_total"),
            # Per-criterion pass/fail map
            "criteria":       meta.get("criteria", {}),
            "computed_at":    now,
        }
        self._db.screen_results.update_one(
            {"ticker": ticker, "screen": screen, "as_of_date": as_of_date},
            {"$set": doc},
            upsert=True,
        )

    def save_decision(self, run_id: str, decision: TradingDecision, as_of_date: Optional[str] = None) -> None:
        signals_summary = {
            name: {"signal": s.signal, "confidence": s.confidence, "weight": s.weight}
            for name, s in decision.signals.items()
        }
        doc = {
            "run_id":          run_id,
            "ticker":          decision.ticker,
            "as_of_date":      as_of_date,
            "action":          decision.action,
            "quantity":        decision.quantity,
            "confidence":      decision.confidence,
            "price":           decision.price,
            "net_score":       decision.net_score,
            "macro_regime":    decision.macro_regime,
            "reasoning":       decision.reasoning,
            "signals_summary": signals_summary,
            "narrative":       decision.narrative,
            "decided_at":      _now(),
        }
        self._db.decisions.update_one(
            {"run_id": run_id, "ticker": decision.ticker},
            {"$set": doc},
            upsert=True,
        )

    def save_backtest_snapshot(self, run_id: str, date: str, portfolio_value: float, cash: float, positions: dict, trades: list) -> None:
        self._db.backtest_results.update_one(
            {"run_id": run_id, "date": date},
            {"$set": {
                "run_id":          run_id,
                "date":            date,
                "portfolio_value": portfolio_value,
                "cash":            cash,
                "positions":       positions,
                "trades_today":    trades,
            }},
            upsert=True,
        )

    def save_backtest_metrics(self, run_id: str, config: dict, metrics: dict) -> None:
        self._db.backtest_metrics.update_one(
            {"run_id": run_id},
            {"$set": {
                "run_id":      run_id,
                "config":      config,
                "metrics":     metrics,
                "computed_at": _now(),
            }},
            upsert=True,
        )
