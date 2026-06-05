from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class WoodScreen(BaseSignalEngine):
    """Cathie Wood: disruptive innovation — hypergrowth revenue, high gross margin, mid-cap."""
    name = "wood_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 2

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}

        rev_thresh  = thr.get("wood_revenue_growth", 30) / 100
        gm_thresh   = thr.get("wood_gross_margin", 60) / 100
        mc_max      = thr.get("wood_max_market_cap", 100_000_000_000)

        gm    = _v(ratios,"gross_margin")
        mktcap = _v(ratios,"market_cap")

        # Revenue YoY growth
        rev_new = _v(annual[0],"revenue") if annual else None
        rev_old = _v(annual[1],"revenue") if len(annual)>=2 else None
        rev_yoy = ((rev_new - rev_old) / abs(rev_old)) if (rev_new and rev_old and rev_old>0) else None

        checks = {
            "revenue_hypergrowth": rev_yoy is not None and rev_yoy > rev_thresh,
            "gross_margin_high":   gm is not None and gm > gm_thresh,
            "mid_cap":             mktcap is not None and mktcap < mc_max,
        }
        cs = sum(checks.values()) / len(checks)
        # Consistency: only need 1-2 years → use criteria score as consistency
        return _make_signal(self, checks, cs, cs,
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
