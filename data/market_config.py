from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MarketConfig:
    exchange:          str
    country:           str    # "US" | "IN"
    currency:          str    # "USD" | "INR"
    trading_days:      int    # 252 US / 250 India
    benchmark_ticker:  str
    vix_ticker:        str
    risk_free_rate:    float
    sector_etfs:       dict = field(default_factory=dict)
    pe_fair_value:     float = 18.0
    pb_fair_value:     float = 3.0

    # Loaded from us_thresholds.yaml / india_thresholds.yaml at runtime
    screen_thresholds: dict = field(default_factory=dict)


# Defaults — ConfigManager overwrites these at runtime from engine.yaml
US_CONFIG = MarketConfig(
    exchange="NYSE",
    country="US",
    currency="USD",
    trading_days=252,
    benchmark_ticker="^GSPC",
    vix_ticker="^VIX",
    risk_free_rate=0.053,
    sector_etfs={
        "tech": "XLK", "finance": "XLF", "energy": "XLE",
        "health": "XLV", "consumer": "XLY", "industrial": "XLI", "utility": "XLU",
    },
    pe_fair_value=18.0,
    pb_fair_value=3.0,
)

INDIA_CONFIG = MarketConfig(
    exchange="NSE",
    country="IN",
    currency="INR",
    trading_days=250,
    benchmark_ticker="^NSEI",
    vix_ticker="INDIAVIX.NS",
    risk_free_rate=0.065,
    sector_etfs={
        "tech": "NIFTYIT.NS", "bank": "NIFTYBANK.NS", "pharma": "NIFTYPHARMA.NS",
        "auto": "NIFTYAUTO.NS", "fmcg": "NIFTYFMCG.NS", "metal": "NIFTYMETAL.NS",
    },
    pe_fair_value=22.0,
    pb_fair_value=4.0,
)


def get_market_config(ticker: str) -> MarketConfig:
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return INDIA_CONFIG
    return US_CONFIG
