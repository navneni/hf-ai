from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class BurryScreen(BaseSignalEngine):
    """Michael Burry: deep value — low P/B, high FCF yield, high short interest."""
    name = "burry_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}

        pb_thresh  = thr.get("burry_pb", 1.0)
        fcf_thresh = thr.get("burry_fcf_yield", 10) / 100
        si_thresh  = thr.get("burry_short_interest", 15) / 100

        pb        = _v(ratios,"pb_ratio")
        fcf_yield = _v(ratios,"fcf_yield")
        mktcap    = _v(ratios,"market_cap")
        fcf       = _v(latest,"free_cash_flow")
        # Compute FCF yield if not in ratios
        if fcf_yield is None and fcf and mktcap and mktcap > 0:
            fcf_yield = fcf / mktcap

        # Short interest (from inst_flow_us — populated in Phase 6)
        si_pct = None
        if data.inst_flow_us:
            si_pct = data.inst_flow_us.get("si_pct")

        fcf_s = [_v(f,"free_cash_flow") for f in annual[:5]]

        checks = {
            "pb_low":        pb is not None and 0 < pb < pb_thresh,
            "fcf_yield":     fcf_yield is not None and fcf_yield > fcf_thresh,
            "fcf_positive":  consistency_score(fcf_s, 0) >= 0.60,
            "high_short_int": si_pct is not None and si_pct > si_thresh,
        }
        # High short interest is optional — skip if data unavailable
        if si_pct is None:
            checks.pop("high_short_int")

        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(fcf_s, 0),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
