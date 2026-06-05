from __future__ import annotations
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _run_id() -> str:
    return "run_" + uuid.uuid4().hex[:8]


class MonitorLayer:
    """Tracks run lifecycle, checkpoints, metrics, and audit events in MongoDB."""

    def __init__(self, db):
        self._db = db

    def start_run(
        self,
        tickers: list[str],
        engines: Optional[list[str]],
        as_of_date: Optional[str],
        run_type: str = "analysis",
    ) -> str:
        run_id = _run_id()
        self._db.runs.insert_one({
            "run_id":     run_id,
            "run_type":   run_type,
            "tickers":    tickers,
            "engines":    engines,
            "as_of_date": as_of_date,
            "started_at": _now(),
            "ended_at":   None,
            "status":     "running",
            "error":      None,
            "checkpoints": [],
            "stats":      {},
        })
        logger.info("Run started: %s | tickers=%s", run_id, tickers)
        return run_id

    def end_run(self, run_id: str, status: str, error: Optional[str] = None, stats: Optional[dict] = None) -> None:
        self._db.runs.update_one(
            {"run_id": run_id},
            {"$set": {
                "status":   status,
                "ended_at": _now(),
                "error":    error,
                "stats":    stats or {},
            }},
        )
        if status == "error":
            logger.error("Run %s failed: %s", run_id, error)
        else:
            logger.info("Run %s completed: %s", run_id, status)

    def checkpoint(self, run_id: str, stage: str) -> None:
        self._db.runs.update_one(
            {"run_id": run_id},
            {"$push": {"checkpoints": {"stage": stage, "at": _now()}}},
        )

    def warn(self, run_id: str, ticker: Optional[str], engine: Optional[str], message: str) -> None:
        self._db.audit_log.insert_one({
            "run_id":  run_id,
            "level":   "WARN",
            "ticker":  ticker,
            "engine":  engine,
            "message": message,
            "stack":   None,
            "at":      _now(),
        })
        logger.warning("[%s] %s/%s: %s", run_id, ticker, engine, message)

    def error(self, run_id: str, ticker: Optional[str], engine: Optional[str], message: str, exc: Optional[Exception] = None) -> None:
        self._db.audit_log.insert_one({
            "run_id":  run_id,
            "level":   "ERROR",
            "ticker":  ticker,
            "engine":  engine,
            "message": message,
            "stack":   traceback.format_exc() if exc else None,
            "at":      _now(),
        })
        logger.error("[%s] %s/%s: %s", run_id, ticker, engine, message)

    def emit_metric(self, name: str, value: float, tags: Optional[dict] = None) -> None:
        self._db.monitoring_events.insert_one({
            "metric": name,
            "value":  value,
            "tags":   tags or {},
            "at":     _now(),
        })


class HealthMetrics:
    """
    Queries MongoDB to produce a system health report.
    Called by `python engine.py --health`.
    """

    def __init__(self, db):
        self._db = db

    def last_run_status(self) -> dict:
        """Most recent run record."""
        doc = self._db.runs.find_one({}, sort=[("started_at", -1)])
        if not doc:
            return {"status": "no_runs", "run_id": None, "started_at": None, "tickers": []}
        return {
            "status":     doc.get("status"),
            "run_id":     doc.get("run_id"),
            "started_at": str(doc.get("started_at", ""))[:19],
            "ended_at":   str(doc.get("ended_at", ""))[:19] if doc.get("ended_at") else None,
            "tickers":    doc.get("tickers", []),
            "stats":      doc.get("stats", {}),
            "error":      doc.get("error"),
        }

    def data_freshness(self) -> list[dict]:
        """
        Check freshness of all cached data types from data_cache_meta.
        Returns list of {ticker, data_type, last_fetched, ttl_seconds, is_stale}.
        """
        from datetime import timezone
        from datetime import datetime as dt_cls
        now = _now()
        rows = []
        for doc in self._db.data_cache_meta.find({}, {"_id": 0}):
            lf = doc.get("last_fetched")
            ttl = int(doc.get("ttl_seconds", 86400))
            if lf is None:
                is_stale = True
                age_s = None
            else:
                if lf.tzinfo is None:
                    lf = lf.replace(tzinfo=timezone.utc)
                age_s = (now - lf).total_seconds()
                is_stale = age_s > ttl
            rows.append({
                "ticker":       doc.get("ticker"),
                "data_type":    doc.get("data_type"),
                "market":       doc.get("market"),
                "last_fetched": str(lf)[:19] if lf else None,
                "age_hours":    round(age_s / 3600, 1) if age_s is not None else None,
                "ttl_hours":    round(ttl / 3600, 1),
                "is_stale":     is_stale,
            })
        return sorted(rows, key=lambda r: (r["ticker"] or "", r["data_type"] or ""))

    def signal_distribution_7d(self) -> dict:
        """
        Count signal directions per engine over the last 7 days.
        Returns {engine: {bullish: n, bearish: n, neutral: n}}.
        """
        from datetime import timedelta
        cutoff = _now() - timedelta(days=7)
        pipeline = [
            {"$match": {"computed_at": {"$gte": cutoff}}},
            {"$group": {
                "_id":    {"engine": "$engine", "signal": "$signal"},
                "count":  {"$sum": 1},
            }},
        ]
        result: dict[str, dict] = {}
        for doc in self._db.signals.aggregate(pipeline):
            engine = doc["_id"]["engine"]
            signal = doc["_id"]["signal"]
            result.setdefault(engine, {"bullish": 0, "bearish": 0, "neutral": 0})
            result[engine][signal] = result[engine].get(signal, 0) + doc["count"]
        return result

    def collection_counts(self) -> dict[str, int]:
        """Row counts for key collections."""
        cols = ["runs", "signals", "decisions", "prices_us", "prices_in",
                "news_raw", "backtest_results"]
        return {col: self._db.db[col].estimated_document_count() for col in cols}

    def engine_count(self) -> int:
        return self._db.engine_registry.estimated_document_count()
