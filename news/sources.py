"""
News source implementations.
All sources return list[dict] with keys: headline, url, source, published_date, ticker.
All failures return [] — never crash the pipeline.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import feedparser
import requests

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; hf-ai-engine/1.0; research use)",
    "Accept": "application/rss+xml, application/xml, text/xml",
})

_GOOGLE_NEWS_URL = "https://news.google.com/rss/search"


def _parse_date(entry) -> str:
    """Extract date string YYYY-MM-DD from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return str(date(*t[:3]))
            except Exception:
                pass
    return str(date.today())


def _is_relevant(text: str, ticker: str, company_name: str) -> bool:
    """Check if headline/summary mentions the ticker or company name."""
    text_lower = text.lower()
    ticker_clean = ticker.split(".")[0].lower()   # strip .NS / .BO
    company_lower = (company_name or "").lower()[:20]
    return (ticker_clean in text_lower or
            (company_lower and company_lower in text_lower))


def _within_lookback(date_str: str, lookback_days: int, as_of_date: Optional[str]) -> bool:
    try:
        pub = date.fromisoformat(date_str)
        ref = date.fromisoformat(as_of_date) if as_of_date else date.today()
        days_ago = (ref - pub).days
        return 0 <= days_ago <= lookback_days
    except Exception:
        return True   # keep if we can't parse


# ─────────────────────────────────────── Google News RSS

class GoogleNewsSource:
    """Fetches from Google News RSS with two queries: ticker and company name."""

    def fetch(
        self,
        ticker: str,
        company_name: str,
        as_of_date: Optional[str] = None,
        lookback_days: int = 90,
    ) -> list[dict]:
        articles: list[dict] = []
        ticker_clean = ticker.split(".")[0]
        queries = list({ticker_clean, company_name or ticker_clean})

        for q in queries:
            try:
                params = {
                    "q":    f"{q} stock",
                    "hl":   "en-US",
                    "gl":   "US",
                    "ceid": "US:en",
                }
                resp = _SESSION.get(_GOOGLE_NEWS_URL, params=params, timeout=15)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                for entry in feed.entries:
                    pub_date = _parse_date(entry)
                    if not _within_lookback(pub_date, lookback_days, as_of_date):
                        continue
                    headline = entry.get("title", "").strip()
                    if not headline:
                        continue
                    articles.append({
                        "headline":       headline,
                        "url":            entry.get("link", ""),
                        "source":         entry.get("source", {}).get("title", "Google News"),
                        "published_date": pub_date,
                        "scrape_source":  "google_news_rss",
                    })
            except Exception as e:
                logger.debug("GoogleNewsSource failed for query '%s': %s", q, e)

        return articles


# ─────────────────────────────────────── Financial RSS Feeds

class RSSFeedSource:
    """Fetches from a list of financial RSS feeds and filters to relevant articles."""

    def fetch(
        self,
        feeds: list[str],
        ticker: str,
        company_name: str,
        as_of_date: Optional[str] = None,
        lookback_days: int = 90,
    ) -> list[dict]:
        articles: list[dict] = []
        for feed_url in feeds:
            try:
                resp = _SESSION.get(feed_url, timeout=15)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                for entry in feed.entries:
                    headline = entry.get("title", "").strip()
                    summary  = entry.get("summary", "")
                    if not _is_relevant(headline + " " + summary, ticker, company_name):
                        continue
                    pub_date = _parse_date(entry)
                    if not _within_lookback(pub_date, lookback_days, as_of_date):
                        continue
                    articles.append({
                        "headline":       headline,
                        "url":            entry.get("link", ""),
                        "source":         feed.feed.get("title", feed_url),
                        "published_date": pub_date,
                        "scrape_source":  "financial_rss",
                    })
            except Exception as e:
                logger.debug("RSSFeedSource failed for %s: %s", feed_url, e)

        return articles


# ─────────────────────────────────────── Yahoo Finance News (via yfinance)

class YahooFinanceNewsSource:
    """Fetches ticker-specific news from yfinance."""

    def fetch(
        self,
        ticker: str,
        as_of_date: Optional[str] = None,
        lookback_days: int = 90,
    ) -> list[dict]:
        articles: list[dict] = []
        try:
            import yfinance as yf
            news_list = yf.Ticker(ticker).news or []
            for item in news_list:
                ts = item.get("providerPublishTime") or item.get("publishedAt")
                if ts:
                    pub_date = str(datetime.fromtimestamp(int(ts), tz=timezone.utc).date())
                else:
                    pub_date = str(date.today())

                if not _within_lookback(pub_date, lookback_days, as_of_date):
                    continue

                headline = (item.get("title") or "").strip()
                if not headline:
                    continue

                articles.append({
                    "headline":       headline,
                    "url":            item.get("link", ""),
                    "source":         item.get("publisher", "Yahoo Finance"),
                    "published_date": pub_date,
                    "scrape_source":  "yahoo_finance",
                })
        except Exception as e:
            logger.debug("YahooFinanceNewsSource failed for %s: %s", ticker, e)

        return articles
