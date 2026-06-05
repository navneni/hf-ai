from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class PabraiScreen(BaseSignalEngine):
    """Mohnish Pabrai: high FCF yield, low P/B, buybacks active, low capex."""
    name = "pabrai_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}

        fcf_thresh    = thr.get("pabrai_fcf_yield", 15) / 100
        pb_thresh     = thr.get("pabrai_pb", 1.5)
        capex_thresh  = thr.get("pabrai_capex_revenue", 10) / 100

        pb        = _v(ratios,"pb_ratio")
        fcf_yield = _v(ratios,"fcf_yield")
        mktcap    = _v(ratios,"market_cap")
        if fcf_yield is None:
            fcf = _v(latest,"free_cash_flow")
            if fcf and mktcap and mktcap > 0:
                fcf_yield = fcf / mktcap

        # Capex/revenue
        capex    = _v(latest,"capex"); rev = _v(latest,"revenue")
        capex_r  = (capex / rev) if (capex and rev and rev>0) else None

        # Share buybacks
        shares = [_v(f,"shares_outstanding") for f in annual[:4] if _v(f,"shares_outstanding")]
        buyback = len(shares) >= 2 and shares[0] < shares[1]

        fcf_s = [_v(f,"free_cash_flow") for f in annual[:5]]

        checks = {
            "fcf_yield":    fcf_yield is not None and fcf_yield > fcf_thresh,
            "pb_low":       pb is not None and 0 < pb < pb_thresh,
            "buybacks":     buyback,
            "low_capex":    capex_r is not None and capex_r < capex_thresh,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(fcf_s, 0),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
