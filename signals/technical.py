"""
Technical Analysis Signal Engine.
Multi-timeframe (daily, weekly, monthly) confluence.
Indicators: EMA crossover, RSI, MACD, Bollinger, ADX, Momentum, Hurst,
            OBV, VWAP, MFI (volume).
"""
from __future__ import annotations
import logging
from typing import Optional

import numpy as np
import pandas as pd

from core.engine_base import BaseSignalEngine, DataBundle, Signal

logger = logging.getLogger(__name__)


# ─────────────────────────────────────── indicator helpers

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = gain / (loss + 1e-10)
    return 100 - 100 / (1 + rs)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr   = pd.concat([high - low,
                      (high - close.shift()).abs(),
                      (low  - close.shift()).abs()], axis=1).max(axis=1)
    atr  = tr.ewm(com=period - 1, adjust=False).mean()

    dm_p = high.diff()
    dm_n = -low.diff()
    dm_p = dm_p.where((dm_p > dm_n) & (dm_p > 0), 0.0)
    dm_n = dm_n.where((dm_n > dm_p) & (dm_n > 0), 0.0)

    di_p = 100 * dm_p.ewm(com=period - 1, adjust=False).mean() / (atr + 1e-10)
    di_n = 100 * dm_n.ewm(com=period - 1, adjust=False).mean() / (atr + 1e-10)
    dx   = 100 * (di_p - di_n).abs() / (di_p + di_n + 1e-10)
    return dx.ewm(com=period - 1, adjust=False).mean()


def _hurst(prices: np.ndarray) -> float:
    """
    Estimate Hurst exponent via RMSE of lagged differences.
    H > 0.5 → trending/persistent; H < 0.5 → mean-reverting.
    Uses sqrt(E[(prices[t+k] - prices[t])^2]) which scales as k^H.
    """
    n = len(prices)
    if n < 20:
        return 0.5
    lags = range(2, min(n // 2, 40))
    tau = [np.sqrt(np.mean(np.square(prices[lag:] - prices[:-lag]))) + 1e-10
           for lag in lags]
    slope = np.polyfit(np.log(list(lags)), np.log(tau), 1)[0]
    return float(np.clip(slope, 0.0, 1.0))


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series,
         volume: pd.Series, period: int = 14) -> pd.Series:
    tp  = (high + low + close) / 3
    rmf = tp * volume
    pos = rmf.where(tp > tp.shift(), 0.0).rolling(period).sum()
    neg = rmf.where(tp < tp.shift(), 0.0).rolling(period).sum()
    return 100 - 100 / (1 + pos / (neg + 1e-10))


# ─────────────────────────────────────── single-timeframe analysis

def _analyze(df: pd.DataFrame) -> Optional[dict]:
    """
    Returns {signal, confidence, meta} for one timeframe,
    or None if data is insufficient.
    """
    if len(df) < 10:
        return None

    close  = df["close"]
    high   = df.get("high", close)
    low    = df.get("low",  close)
    volume = df.get("volume", pd.Series(0, index=df.index))
    n      = len(close)
    scores: dict[str, float] = {}
    meta:   dict = {}

    # 1. EMA Crossover (8/21/55)
    if n >= 55:
        e8  = close.ewm(span=8,  adjust=False).mean().iloc[-1]
        e21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
        e55 = close.ewm(span=55, adjust=False).mean().iloc[-1]
        if   e8 > e21 > e55: scores["ema"] =  1.0
        elif e55 > e21 > e8: scores["ema"] = -1.0
        elif e8 > e21:       scores["ema"] =  0.5
        else:                scores["ema"] = -0.5
        meta.update({"ema8": round(e8, 2), "ema21": round(e21, 2), "ema55": round(e55, 2)})

    # 2. RSI-14
    if n >= 16:
        r14 = _rsi(close, 14).iloc[-1]
        if   r14 < 30: scores["rsi"] =  1.0
        elif r14 < 45: scores["rsi"] =  0.4
        elif r14 > 70: scores["rsi"] = -1.0
        elif r14 > 55: scores["rsi"] = -0.4
        else:          scores["rsi"] =  0.0
        meta["rsi14"] = round(r14, 1)

    # 3. MACD (12/26/9)
    if n >= 35:
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        sig  = macd.ewm(span=9, adjust=False).mean()
        m, s = macd.iloc[-1], sig.iloc[-1]
        if n >= 36:
            mp, sp = macd.iloc[-2], sig.iloc[-2]
            if   m > s and mp <= sp: scores["macd"] =  1.0   # bullish crossover
            elif m > s:              scores["macd"] =  0.5
            elif m < s and mp >= sp: scores["macd"] = -1.0   # bearish crossover
            else:                    scores["macd"] = -0.5
        else:
            scores["macd"] = 0.5 if m > s else -0.5
        meta["macd_hist"] = round(m - s, 4)

    # 4. Bollinger Bands (20, 2σ)
    if n >= 22:
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        z   = (close.iloc[-1] - sma.iloc[-1]) / (std.iloc[-1] + 1e-10)
        scores["bb"] = float(np.clip(-z, -1.0, 1.0))   # negative z = oversold = bullish
        meta["bb_zscore"] = round(z, 3)

    # 5. Momentum (1m / 3m / 6m)
    mom_votes = []
    for lb, tag in [(21, "1m"), (63, "3m"), (126, "6m")]:
        if n >= lb + 1:
            ret = close.iloc[-1] / close.iloc[-lb] - 1
            mom_votes.append(1.0 if ret > 0 else -1.0)
            meta[f"mom_{tag}"] = round(ret * 100, 2)
    if mom_votes:
        scores["momentum"] = sum(mom_votes) / len(mom_votes)

    # 6. Volume: OBV trend + MFI
    if n >= 10 and hasattr(volume, "sum") and volume.sum() > 0:
        # OBV
        obv = (np.sign(close.diff().fillna(0)) * volume).cumsum()
        win = min(20, n // 2)
        obv_ma = obv.rolling(win).mean()
        price_up = close.iloc[-1] > close.iloc[-win]
        obv_up   = obv.iloc[-1]  > obv_ma.iloc[-1]
        if obv_up and price_up:       vol_s =  0.8
        elif not obv_up and not price_up: vol_s = -0.8
        elif obv_up:                  vol_s =  0.3   # accumulation
        else:                         vol_s = -0.5   # distribution
        # MFI modifier
        if n >= 16 and isinstance(high, pd.Series) and isinstance(low, pd.Series):
            mfi_val = _mfi(high, low, close, volume, 14).iloc[-1]
            if not np.isnan(mfi_val):
                meta["mfi"] = round(mfi_val, 1)
                if mfi_val < 20:  vol_s = min(1.0, vol_s + 0.3)   # oversold volume
                if mfi_val > 80:  vol_s = max(-1.0, vol_s - 0.3)  # overbought
        scores["volume"] = vol_s

    # ADX (strength modifier, no direction vote)
    adx_val = None
    if n >= 20 and isinstance(high, pd.Series) and isinstance(low, pd.Series):
        adx_s = _adx(high, low, close, 14).dropna()
        if len(adx_s):
            adx_val = float(adx_s.iloc[-1])
            meta["adx"] = round(adx_val, 1)

    # Hurst (trend persistence modifier)
    hurst_val = None
    if n >= 50:
        hurst_val = _hurst(close.values[-50:])
        meta["hurst"] = round(hurst_val, 3)

    if not scores:
        return None

    # VWAP position (metadata only)
    if isinstance(high, pd.Series) and isinstance(volume, pd.Series) and volume.sum() > 0:
        tp   = (high + low + close) / 3
        vwap = (tp * volume).rolling(min(20, n)).sum() / (volume.rolling(min(20, n)).sum() + 1e-10)
        meta["above_vwap"] = bool(close.iloc[-1] > vwap.iloc[-1])

    # ── Aggregate ──────────────────────────────────────────────────
    net = sum(scores.values()) / len(scores)

    # ADX modifier
    if adx_val is not None:
        net *= 1.15 if adx_val > 25 else (0.85 if adx_val < 20 else 1.0)

    # Hurst modifier
    if hurst_val is not None:
        net *= 1.10 if hurst_val > 0.55 else (0.90 if hurst_val < 0.45 else 1.0)

    net = float(np.clip(net, -1.0, 1.0))
    signal = "bullish" if net > 0.10 else "bearish" if net < -0.10 else "neutral"
    conf   = min(95.0, abs(net) * 100)

    meta["net"]   = round(net, 3)
    meta["votes"] = len(scores)
    return {"signal": signal, "confidence": conf, "meta": meta}


# ─────────────────────────────────────── engine

class TechnicalEngine(BaseSignalEngine):
    """Multi-timeframe technical analysis: EMA, RSI, MACD, Bollinger, ADX, Hurst, OBV, VWAP, MFI."""

    name    = "technical"
    version = "1.0.0"
    weight  = 0.20

    def validate_data(self, data: DataBundle) -> bool:
        return bool(data.prices and len(data.prices) >= 60)

    def required_data_types(self) -> list[str]:
        return ["prices"]

    def compute(self, data: DataBundle) -> Signal:
        df = pd.DataFrame(data.prices).copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = df.get("close", 0)

        # Build three timeframe DataFrames
        daily   = df.iloc[-252:]                                    # last 252 trading days
        weekly  = df.resample("W").agg({"open": "first", "high": "max",
                                         "low": "min", "close": "last",
                                         "volume": "sum"}).dropna(subset=["close"])
        monthly = df.resample("ME").agg({"open": "first", "high": "max",
                                          "low": "min", "close": "last",
                                          "volume": "sum"}).dropna(subset=["close"])

        tf_results: list[dict] = []
        tf_weights = {"daily": 0.35, "weekly": 0.40, "monthly": 0.25}

        for name, frame, min_bars in [("daily", daily, 60),
                                       ("weekly", weekly, 15),
                                       ("monthly", monthly, 10)]:
            if len(frame) >= min_bars:
                res = _analyze(frame)
                if res:
                    res["name"]   = name
                    res["weight"] = tf_weights[name]
                    tf_results.append(res)

        if not tf_results:
            return Signal("neutral", 30.0, self.weight, "Insufficient data for technical analysis", {})

        # ── Confluence rule ────────────────────────────────────────
        signals = [r["signal"] for r in tf_results]
        bullish = signals.count("bullish")
        bearish = signals.count("bearish")

        # Weighted confidence
        total_w = sum(r["weight"] for r in tf_results)
        weighted_conf = sum(r["confidence"] * r["weight"] for r in tf_results) / total_w

        if len(tf_results) >= 2:
            if bullish == len(tf_results):   # all agree bullish
                direction = "bullish"
                weighted_conf = min(95.0, weighted_conf * 1.30)
            elif bearish == len(tf_results): # all agree bearish
                direction = "bearish"
                weighted_conf = min(95.0, weighted_conf * 1.30)
            elif bullish == 1 and bearish == 0 or (bullish == 0 and bearish == 1):
                direction = "neutral"
                weighted_conf = min(55.0, weighted_conf)
            elif bullish > bearish:
                direction = "bullish"
            elif bearish > bullish:
                direction = "bearish"
            else:
                direction = "neutral"
                weighted_conf = min(55.0, weighted_conf)
        else:
            direction = tf_results[0]["signal"]

        tf_meta = {r["name"]: r["meta"] for r in tf_results}
        tf_meta["timeframes_used"] = [r["name"] for r in tf_results]

        reasoning = (
            f"{direction.capitalize()} — {bullish}↑/{bearish}↓ across "
            f"{len(tf_results)} timeframe(s); conf={weighted_conf:.0f}%"
        )
        return Signal(direction, round(weighted_conf, 1), self.weight, reasoning, tf_meta)
