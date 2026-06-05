"""
Risk Engine — Phase 7.
Computes volatility-based position limits and cross-sectional correlation adjustments.
Called once per run across ALL tickers together (correlation is cross-sectional).

Outputs a PositionLimit per ticker, consumed by the Aggregator for quantity sizing.
"""
from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.engine_base import DataBundle

logger = logging.getLogger(__name__)

_DEFAULT_PORTFOLIO_VALUE = 100_000.0


@dataclass
class PositionLimit:
    ticker: str
    annualized_vol: float       # e.g. 0.25 = 25% annualized realized vol
    vol_tier: str               # low / medium_low / medium / high / very_high
    max_alloc_pct: float        # fraction of portfolio before corr adjustment
    corr_multiplier: float      # 0.70 / 1.0 / 1.10 from pairwise correlation
    max_position_usd: float     # portfolio_value × max_alloc_pct × corr_multiplier
    max_shares: int             # floor(max_position_usd / current_price)
    current_price: float        # last close price (needed by Aggregator for sizing)


class RiskEngine:
    """
    Volatility-based position sizer with pairwise correlation adjustment.

    Vol tiers (from config/engine.yaml risk.vol_tiers):
      low       : vol ≤ 0.15 → 25% max alloc
      medium_low: vol ≤ 0.22 → 20%
      medium    : vol ≤ 0.30 → 15%
      high      : vol ≤ 0.50 → 12.5%
      very_high : vol >  0.50 → 10%

    Correlation multiplier:
      max pairwise corr > 0.80 → × 0.70  (concentrate less)
      max pairwise corr < 0.30 → × 1.10  (diversification benefit)
      else                     → × 1.00
    """

    _FALLBACK_TIERS: list[tuple[str, float, float]] = [
        ("low",        0.15,  0.25),
        ("medium_low", 0.22,  0.20),
        ("medium",     0.30,  0.15),
        ("high",       0.50,  0.125),
        ("very_high",  999.0, 0.10),
    ]

    def __init__(self, config: dict):
        risk = config.get("risk", {})
        self.lookback          = int(  risk.get("vol_lookback_days",      60))
        self.corr_high_thresh  = float(risk.get("corr_high_threshold",   0.80))
        self.corr_low_thresh   = float(risk.get("corr_low_threshold",    0.30))
        self.corr_high_mult    = float(risk.get("corr_high_multiplier",  0.70))
        self.corr_low_mult     = float(risk.get("corr_low_multiplier",   1.10))
        self.default_portfolio = float(risk.get("default_portfolio_value", _DEFAULT_PORTFOLIO_VALUE))

        raw_tiers = risk.get("vol_tiers", {})
        if raw_tiers:
            self._vol_tiers = sorted(
                [
                    (name, float(v.get("threshold", 999.0)), float(v.get("max_alloc", 0.10)))
                    for name, v in raw_tiers.items()
                ],
                key=lambda t: t[1],
            )
        else:
            self._vol_tiers = self._FALLBACK_TIERS

    # ──────────────────────────────────── public

    def compute(
        self,
        data_bundles: dict[str, DataBundle],
        portfolio: Optional[dict] = None,
    ) -> dict[str, PositionLimit]:
        """
        Compute PositionLimit for each ticker.
        portfolio: {ticker: shares, "portfolio_value": float, "cash": float}
        """
        portfolio_value = float(
            (portfolio or {}).get("portfolio_value", self.default_portfolio)
        )

        # Build returns series and current prices
        returns_map: dict[str, list[float]] = {}
        price_map:   dict[str, float]       = {}

        for ticker, data in data_bundles.items():
            prices = data.prices
            if not prices:
                continue
            closes = [float(p["close"]) for p in prices]
            price_map[ticker] = closes[-1]
            if len(closes) >= 2:
                returns_map[ticker] = [
                    closes[i] / closes[i - 1] - 1.0
                    for i in range(1, len(closes))
                ]

        # Annualized vol per ticker
        vols: dict[str, float] = {}
        for ticker, rets in returns_map.items():
            lb_rets = rets[-self.lookback:] if len(rets) > self.lookback else rets
            if len(lb_rets) < 2:
                vols[ticker] = 0.30
            else:
                vols[ticker] = float(np.std(lb_rets, ddof=1)) * math.sqrt(252)

        # Cross-sectional correlation matrix
        corr_matrix = self._compute_correlation(returns_map)

        # Build PositionLimit per ticker
        limits: dict[str, PositionLimit] = {}
        for ticker, data in data_bundles.items():
            ann_vol   = vols.get(ticker, 0.30)
            tier_name, max_alloc = self._vol_tier(ann_vol)
            corr_mult = self._corr_multiplier(ticker, corr_matrix)
            price     = price_map.get(ticker, 0.0)

            max_pos_usd = portfolio_value * max_alloc * corr_mult
            max_shares  = max(1, int(max_pos_usd / price)) if price > 0 else 0

            limits[ticker] = PositionLimit(
                ticker           = ticker,
                annualized_vol   = round(ann_vol, 4),
                vol_tier         = tier_name,
                max_alloc_pct    = max_alloc,
                corr_multiplier  = round(corr_mult, 3),
                max_position_usd = round(max_pos_usd, 2),
                max_shares       = max_shares,
                current_price    = price,
            )
            logger.debug(
                "Risk [%s]: vol=%.1f%% tier=%s alloc=%.1f%% corr=%.2f "
                "max_pos=$%.0f (%d shares @ $%.2f)",
                ticker, ann_vol * 100, tier_name, max_alloc * 100,
                corr_mult, max_pos_usd, max_shares, price,
            )

        return limits

    # ──────────────────────────────────── helpers

    def _vol_tier(self, ann_vol: float) -> tuple[str, float]:
        for name, threshold, max_alloc in self._vol_tiers:
            if ann_vol <= threshold:
                return name, max_alloc
        return self._vol_tiers[-1][0], self._vol_tiers[-1][2]

    def _compute_correlation(
        self, returns_map: dict[str, list[float]]
    ) -> dict[str, dict[str, float]]:
        tickers = [t for t, r in returns_map.items() if len(r) >= 2]
        if len(tickers) < 2:
            return {}

        min_len = min(len(returns_map[t]) for t in tickers)
        lb = min(min_len, self.lookback)
        if lb < 2:
            return {}

        matrix = np.array([returns_map[t][-lb:] for t in tickers])
        try:
            corr = np.corrcoef(matrix)
        except Exception as e:
            logger.debug("Correlation computation failed: %s", e)
            return {}

        result: dict[str, dict[str, float]] = {}
        for i, t1 in enumerate(tickers):
            result[t1] = {
                t2: float(corr[i, j])
                for j, t2 in enumerate(tickers)
                if i != j
            }
        return result

    def _corr_multiplier(
        self, ticker: str, corr_matrix: dict[str, dict[str, float]]
    ) -> float:
        peers = corr_matrix.get(ticker, {})
        if not peers:
            return 1.0
        max_corr = max(abs(v) for v in peers.values())
        if max_corr > self.corr_high_thresh:
            return self.corr_high_mult
        if max_corr < self.corr_low_thresh:
            return self.corr_low_mult
        return 1.0
