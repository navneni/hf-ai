from __future__ import annotations
import numpy as np
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class TalebScreen(BaseSignalEngine):
    """Nassim Taleb: anti-fragile — low leverage, high cash, stable FCF, no concentration."""
    name = "taleb_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}

        de_thresh  = thr.get("taleb_de", 0.2)
        cr_thresh  = thr.get("taleb_cash_ratio", 0.2)

        de         = _v(ratios,"debt_to_equity")
        assets     = _v(latest,"total_assets")
        cash       = _v(latest,"cash")
        cash_ratio = (cash / assets) if (cash and assets and assets>0) else None

        # FCF stability: coefficient of variation < 0.20
        fcf_s = [_v(f,"free_cash_flow") for f in annual[:5] if _v(f,"free_cash_flow") is not None]
        fcf_cv = None
        if len(fcf_s) >= 3:
            mean_fcf = abs(float(np.mean(fcf_s)))
            if mean_fcf > 0:
                fcf_cv = float(np.std(fcf_s)) / mean_fcf

        checks = {
            "low_leverage":  de is not None and de < de_thresh,
            "high_cash":     cash_ratio is not None and cash_ratio > cr_thresh,
            "fcf_stable":    fcf_cv is not None and fcf_cv < 0.30,
            "fcf_positive":  bool(fcf_s and sum(1 for f in fcf_s if f > 0) / len(fcf_s) >= 0.80),
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            (1.0 if fcf_cv is not None and fcf_cv < 0.30 else 0.3),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
