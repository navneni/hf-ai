from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class DamodaranScreen(BaseSignalEngine):
    """Aswath Damodaran: DCF intrinsic value gap > 20% margin of safety."""
    name = "damodaran_screen"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        ratios = data.ratios or {}
        return bool(data.financials and
                    (ratios.get("market_cap") or ratios.get("pe_ratio")))

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}
        mc     = data.market_config or {}

        mos_thresh = thr.get("damodaran_margin_of_safety", 20) / 100

        mos = None
        try:
            from signals.valuation import _three_stage_dcf, _fcf_cagr, _margin_of_safety
            mktcap = _v(ratios,"market_cap")
            shares = _v(annual[0],"shares_outstanding") if annual else None
            price  = (mktcap/shares) if (mktcap and shares and shares>0) else None
            cagr   = _fcf_cagr(data.financials, 5)
            fcf    = _v(latest,"free_cash_flow")
            wacc   = mc.get("risk_free_rate", 0.053) + 0.055
            if fcf and fcf>0 and cagr is not None and price:
                iv  = _three_stage_dcf(fcf, cagr, wacc)
                mos = _margin_of_safety((iv/shares) if (iv and shares) else None, price)
        except Exception:
            pass

        checks = {
            "dcf_mos": mos is not None and mos > mos_thresh,
        }
        cs = float(checks["dcf_mos"])
        return _make_signal(self, checks, cs, cs,
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
