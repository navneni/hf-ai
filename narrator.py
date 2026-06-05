"""
Ollama Narrative Generator — Phase 10.
Generates a short plain-English explanation of a trading decision.

Contract:
  - 10-second HTTP timeout — never blocks the decision pipeline.
  - Returns None if Ollama is unreachable, disabled, or times out.
  - Synchronous — no threads or async.
  - Never called unless engine.yaml ollama.enabled = true AND --explain flag is set.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """You are a concise financial analyst.
Summarize this trading signal in 2-3 sentences for a portfolio manager.
Be factual, specific, and mention the key drivers.

Ticker: {ticker}
Action: {action}
Confidence: {confidence:.1f}%
Macro Regime: {macro_regime}
Net Score: {net_score:+.3f}
Top signals:
{signal_lines}

Write a brief narrative explanation:"""


def generate_narrative(
    decision,
    config: Optional[dict] = None,
) -> Optional[str]:
    """
    Generate a plain-English narrative for a TradingDecision via Ollama.
    Returns None on any failure (unreachable, timeout, disabled).

    decision: TradingDecision dataclass
    config:   dict from ConfigManager._data (reads ollama section)
    """
    cfg = (config or {}).get("ollama", {})
    if not cfg.get("enabled", False):
        return None

    base_url = cfg.get("base_url", "http://localhost:11434")
    model    = cfg.get("model", "llama3.2:3b")
    timeout  = int(cfg.get("timeout_seconds", 10))

    # Build signal summary lines (top 5 by confidence)
    signals = getattr(decision, "signals", {}) or {}
    top = sorted(
        [(name, sig) for name, sig in signals.items() if name != "macro_context"],
        key=lambda x: x[1].confidence,
        reverse=True,
    )[:5]
    signal_lines = "\n".join(
        f"  {name}: {sig.signal} (conf={sig.confidence:.1f}%)"
        for name, sig in top
    )

    prompt = _PROMPT_TEMPLATE.format(
        ticker=decision.ticker,
        action=decision.action.upper(),
        confidence=decision.confidence,
        macro_regime=decision.macro_regime,
        net_score=decision.net_score,
        signal_lines=signal_lines or "  (none)",
    )

    try:
        import requests
        resp = requests.post(
            f"{base_url}/api/generate",
            json={
                "model":  model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 150, "temperature": 0.3},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        narrative = data.get("response", "").strip()
        if narrative:
            logger.debug("Narrator generated %d chars for %s", len(narrative), decision.ticker)
            return narrative
    except Exception as e:
        logger.debug("Ollama narrator failed for %s: %s", decision.ticker, e)

    return None
