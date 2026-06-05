"""
Institutional Flow Engine — US path (Phase 6).
India path implemented in Phase 9.

Signal sources and weights (within this engine):
  1. Short interest squeeze setup   — bullish when SI high + declining
  2. Institutional ownership (13F proxy) — directional signal
  3. CBOE P/C ratio                 — contrarian: high put volume → bullish
  4. IV rank                        — high IV → caution on longs
  5. Dark pool activity              — rising off-exchange volume → accumulation

Engine weight: 0.10 (configurable in engine.yaml)
"""
from __future__ import annotations
import logging

from core.engine_base import BaseSignalEngine, DataBundle, Signal

logger = logging.getLogger(__name__)


class InstitutionalFlowEngine(BaseSignalEngine):
    """Institutional flow signal from 13F proxy, SI, CBOE options, and dark pool."""

    name    = "institutional_flow"
    version = "1.0.0"
    weight  = 0.10

    def initialize(self, config: dict) -> None:
        eng_cfg = config.get("engines", {}).get("institutional_flow", {})
        w = eng_cfg.get("weight")
        if w is not None:
            self.weight = float(w)

    def validate_data(self, data: DataBundle) -> bool:
        return True   # both markets; returns neutral if data missing

    def compute(self, data: DataBundle) -> Signal:
        if data.market == "IN":
            return self._compute_india(data)

        flow = data.inst_flow_us or {}

        # ── Sub-signal contributions: (label, score, weight_within_engine)
        sub: list[tuple[str, float, float]] = []
        meta: dict = {}

        # 1. Short-interest signal
        si_pct   = flow.get("si_pct")
        si_cover = flow.get("si_days_to_cover")
        si_chg   = flow.get("si_biweekly_change")   # usually None in Phase 6

        if si_pct is not None:
            if si_pct > 0.15:
                if si_chg is not None and si_chg < -0.05:
                    # High SI + actively covering → short squeeze → bullish
                    sub.append(("si_squeeze", +0.70, 1.5))
                    meta["si"] = f"squeeze setup (SI={si_pct:.1%}, chg={si_chg:.1%})"
                else:
                    # High SI but no confirmed squeeze → mild caution
                    sub.append(("si_high", -0.20, 1.0))
                    meta["si"] = f"elevated (SI={si_pct:.1%})"
            elif si_pct < 0.02:
                # Very low short interest — institutions bullish
                sub.append(("si_low", +0.25, 0.5))
                meta["si"] = f"clean (SI={si_pct:.1%})"

        if si_cover is not None:
            meta["days_to_cover"] = round(si_cover, 1)

        # 2. Institutional ownership (13F proxy)
        inst_pct = flow.get("inst_ownership_pct")
        if inst_pct is not None:
            if inst_pct > 0.70:
                sub.append(("inst_heavy", +0.30, 1.0))
                meta["inst_ownership"] = f"high ({inst_pct:.0%})"
            elif inst_pct < 0.20:
                sub.append(("inst_light", -0.20, 1.0))
                meta["inst_ownership"] = f"low ({inst_pct:.0%})"
            else:
                meta["inst_ownership"] = f"moderate ({inst_pct:.0%})"

        # 3. CBOE P/C ratio (contrarian — extreme put buying = fear peak = bullish)
        pc = flow.get("pc_ratio")
        if pc is not None:
            if pc > 1.5:
                sub.append(("pc_contrarian", +0.40, 1.5))
                meta["pc_ratio"] = f"contrarian bullish ({pc:.2f})"
            elif pc < 0.50:
                sub.append(("pc_caution", -0.25, 1.0))
                meta["pc_ratio"] = f"complacency caution ({pc:.2f})"
            else:
                meta["pc_ratio"] = f"neutral ({pc:.2f})"

        # 4. IV rank — high IV means expensive options, often near price peaks
        iv_rank = flow.get("iv_rank")
        if iv_rank is not None and iv_rank > 80:
            sub.append(("iv_expensive", -0.20, 0.8))
            meta["iv_rank"] = f"expensive ({iv_rank:.0f})"
        elif iv_rank is not None:
            meta["iv_rank"] = round(iv_rank, 0)

        # 5. Dark pool (off-exchange) activity
        dp_pct = flow.get("dark_pool_pct")
        if dp_pct is not None:
            if dp_pct > 0.55:
                # High off-exchange volume often indicates institutional accumulation
                sub.append(("dark_pool_high", +0.20, 0.8))
                meta["dark_pool"] = f"high OTC ({dp_pct:.0%})"
            elif dp_pct < 0.30:
                meta["dark_pool"] = f"normal ({dp_pct:.0%})"

        # ── No data at all
        if not sub:
            return Signal(
                signal="neutral",
                confidence=25.0,
                weight=self.weight,
                reasoning="Insufficient institutional flow data",
                metadata={"flow_data": bool(flow)},
            )

        # ── Weighted composite score
        total_w  = sum(w for _, _, w in sub)
        net      = sum(s * w for _, s, w in sub) / total_w

        if net > 0.15:
            signal     = "bullish"
            confidence = min(88.0, net * 100 * 1.2)
        elif net < -0.15:
            signal     = "bearish"
            confidence = min(88.0, abs(net) * 100 * 1.2)
        else:
            signal     = "neutral"
            confidence = 35.0

        reasoning = (
            f"Inst flow: {signal} (net={net:+.3f}) | "
            + " | ".join(f"{k}={v}" for k, v in meta.items())
        )

        return Signal(
            signal=signal,
            confidence=round(confidence, 1),
            weight=self.weight,
            reasoning=reasoning,
            metadata={
                "net_score":     round(net, 4),
                "sub_signals":   {label: score for label, score, _ in sub},
                "si_pct":        si_pct,
                "pc_ratio":      pc,
                "iv_rank":       iv_rank,
                "dark_pool_pct": dp_pct,
                **meta,
            },
        )

    # ─────────────────────────────────── India path

    def _compute_india(self, data: DataBundle) -> Signal:
        """
        India institutional flow signal.
        Sources: FII/DII 5-day net flow + bulk deal direction.
        FII sector breakdown divergence is best-effort via inst_flow_india.
        """
        flow_india = data.inst_flow_india or {}
        bulk       = data.bulk_deals or []

        sub:  list[tuple[str, float, float]] = []
        meta: dict = {}

        # 1. FII net 5-day flow (from inst_flow_india; fallback to macro dict)
        net_fii_5d = (
            flow_india.get("net_fii_5d")
            or (data.macro.get("net_fii_5d") if data.macro else None)
        )
        if net_fii_5d is not None:
            # Scale: ±5000 Cr = typical large day. Use ±2000 Cr as moderate signal.
            normalized = max(-1.0, min(1.0, net_fii_5d / 10_000.0))
            if abs(normalized) > 0.10:
                sub.append(("fii_5d", normalized, 2.0))
                meta["fii_5d"] = f"{'bullish' if normalized > 0 else 'bearish'} ({net_fii_5d:+,.0f} Cr)"

        # 2. DII net 5-day (partially offsets FII — DIIs are domestic contra players)
        net_dii_5d = flow_india.get("net_dii_5d")
        if net_dii_5d is not None:
            normalized_dii = max(-1.0, min(1.0, net_dii_5d / 10_000.0))
            # DII buying when FII sells often cushions downside (weight 0.5)
            if abs(normalized_dii) > 0.10:
                sub.append(("dii_5d", normalized_dii, 0.8))
                meta["dii_5d"] = f"{'bullish' if normalized_dii > 0 else 'bearish'} ({net_dii_5d:+,.0f} Cr)"

        # 3. Bulk deals — promoter/institution buy vs sell
        if bulk:
            ticker_sym = data.ticker.replace(".NS", "").replace(".BO", "").upper()
            recent_bulk = [
                b for b in bulk
                if b.get("date", "") >= str(
                    __import__("datetime").date.fromisoformat(data.as_of_date)
                    - __import__("datetime").timedelta(days=30)
                )
            ]
            buy_qty  = sum(b.get("quantity", 0) or 0 for b in recent_bulk
                          if "buy" in str(b.get("buy_sell", "")).lower())
            sell_qty = sum(b.get("quantity", 0) or 0 for b in recent_bulk
                          if "sell" in str(b.get("buy_sell", "")).lower())
            if buy_qty + sell_qty > 0:
                bulk_score = (buy_qty - sell_qty) / (buy_qty + sell_qty)
                sub.append(("bulk_deals", bulk_score, 1.0))
                meta["bulk_deals"] = f"ratio={bulk_score:+.2f} (buy={buy_qty:,} sell={sell_qty:,})"

        if not sub:
            return Signal(
                signal="neutral",
                confidence=25.0,
                weight=self.weight,
                reasoning="No India institutional flow data available",
                metadata={"path": "IN"},
            )

        total_w = sum(w for _, _, w in sub)
        net     = sum(s * w for _, s, w in sub) / total_w

        if net > 0.15:
            signal, confidence = "bullish", min(85.0, abs(net) * 100 * 1.2)
        elif net < -0.15:
            signal, confidence = "bearish", min(85.0, abs(net) * 100 * 1.2)
        else:
            signal, confidence = "neutral", 35.0

        return Signal(
            signal=signal,
            confidence=round(confidence, 1),
            weight=self.weight,
            reasoning=(
                f"India inst flow: {signal} (net={net:+.3f}) | "
                + " | ".join(f"{k}={v}" for k, v in meta.items())
            ),
            metadata={
                "path":       "IN",
                "net_score":  round(net, 4),
                "net_fii_5d": net_fii_5d,
                "net_dii_5d": net_dii_5d,
                **meta,
            },
        )

    def required_data_types(self) -> list[str]:
        return ["inst_flow_us", "inst_flow_india"]
