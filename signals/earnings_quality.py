"""
Earnings Quality Signal Engine.
Beneish M-Score (manipulation detection) +
Altman Z-Score (bankruptcy risk) +
Piotroski F-Score (financial strength).
"""
from __future__ import annotations
import logging
from typing import Optional

from core.engine_base import BaseSignalEngine, DataBundle, Signal

logger = logging.getLogger(__name__)


def _v(d: dict, key: str) -> Optional[float]:
    val = d.get(key)
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────── Beneish M-Score

def _beneish(cur: dict, prv: dict) -> tuple[Optional[float], dict]:
    """
    Compute Beneish M-Score.
    Returns (m_score, {component: value}).
    M < -1.78 → likely not manipulating (clean).
    M > -1.78 → possible manipulation (bearish flag).
    """
    meta: dict = {}

    def _safe(d, k):
        return _v(d, k)

    rev_c  = _safe(cur, "revenue")
    rev_p  = _safe(prv, "revenue")
    rec_c  = _safe(cur, "receivables")
    rec_p  = _safe(prv, "receivables")
    gp_c   = _safe(cur, "gross_profit")
    gp_p   = _safe(prv, "gross_profit")
    ca_c   = _safe(cur, "current_assets")
    ca_p   = _safe(prv, "current_assets")
    ppe_c  = _safe(cur, "ppe")
    ppe_p  = _safe(prv, "ppe")
    at_c   = _safe(cur, "total_assets")
    at_p   = _safe(prv, "total_assets")
    da_c   = _safe(cur, "depreciation_amortization")
    da_p   = _safe(prv, "depreciation_amortization")
    sga_c  = _safe(cur, "sga_expense")
    sga_p  = _safe(prv, "sga_expense")
    ni_c   = _safe(cur, "net_income")
    ocf_c  = _safe(cur, "operating_cash_flow")
    td_c   = _safe(cur, "total_debt")
    td_p   = _safe(prv, "total_debt")

    # DSRI: Days Sales Receivables Index
    dsri = None
    if rec_c and rev_c and rec_p and rev_p and rev_p > 0 and rev_c > 0:
        dsri = (rec_c / rev_c) / (rec_p / rev_p)
        meta["DSRI"] = round(dsri, 4)

    # GMI: Gross Margin Index
    gmi = None
    if gp_c and rev_c and gp_p and rev_p and rev_p > 0 and rev_c > 0:
        gm_cur = gp_c / rev_c
        gm_prv = gp_p / rev_p
        gmi = gm_prv / (gm_cur + 1e-10)
        meta["GMI"] = round(gmi, 4)

    # AQI: Asset Quality Index
    aqi = None
    if ca_c and ppe_c and at_c and ca_p and ppe_p and at_p and at_c > 0 and at_p > 0:
        aqi = (1 - (ca_c + ppe_c) / at_c) / (1 - (ca_p + ppe_p) / at_p + 1e-10)
        meta["AQI"] = round(aqi, 4)

    # SGI: Sales Growth Index
    sgi = None
    if rev_c and rev_p and rev_p > 0:
        sgi = rev_c / rev_p
        meta["SGI"] = round(sgi, 4)

    # DEPI: Depreciation Index
    depi = None
    if da_c and ppe_c and da_p and ppe_p:
        denom_p = ppe_p + da_p
        denom_c = ppe_c + da_c
        if denom_p > 0 and denom_c > 0:
            depi = (da_p / denom_p) / (da_c / denom_c)
            meta["DEPI"] = round(depi, 4)

    # SGAI: Sales General Admin Index
    sgai = None
    if sga_c and rev_c and sga_p and rev_p and rev_p > 0 and rev_c > 0:
        sgai = (sga_c / rev_c) / (sga_p / rev_p)
        meta["SGAI"] = round(sgai, 4)

    # TATA: Total Accruals to Total Assets (strongest predictor)
    tata = None
    if ni_c is not None and ocf_c is not None and at_c and at_c > 0:
        tata = (ni_c - ocf_c) / at_c
        meta["TATA"] = round(tata, 4)

    # LVGI: Leverage Index
    lvgi = None
    if td_c is not None and td_p is not None and at_c and at_p and at_c > 0 and at_p > 0:
        lvgi = (td_c / at_c) / (td_p / at_p + 1e-10)
        meta["LVGI"] = round(lvgi, 4)

    # Count available components
    comps = [dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi]
    if sum(1 for c in comps if c is not None) < 4:
        return None, meta   # insufficient data for reliable score

    # Weights from Beneish (1999)
    m = -4.84
    m += 0.920 * (dsri or 1.0)
    m += 0.528 * (gmi  or 1.0)
    m += 0.404 * (aqi  or 1.0)
    m += 0.892 * (sgi  or 1.0)
    m += 0.115 * (depi or 1.0)
    m -= 0.172 * (sgai or 1.0)
    m += 4.679 * (tata or 0.0)   # strongest predictor
    m -= 0.327 * (lvgi or 1.0)

    meta["m_score"] = round(m, 4)
    return m, meta


# ─────────────────────────────────────── Altman Z-Score

def _altman(fin: dict, ratios: dict, is_service: bool = False) -> tuple[Optional[float], dict]:
    """
    Standard Altman Z-Score (manufacturing).
    Z' model for service/software companies.
    Returns (z_score, {component: value}).
    """
    wc   = (_v(fin, "current_assets") or 0) - (_v(fin, "current_liabilities") or 0)
    re   = _v(fin, "retained_earnings")
    ebit = _v(fin, "ebit") or _v(fin, "operating_income")
    at   = _v(fin, "total_assets")
    rev  = _v(fin, "revenue")
    mktcap = _v(ratios, "market_cap")
    td   = _v(fin, "total_debt") or 0
    eq   = _v(fin, "equity")

    meta: dict = {}

    if not at or at <= 0:
        return None, meta

    x1 = wc / at
    x2 = re / at if re is not None else 0.0
    x3 = ebit / at if ebit is not None else 0.0
    x4 = mktcap / (td or 1) if mktcap else (eq or 0) / (td or 1)  # fallback to book equity
    x5 = rev / at if rev else 0.0

    meta.update({"X1": round(x1, 4), "X2": round(x2, 4),
                 "X3": round(x3, 4), "X4": round(x4, 4), "X5": round(x5, 4)})

    if is_service:
        # Z' model: no X5 (asset turnover)
        z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    else:
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    meta["z_score"] = round(z, 4)
    return z, meta


# ─────────────────────────────────────── Piotroski (recomputed independently)

def _piotroski_score(financials: list[dict]) -> int:
    """Lightweight Piotroski F-Score for cross-check in earnings_quality."""
    annual = sorted(
        [f for f in financials if f.get("period", "").isdigit()],
        key=lambda f: f.get("period_end", ""), reverse=True,
    )
    if len(annual) < 2:
        return -1
    c, p = annual[0], annual[1]

    def _f(d, k): return _v(d, k)

    roa_c = (_f(c,"net_income") / max(_f(c,"total_assets") or 1,1e-6)) if _f(c,"net_income") else None
    roa_p = (_f(p,"net_income") / max(_f(p,"total_assets") or 1,1e-6)) if _f(p,"net_income") else None
    ocf   = _f(c,"operating_cash_flow")
    at_c  = _f(c,"total_assets") or 1
    at_p  = _f(p,"total_assets") or 1

    checks = [
        roa_c is not None and roa_c > 0,
        ocf is not None and ocf > 0,
        roa_c is not None and roa_p is not None and roa_c > roa_p,
        ocf is not None and roa_c is not None and (ocf / at_c) > roa_c,
        (_f(c,"total_debt") or 0) / at_c < (_f(p,"total_debt") or 0) / at_p,
        (_f(c,"current_assets") or 0) / max(_f(c,"current_liabilities") or 1, 1e-6) >
        (_f(p,"current_assets") or 0) / max(_f(p,"current_liabilities") or 1, 1e-6),
        (_f(c,"shares_outstanding") or 0) <= (_f(p,"shares_outstanding") or float("inf")),
        (_f(c,"gross_profit") or 0) / max(_f(c,"revenue") or 1, 1e-6) >
        (_f(p,"gross_profit") or 0) / max(_f(p,"revenue") or 1, 1e-6),
        (_f(c,"revenue") or 0) / at_c > (_f(p,"revenue") or 0) / at_p,
    ]
    return sum(checks)


# ─────────────────────────────────────── engine

class EarningsQualityEngine(BaseSignalEngine):
    """Beneish M-Score + Altman Z-Score + Piotroski F-Score earnings quality signal."""

    name    = "earnings_quality"
    version = "1.0.0"
    weight  = 0.10

    def validate_data(self, data: DataBundle) -> bool:
        annual = [f for f in data.financials if f.get("period", "").isdigit()]
        return len(annual) >= 2

    def required_data_types(self) -> list[str]:
        return ["financials", "ratios"]

    def compute(self, data: DataBundle) -> Signal:
        ratios = data.ratios or {}
        annual = sorted(
            [f for f in data.financials if f.get("period", "").isdigit()],
            key=lambda f: f.get("period_end", ""), reverse=True,
        )
        cur, prv = annual[0], annual[1]

        # ── Beneish M-Score ─────────────────────────────────────────
        m_score, beneish_meta = _beneish(cur, prv)
        beneish_ok = m_score is not None and m_score < -1.78
        beneish_flag = m_score is not None and m_score > -1.78

        # ── Altman Z-Score ──────────────────────────────────────────
        sector   = ratios.get("sector", "") or ""
        industry = ratios.get("industry", "") or ""
        is_svc   = any(kw in (sector + industry).lower()
                       for kw in ("software", "service", "technology", "financial",
                                  "healthcare", "media", "internet"))
        z_score, altman_meta = _altman(cur, ratios, is_service=is_svc)

        if z_score is not None:
            altman_ok      = z_score > 2.99
            altman_grey    = 1.81 <= z_score <= 2.99
            altman_distress = z_score < 1.81
        else:
            altman_ok = altman_grey = altman_distress = False

        # ── Piotroski F-Score ────────────────────────────────────────
        f_score = _piotroski_score(data.financials)
        piotroski_ok = f_score >= 7 if f_score >= 0 else False

        # ── Combined Signal ─────────────────────────────────────────
        bearish_flags = []
        if beneish_flag:         bearish_flags.append(f"M={beneish_meta.get('m_score', '?'):.2f} > -1.78")
        if altman_distress:      bearish_flags.append(f"Z={z_score:.2f} (distress)")
        if f_score >= 0 and f_score <= 3: bearish_flags.append(f"F={f_score}/9 (weak)")

        if bearish_flags:
            signal    = "bearish"
            confidence = 75.0 + min(20.0, len(bearish_flags) * 7)
            reasoning  = f"Earnings quality concerns: {'; '.join(bearish_flags)}"
        elif beneish_ok and altman_ok and piotroski_ok:
            signal    = "bullish"
            confidence = 88.0
            reasoning  = (f"Clean earnings: M={beneish_meta.get('m_score', '?'):.2f}, "
                          f"Z={z_score:.2f}, F={f_score}/9")
        elif beneish_ok and (altman_ok or altman_grey):
            signal    = "bullish"
            confidence = 65.0
            reasoning  = f"Solid quality: M clean, Z={'safe' if altman_ok else 'grey zone'}"
        else:
            signal    = "neutral"
            confidence = 50.0
            reasoning  = "Mixed earnings quality signals"

        meta = {
            **beneish_meta,
            **altman_meta,
            "piotroski_score": f_score,
            "beneish_ok":      beneish_ok,
            "altman_ok":       altman_ok,
            "altman_grey":     altman_grey,
            "is_service_model": is_svc,
        }
        return Signal(signal, round(confidence, 1), self.weight, reasoning, meta)
