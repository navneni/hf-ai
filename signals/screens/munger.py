from __future__ import annotations
import numpy as np
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class MungerScreen(BaseSignalEngine):
    """Charlie Munger: moat stability — high consistent ROE, operating margin, low variance."""
    name = "munger_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        ratios = data.ratios or {}

        roe_thresh = thr.get("munger_roe", 20) / 100
        om_thresh  = thr.get("munger_op_margin", 20) / 100

        roe_s = [(_v(f,"net_income") / max(_v(f,"equity") or 1e-6, 1e-6))
                 for f in annual[:10] if _v(f,"net_income") and _v(f,"equity")]
        om_s  = [(_v(f,"operating_income") / _v(f,"revenue"))
                 if (_v(f,"operating_income") and _v(f,"revenue") and _v(f,"revenue")>0) else None
                 for f in annual[:10]]

        roe_cv = (float(np.std(roe_s)) / max(abs(float(np.mean(roe_s))), 1e-4)
                  if len(roe_s) >= 3 else 1.0)

        checks = {
            "roe_consistency": consistency_score(roe_s, roe_thresh) >= 0.80,
            "op_margin":       (_v(ratios,"operating_margin") or 0) > om_thresh,
            "roe_stability":   roe_cv < 0.25,
            "op_consistency":  consistency_score([v for v in om_s if v], om_thresh) >= 0.60,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(roe_s, roe_thresh),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
