from __future__ import annotations
from core.engine_base import BaseSignalEngine, DataBundle, Signal
from signals.screens import (_v, _annual_sorted, _ttm_or_latest, _cagr,
                              moat_text_score, management_quality_score, _make_signal,
                              SCREEN_WEIGHT)


class JhunjhunwalaScreen(BaseSignalEngine):
    """Rakesh Jhunjhunwala: India growth — EPS CAGR, revenue CAGR, promoter holding, ROCE."""
    name = "jhunjhunwala"; version = "1.0.0"; weight = SCREEN_WEIGHT

    def initialize(self, config):
        self._us = config.get("us_thresholds", {}); self._in = config.get("india_thresholds", {})

    def validate_data(self, data):
        return len(_annual_sorted(data.financials)) >= 3

    def compute(self, data: DataBundle) -> Signal:
        thr    = self._us if data.market == "US" else self._in
        annual = _annual_sorted(data.financials)
        latest = _ttm_or_latest(data.financials) or {}
        ratios = data.ratios or {}

        eps_thresh  = thr.get("jhunjhunwala_eps_cagr", 20) / 100
        rev_thresh  = thr.get("jhunjhunwala_revenue_cagr", 15) / 100
        prom_thresh = thr.get("jhunjhunwala_promoter", 50)   # % for India
        roce_thresh = thr.get("jhunjhunwala_roce", 20) / 100

        eps_s = [_v(f,"eps") for f in annual[:4]]
        rev_s = [_v(f,"revenue") for f in annual[:4]]

        eps_cagr = _cagr(eps_s, 3)
        rev_cagr = _cagr(rev_s, 3)

        # ROCE = EBIT / (Total Assets - Current Liabilities)
        ebit   = _v(latest,"ebit") or _v(latest,"operating_income")
        assets = _v(latest,"total_assets")
        cl     = _v(latest,"current_liabilities")
        cap_em = ((assets or 0) - (cl or 0))
        roce   = (ebit / cap_em) if (ebit and cap_em and cap_em > 0) else None

        # Promoter holding (India) or insider ownership proxy (US)
        promoter_ok = False
        if data.promoter_holdings:
            ph = sorted(data.promoter_holdings, key=lambda p: p.get("quarter",""), reverse=True)
            if ph:
                promoter_pct = ph[0].get("promoter_pct", 0)
                promoter_ok  = promoter_pct >= prom_thresh
        elif ratios.get("market_cap"):
            # US: high ROE and buybacks as proxy for alignment
            roe = _v(ratios,"roe")
            promoter_ok = roe is not None and roe > 0.25

        checks = {
            "eps_cagr":    eps_cagr is not None and eps_cagr > eps_thresh,
            "rev_cagr":    rev_cagr is not None and rev_cagr > rev_thresh,
            "promoter":    promoter_ok,
            "roce":        roce is not None and roce > roce_thresh,
        }
        cs = sum(checks.values()) / len(checks)
        return _make_signal(self, checks, cs, cs,
                            moat_text_score(data.filing_text or ""),
                            management_quality_score(annual, ratios),
                            data.filing_text or "")
