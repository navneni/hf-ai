"""
Fundamental Analysis Signal Engine.
12 ratio checks (Profitability, Growth, Health, Valuation) + Piotroski F-Score.
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
        return None if f != f else f   # NaN → None
    except (TypeError, ValueError):
        return None


def _piotroski(financials: list[dict]) -> tuple[int, dict]:
    """
    Compute Piotroski F-Score (0–9).
    Returns (score, {criterion: bool}).
    Requires at least 2 annual periods (current + prior).
    """
    annual = sorted(
        [f for f in financials if f.get("period", "").isdigit()],
        key=lambda f: f.get("period_end", ""),
        reverse=True,
    )
    if len(annual) < 2:
        return -1, {}   # insufficient data

    cur = annual[0]
    prv = annual[1]

    def _r(f, key):
        return _v(f, key)

    # Profitability signals
    roa_cur = (_r(cur, "net_income") / _r(cur, "total_assets")) if \
              (_r(cur, "net_income") is not None and _r(cur, "total_assets") and _r(cur, "total_assets") > 0) else None
    roa_prv = (_r(prv, "net_income") / _r(prv, "total_assets")) if \
              (_r(prv, "net_income") is not None and _r(prv, "total_assets") and _r(prv, "total_assets") > 0) else None
    op_cf   = _r(cur, "operating_cash_flow")
    assets  = _r(cur, "total_assets")

    f1 = bool(roa_cur is not None and roa_cur > 0)
    f2 = bool(op_cf is not None and op_cf > 0)
    f3 = bool(roa_cur is not None and roa_prv is not None and roa_cur > roa_prv)
    f4 = bool(op_cf is not None and roa_cur is not None and assets and assets > 0 and
              (op_cf / assets) > roa_cur)   # accruals: CF > ROA

    # Leverage signals
    lt_debt_cur = _r(cur, "total_debt")
    lt_debt_prv = _r(prv, "total_debt")
    assets_cur  = _r(cur, "total_assets") or 1
    assets_prv  = _r(prv, "total_assets") or 1
    cur_ratio_cur = (_r(cur, "current_assets") / max(_r(cur, "current_liabilities") or 1, 1e-6)) \
                    if _r(cur, "current_assets") else None
    cur_ratio_prv = (_r(prv, "current_assets") / max(_r(prv, "current_liabilities") or 1, 1e-6)) \
                    if _r(prv, "current_assets") else None
    shares_cur = _r(cur, "shares_outstanding")
    shares_prv = _r(prv, "shares_outstanding")

    f5 = bool(lt_debt_cur is not None and lt_debt_prv is not None and
              (lt_debt_cur / assets_cur) < (lt_debt_prv / assets_prv))
    f6 = bool(cur_ratio_cur is not None and cur_ratio_prv is not None and
              cur_ratio_cur > cur_ratio_prv)
    f7 = bool(shares_cur is not None and shares_prv is not None and
              shares_cur <= shares_prv)   # no dilution

    # Operating efficiency signals
    gm_cur = (_r(cur, "gross_profit") / _r(cur, "revenue")) if \
             (_r(cur, "gross_profit") is not None and _r(cur, "revenue") and _r(cur, "revenue") > 0) else None
    gm_prv = (_r(prv, "gross_profit") / _r(prv, "revenue")) if \
             (_r(prv, "gross_profit") is not None and _r(prv, "revenue") and _r(prv, "revenue") > 0) else None
    at_cur = (_r(cur, "revenue") / assets_cur) if _r(cur, "revenue") else None
    at_prv = (_r(prv, "revenue") / assets_prv) if _r(prv, "revenue") else None

    f8 = bool(gm_cur is not None and gm_prv is not None and gm_cur > gm_prv)
    f9 = bool(at_cur is not None and at_prv is not None and at_cur > at_prv)

    checks = {"f1_roa_positive": f1, "f2_cf_positive": f2, "f3_roa_improving": f3,
              "f4_accruals": f4, "f5_leverage": f5, "f6_liquidity": f6,
              "f7_dilution": f7, "f8_gross_margin": f8, "f9_asset_turnover": f9}
    score = sum(checks.values())
    return score, checks


# ─────────────────────────────────────── engine

class FundamentalEngine(BaseSignalEngine):
    """12 ratio checks across profitability, growth, health, valuation + Piotroski F-Score."""

    name    = "fundamental"
    version = "1.0.0"
    weight  = 0.15

    def initialize(self, config: dict) -> None:
        self._us = config.get("us_thresholds", {})
        self._in = config.get("india_thresholds", {})

    def _thr(self, market: str) -> dict:
        return self._us if market == "US" else self._in

    def validate_data(self, data: DataBundle) -> bool:
        if not data.financials:
            return False
        ttm = next((f for f in data.financials if f.get("period") == "TTM"), None)
        return ttm is not None or len(data.financials) >= 1

    def required_data_types(self) -> list[str]:
        return ["financials", "ratios", "market_config"]

    def compute(self, data: DataBundle) -> Signal:
        market = data.market
        thr    = self._thr(market)
        ratios = data.ratios or {}

        # Find latest financials (prefer TTM, fall back to most recent annual)
        fins   = sorted(data.financials, key=lambda f: f.get("period_end", ""), reverse=True)
        ttm    = next((f for f in fins if f.get("period") == "TTM"), None)
        latest = ttm or (fins[0] if fins else None)

        if latest is None:
            return Signal("neutral", 30.0, self.weight, "No financial data available", {})

        def _f(key: str, src: dict = None) -> Optional[float]:
            return _v(src or latest, key)

        def _r(key: str) -> Optional[float]:
            return _v(ratios, key)

        passed = 0
        checks = {}

        # ── Profitability (3 checks) ────────────────────────────────
        roe_thresh = thr.get("buffett_roe", 15) / 100
        roe = _r("roe")
        checks["roe"] = bool(roe is not None and roe > roe_thresh)
        if checks["roe"]: passed += 1

        net_m = _r("net_margin")
        if net_m is None and _f("net_income") is not None and _f("revenue"):
            net_m = _f("net_income") / max(_f("revenue"), 1)
        checks["net_margin"] = bool(net_m is not None and net_m > 0.20)
        if checks["net_margin"]: passed += 1

        op_m = _r("operating_margin")
        if op_m is None and _f("operating_income") is not None and _f("revenue"):
            op_m = _f("operating_income") / max(_f("revenue"), 1)
        checks["op_margin"] = bool(op_m is not None and op_m > 0.15)
        if checks["op_margin"]: passed += 1

        # ── Growth (3 checks) ───────────────────────────────────────
        # Find prior annual for YoY comparisons
        annual = [f for f in fins if f.get("period", "").isdigit()]
        prior  = annual[1] if len(annual) >= 2 else None

        rev_yoy = None
        if prior and _f("revenue") and _v(prior, "revenue"):
            rev_yoy = (_f("revenue") - _v(prior, "revenue")) / abs(_v(prior, "revenue"))
        checks["revenue_growth"] = bool(rev_yoy is not None and rev_yoy > 0.10)
        if checks["revenue_growth"]: passed += 1

        eps_yoy = None
        if prior and _f("eps") and _v(prior, "eps") and _v(prior, "eps") > 0:
            eps_yoy = (_f("eps") - _v(prior, "eps")) / _v(prior, "eps")
        checks["eps_growth"] = bool(eps_yoy is not None and eps_yoy > 0.10)
        if checks["eps_growth"]: passed += 1

        bvps_yoy = None
        if prior and _f("equity") and _v(prior, "equity") and _f("shares_outstanding"):
            bvps_cur = _f("equity") / _f("shares_outstanding")
            shares_p = _v(prior, "shares_outstanding") or _f("shares_outstanding")
            bvps_prv = _v(prior, "equity") / shares_p if shares_p else None
            if bvps_prv and bvps_prv > 0:
                bvps_yoy = (bvps_cur - bvps_prv) / abs(bvps_prv)
        checks["bvps_growth"] = bool(bvps_yoy is not None and bvps_yoy > 0.10)
        if checks["bvps_growth"]: passed += 1

        # ── Health (3 checks) ───────────────────────────────────────
        cr = _r("current_ratio")
        if cr is None and _f("current_assets") and _f("current_liabilities") and _f("current_liabilities") > 0:
            cr = _f("current_assets") / _f("current_liabilities")
        checks["current_ratio"] = bool(cr is not None and cr > 1.5)
        if checks["current_ratio"]: passed += 1

        de = _r("debt_to_equity")
        if de is None and _f("total_debt") and _f("equity") and _f("equity") > 0:
            de = _f("total_debt") / _f("equity")
        de_thresh = thr.get("buffett_de", 0.5)
        checks["debt_equity"] = bool(de is not None and de < de_thresh)
        if checks["debt_equity"]: passed += 1

        fcf_ratio = None
        if _f("free_cash_flow") is not None and _f("net_income") and _f("net_income") > 0:
            fcf_ratio = _f("free_cash_flow") / _f("net_income")
        checks["fcf_quality"] = bool(fcf_ratio is not None and fcf_ratio > 0.8)
        if checks["fcf_quality"]: passed += 1

        # ── Valuation (3 checks) ────────────────────────────────────
        pe = _r("pe_ratio")
        pe_thresh = 30 if market == "IN" else 25
        checks["pe_ratio"] = bool(pe is not None and 0 < pe < pe_thresh)
        if checks["pe_ratio"]: passed += 1

        pb = _r("pb_ratio")
        pb_thresh = thr.get("graham_pb", 1.5) * 2   # generous upper bound
        checks["pb_ratio"] = bool(pb is not None and 0 < pb < pb_thresh)
        if checks["pb_ratio"]: passed += 1

        ps = _r("ps_ratio")
        checks["ps_ratio"] = bool(ps is not None and 0 < ps < 5)
        if checks["ps_ratio"]: passed += 1

        # ── Piotroski F-Score ───────────────────────────────────────
        f_score, f_checks = _piotroski(data.financials)
        f_score_label = f_score if f_score >= 0 else "N/A"

        # ── Signal ─────────────────────────────────────────────────
        if passed >= 9:
            signal, conf = "bullish", min(95.0, 60 + (passed - 9) * 10)
        elif passed <= 4:
            signal, conf = "bearish", min(95.0, 60 + (4 - passed) * 10)
        else:
            signal, conf = "neutral", 40 + passed * 3

        # Piotroski modifier
        if f_score >= 0:
            if f_score >= 7 and signal != "bearish":
                conf = min(95.0, conf + 10)
            elif f_score <= 3 and signal != "bullish":
                signal = "bearish"
                conf   = min(95.0, conf + 5)

        meta = {
            "checks_passed": passed,
            "checks_total":  12,
            "piotroski_score": f_score_label,
            "piotroski_checks": f_checks,
            "ratio_checks":    checks,
        }
        reasoning = (
            f"{signal.capitalize()} — {passed}/12 checks; "
            f"Piotroski F={f_score_label}"
        )
        return Signal(signal, round(conf, 1), self.weight, reasoning, meta)
