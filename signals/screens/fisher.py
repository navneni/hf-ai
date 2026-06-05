from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _cagr, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class FisherScreen(BaseSignalEngine):
    """Phil Fisher: long-term growth — revenue CAGR, expanding margins, increasing R&D."""
    name = "fisher_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        ratios = data.ratios or {}

        rev_thresh = thr.get("fisher_revenue_cagr", 15) / 100

        rev_s = [_v(f,"revenue") for f in annual[:6]]
        rev_cagr = _cagr(rev_s, 5)

        gm_s = [(_v(f,"gross_profit") / _v(f,"revenue"))
                if (_v(f,"gross_profit") and _v(f,"revenue") and _v(f,"revenue")>0) else None
                for f in annual[:5]]
        op_s = [(_v(f,"operating_income") / _v(f,"revenue"))
                if (_v(f,"operating_income") and _v(f,"revenue") and _v(f,"revenue")>0) else None
                for f in annual[:5]]

        # Expanding: recent avg > older avg
        def _expanding(series):
            vals = [v for v in series if v is not None]
            if len(vals) < 3:
                return False
            mid = len(vals) // 2
            return sum(vals[:mid]) / mid > sum(vals[mid:]) / (len(vals) - mid)

        checks = {
            "revenue_cagr":    rev_cagr is not None and rev_cagr > rev_thresh,
            "gross_expanding": _expanding(gm_s),
            "op_expanding":    _expanding(op_s),
            "revenue_stable":  consistency_score(
                                 [r for r in rev_s if r is not None], 0) >= 0.80,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score([r for r in rev_s if r], 0),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
