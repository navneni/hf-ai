"""
Unit tests for news sentiment pipeline.
FinBERT is mocked — no 500MB download required.
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest

from core.engine_base import DataBundle


# ─────────────────────────────────────── Fixtures

def _article(headline: str, date: str = "2024-01-10", url: str = "") -> dict:
    return {
        "headline":       headline,
        "url":            url or f"https://example.com/{headline[:20]}",
        "source":         "TestSource",
        "published_date": date,
        "ticker":         "AAPL",
    }


def _bundle(news_items=None, mda_text="", analyst_ratings=None, inst_flow_us=None) -> DataBundle:
    return DataBundle(
        ticker="AAPL", market="US", as_of_date="2024-01-15",
        news_items=news_items or [],
        mda_text=mda_text,
        analyst_ratings=analyst_ratings,
        inst_flow_us=inst_flow_us,
        market_config={"country": "US"},
    )


# ─────────────────────────────────────── FinBERT scorer tests (mocked)

def test_finbert_scorer_to_float():
    from news.sentiment import FinBERTScorer
    assert FinBERTScorer.to_float("positive", 0.9) ==  pytest.approx(0.9)
    assert FinBERTScorer.to_float("negative", 0.8) == pytest.approx(-0.8)
    assert FinBERTScorer.to_float("neutral",  0.7) == pytest.approx(0.0)


def test_finbert_fallback_positive():
    from news.sentiment import _simple_sentiment
    label, conf = _simple_sentiment("Apple beats earnings record high profit")
    assert label == "positive"
    assert conf > 0.5


def test_finbert_fallback_negative():
    from news.sentiment import _simple_sentiment
    label, conf = _simple_sentiment("Company faces investigation SEC probe fraud")
    assert label == "negative"
    assert conf > 0.5


def test_finbert_fallback_neutral():
    from news.sentiment import _simple_sentiment
    label, conf = _simple_sentiment("Company announces quarterly results")
    assert label == "neutral"


# ─────────────────────────────────────── Recency weighting

def test_recency_weight_today():
    from news.sentiment import _recency_weight
    w = _recency_weight("2024-01-15", "2024-01-15")
    assert w == pytest.approx(1.0)


def test_recency_weight_30d_ago():
    from news.sentiment import _recency_weight
    w = _recency_weight("2023-12-16", "2024-01-15")   # ~30 days ago
    assert pytest.approx(0.5, abs=0.05) == w


def test_recency_weight_older_is_less():
    from news.sentiment import _recency_weight
    w_recent = _recency_weight("2024-01-14", "2024-01-15")
    w_old    = _recency_weight("2023-11-15", "2024-01-15")
    assert w_recent > w_old


# ─────────────────────────────────────── Score headlines (Source 1)

def test_score_headlines_not_enough_articles():
    from news.sentiment import score_headlines
    articles = [_article("Apple news", "2024-01-10"), _article("More news", "2024-01-11")]
    result = score_headlines(articles, "2024-01-15")
    assert result is None   # < 3 articles


def test_score_headlines_positive_majority(monkeypatch):
    from news.sentiment import score_headlines, FinBERTScorer
    # Mock FinBERT to return positive for all headlines
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("positive", 0.85)] * len(texts)))
    articles = [_article(f"Positive news {i}", "2024-01-10") for i in range(5)]
    result = score_headlines(articles, "2024-01-15")
    assert result is not None and result > 0


def test_score_headlines_negative_majority(monkeypatch):
    from news.sentiment import score_headlines, FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("negative", 0.90)] * len(texts)))
    articles = [_article(f"Bad news {i}", "2024-01-10") for i in range(5)]
    result = score_headlines(articles, "2024-01-15")
    assert result is not None and result < 0


def test_score_headlines_in_range(monkeypatch):
    from news.sentiment import score_headlines, FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("positive", 0.70)] * len(texts)))
    articles = [_article(f"News {i}", "2024-01-10") for i in range(5)]
    result = score_headlines(articles, "2024-01-15")
    assert result is not None and -1.0 <= result <= 1.0


# ─────────────────────────────────────── Score MD&A (Source 2)

def test_score_mda_empty():
    from news.sentiment import score_mda
    assert score_mda("") is None
    assert score_mda("   ") is None


def test_score_mda_positive(monkeypatch):
    from news.sentiment import score_mda, FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("positive", 0.80)] * len(texts)))
    text = "Revenue exceeded expectations. Record growth across all segments. Profit margins improved."
    result = score_mda(text)
    assert result is not None and result > 0


# ─────────────────────────────────────── Analyst ratings (Source 3)

def test_analyst_score_upgrades():
    from news.sentiment import score_analyst_ratings
    ratings = [
        {"date": "2024-01-10", "direction": "upgrade"},
        {"date": "2024-01-08", "direction": "upgrade"},
    ]
    score = score_analyst_ratings(ratings, "2024-01-15")
    assert score is not None and score > 0


def test_analyst_score_downgrades():
    from news.sentiment import score_analyst_ratings
    ratings = [
        {"date": "2024-01-10", "direction": "downgrade"},
        {"date": "2024-01-09", "direction": "downgrade"},
    ]
    score = score_analyst_ratings(ratings, "2024-01-15")
    assert score is not None and score < 0


def test_analyst_score_empty():
    from news.sentiment import score_analyst_ratings
    assert score_analyst_ratings([], "2024-01-15") is None
    assert score_analyst_ratings(None, "2024-01-15") is None


# ─────────────────────────────────────── Options overlay (Source 4)

def test_options_high_pc_ratio_bullish():
    from news.sentiment import score_options_overlay
    score = score_options_overlay({"pc_ratio": 2.0, "iv_rank": 50})
    assert score is not None and score > 0   # contrarian bullish


def test_options_low_pc_ratio_bearish():
    from news.sentiment import score_options_overlay
    score = score_options_overlay({"pc_ratio": 0.3, "iv_rank": 30})
    assert score is not None and score < 0


def test_options_high_iv_rank():
    from news.sentiment import score_options_overlay
    score = score_options_overlay({"pc_ratio": 1.0, "iv_rank": 90})
    assert score is not None and score < 0   # high IV = uncertainty = caution


def test_options_none():
    from news.sentiment import score_options_overlay
    assert score_options_overlay(None) is None
    assert score_options_overlay({}) is None


# ─────────────────────────────────────── FourSourceComposite

def test_composite_all_sources_available(monkeypatch):
    from news.sentiment import FourSourceComposite, FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("positive", 0.80)] * len(texts)))
    comp = FourSourceComposite()
    articles = [_article(f"Good news {i}", "2024-01-10") for i in range(5)]
    score, breakdown = comp.score(
        news_items=articles,
        mda_text="Revenue grew significantly. Record profits.",
        analyst_ratings=[{"date": "2024-01-10", "direction": "upgrade"}],
        inst_flow_us={"pc_ratio": 1.6, "iv_rank": 40},
        as_of_date="2024-01-15",
    )
    assert -1.0 <= score <= 1.0
    assert "sources_used" in breakdown
    assert len(breakdown["sources_used"]) >= 1


def test_composite_reweights_missing_sources(monkeypatch):
    """When MD&A and options are missing, headlines + analyst still sum to 1.0."""
    from news.sentiment import FourSourceComposite, FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("positive", 0.70)] * len(texts)))
    comp = FourSourceComposite()
    articles = [_article(f"News {i}", "2024-01-10") for i in range(5)]
    score, breakdown = comp.score(
        news_items=articles,
        mda_text="",          # not available
        analyst_ratings=None, # not available
        inst_flow_us=None,    # not available
        as_of_date="2024-01-15",
    )
    # Only headlines available; weight should be 1.0 for headlines
    assert breakdown["sources_used"] == ["headlines"]
    weights = breakdown.get("weights_used", {})
    total = sum(weights.values())
    assert abs(total - 1.0) < 0.01, f"Weights should sum to 1.0, got {total}"


def test_composite_no_data_returns_zero():
    from news.sentiment import FourSourceComposite
    comp = FourSourceComposite()
    score, _ = comp.score(
        news_items=[], mda_text="", analyst_ratings=None,
        inst_flow_us=None, as_of_date="2024-01-15"
    )
    assert score == 0.0


# ─────────────────────────────────────── NewsSentimentEngine

def test_engine_name_weight():
    from signals.news_sentiment import NewsSentimentEngine
    e = NewsSentimentEngine()
    assert e.name == "news_sentiment"
    assert e.weight == 0.10


def test_validate_data_not_enough_articles():
    from signals.news_sentiment import NewsSentimentEngine
    e = NewsSentimentEngine()
    bundle = _bundle(news_items=[_article("a"), _article("b")])
    assert e.validate_data(bundle) is False


def test_validate_data_passes_with_recent_articles():
    from signals.news_sentiment import NewsSentimentEngine
    e = NewsSentimentEngine()
    articles = [_article(f"News {i}", "2024-01-10") for i in range(5)]
    bundle = _bundle(news_items=articles)
    assert e.validate_data(bundle) is True


def test_engine_bullish_signal(monkeypatch):
    from signals.news_sentiment import NewsSentimentEngine
    from news.sentiment import FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("positive", 0.85)] * len(texts)))
    e = NewsSentimentEngine()
    e._composite = __import__("news.sentiment", fromlist=["FourSourceComposite"]).FourSourceComposite()
    articles = [_article(f"Great earnings {i}", "2024-01-12") for i in range(5)]
    sig = e.compute(_bundle(news_items=articles))
    assert sig.signal in ("bullish", "neutral")
    assert 0 <= sig.confidence <= 95


def test_engine_bearish_signal(monkeypatch):
    from signals.news_sentiment import NewsSentimentEngine
    from news.sentiment import FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("negative", 0.90)] * len(texts)))
    e = NewsSentimentEngine()
    e._composite = __import__("news.sentiment", fromlist=["FourSourceComposite"]).FourSourceComposite()
    articles = [_article(f"Bad news {i}", "2024-01-12") for i in range(5)]
    sig = e.compute(_bundle(news_items=articles))
    assert sig.signal in ("bearish", "neutral")


def test_engine_metadata_has_required_keys(monkeypatch):
    from signals.news_sentiment import NewsSentimentEngine
    from news.sentiment import FinBERTScorer
    monkeypatch.setattr(FinBERTScorer, "score_batch",
                        staticmethod(lambda texts: [("neutral", 0.6)] * len(texts)))
    e = NewsSentimentEngine()
    e._composite = __import__("news.sentiment", fromlist=["FourSourceComposite"]).FourSourceComposite()
    articles = [_article(f"News {i}", "2024-01-12") for i in range(5)]
    sig = e.compute(_bundle(news_items=articles))
    for key in ("composite_score", "sources_used", "article_count"):
        assert key in sig.metadata, f"Missing metadata key: {key}"


# ─────────────────────────────────────── Scraper unit tests

def test_clean_headline():
    from news.scraper import _clean
    assert _clean("  <b>Apple</b> beats  earnings  ") == "Apple beats earnings"


def test_is_india_ticker():
    from news.scraper import _is_india
    assert _is_india("TCS.NS") is True
    assert _is_india("RELIANCE.BO") is True
    assert _is_india("AAPL") is False


def test_source_relevance():
    from news.sources import _is_relevant
    assert _is_relevant("AAPL stock hits new high", "AAPL", "Apple Inc") is True
    assert _is_relevant("Apple reports record profits", "AAPL", "Apple") is True
    assert _is_relevant("Tesla announces new model", "AAPL", "Apple") is False
