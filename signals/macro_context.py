"""
Macro Context Engine — dual-market regime classifier (US + India).
NOT a voting engine: weight=0.0, does not contribute to the weighted signal average.
The Aggregator reads this engine's metadata to apply a regime multiplier to all
bullish signal confidences before the vote.

US regime: majority vote of VIX, yield spread, S&P 500 vs 200d MA, sector breadth.
India regime: majority vote of India VIX, Nifty vs 200d MA, USD/INR change, FII 5-day net.
"""
from __future__ import annotations
import logging

from core.engine_base import BaseSignalEngine, DataBundle, Signal

logger = logging.getLogger(__name__)


class MacroContextEngine(BaseSignalEngine):
    """Macro regime classifier for US market. Returns regime metadata; does not vote."""

    name    = "macro_context"
    version = "1.0.0"
    weight  = 0.0   # excluded from signal aggregation; read as metadata only

    _thresholds: dict = {}

    def initialize(self, config: dict) -> None:
        m = config.get("macro", {})
        self._thresholds = {
            "vix_bearish":        float(m.get("vix_bearish_threshold",    30)),
            "vix_bullish":        float(m.get("vix_bullish_threshold",    20)),
            "spread_bearish":     float(m.get("yield_spread_bearish",    -0.001)),
            "spread_bullish":     float(m.get("yield_spread_bullish",     0.001)),
            "sp_bearish":         float(m.get("sp500_vs_200ma_bearish",  -0.05)),
            "sp_bullish":         float(m.get("sp500_vs_200ma_bullish",   0.05)),
            "breadth_bearish":    float(m.get("breadth_bearish",          0.35)),
            "breadth_bullish":    float(m.get("breadth_bullish",          0.65)),
            "mult_bearish":       float(m.get("regime_multiplier_bearish", 0.80)),
            "mult_bullish":       float(m.get("regime_multiplier_bullish", 1.10)),
        }

    def validate_data(self, data: DataBundle) -> bool:
        return bool(data.macro)

    def compute(self, data: DataBundle) -> Signal:
        macro = data.macro
        if data.market == "IN":
            return self._compute_india(macro, self._thresholds or {
                "sp_bearish": -0.05, "sp_bullish": 0.05,
                "mult_bearish": 0.80, "mult_bullish": 1.10,
            })
        t     = self._thresholds or {
            "vix_bearish": 30, "vix_bullish": 20,
            "spread_bearish": -0.001, "spread_bullish": 0.001,
            "sp_bearish": -0.05, "sp_bullish": 0.05,
            "breadth_bearish": 0.35, "breadth_bullish": 0.65,
            "mult_bearish": 0.80, "mult_bullish": 1.10,
        }

        votes: list[str] = []
        factor_detail: dict = {}

        # Factor 1: VIX level
        vix = macro.get("vix")
        if vix is not None:
            if vix > t["vix_bearish"]:
                votes.append("bearish");  factor_detail["vix"] = f"bearish ({vix:.1f} > {t['vix_bearish']})"
            elif vix < t["vix_bullish"]:
                votes.append("bullish");  factor_detail["vix"] = f"bullish ({vix:.1f} < {t['vix_bullish']})"
            else:
                votes.append("neutral");  factor_detail["vix"] = f"neutral ({vix:.1f})"

        # Factor 2: Yield spread (10yr − 2yr)
        spread = macro.get("yield_spread")
        if spread is not None:
            if spread < t["spread_bearish"]:
                votes.append("bearish");  factor_detail["spread"] = f"bearish ({spread:.4f} inverted)"
            elif spread > t["spread_bullish"]:
                votes.append("bullish");  factor_detail["spread"] = f"bullish ({spread:.4f} normal)"
            else:
                votes.append("neutral");  factor_detail["spread"] = f"neutral ({spread:.4f})"

        # Factor 3: S&P 500 vs 200d MA
        sp_vs_ma = macro.get("sp500_vs_200ma")
        if sp_vs_ma is not None:
            if sp_vs_ma < t["sp_bearish"]:
                votes.append("bearish");  factor_detail["sp_vs_200ma"] = f"bearish ({sp_vs_ma:.2%})"
            elif sp_vs_ma > t["sp_bullish"]:
                votes.append("bullish");  factor_detail["sp_vs_200ma"] = f"bullish ({sp_vs_ma:.2%})"
            else:
                votes.append("neutral");  factor_detail["sp_vs_200ma"] = f"neutral ({sp_vs_ma:.2%})"

        # Factor 4: Sector breadth
        breadth = macro.get("market_breadth")
        if breadth is not None:
            if breadth < t["breadth_bearish"]:
                votes.append("bearish");  factor_detail["breadth"] = f"bearish ({breadth:.0%})"
            elif breadth > t["breadth_bullish"]:
                votes.append("bullish");  factor_detail["breadth"] = f"bullish ({breadth:.0%})"
            else:
                votes.append("neutral");  factor_detail["breadth"] = f"neutral ({breadth:.0%})"

        # Majority vote — ties default to neutral (conservative)
        bearish_n = votes.count("bearish")
        bullish_n = votes.count("bullish")
        n = len(votes)
        if n == 0:
            regime = "neutral"
        elif bearish_n >= 2 and bearish_n >= bullish_n:
            regime = "bearish"
        elif bullish_n >= 2 and bullish_n > bearish_n:
            regime = "bullish"
        else:
            regime = "neutral"

        multiplier = {
            "bearish": t["mult_bearish"],
            "neutral": 1.0,
            "bullish": t["mult_bullish"],
        }[regime]

        vix_str    = f"{vix:.1f}" if vix is not None else "N/A"
        spread_str = f"{spread:.4f}" if spread is not None else "N/A"
        sp_str     = f"{sp_vs_ma:.2%}" if sp_vs_ma is not None else "N/A"
        reasoning  = (
            f"Macro regime: {regime} (mult={multiplier}) | "
            f"VIX={vix_str} spread={spread_str} sp_vs_200={sp_str} | "
            f"votes={votes}"
        )

        logger.info("MacroContext: regime=%s mult=%.2f | %s", regime, multiplier,
                    " | ".join(f"{k}={v}" for k, v in factor_detail.items()))

        return Signal(
            signal=regime,
            confidence=50.0,  # not meaningful (weight=0.0)
            weight=self.weight,
            reasoning=reasoning,
            metadata={
                "regime":         regime,
                "multiplier":     multiplier,
                "vix":            vix,
                "yield_spread":   spread,
                "sp500_vs_200ma": sp_vs_ma,
                "market_breadth": breadth,
                "factor_votes":   votes,
                "factor_detail":  factor_detail,
            },
        )

    # ─────────────────────────────────── India path

    def _compute_india(self, macro: dict, t: dict) -> Signal:
        """
        India regime: India VIX, Nifty vs 200d MA, USD/INR 30d change, FII 5d net.
        India VIX thresholds differ (20/13 vs US 30/20).
        """
        votes: list[str] = []
        factor_detail: dict = {}

        vix_in_bearish = 20.0
        vix_in_bullish = 13.0

        # Factor 1: India VIX
        vix = macro.get("india_vix")
        if vix is not None:
            if vix > vix_in_bearish:
                votes.append("bearish"); factor_detail["india_vix"] = f"bearish ({vix:.1f})"
            elif vix < vix_in_bullish:
                votes.append("bullish"); factor_detail["india_vix"] = f"bullish ({vix:.1f})"
            else:
                votes.append("neutral"); factor_detail["india_vix"] = f"neutral ({vix:.1f})"

        # Factor 2: Nifty vs 200d MA
        nifty_vs = macro.get("nifty_vs_200ma")
        if nifty_vs is not None:
            if nifty_vs < t["sp_bearish"]:
                votes.append("bearish"); factor_detail["nifty_vs_200"] = f"bearish ({nifty_vs:.2%})"
            elif nifty_vs > t["sp_bullish"]:
                votes.append("bullish"); factor_detail["nifty_vs_200"] = f"bullish ({nifty_vs:.2%})"
            else:
                votes.append("neutral"); factor_detail["nifty_vs_200"] = f"neutral ({nifty_vs:.2%})"

        # Factor 3: USD/INR 30d change (INR weakening = bearish for India equities)
        usdinr_chg = macro.get("usdinr_30d_change")
        if usdinr_chg is not None:
            if usdinr_chg > 0.02:    # INR depreciated >2% → bearish
                votes.append("bearish"); factor_detail["usdinr"] = f"bearish (INR -{usdinr_chg:.1%})"
            elif usdinr_chg < -0.01: # INR appreciated >1% → bullish
                votes.append("bullish"); factor_detail["usdinr"] = f"bullish (INR +{abs(usdinr_chg):.1%})"
            else:
                votes.append("neutral"); factor_detail["usdinr"] = f"neutral ({usdinr_chg:+.2%})"

        # Factor 4: FII 5-day net flow
        fii_5d = macro.get("net_fii_5d")
        if fii_5d is not None:
            if fii_5d < -2000:
                votes.append("bearish"); factor_detail["fii_5d"] = f"bearish ({fii_5d:,.0f} Cr)"
            elif fii_5d > 2000:
                votes.append("bullish"); factor_detail["fii_5d"] = f"bullish ({fii_5d:,.0f} Cr)"
            else:
                votes.append("neutral"); factor_detail["fii_5d"] = f"neutral ({fii_5d:,.0f} Cr)"

        bearish_n = votes.count("bearish")
        bullish_n = votes.count("bullish")
        n         = len(votes)
        if n == 0:
            regime = "neutral"
        elif bearish_n >= 2 and bearish_n >= bullish_n:
            regime = "bearish"
        elif bullish_n >= 2 and bullish_n > bearish_n:
            regime = "bullish"
        else:
            regime = "neutral"

        multiplier = {
            "bearish": t["mult_bearish"], "neutral": 1.0, "bullish": t["mult_bullish"],
        }[regime]

        logger.info("MacroContext[IN]: regime=%s mult=%.2f | %s", regime, multiplier,
                    " | ".join(f"{k}={v}" for k, v in factor_detail.items()))

        return Signal(
            signal=regime,
            confidence=50.0,
            weight=self.weight,
            reasoning=(
                f"India macro regime: {regime} (mult={multiplier}) | votes={votes}"
            ),
            metadata={
                "regime":          regime,
                "multiplier":      multiplier,
                "india_vix":       vix,
                "nifty_vs_200ma":  nifty_vs,
                "usdinr_30d_chg":  usdinr_chg,
                "fii_5d":          fii_5d,
                "factor_votes":    votes,
                "factor_detail":   factor_detail,
            },
        )

    def required_data_types(self) -> list[str]:
        return ["macro"]
