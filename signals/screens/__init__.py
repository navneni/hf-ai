"""
Shared helpers for all 13 investor screens.
Every screen uses: consistency_score, moat_text_score,
management_quality_score, master_screen_score, _make_signal.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from core.engine_base import Signal

logger = logging.getLogger(__name__)

# ─────────────────────────────────────── constants

SCREEN_WEIGHT   = 0.20 / 13          # ≈ 0.01538 per screen
BULLISH_THRESH  = 0.65
BEARISH_THRESH  = 0.35
RED_FLAGS       = [
    "going concern", "material weakness", "restatement",
    "sec investigation", "class action", "fraud", "going-concern",
]

MOAT_EVIDENCE = {
    "switching_costs":   ["switching cost", "proprietary", "integrated", "lock-in", "mission-critical"],
    "network_effects":   ["network effect", "platform", "marketplace", "ecosystem", "two-sided"],
    "cost_advantage":    ["lowest cost", "scale advantage", "cost leadership"],
    "intangible_assets": ["patent", "proprietary technology", "brand loyalty", "trade secret"],
    "regulatory_moat":   ["regulatory approval", "fda clearance", "fcc license", "exclusive"],
}

_IDF_CACHE: Optional[dict] = None


def _load_idf() -> dict:
    global _IDF_CACHE
    if _IDF_CACHE is not None:
        return _IDF_CACHE
    path = Path(__file__).parent.parent.parent / "config" / "moat_idf.json"
    if path.exists():
        try:
            _IDF_CACHE = json.loads(path.read_text())
            return _IDF_CACHE
        except Exception:
            pass
    _IDF_CACHE = {}
    return _IDF_CACHE


# ─────────────────────────────────────── safe helpers

def _v(d: dict, key: str) -> Optional[float]:
    if not d:
        return None
    val = d.get(key)
    if val is None:
        return None
    try:
        f = float(val)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None


def _annual_sorted(financials: list[dict]) -> list[dict]:
    """Annual periods sorted newest-first."""
    return sorted(
        [f for f in financials if str(f.get("period", "")).isdigit()],
        key=lambda f: f.get("period_end", ""),
        reverse=True,
    )


def _cagr(series: list, years: int) -> Optional[float]:
    """CAGR from newest to oldest over `years` periods."""
    vals = [v for v in series if v is not None and v > 0]
    if len(vals) < 2:
        return None
    n = min(years, len(vals) - 1)
    return (vals[0] / vals[n]) ** (1 / n) - 1


def _ttm_or_latest(financials: list[dict]) -> Optional[dict]:
    ttm = next((f for f in financials if f.get("period") == "TTM"), None)
    if ttm:
        return ttm
    ann = _annual_sorted(financials)
    return ann[0] if ann else None


# ─────────────────────────────────────── consistency_score

def consistency_score(series: list, threshold: float) -> float:
    """% of non-None values that exceed threshold. Returns 0.0–1.0."""
    valid = [v for v in series if v is not None]
    if not valid:
        return 0.0
    return sum(1 for v in valid if v > threshold) / len(valid)


# ─────────────────────────────────────── moat_text_score (TF-IDF)

def moat_text_score(filing_text: str) -> float:
    """TF-IDF weighted moat evidence. Returns 0.0–1.0."""
    if not filing_text or len(filing_text.strip()) < 50:
        return 0.0

    idf     = _load_idf()
    text    = filing_text.lower()
    n_words = max(len(text.split()), 1)
    scores  = []

    for keywords in MOAT_EVIDENCE.values():
        tf_idf_sum = 0.0
        for kw in keywords:
            tf     = text.count(kw) / n_words
            weight = idf.get(kw, 1.0)
            tf_idf_sum += tf * weight
        scores.append(min(1.0, tf_idf_sum * 100))

    return round(sum(scores) / len(scores), 4) if scores else 0.0


# ─────────────────────────────────────── management_quality_score

def management_quality_score(annual: list[dict], ratios: dict) -> float:
    """ROIC level + stability + buybacks + ROE proxy. Returns 0.0–1.0."""
    if not annual:
        return 0.3

    score = 0.0

    # ROIC (30%)
    roic_series = []
    for f in annual[:10]:
        ebit    = _v(f, "ebit") or _v(f, "operating_income")
        assets  = _v(f, "total_assets") or 0
        cash    = _v(f, "cash") or 0
        inv_cap = assets - cash
        if ebit and inv_cap > 0:
            roic_series.append(ebit / inv_cap)

    if roic_series:
        mean_roic = float(np.mean(roic_series))
        score    += 0.30 * (1.0 if mean_roic > 0.15 else max(0.0, mean_roic / 0.15))
        if len(roic_series) >= 3:
            cv = float(np.std(roic_series)) / max(abs(mean_roic), 1e-4)
            score += 0.30 * min(1.0, max(0.0, 1.0 - cv))
        else:
            score += 0.15
    else:
        score += 0.15

    # Buybacks (20%)
    shares = [_v(f, "shares_outstanding") for f in annual[:9]]
    shares = [v for v in shares if v is not None and v > 0]
    if len(shares) >= 3:
        dec = sum(1 for i in range(1, len(shares)) if shares[i] < shares[i - 1])
        score += 0.20 * (dec / (len(shares) - 1))
    else:
        score += 0.10

    # ROE proxy (20%)
    roe = _v(ratios, "roe")
    if roe is not None and roe > 0.20:
        score += 0.20
    elif roe is not None and roe > 0.10:
        score += 0.10

    return float(min(1.0, max(0.0, score)))


# ─────────────────────────────────────── master_screen_score

def master_screen_score(
    criteria_score: float,
    consistency:    float,
    moat:           float,
    mgmt:           float,
    filing_text:    str = "",
) -> float:
    """0.40·criteria + 0.25·consistency + 0.20·moat + 0.15·mgmt. Red-flag ×0.50."""
    score = (0.40 * criteria_score +
             0.25 * consistency    +
             0.20 * moat           +
             0.15 * mgmt)

    text_lower = (filing_text or "").lower()
    if any(rf in text_lower for rf in RED_FLAGS):
        score *= 0.50

    return float(min(1.0, max(0.0, score)))


# ─────────────────────────────────────── signal builder

def _make_signal(
    engine,
    checks:         dict[str, bool],
    criteria_score: float,
    consistency:    float,
    moat:           float,
    mgmt:           float,
    filing_text:    str = "",
) -> Signal:
    total  = master_screen_score(criteria_score, consistency, moat, mgmt, filing_text)
    passed = sum(1 for v in checks.values() if v)

    if total >= BULLISH_THRESH:
        sig, conf = "bullish", min(95.0, 50 + total * 50)
    elif total <= BEARISH_THRESH:
        sig, conf = "bearish", min(95.0, 50 + (1 - total) * 50)
    else:
        sig, conf = "neutral", 40.0 + total * 20

    meta = {
        "total_score":    round(total, 4),
        "criteria_score": round(criteria_score, 4),
        "consistency":    round(consistency, 4),
        "moat_score":     round(moat, 4),
        "mgmt_score":     round(mgmt, 4),
        "checks_passed":  passed,
        "checks_total":   len(checks),
        "criteria":       {k: bool(v) for k, v in checks.items()},   # ensure Python bool for MongoDB
    }
    return Signal(sig, round(conf, 1), engine.weight,
                  f"{engine.name}: {total:.2f} ({passed}/{len(checks)} checks)", meta)
