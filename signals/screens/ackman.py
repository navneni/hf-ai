from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class AckmanScreen(BaseSignalEngine):
    """Bill Ackman: large-cap activist — big revenue, positive FCF, margin improvement potential."""
    name = "ackman_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}

        rev_min = thr.get("ackman_min_revenue", 1_000_000_000)

        rev      = _v(latest,"revenue") or _v(ratios,"totalRevenue")
        fcf      = _v(latest,"free_cash_flow")
        op_m     = _v(ratios,"operating_margin")
        # Margin improvement potential: current op margin below sector average (proxy: < 15%)
        om_s     = [(_v(f,"operating_income") / _v(f,"revenue"))
                    if (_v(f,"operating_income") and _v(f,"revenue") and _v(f,"revenue")>0) else None
                    for f in annual[:3]]
        om_recent = next((v for v in om_s if v is not None), None)
        fcf_s    = [_v(f,"free_cash_flow") for f in annual[:5]]

        checks = {
            "large_company":     rev is not None and rev > rev_min,
            "fcf_positive":      fcf is not None and fcf > 0,
            "fcf_consistency":   consistency_score(fcf_s, 0) >= 0.60,
            "margin_potential":  om_recent is not None and 0 < om_recent < 0.20,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(fcf_s, 0),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
