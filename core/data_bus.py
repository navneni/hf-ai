"""
DataBus — single data access point for all signal engines.

3-layer cache:
  Layer 1: in-memory dict  (same process run, zero cost)
  Layer 2: MongoDB          (cross-run, respects TTL for live data)
  Layer 3: live API         (yfinance, SEC EDGAR, etc.)

Engines NEVER call fetchers directly. They receive a DataBundle from DataBus.
"""
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from core.engine_base import DataBundle
from data.market_config import get_market_config

logger = logging.getLogger(__name__)


# TTL in seconds for live (is_historical=False) data
_TTL = {
    "prices":     6 * 3600,       # 6h
    "financials": 90 * 86400,     # 90d
    "ratios":     86400,          # 24h
    "insider":    7 * 86400,      # 7d
    "filing":     90 * 86400,     # 90d
}


def _today() -> str:
    return str(date.today())


def _is_historical(as_of_date: Optional[str]) -> bool:
    return as_of_date is not None and as_of_date < _today()


def _is_stale(last_fetched: Optional[datetime], data_type: str, as_of_date: Optional[str]) -> bool:
    if _is_historical(as_of_date):
        return False    # historical data never stale
    if last_fetched is None:
        return True
    ttl = _TTL.get(data_type, 86400)
    # MongoDB may return naive datetimes; treat as UTC
    if last_fetched.tzinfo is None:
        last_fetched = last_fetched.replace(tzinfo=timezone.utc)
    age = (datetime.now(tz=timezone.utc) - last_fetched).total_seconds()
    return age > ttl


class DataBus:
    """
    Fetch and cache all data required to build a DataBundle for any ticker.
    Thread-safe: PyMongo connection pool handles concurrent reads/writes.
    """

    def __init__(self, db, force_refresh: bool = False, no_news: bool = False):
        self._db = db
        self._force_refresh = force_refresh
        self._no_news = no_news
        self._mem: dict[str, DataBundle] = {}   # in-memory cache
        self._macro_cache: dict[str, dict] = {} # market:as_of_date → macro dict (once per run)

    # ─────────────────────────────────────── public API

    def fetch(self, ticker: str, as_of_date: Optional[str] = None) -> DataBundle:
        """Return a fully populated DataBundle for ticker as of as_of_date."""
        key = f"{ticker}:{as_of_date or _today()}"

        # Layer 1: in-memory
        if not self._force_refresh and key in self._mem:
            logger.debug("Cache HIT (memory): %s", key)
            return self._mem[key]

        # Layer 2: MongoDB
        if not self._force_refresh:
            bundle = self._load_from_db(ticker, as_of_date)
            if bundle is not None:
                self._mem[key] = bundle
                logger.debug("Cache HIT (MongoDB): %s", key)
                return bundle

        # Layer 3: live fetch
        logger.info("Cache MISS — live fetch: %s", key)
        self._log_cache_miss(ticker, as_of_date)
        bundle = self._live_fetch(ticker, as_of_date)
        self._save_to_db(bundle, ticker, as_of_date)
        self._mem[key] = bundle
        return bundle

    def prefetch(self, tickers: list[str], as_of_date: Optional[str] = None) -> None:
        """Prefetch all tickers in parallel (8 workers, IO-bound)."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(self.fetch, t, as_of_date): t for t in tickers}
            for future in as_completed(futures):
                t = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error("Prefetch failed for %s: %s", t, e)

    # ─────────────────────────────────────── live fetch

    def _live_fetch(self, ticker: str, as_of_date: Optional[str]) -> DataBundle:
        mc = get_market_config(ticker)

        if mc.country == "IN":
            return self._live_fetch_india(ticker, as_of_date, mc)
        return self._live_fetch_us(ticker, as_of_date, mc)

    def _live_fetch_us(self, ticker: str, as_of_date: Optional[str], mc) -> DataBundle:
        from data.fetcher_us import (
            fetch_prices, fetch_financials, fetch_ttm_financials,
            fetch_ratios, fetch_insider_trades, fetch_filing_text,
            fetch_analyst_ratings, fetch_macro_us, fetch_inst_flow_us,
        )

        prices     = fetch_prices(ticker, as_of_date)
        financials = fetch_financials(ticker, as_of_date)
        ttm        = fetch_ttm_financials(ticker, as_of_date)
        if ttm:
            financials = [f for f in financials if f.get("period") != "TTM"]
            financials = [ttm] + financials

        ratios           = fetch_ratios(ticker, as_of_date, financials)
        insider_trades   = fetch_insider_trades(ticker, as_of_date)
        analyst_ratings  = fetch_analyst_ratings(ticker, as_of_date)
        filing_text, mda_text = fetch_filing_text(ticker, as_of_date)

        # Macro — once per market per run
        macro_key = f"US:{as_of_date or _today()}"
        if macro_key not in self._macro_cache:
            try:
                self._macro_cache[macro_key] = fetch_macro_us(as_of_date)
            except Exception as e:
                logger.warning("US macro fetch failed: %s", e)
                self._macro_cache[macro_key] = {}
        macro = self._macro_cache[macro_key]

        inst_flow_us = None
        try:
            inst_flow_us = fetch_inst_flow_us(ticker, as_of_date)
        except Exception as e:
            logger.warning("US inst flow fetch failed for %s: %s", ticker, e)

        news_items = self._fetch_news(ticker, ratios.get("company_name"), as_of_date)

        return DataBundle(
            ticker=ticker, market="US", as_of_date=as_of_date or _today(),
            prices=prices, financials=financials, ratios=ratios,
            filing_text=filing_text, mda_text=mda_text,
            insider_trades=insider_trades, analyst_ratings=analyst_ratings,
            news_items=news_items, macro=macro,
            inst_flow_us=inst_flow_us, market_config=mc.__dict__,
        )

    def _live_fetch_india(self, ticker: str, as_of_date: Optional[str], mc) -> DataBundle:
        from data.fetcher_india import (
            fetch_prices_india, fetch_financials_india, fetch_ttm_financials_india,
            fetch_ratios_india, fetch_fii_dii, fetch_promoter_holdings,
            fetch_bulk_deals, fetch_macro_india,
        )
        from data.fetcher_us import fetch_analyst_ratings   # yfinance works for .NS

        prices     = fetch_prices_india(ticker, as_of_date)
        financials = fetch_financials_india(ticker, as_of_date)
        ttm        = fetch_ttm_financials_india(ticker, as_of_date)
        if ttm:
            financials = [f for f in financials if f.get("period") != "TTM"]
            financials = [ttm] + financials

        ratios           = fetch_ratios_india(ticker, as_of_date, financials)
        analyst_ratings  = fetch_analyst_ratings(ticker, as_of_date)
        promoter_holdings = fetch_promoter_holdings(ticker, as_of_date)
        bulk_deals        = fetch_bulk_deals(ticker, as_of_date)

        # Macro — once per run for India
        macro_key = f"IN:{as_of_date or _today()}"
        if macro_key not in self._macro_cache:
            try:
                self._macro_cache[macro_key] = fetch_macro_india(as_of_date)
            except Exception as e:
                logger.warning("India macro fetch failed: %s", e)
                self._macro_cache[macro_key] = {}
        macro = self._macro_cache[macro_key]

        # FII/DII — once per run (market-wide, same as macro)
        fii_key = f"IN_FII:{as_of_date or _today()}"
        if fii_key not in self._macro_cache:
            try:
                self._macro_cache[fii_key] = fetch_fii_dii(as_of_date)
            except Exception as e:
                logger.warning("FII/DII fetch failed: %s", e)
                self._macro_cache[fii_key] = {}
        fii_dii = self._macro_cache[fii_key]

        # Merge FII/DII into macro (MacroContextEngine reads net_fii_5d from macro)
        if fii_dii:
            macro = {**macro, "net_fii_5d": fii_dii.get("net_fii_5d")}

        # inst_flow_india: combine FII/DII with bulk deal context
        inst_flow_india = {
            "ticker":       ticker,
            "as_of_date":   as_of_date or _today(),
            "net_fii_5d":   fii_dii.get("net_fii_5d"),
            "net_dii_5d":   fii_dii.get("net_dii_5d"),
            "fii_buy":      fii_dii.get("fii_buy"),
            "fii_sell":     fii_dii.get("fii_sell"),
            "bulk_deals_count": len(bulk_deals),
            "source":       "nse",
        } if fii_dii else None

        news_items = self._fetch_news(ticker, ratios.get("company_name"), as_of_date)

        return DataBundle(
            ticker=ticker, market="IN", as_of_date=as_of_date or _today(),
            prices=prices, financials=financials, ratios=ratios,
            filing_text="", mda_text="",   # India: no SEC EDGAR
            insider_trades=None,            # India: use promoter_holdings instead
            analyst_ratings=analyst_ratings,
            news_items=news_items, macro=macro,
            promoter_holdings=promoter_holdings,
            inst_flow_india=inst_flow_india,
            bulk_deals=bulk_deals,
            market_config=mc.__dict__,
        )

    def _fetch_news(
        self, ticker: str, company_name: Optional[str], as_of_date: Optional[str]
    ) -> list[dict]:
        if self._no_news:
            return []
        try:
            from news.scraper import NewsScraperModule
            return NewsScraperModule(db=self._db).fetch(
                ticker=ticker,
                company_name=company_name or ticker,
                as_of_date=as_of_date,
            )
        except Exception as e:
            logger.warning("News fetch failed for %s: %s", ticker, e)
            return []

    # ─────────────────────────────────────── MongoDB save

    def _save_to_db(self, bundle: DataBundle, ticker: str, as_of_date: Optional[str]) -> None:
        is_hist = _is_historical(as_of_date)
        now = datetime.now(tz=timezone.utc)
        col = "prices_us" if bundle.market == "US" else "prices_in"

        # Prices — upsert each day
        for rec in bundle.prices:
            self._db.db[col].update_one(
                {"ticker": rec["ticker"], "date": rec["date"]},
                {"$set": {**rec, "is_historical": is_hist}},
                upsert=True,
            )
        self._update_cache_meta(ticker, "prices", bundle.market, is_hist, len(bundle.prices), now)

        # Financials
        for rec in bundle.financials:
            self._db.financials.update_one(
                {"ticker": rec["ticker"], "period": rec["period"], "period_end": rec["period_end"]},
                {"$set": {**rec, "is_historical": is_hist}},
                upsert=True,
            )
        self._update_cache_meta(ticker, "financials", bundle.market, is_hist, len(bundle.financials), now)

        # Ratios
        if bundle.ratios:
            self._db.ratios.update_one(
                {"ticker": ticker, "date": bundle.ratios.get("date", _today())},
                {"$set": {**bundle.ratios, "is_historical": is_hist}},
                upsert=True,
            )
            self._update_cache_meta(ticker, "ratios", bundle.market, is_hist, 1, now)

        # Insider trades
        for rec in (bundle.insider_trades or []):
            self._db.insider_trades.update_one(
                {"ticker": rec["ticker"], "transaction_date": rec["transaction_date"],
                 "insider_name": rec["insider_name"], "shares": rec["shares"]},
                {"$set": {**rec, "is_historical": is_hist}},
                upsert=True,
            )
        if bundle.insider_trades:
            self._update_cache_meta(ticker, "insider", bundle.market, is_hist, len(bundle.insider_trades), now)

        # Analyst ratings
        for rec in (bundle.analyst_ratings or []):
            self._db.db["analyst_ratings"].update_one(
                {"ticker": ticker, "date": rec.get("date"), "firm": rec.get("firm")},
                {"$set": {**rec, "ticker": ticker, "is_historical": is_hist}},
                upsert=True,
            )

        # Macro (market-wide, keyed by date)
        if bundle.macro and bundle.macro.get("date"):
            col_name = "macro_us" if bundle.market == "US" else "macro_in"
            self._db.db[col_name].update_one(
                {"date": bundle.macro["date"]},
                {"$set": {**bundle.macro, "is_historical": is_hist}},
                upsert=True,
            )

        # India-specific collections
        for rec in (bundle.promoter_holdings or []):
            self._db.promoter_holdings.update_one(
                {"ticker": ticker, "quarter": rec.get("quarter")},
                {"$set": {**rec, "is_historical": is_hist}},
                upsert=True,
            )
        for rec in (bundle.bulk_deals or []):
            self._db.bulk_deals.update_one(
                {"ticker": ticker, "date": rec.get("date"), "client": rec.get("client")},
                {"$set": {**rec, "is_historical": is_hist}},
                upsert=True,
            )

        # Institutional flow (per ticker)
        if bundle.inst_flow_us and bundle.inst_flow_us.get("as_of_date"):
            self._db.inst_flow_us.update_one(
                {"ticker": ticker, "as_of_date": bundle.inst_flow_us["as_of_date"]},
                {"$set": {**bundle.inst_flow_us, "is_historical": is_hist}},
                upsert=True,
            )

        # Filing texts
        for ftype, text in [("10-K", bundle.filing_text), ("8-K-MDA", bundle.mda_text)]:
            if text:
                self._db.filing_texts.update_one(
                    {"ticker": ticker, "filing_type": ftype},
                    {"$set": {
                        "ticker": ticker, "market": bundle.market,
                        "filing_type": ftype, "text": text,
                        "word_count": len(text.split()),
                        "period_end": as_of_date or _today(),
                        "source": "sec_edgar",
                        "is_historical": is_hist,
                        "fetched_at": now,
                    }},
                    upsert=True,
                )

    def _update_cache_meta(self, ticker: str, data_type: str, market: str,
                           is_hist: bool, count: int, now: datetime) -> None:
        self._db.data_cache_meta.update_one(
            {"ticker": ticker, "data_type": data_type, "market": market},
            {"$set": {
                "ticker":       ticker,
                "data_type":    data_type,
                "market":       market,
                "last_fetched": now,
                "ttl_seconds":  _TTL.get(data_type, 86400),
                "is_stale":     False,
                "record_count": count,
            }},
            upsert=True,
        )

    # ─────────────────────────────────────── MongoDB load

    def _load_from_db(self, ticker: str, as_of_date: Optional[str]) -> Optional[DataBundle]:
        """Load DataBundle from MongoDB if all required data types are fresh."""
        mc = get_market_config(ticker)
        price_col = "prices_us" if mc.country == "US" else "prices_in"

        # Check freshness for each data type
        for data_type in ("prices", "financials", "ratios"):
            meta = self._db.data_cache_meta.find_one(
                {"ticker": ticker, "data_type": data_type, "market": mc.country}
            )
            last_fetched = meta.get("last_fetched") if meta else None
            if _is_stale(last_fetched, data_type, as_of_date):
                return None     # at least one type is stale → full live fetch

        # Load prices
        price_filter = {"ticker": ticker}
        if as_of_date:
            price_filter["date"] = {"$lte": as_of_date}
        prices = list(
            self._db.db[price_col]
            .find(price_filter, {"_id": 0})
            .sort("date", -1)
            .limit(504)
        )
        prices.reverse()    # ascending by date

        if not prices:
            return None

        # Load financials
        fin_filter = {"ticker": ticker, "market": mc.country}
        if as_of_date:
            fin_filter["period_end"] = {"$lte": as_of_date}
        financials = list(
            self._db.financials
            .find(fin_filter, {"_id": 0})
            .sort("period_end", -1)
            .limit(15)
        )
        financials.reverse()

        # Load ratios
        rat_filter = {"ticker": ticker, "market": mc.country}
        if as_of_date:
            rat_filter["date"] = {"$lte": as_of_date}
        ratios_doc = self._db.ratios.find_one(
            rat_filter, {"_id": 0}, sort=[("date", -1)]
        ) or {}

        # Load insider trades
        cutoff = str(date.fromisoformat(as_of_date or _today()) - timedelta(days=365))
        ins_filter = {"ticker": ticker, "transaction_date": {"$gte": cutoff}}
        if as_of_date:
            ins_filter["transaction_date"]["$lte"] = as_of_date
        insider_trades = list(
            self._db.insider_trades.find(ins_filter, {"_id": 0}).sort("transaction_date", -1)
        )

        # Load filing texts
        ft_doc = self._db.filing_texts.find_one(
            {"ticker": ticker, "filing_type": "10-K"}, {"_id": 0}, sort=[("period_end", -1)]
        )
        mda_doc = self._db.filing_texts.find_one(
            {"ticker": ticker, "filing_type": "8-K-MDA"}, {"_id": 0}, sort=[("period_end", -1)]
        )

        # Load news_raw (last 60 articles within lookback)
        news_items: list[dict] = []
        if not self._no_news:
            news_cutoff = str(date.fromisoformat(as_of_date or _today()) - timedelta(days=90))
            news_filter = {"ticker": ticker, "published_at": {"$gte": news_cutoff}}
            if as_of_date:
                news_filter["published_at"]["$lte"] = as_of_date
            news_items = list(
                self._db.news_raw.find(news_filter, {"_id": 0, "headline": 1,
                    "url": 1, "source": 1, "published_at": 1, "scrape_source": 1})
                .sort("published_at", -1).limit(60)
            )
            # Normalize published_at to string field name expected by engines
            for n in news_items:
                n.setdefault("published_date", str(n.get("published_at", ""))[:10])
                n.setdefault("ticker", ticker)

        # Load analyst ratings (last 180 days)
        analyst_ratings: Optional[list[dict]] = None
        ar_cutoff = str(date.fromisoformat(as_of_date or _today()) - timedelta(days=180))
        ar_filter = {"ticker": ticker, "date": {"$gte": ar_cutoff}}
        if as_of_date:
            ar_filter["date"]["$lte"] = as_of_date
        ar_docs = list(
            self._db.db["analyst_ratings"].find(ar_filter, {"_id": 0})
            .sort("date", -1).limit(20)
        )
        if ar_docs:
            analyst_ratings = ar_docs

        # Load macro (market-wide, most recent before as_of_date)
        macro_col  = "macro_us" if mc.country == "US" else "macro_in"
        macro_filter = {}
        if as_of_date:
            macro_filter["date"] = {"$lte": as_of_date}
        macro_doc = self._db.db[macro_col].find_one(macro_filter, {"_id": 0}, sort=[("date", -1)]) or {}
        macro = {k: v for k, v in macro_doc.items()} if macro_doc else {}

        # Load inst_flow_us (per ticker, US only)
        inst_flow_us = None
        if mc.country == "US":
            ifu_filter: dict = {"ticker": ticker}
            if as_of_date:
                ifu_filter["as_of_date"] = {"$lte": as_of_date}
            ifu_doc = self._db.inst_flow_us.find_one(
                ifu_filter, {"_id": 0}, sort=[("as_of_date", -1)]
            )
            if ifu_doc:
                inst_flow_us = {k: v for k, v in ifu_doc.items()}

        # Load India-specific data
        promoter_holdings: Optional[list[dict]] = None
        bulk_deals: Optional[list[dict]] = None
        inst_flow_india: Optional[dict] = None
        if mc.country == "IN":
            ph_filter: dict = {"ticker": ticker}
            if as_of_date:
                ph_filter["quarter"] = {"$lte": as_of_date[:7]}
            ph_docs = list(
                self._db.promoter_holdings.find(ph_filter, {"_id": 0})
                .sort("quarter", -1).limit(8)
            )
            if ph_docs:
                promoter_holdings = ph_docs

            bd_cutoff = str(
                __import__("datetime").date.fromisoformat(as_of_date or _today())
                - __import__("datetime").timedelta(days=30)
            )
            bd_filter: dict = {"ticker": ticker, "date": {"$gte": bd_cutoff}}
            if as_of_date:
                bd_filter["date"]["$lte"] = as_of_date
            bd_docs = list(self._db.bulk_deals.find(bd_filter, {"_id": 0}).sort("date", -1))
            if bd_docs:
                bulk_deals = bd_docs

        return DataBundle(
            ticker=ticker,
            market=mc.country,
            as_of_date=as_of_date or _today(),
            prices=prices,
            financials=financials,
            ratios=ratios_doc,
            filing_text=ft_doc.get("text", "") if ft_doc else "",
            mda_text=mda_doc.get("text", "") if mda_doc else "",
            insider_trades=insider_trades,
            analyst_ratings=analyst_ratings,
            news_items=news_items,
            macro=macro,
            inst_flow_us=inst_flow_us,
            promoter_holdings=promoter_holdings,
            bulk_deals=bulk_deals,
            inst_flow_india=inst_flow_india,
            market_config=mc.__dict__,
        )

    # ─────────────────────────────────────── audit

    def _log_cache_miss(self, ticker: str, as_of_date: Optional[str]) -> None:
        try:
            self._db.audit_log.insert_one({
                "run_id":  None,
                "level":   "DEBUG",
                "ticker":  ticker,
                "engine":  None,
                "message": f"DataBus cache miss: {ticker} as_of={as_of_date}",
                "stack":   None,
                "at":      datetime.now(tz=timezone.utc),
            })
        except Exception:
            pass
