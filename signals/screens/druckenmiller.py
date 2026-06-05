from __future__ import annotations
import numpy as np
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class DruckenmillerScreen(BaseSignalEngine):
    """Stanley Druckenmiller: momentum + earnings acceleration + sector tailwind."""
    name = "druckenmiller"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return bool(data.prices and len(data.prices) >= 60)

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        ratios = data.ratios or {}
        macro  = data.macro or {}

        mom_thresh = thr.get("druckenmiller_momentum", 20) / 100

        # 52-week momentum
        prices = sorted(data.prices, key=lambda p: p.get("date",""))
        close  = [p.get("close",0) for p in prices]
        mom_52w = (close[-1] / close[max(-252, -len(close))] - 1) if len(close) >= 52 else None

        # EPS acceleration: recent YoY EPS growth > prior YoY EPS growth
        eps_acc = False
        if len(annual) >= 3:
            e0, e1, e2 = (_v(annual[i],"eps") for i in range(3))
            if e0 and e1 and e2 and e1>0 and e2>0:
                g1 = (e0-e1)/e1; g2 = (e1-e2)/e2
                eps_acc = g1 > g2

        # OBV trend (last 20 days)
        obv_up = False
        if len(prices) >= 20:
            recent = prices[-20:]
            closes = np.array([p.get("close",0) for p in recent])
            vols   = np.array([p.get("volume",0) for p in recent])
            signs  = np.sign(np.diff(np.concatenate([[closes[0]], closes])))
            obv    = np.cumsum(signs * vols)
            obv_up = obv[-1] > obv[-10] if len(obv) >= 10 else False

        # Sector ETF 3m return (from macro context — Phase 6)
        sector_pos = None
        sector_returns = macro.get("sector_returns_3m", {})
        ticker_sector  = (ratios.get("sector") or "").lower()
        for etf_name, ret in sector_returns.items():
            if any(kw in ticker_sector for kw in (etf_name.lower().replace("xl",""),)):
                sector_pos = ret > 0
                break

        checks = {
            "momentum_52w": mom_52w is not None and mom_52w > mom_thresh,
            "eps_accel":    eps_acc,
            "obv_rising":   obv_up,
        }
        if sector_pos is not None:
            checks["sector_tailwind"] = sector_pos

        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs, cs,
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
