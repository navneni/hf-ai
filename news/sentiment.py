"""
Sentiment analysis for the 4-source news composite.

Sources:
  1. FinBERT on headlines        (weight 0.25)
  2. FinBERT on MD&A text        (weight 0.30)
  3. Analyst rating changes      (weight 0.25)
  4. Options sentiment overlay   (weight 0.20)

If any source is unavailable, its weight is redistributed proportionally.
"""
from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────── FinBERT scorer

# Financial domain keywords for rule-based fallback when FinBERT not available
_POS_KW = {"beat", "exceed", "record", "growth", "profit", "dividend", "upgrade",
           "buy", "outperform", "raise", "surpass", "strong", "bullish", "optimistic"}
_NEG_KW = {"miss", "loss", "decline", "downgrade", "sell", "cut", "warning", "layoff",
           "investigation", "probe", "fraud", "restatement", "concern", "weak", "bearish",
           "lawsuit", "recall", "suspend", "halt"}


def _simple_sentiment(text: str) -> tuple[str, float]:
    """Rule-based fallback for when FinBERT is unavailable."""
    words = set(text.lower().split())
    pos = len(words & _POS_KW)
    neg = len(words & _NEG_KW)
    if pos > neg:
        return "positive", min(0.5 + 0.1 * (pos - neg), 0.85)
    if neg > pos:
        return "negative", min(0.5 + 0.1 * (neg - pos), 0.85)
    return "neutral", 0.5


class FinBERTScorer:
    """
    Singleton FinBERT scorer.
    Loads ProsusAI/finbert once; falls back to rule-based if transformers unavailable.
    """
    _model = None
    _available: Optional[bool] = None

    @classmethod
    def _ensure(cls) -> None:
        if cls._available is not None:
            return
        try:
            from transformers import pipeline
            cls._model = pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                device=-1,          # CPU
                truncation=True,
                max_length=512,
            )
            cls._available = True
            logger.info("FinBERT loaded (ProsusAI/finbert)")
        except Exception as e:
            cls._available = False
            logger.warning("FinBERT unavailable (%s) — using rule-based fallback", e)

    @classmethod
    def score(cls, text: str) -> tuple[str, float]:
        """Returns (label, confidence) where label ∈ {'positive','negative','neutral'}."""
        cls._ensure()
        if not cls._available or cls._model is None:
            return _simple_sentiment(text)
        try:
            result = cls._model(text[:512])[0]
            return result["label"].lower(), float(result["score"])
        except Exception:
            return _simple_sentiment(text)

    @classmethod
    def score_batch(cls, texts: list[str]) -> list[tuple[str, float]]:
        cls._ensure()
        if not cls._available or cls._model is None:
            return [_simple_sentiment(t) for t in texts]
        try:
            results = cls._model([t[:512] for t in texts], batch_size=16)
            return [(r["label"].lower(), float(r["score"])) for r in results]
        except Exception:
            return [_simple_sentiment(t) for t in texts]

    @staticmethod
    def to_float(label: str, confidence: float) -> float:
        if label == "positive": return  confidence
        if label == "negative": return -confidence
        return 0.0


# ─────────────────────────────────────── Recency weighting

def _recency_weight(pub_date: str, as_of_date: Optional[str]) -> float:
    """w = 1 / (1 + days_ago / 30). Returns 1.0 on parse failure."""
    try:
        ref = date.fromisoformat(as_of_date) if as_of_date else date.today()
        pub = date.fromisoformat(str(pub_date)[:10])
        days_ago = max(0, (ref - pub).days)
        return 1.0 / (1 + days_ago / 30)
    except Exception:
        return 1.0


# ─────────────────────────────────────── Source 1: FinBERT on headlines

def score_headlines(
    news_items: list[dict],
    as_of_date: Optional[str],
) -> Optional[float]:
    """
    Recency-weighted average of FinBERT scores across scraped headlines.
    Returns float -1..+1 or None if < 3 articles.
    """
    if len(news_items) < 3:
        return None

    headlines = [a.get("headline", "") for a in news_items if a.get("headline")]
    if len(headlines) < 3:
        return None

    scored = FinBERTScorer.score_batch(headlines)
    weights = [_recency_weight(a.get("published_date", ""), as_of_date) for a in news_items]

    total_w = sum(weights)
    if total_w <= 0:
        return None

    weighted_sum = sum(
        FinBERTScorer.to_float(label, conf) * w
        for (label, conf), w in zip(scored, weights)
    )
    return float(max(-1.0, min(1.0, weighted_sum / total_w)))


# ─────────────────────────────────────── Source 2: FinBERT on MD&A

def score_mda(mda_text: str) -> Optional[float]:
    """
    Apply FinBERT to MD&A sentences.
    Returns average float -1..+1 or None if text is empty.
    """
    if not mda_text or len(mda_text.strip()) < 50:
        return None

    # Split into sentences; score each; average
    sentences = [s.strip() for s in mda_text.replace(".", ".\n").split("\n")
                 if len(s.strip()) > 20][:60]   # limit to 60 sentences
    if not sentences:
        return None

    scored = FinBERTScorer.score_batch(sentences)
    floats = [FinBERTScorer.to_float(label, conf) for label, conf in scored]
    return float(max(-1.0, min(1.0, sum(floats) / len(floats))))


# ─────────────────────────────────────── Source 3: Analyst ratings

_DIRECTION_SCORE = {
    "upgrade":   +0.70,
    "downgrade": -0.70,
    "initiate":  +0.30,
    "reiterate":  0.00,
}


def fetch_screener_analyst_ratings(ticker: str) -> list[dict]:
    """
    India fallback: scrape analyst recommendations from screener.in.
    Returns list[dict] in the same format as yfinance analyst_ratings.
    Returns [] on any failure.
    """
    try:
        symbol = ticker.replace(".NS", "").replace(".BO", "")
        import requests
        r = requests.get(
            f"https://www.screener.in/company/{symbol}/consolidated/",
            headers={"User-Agent": "Mozilla/5.0 hf-ai-engine/1.0"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        # Look for "analysts" or "ratings" section — screener.in doesn't always have this
        recs = []
        for tag in soup.find_all(string=lambda t: t and "recommend" in t.lower()):
            parent = tag.parent
            text   = parent.get_text(strip=True).lower()
            if "buy" in text:
                recs.append({"date": str(date.today()), "direction": "upgrade",
                             "firm": "screener.in", "action": "buy", "from_grade": "", "to_grade": "Buy"})
            elif "sell" in text:
                recs.append({"date": str(date.today()), "direction": "downgrade",
                             "firm": "screener.in", "action": "sell", "from_grade": "", "to_grade": "Sell"})
        return recs[:5]
    except Exception:
        return []


def score_analyst_ratings(
    analyst_ratings: Optional[list[dict]],
    as_of_date: Optional[str],
    ticker: Optional[str] = None,
) -> Optional[float]:
    """
    Recency-weighted average of analyst direction scores.
    Falls back to screener.in for India tickers (.NS/.BO) if yfinance ratings empty.
    Returns float -1..+1 or None if no ratings.
    """
    ratings = analyst_ratings
    # India fallback: try screener.in if yfinance ratings are empty
    if not ratings and ticker and (ticker.endswith(".NS") or ticker.endswith(".BO")):
        ratings = fetch_screener_analyst_ratings(ticker)

    if not ratings:
        return None

    scores, weights = [], []
    for r in analyst_ratings:
        direction = r.get("direction", "reiterate")
        s = _DIRECTION_SCORE.get(direction, 0.0)
        w = _recency_weight(r.get("date", ""), as_of_date)
        scores.append(s)
        weights.append(w)

    total_w = sum(weights)
    if total_w <= 0:
        return None

    weighted = sum(s * w for s, w in zip(scores, weights)) / total_w
    return float(max(-1.0, min(1.0, weighted)))


# ─────────────────────────────────────── Source 4: Options overlay

def score_options_overlay(inst_flow_us: Optional[dict]) -> Optional[float]:
    """
    Contrarian signal from options positioning.
    pc_ratio > 1.5 → fear in market → contrarian bullish (+0.4)
    pc_ratio < 0.5 → complacency → caution (-0.3)
    iv_rank > 80   → expensive options / high uncertainty → (-0.2)
    Returns None if no options data available (Phase 6 fills this).
    """
    if not inst_flow_us:
        return None

    pc_ratio = inst_flow_us.get("pc_ratio")
    iv_rank  = inst_flow_us.get("iv_rank")

    if pc_ratio is None and iv_rank is None:
        return None

    score = 0.0
    if pc_ratio is not None:
        if   pc_ratio > 1.5: score += 0.40
        elif pc_ratio < 0.5: score -= 0.30
    if iv_rank is not None:
        if iv_rank > 80:     score -= 0.20

    return float(max(-1.0, min(1.0, score)))


# ─────────────────────────────────────── 4-Source Composite

class FourSourceComposite:
    """Combines all four sources with proportional reweighting for missing sources."""

    BASE_WEIGHTS = {
        "headlines": 0.25,
        "mda":       0.30,
        "analyst":   0.25,
        "options":   0.20,
    }

    def initialize(self) -> None:
        """Pre-load FinBERT model."""
        FinBERTScorer._ensure()

    def score(
        self,
        news_items: list[dict],
        mda_text: str,
        analyst_ratings: Optional[list[dict]],
        inst_flow_us: Optional[dict],
        as_of_date: Optional[str],
        ticker: Optional[str] = None,
    ) -> tuple[float, dict]:
        """
        Returns (composite_score, breakdown_dict).
        composite_score: -1.0 to +1.0
        breakdown: per-source scores and weights used.
        """
        scores: dict[str, Optional[float]] = {
            "headlines": score_headlines(news_items, as_of_date),
            "mda":       score_mda(mda_text),
            "analyst":   score_analyst_ratings(analyst_ratings, as_of_date, ticker),
            "options":   score_options_overlay(inst_flow_us),
        }

        available = {k: v for k, v in scores.items() if v is not None}

        if not available:
            return 0.0, {**scores, "composite": 0.0, "sources_used": []}

        # Redistribute weights proportionally
        base_total  = sum(self.BASE_WEIGHTS[k] for k in available)
        adj_weights = {k: self.BASE_WEIGHTS[k] / base_total for k in available}

        composite = sum(v * adj_weights[k] for k, v in available.items())
        composite = float(max(-1.0, min(1.0, composite)))

        breakdown = {
            **scores,
            "composite":     round(composite, 4),
            "sources_used":  list(available.keys()),
            "weights_used":  {k: round(w, 4) for k, w in adj_weights.items()},
            "article_count": len(news_items),
        }
        return composite, breakdown
