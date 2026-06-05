from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)

# TTL values in seconds for live (non-historical) data
_TTL = {
    "prices":            6 * 3600,       # 6 hours
    "financials":        90 * 86400,     # 90 days
    "ratios":            86400,          # 24 hours
    "filing_texts":      90 * 86400,     # 90 days
    "news_raw":          90 * 86400,     # 90 days
    "news_sentiment":    3600,           # 1 hour
    "insider_trades":    7 * 86400,      # 7 days
    "promoter_holdings": 90 * 86400,     # 90 days
    "fii_dii_daily":     86400,          # 24 hours
    "bulk_deals":        86400,          # 24 hours
    "dark_pool_us":      7 * 86400,      # 7 days
    "inst_flow_us":      6 * 3600,       # 6 hours
    "macro_us":          3600,           # 1 hour
    "macro_in":          3600,           # 1 hour
    "monitoring_events": 30 * 86400,     # 30 days
    "audit_log":         90 * 86400,     # 90 days
}


class MongoDBClient:
    """
    Wrapper around PyMongo. Always uses hf_ai_engine database.
    Uses a scheduled cleanup job instead of MongoDB TTL indexes so that
    historical backtest data (is_historical=True) is never auto-deleted.
    """

    DB_NAME = "hf_ai_engine"

    def __init__(self, uri: str = "mongodb://localhost:27017"):
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            self._client.admin.command("ping")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            raise RuntimeError(
                f"Cannot connect to MongoDB at {uri}. "
                "Start MongoDB and retry. Original error: " + str(e)
            )
        self.db = self._client[self.DB_NAME]
        self._ensure_indexes()
        logger.info("MongoDB connected: %s / %s", uri, self.DB_NAME)

    # ------------------------------------------------------------------ indexes

    def _ensure_indexes(self) -> None:
        db = self.db
        db.prices_us.create_index([("ticker", ASCENDING), ("date", DESCENDING)], unique=True)
        db.prices_in.create_index([("ticker", ASCENDING), ("date", DESCENDING)], unique=True)
        db.financials.create_index(
            [("ticker", ASCENDING), ("period", ASCENDING), ("period_end", DESCENDING)],
            unique=True,
        )
        db.ratios.create_index([("ticker", ASCENDING), ("date", DESCENDING)])
        db.filing_texts.create_index(
            [("ticker", ASCENDING), ("filing_type", ASCENDING), ("period_end", DESCENDING)],
            unique=True,
        )
        db.signals.create_index(
            [("run_id", ASCENDING), ("ticker", ASCENDING), ("engine", ASCENDING)],
            unique=True,
        )
        db.signals.create_index([("ticker", ASCENDING), ("engine", ASCENDING), ("as_of_date", DESCENDING)])
        db.decisions.create_index([("run_id", ASCENDING), ("ticker", ASCENDING)], unique=True)
        db.decisions.create_index([("ticker", ASCENDING), ("as_of_date", DESCENDING)])
        db.runs.create_index([("run_id", ASCENDING)], unique=True)
        db.runs.create_index([("started_at", DESCENDING)])
        db.backtest_results.create_index([("run_id", ASCENDING), ("date", ASCENDING)], unique=True)
        db.backtest_metrics.create_index([("run_id", ASCENDING)], unique=True)
        db.news_raw.create_index([("ticker", ASCENDING), ("published_at", DESCENDING)])
        db.news_raw.create_index([("url", ASCENDING)], unique=True)
        db.news_sentiment.create_index([("ticker", ASCENDING), ("as_of_date", DESCENDING)])
        db.macro_us.create_index([("date", DESCENDING)], unique=True)
        db.macro_in.create_index([("date", DESCENDING)], unique=True)
        db.fii_dii_daily.create_index([("date", DESCENDING)], unique=True)
        db.bulk_deals.create_index([("ticker", ASCENDING), ("date", DESCENDING)])
        db.dark_pool_us.create_index([("ticker", ASCENDING), ("week_ending", DESCENDING)], unique=True)
        db.promoter_holdings.create_index([("ticker", ASCENDING), ("quarter", DESCENDING)], unique=True)
        db.insider_trades.create_index([("ticker", ASCENDING), ("transaction_date", DESCENDING)])
        db.monitoring_events.create_index([("metric", ASCENDING), ("at", DESCENDING)])
        db.monitoring_events.create_index([("tags.run_id", ASCENDING)])
        db.audit_log.create_index([("run_id", ASCENDING), ("at", DESCENDING)])
        db.engine_registry.create_index([("name", ASCENDING)], unique=True)
        db.data_cache_meta.create_index(
            [("ticker", ASCENDING), ("data_type", ASCENDING), ("market", ASCENDING)],
            unique=True,
        )
        db.inst_flow_us.create_index(
            [("ticker", ASCENDING), ("as_of_date", DESCENDING)], unique=True
        )
        db.screen_results.create_index(
            [("ticker", ASCENDING), ("screen", ASCENDING), ("as_of_date", DESCENDING)],
            unique=True,
        )
        db.screen_results.create_index([("as_of_date", DESCENDING), ("screen", ASCENDING)])
        db.screen_results.create_index([("ticker", ASCENDING), ("as_of_date", DESCENDING)])
        # is_historical index on data collections for fast cleanup queries
        for col in ("prices_us", "prices_in", "financials", "ratios", "filing_texts",
                    "news_raw", "insider_trades", "promoter_holdings", "fii_dii_daily",
                    "bulk_deals", "dark_pool_us", "macro_us", "macro_in", "inst_flow_us"):
            self.db[col].create_index([("is_historical", ASCENDING), ("fetched_at", DESCENDING)])

    # ------------------------------------------------------------------ cleanup

    def cleanup_stale_data(self) -> dict[str, int]:
        """
        Delete live (is_historical=False) documents older than their TTL.
        Called at engine startup and after each live run.
        Historical backtest data is never deleted.
        Returns counts of deleted documents per collection.
        """
        now = datetime.now(tz=timezone.utc)
        deleted = {}
        collection_map = {
            "prices_us":          "prices",
            "prices_in":          "prices",
            "financials":         "financials",
            "ratios":             "ratios",
            "filing_texts":       "filing_texts",
            "news_raw":           "news_raw",
            "news_sentiment":     "news_sentiment",
            "insider_trades":     "insider_trades",
            "promoter_holdings":  "promoter_holdings",
            "fii_dii_daily":      "fii_dii_daily",
            "bulk_deals":         "bulk_deals",
            "dark_pool_us":       "dark_pool_us",
            "inst_flow_us":       "inst_flow_us",
            "macro_us":           "macro_us",
            "macro_in":           "macro_in",
            "monitoring_events":  "monitoring_events",
            "audit_log":          "audit_log",
        }
        for col_name, ttl_key in collection_map.items():
            ttl_seconds = _TTL.get(ttl_key, 86400)
            cutoff = now - timedelta(seconds=ttl_seconds)
            result = self.db[col_name].delete_many({
                "is_historical": False,
                "fetched_at": {"$lt": cutoff},
            })
            if result.deleted_count:
                deleted[col_name] = result.deleted_count
                logger.debug("Cleaned %d stale docs from %s", result.deleted_count, col_name)
        return deleted

    # ------------------------------------------------------------------ collection properties

    @property
    def prices_us(self):         return self.db["prices_us"]
    @property
    def prices_in(self):         return self.db["prices_in"]
    @property
    def financials(self):        return self.db["financials"]
    @property
    def ratios(self):            return self.db["ratios"]
    @property
    def filing_texts(self):      return self.db["filing_texts"]
    @property
    def signals(self):           return self.db["signals"]
    @property
    def decisions(self):         return self.db["decisions"]
    @property
    def runs(self):              return self.db["runs"]
    @property
    def backtest_results(self):  return self.db["backtest_results"]
    @property
    def backtest_metrics(self):  return self.db["backtest_metrics"]
    @property
    def news_raw(self):          return self.db["news_raw"]
    @property
    def news_sentiment(self):    return self.db["news_sentiment"]
    @property
    def macro_us(self):          return self.db["macro_us"]
    @property
    def macro_in(self):          return self.db["macro_in"]
    @property
    def fii_dii_daily(self):     return self.db["fii_dii_daily"]
    @property
    def bulk_deals(self):        return self.db["bulk_deals"]
    @property
    def dark_pool_us(self):      return self.db["dark_pool_us"]
    @property
    def promoter_holdings(self): return self.db["promoter_holdings"]
    @property
    def insider_trades(self):    return self.db["insider_trades"]
    @property
    def monitoring_events(self): return self.db["monitoring_events"]
    @property
    def audit_log(self):         return self.db["audit_log"]
    @property
    def engine_registry(self):   return self.db["engine_registry"]
    @property
    def configurations(self):    return self.db["configurations"]
    @property
    def data_cache_meta(self):   return self.db["data_cache_meta"]
    @property
    def inst_flow_us(self):      return self.db["inst_flow_us"]
    @property
    def screen_results(self):    return self.db["screen_results"]

    def close(self) -> None:
        self._client.close()
