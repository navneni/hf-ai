"""
Valuation Signal Engine — 6 models averaged for margin of safety.
Models: 3-stage DCF, Owner Earnings DCF, EV/EBITDA relative,
        P/E relative (5yr avg), Graham Number, Sector ETF P/E.
"""
from __future__ import annotations
import logging
import math
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


# ─────────────────────────────────────── DCF helpers

def _fcf_cagr(financials: list[dict], years: int = 5) -> Optional[float]:
    """Compute FCF CAGR from last `years` annual periods."""
    annual = sorted(
        [f for f in financials if f.get("period", "").isdigit() and _v(f, "free_cash_flow") is not None],
        key=lambda f: f.get("period_end", ""),
        reverse=True,
    )
    relevant = annual[:years]
    if len(relevant) < 2:
        return None
    fcf_new = _v(relevant[0], "free_cash_flow")
    fcf_old = _v(relevant[-1], "free_cash_flow")
    n = len(relevant) - 1
    if fcf_old is None or fcf_old <= 0 or fcf_new is None or fcf_new <= 0:
        return None
    cagr = (fcf_new / fcf_old) ** (1 / n) - 1
    return float(max(-0.20, min(0.50, cagr)))   # cap at -20% to +50%


def _three_stage_dcf(fcf: float, cagr: float, wacc: float,
                     terminal_growth: float = 0.03,
                     years1: int = 5, years2: int = 5) -> Optional[float]:
    """3-stage DCF returning intrinsic value (present value of all future cash flows)."""
    if wacc <= terminal_growth or fcf <= 0:
        return None
    pv = 0.0
    cf = fcf
    # Stage 1: constant growth
    for yr in range(1, years1 + 1):
        cf  *= (1 + cagr)
        pv  += cf / (1 + wacc) ** yr
    # Stage 2: declining growth
    for yr in range(1, years2 + 1):
        g    = cagr - (cagr - terminal_growth) * yr / years2
        cf  *= (1 + g)
        pv  += cf / (1 + wacc) ** (years1 + yr)
    # Terminal
    term_cf = cf * (1 + terminal_growth)
    term_pv = (term_cf / (wacc - terminal_growth)) / (1 + wacc) ** (years1 + years2)
    return pv + term_pv


def _margin_of_safety(intrinsic: Optional[float], price: float) -> Optional[float]:
    """Positive → undervalued; negative → overvalued."""
    if intrinsic is None or price is None or price <= 0:
        return None
    return (intrinsic - price) / intrinsic


# ─────────────────────────────────────── engine

class ValuationEngine(BaseSignalEngine):
    """6-model valuation: 3-stage DCF, Owner Earnings DCF, EV/EBITDA, P/E relative, Graham Number, Sector P/E."""

    name    = "valuation"
    version = "1.0.0"
    weight  = 0.15

    def initialize(self, config: dict) -> None:
        self._us = config.get("us_thresholds", {})
        self._in = config.get("india_thresholds", {})

    def validate_data(self, data: DataBundle) -> bool:
        ratios = data.ratios or {}
        return bool(
            data.financials and
            (ratios.get("market_cap") or ratios.get("pe_ratio"))
        )

    def required_data_types(self) -> list[str]:
        return ["financials", "ratios", "market_config"]

    def compute(self, data: DataBundle) -> Signal:
        ratios = data.ratios or {}
        mc     = data.market_config or {}
        fins   = data.financials

        rfr  = mc.get("risk_free_rate", 0.053)
        erp  = 0.055   # equity risk premium
        wacc = rfr + erp

        # Market price per share
        mktcap = _v(ratios, "market_cap")
        shares = None
        annual = sorted(
            [f for f in fins if f.get("period", "").isdigit()],
            key=lambda f: f.get("period_end", ""),
            reverse=True,
        )
        ttm = next((f for f in fins if f.get("period") == "TTM"), None)
        latest = ttm or (annual[0] if annual else None)

        if not latest:
            return Signal("neutral", 30.0, self.weight, "No financial data for valuation", {})

        shares = _v(latest, "shares_outstanding") or (
            _v(annual[0], "shares_outstanding") if annual else None
        )
        eps   = _v(latest, "eps")
        bvps  = (_v(latest, "equity") / shares) if (shares and shares > 0 and _v(latest, "equity")) else None
        price = (mktcap / shares) if (mktcap and shares and shares > 0) else None

        gaps: list[float] = []
        model_meta: dict  = {}

        # ── Model 1: 3-Stage DCF ────────────────────────────────────
        fcf_ttm  = _v(latest, "free_cash_flow")
        fcf_cagr = _fcf_cagr(fins, 5)

        if fcf_ttm and fcf_ttm > 0 and fcf_cagr is not None and shares and price:
            iv   = _three_stage_dcf(fcf_ttm, fcf_cagr, wacc)
            iv_s = (iv / shares) if iv else None
            mos  = _margin_of_safety(iv_s, price)
            if mos is not None:
                gaps.append(mos)
                model_meta["dcf_mos"] = round(mos * 100, 1)

        # ── Model 2: Owner Earnings DCF ─────────────────────────────
        net_inc = _v(latest, "net_income")
        da      = _v(latest, "depreciation_amortization")
        capex   = _v(latest, "capex")
        if net_inc and da and capex and shares and price:
            owner_earnings = net_inc + da - (capex * 0.70)   # maintenance capex ≈ 70%
            if owner_earnings > 0:
                iv_oe = _three_stage_dcf(owner_earnings, fcf_cagr or 0.05, wacc)
                iv_oe_s = (iv_oe / shares) if iv_oe else None
                mos = _margin_of_safety(iv_oe_s, price)
                if mos is not None:
                    gaps.append(mos)
                    model_meta["owner_earnings_mos"] = round(mos * 100, 1)

        # ── Model 3: EV/EBITDA relative ─────────────────────────────
        ev_ebitda_cur  = _v(ratios, "ev_ebitda")
        pe_fair        = mc.get("pe_fair_value", 18.0)   # used as EV/EBITDA fair proxy
        if ev_ebitda_cur and ev_ebitda_cur > 0 and pe_fair:
            gap = (pe_fair - ev_ebitda_cur) / pe_fair
            gaps.append(float(max(-1.0, min(1.0, gap))))
            model_meta["ev_ebitda_gap"] = round(gap * 100, 1)

        # ── Model 4: P/E relative to own 5-year average ─────────────
        pe_cur = _v(ratios, "pe_ratio")
        pe_hist = [1 / (f.get("eps", 0) or 1e-6) * (price or 0)
                   for f in annual[:5] if f.get("eps") and f["eps"] > 0 and price]
        # Better: use earnings yield approach
        if pe_cur and pe_cur > 0:
            # Compare to simple fair value (market average P/E)
            pe_fair_mkt = pe_fair  # 18 US / 22 India
            gap = (pe_fair_mkt - pe_cur) / pe_fair_mkt
            # Also compare to own 5yr avg if available
            eps_series = [_v(f, "eps") for f in annual[:5] if _v(f, "eps") and _v(f, "eps") > 0]
            if len(eps_series) >= 3 and price:
                pe_hist_vals = [price / e for e in eps_series if e > 0]
                pe_5yr_avg   = sum(pe_hist_vals) / len(pe_hist_vals)
                gap = (pe_5yr_avg - pe_cur) / pe_5yr_avg
            gaps.append(float(max(-1.0, min(1.0, gap))))
            model_meta["pe_relative_gap"] = round(gap * 100, 1)

        # ── Model 5: Graham Number ───────────────────────────────────
        if eps and eps > 0 and bvps and bvps > 0 and price:
            graham = math.sqrt(22.5 * eps * bvps)
            mos = (graham - price) / graham
            gaps.append(float(max(-1.0, min(1.0, mos))))
            model_meta["graham_number"] = round(graham, 2)
            model_meta["graham_mos"]    = round(mos * 100, 1)

        # ── Model 6: Sector ETF P/E ─────────────────────────────────
        sector_pe = _v(ratios, "sector_pe")
        if sector_pe and pe_cur and sector_pe > 0 and pe_cur > 0:
            gap = (sector_pe - pe_cur) / sector_pe
            gaps.append(float(max(-1.0, min(1.0, gap))))
            model_meta["sector_pe_gap"] = round(gap * 100, 1)

        # ── Aggregate ───────────────────────────────────────────────
        if len(gaps) < 3:
            return Signal(
                "neutral", 30.0, self.weight,
                f"Insufficient valuation data ({len(gaps)}/6 models)",
                model_meta
            )

        avg_mos = sum(gaps) / len(gaps)
        conf    = min(95.0, abs(avg_mos) * 200)

        if avg_mos > 0.20:
            signal = "bullish"
            reasoning = f"Undervalued avg MoS +{avg_mos*100:.0f}% across {len(gaps)} models"
        elif avg_mos < -0.20:
            signal = "bearish"
            reasoning = f"Overvalued avg MoS {avg_mos*100:.0f}% across {len(gaps)} models"
        else:
            signal = "neutral"
            conf = max(30.0, conf)
            reasoning = f"Fairly valued avg MoS {avg_mos*100:.0f}% across {len(gaps)} models"

        model_meta["avg_mos"] = round(avg_mos * 100, 1)
        model_meta["models_used"] = len(gaps)
        return Signal(signal, round(conf, 1), self.weight, reasoning, model_meta)
