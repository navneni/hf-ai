from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest, consistency_score,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class BuffettScreen(BaseSignalEngine):
    """Warren Buffett: durable competitive advantage, consistent FCF, DCF margin of safety."""
    name = "buffett_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 5

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}
        mc     = data.market_config or {}

        roe_thresh = thr.get("buffett_roe", 15) / 100
        de_thresh  = thr.get("buffett_de", 0.5)
        ms_thresh  = thr.get("buffett_margin_safety", 25) / 100
        nm_thresh  = thr.get("buffett_net_margin", 10) / 100

        roe_s = [(_v(f,"net_income") / max(_v(f,"equity") or 1e-6, 1e-6))
                 for f in annual[:10] if _v(f,"net_income") and _v(f,"equity")]
        fcf_s = [_v(f,"free_cash_flow") for f in annual[:10]]

        # DCF margin of safety
        mos = None
        try:
            from signals.valuation import _three_stage_dcf, _fcf_cagr, _margin_of_safety
            mktcap = _v(ratios,"market_cap"); shares = _v(annual[0],"shares_outstanding") if annual else None
            price  = (mktcap/shares) if (mktcap and shares and shares>0) else None
            cagr   = _fcf_cagr(data.financials, 5)
            fcf    = _v(latest,"free_cash_flow")
            wacc   = mc.get("risk_free_rate", 0.053) + 0.055
            if fcf and fcf>0 and cagr is not None and price:
                iv = _three_stage_dcf(fcf, cagr, wacc)
                mos = _margin_of_safety((iv/shares) if (iv and shares) else None, price)
        except Exception:
            pass

        checks = {
            "roe_consistency": consistency_score(roe_s, roe_thresh) >= 0.80,
            "de_low":          (_v(ratios,"debt_to_equity") or 999) < de_thresh,
            "fcf_consistency": consistency_score(fcf_s, 0) >= 0.80,
            "net_margin":      (_v(ratios,"net_margin") or 0) > nm_thresh,
            "dcf_mos":         mos is not None and mos > ms_thresh,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs,
                            consistency_score(roe_s, roe_thresh),
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
