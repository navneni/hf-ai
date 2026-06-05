"""
NewsScraperModule — orchestrates all news sources, deduplicates, persists to MongoDB.
Called by DataBus._live_fetch() to populate DataBundle.news_items.
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Configurable RSS feeds (also read from engine.yaml if db config is available)
_DEFAULT_US_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline",
    "https://www.wsj.com/xml/rss/3_7085.xml",
]
_DEFAULT_IN_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rss.cms",
    "https://www.moneycontrol.com/rss/marketsindia.xml",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://www.livemint.com/rss/markets",
]


def _clean(text: str) -> str:
    """Normalize headline: strip HTML tags, collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_india(ticker: str) -> bool:
    return ticker.endswith(".NS") or ticker.endswith(".BO")


class NewsScraperModule:
    """
    Fetch, merge, deduplicate and persist news articles for a ticker.
    Returns list[dict] suitable for DataBundle.news_items.
    """

    def __init__(self, db=None, lookback_days: int = 90):
        self._db = db
        self._lookback = lookback_days

    def fetch(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        as_of_date: Optional[str] = None,
    ) -> list[dict]:
        from news.sources import GoogleNewsSource, RSSFeedSource, YahooFinanceNewsSource

        company = company_name or ticker.split(".")[0]
        india   = _is_india(ticker)
        feeds   = _DEFAULT_IN_FEEDS if india else _DEFAULT_US_FEEDS

        all_articles: list[dict] = []

        # Source 1: Google News RSS
        try:
            all_articles += GoogleNewsSource().fetch(
                ticker, company, as_of_date, self._lookback
            )
        except Exception as e:
            logger.debug("Google News failed: %s", e)

        # Source 2: Financial RSS feeds
        try:
            all_articles += RSSFeedSource().fetch(
                feeds, ticker, company, as_of_date, self._lookback
            )
        except Exception as e:
            logger.debug("RSS feeds failed: %s", e)

        # Source 3: Yahoo Finance news
        try:
            all_articles += YahooFinanceNewsSource().fetch(
                ticker, as_of_date, self._lookback
            )
        except Exception as e:
            logger.debug("Yahoo Finance news failed: %s", e)

        # Deduplicate by URL; clean headlines
        seen_urls: set[str] = set()
        unique: list[dict] = []
        for a in all_articles:
            url = (a.get("url") or "").strip()
            headline = _clean(a.get("headline", ""))
            if not headline:
                continue
            # URL dedup; fall back to headline dedup if no URL
            key = url if url else headline[:80]
            if key in seen_urls:
                continue
            seen_urls.add(key)
            a["headline"] = headline
            a["ticker"] = ticker
            unique.append(a)

        # Persist to MongoDB (news_raw collection)
        if self._db and unique:
            self._save(unique, as_of_date)

        logger.info("NewsScraperModule: %d unique articles for %s", len(unique), ticker)
        return unique

    def _save(self, articles: list[dict], as_of_date: Optional[str]) -> None:
        now = datetime.now(tz=timezone.utc)
        from datetime import date as date_cls
        is_hist = as_of_date is not None and as_of_date < str(date_cls.today())

        for a in articles:
            url = a.get("url", "").strip() or a.get("headline", "")[:100]
            if not url:
                continue
            doc = {
                "ticker":           a.get("ticker"),
                "headline":         a.get("headline"),
                "source":           a.get("source"),
                "url":              url,
                "published_at":     a.get("published_date"),
                "scrape_source":    a.get("scrape_source"),
                "scraped_at":       now,
                "is_historical":    is_hist,
                "finbert_label":    None,
                "finbert_score":    None,
                "sentiment_float":  None,
                "scored_at":        None,
            }
            try:
                self._db.news_raw.update_one(
                    {"url": url},
                    {"$set": doc},
                    upsert=True,
                )
            except Exception as e:
                logger.debug("Failed to save article: %s", e)
