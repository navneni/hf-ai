from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class GrahamScreen(BaseSignalEngine):
    """Ben Graham: statistical value — low P/E, P/B, strong balance sheet, EPS positive."""
    name = "graham_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        ratios = data.ratios or {}

        pe_thresh  = thr.get("graham_pe", 15)
        pb_thresh  = thr.get("graham_pb", 1.5)
        de_thresh  = thr.get("buffett_de", 0.5)

        eps_s  = [_v(f,"eps") for f in annual[:5]]
        pe     = _v(ratios,"pe_ratio"); pb = _v(ratios,"pb_ratio")
        cr     = _v(ratios,"current_ratio"); de = _v(ratios,"debt_to_equity")
        div_y  = _v(ratios,"dividend_yield")

        checks = {
            "pe_low":        pe is not None and 0 < pe < pe_thresh,
            "pb_low":        pb is not None and 0 < pb < pb_thresh,
            "current_ratio": cr is not None and cr > 2.0,
            "de_low":        de is not None and de < de_thresh,
            "eps_positive":  consistency_score(eps_s, 0) >= 0.80,
            "pays_dividend": div_y is not None and div_y > 0,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(eps_s, 0),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
