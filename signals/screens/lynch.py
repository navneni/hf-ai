from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class LynchScreen(BaseSignalEngine):
    """Peter Lynch: GARP — low PEG, consistent EPS growth, low debt."""
    name = "lynch_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        ratios = data.ratios or {}

        peg_thresh  = thr.get("lynch_peg", 1.0)
        eps_thresh  = thr.get("lynch_eps_growth", 20) / 100
        de_thresh   = thr.get("lynch_de", 0.35)

        peg  = _v(ratios,"peg_ratio"); de = _v(ratios,"debt_to_equity")
        eps_s = [_v(f,"eps") for f in annual[:5]]
        rev_s = [_v(f,"revenue") for f in annual[:5]]

        # EPS YoY growth last period
        eps_yoy = None
        if len(annual) >= 2:
            e_new, e_old = _v(annual[0],"eps"), _v(annual[1],"eps")
            if e_new and e_old and e_old > 0:
                eps_yoy = (e_new - e_old) / e_old

        checks = {
            "peg_low":           peg is not None and 0 < peg < peg_thresh,
            "eps_growth":        eps_yoy is not None and eps_yoy > eps_thresh,
            "eps_consistency":   consistency_score(eps_s, 0) >= 0.80,
            "de_low":            de is not None and de < de_thresh,
            "revenue_growing":   consistency_score(
                                   [(_v(rev_s[i],"") if False else
                                     (rev_s[i] - rev_s[i+1]) / abs(rev_s[i+1])
                                     if rev_s[i] is not None and rev_s[i+1] and rev_s[i+1]>0
                                     else None)
                                    for i in range(len(rev_s)-1)], 0) >= 0.60,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(eps_s, 0),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
