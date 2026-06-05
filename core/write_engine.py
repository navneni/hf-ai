from __future__ import annotations
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from core.aggregator import Aggregator
from core.config import ConfigManager
from core.data_bus import DataBus
from core.engine_base import DataBundle, RunResult, TradingDecision
from core.engine_registry import EngineRegistry
from core.monitor import MonitorLayer
from core.result_store import ResultStore
from core.risk_engine import RiskEngine
from db.client import MongoDBClient

logger = logging.getLogger(__name__)


class WriteEngine:
    """
    Core orchestrator. Fixed runtime — never contains financial logic.
    All signal computation lives in engines registered via EngineRegistry.
    """

    def __init__(self, config_path: str = "config/engine.yaml", force_refresh: bool = False, no_news: bool = False):
        self.config = ConfigManager(config_path)

        mongo_uri = self.config.get("mongodb.uri", "mongodb://localhost:27017")
        self.db = MongoDBClient(uri=mongo_uri)

        self.registry = EngineRegistry()
        self.registry.discover("signals")
        self.registry.initialize_all(self.config._data)

        self.monitor = MonitorLayer(self.db)
        self.store = ResultStore(self.db)
        self.data_bus = DataBus(self.db, force_refresh=force_refresh, no_news=no_news)
        self.risk_engine = RiskEngine(self.config._data)
        self.aggregator  = Aggregator(self.config._data)

        # Clean up stale live data from previous runs
        self.db.cleanup_stale_data()

        logger.info(
            "WriteEngine ready — %d engine(s) registered",
            len(self.registry),
        )

    # ------------------------------------------------------------------ run

    def fetch_only(self, tickers: list[str], as_of_date: Optional[str] = None) -> None:
        """Prefetch and cache data for all tickers without running engines."""
        logger.info("Prefetching data for: %s", tickers)
        self.data_bus.prefetch(tickers, as_of_date)
        logger.info("Prefetch complete for %d ticker(s)", len(tickers))

    def run(
        self,
        tickers: list[str],
        engines: Optional[list[str]] = None,
        as_of_date: Optional[str] = None,
        portfolio: Optional[dict] = None,
        dry_run: bool = False,
    ) -> RunResult:

        run_id = self.monitor.start_run(tickers, engines, as_of_date)

        if dry_run:
            logger.info("Dry run — skipping data fetch and engine execution")
            self.monitor.end_run(run_id, "success", stats={"dry_run": True})
            return RunResult(run_id=run_id, status="success")

        active_engines = self.registry.resolve(engines or "all")

        if not active_engines:
            logger.warning("No engines registered. Add signal engines to signals/")
            self.monitor.warn(run_id, None, None, "No engines registered")
            self.monitor.end_run(run_id, "success", stats={"engines_run": 0})
            return RunResult(run_id=run_id, status="success")

        try:
            all_signals: dict[str, dict] = {}
            all_decisions: dict[str, TradingDecision] = {}

            # Prefetch all tickers in parallel, then fetch individually
            self.data_bus.prefetch(tickers, as_of_date)
            data_bundles = self._fetch_data(tickers, as_of_date)
            self.monitor.checkpoint(run_id, "data_fetched")

            for ticker, data in data_bundles.items():
                t0 = time.perf_counter()
                signals = self._run_engines_parallel(
                    run_id, ticker, data, active_engines
                )
                all_signals[ticker] = signals
                self.store.save_signals_bulk(run_id, ticker, signals, as_of_date)
                self.monitor.emit_metric(
                    "engine.compute.duration_ms",
                    (time.perf_counter() - t0) * 1000,
                    tags={"run_id": run_id, "ticker": ticker},
                )

            self.monitor.checkpoint(run_id, "signals_computed")

            all_decisions = self._aggregate_and_decide(
                run_id, all_signals, data_bundles, portfolio, as_of_date
            )
            for decision in all_decisions.values():
                self.store.save_decision(run_id, decision, as_of_date)

            self.monitor.checkpoint(run_id, "decisions_made")

            stats = {
                "tickers_processed": len(tickers),
                "engines_run":       len(active_engines),
                "signals_computed":  sum(len(s) for s in all_signals.values()),
                "decisions_made":    len(all_decisions),
            }
            self.monitor.end_run(run_id, "success", stats=stats)
            return RunResult(
                run_id=run_id,
                decisions=all_decisions,
                signals=all_signals,
                status="success",
            )

        except Exception as e:
            self.monitor.end_run(run_id, "error", error=str(e))
            raise

    # ------------------------------------------------------------------ internal

    def _fetch_data(
        self, tickers: list[str], as_of_date: Optional[str]
    ) -> dict[str, DataBundle]:
        """Fetch DataBundle for each ticker via DataBus (mem → MongoDB → live)."""
        return {ticker: self.data_bus.fetch(ticker, as_of_date) for ticker in tickers}

    def _run_engines_parallel(
        self, run_id: str, ticker: str, data: DataBundle, active_engines: list
    ) -> dict:
        """Run all engines for a single ticker in parallel (4 workers)."""
        signals = {}
        valid_engines = [e for e in active_engines if e.validate_data(data)]

        if not valid_engines:
            self.monitor.warn(run_id, ticker, None, "All engines skipped — insufficient data")
            return signals

        max_workers = min(4, len(valid_engines))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_engine = {
                pool.submit(engine.compute, data): engine
                for engine in valid_engines
            }
            for future in as_completed(future_to_engine):
                engine = future_to_engine[future]
                try:
                    signals[engine.name] = future.result()
                except Exception as e:
                    self.monitor.error(run_id, ticker, engine.name, str(e), exc=e)
        return signals

    def _aggregate_and_decide(
        self,
        run_id: str,
        all_signals: dict,
        data_bundles: dict,
        portfolio: Optional[dict],
        as_of_date: Optional[str],
    ) -> dict[str, TradingDecision]:
        """
        Phase 7: RiskEngine computes position limits; Aggregator produces real decisions.
        RiskEngine runs once across all tickers (correlation is cross-sectional).
        """
        risk_limits = self.risk_engine.compute(data_bundles, portfolio)

        decisions = {}
        for ticker, signals in all_signals.items():
            limit = risk_limits.get(ticker)
            decisions[ticker] = self.aggregator.aggregate(
                ticker, signals, risk_limit=limit, portfolio=portfolio
            )
        return decisions

    def run_backtest(self, config: dict) -> dict:
        """Phase 8 will implement this via BacktestFramework."""
        raise NotImplementedError("Backtesting implemented in Phase 8")
