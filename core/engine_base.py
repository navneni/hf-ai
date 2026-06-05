from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    signal: str        # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 – 100.0
    weight: float
    reasoning: str
    metadata: dict = field(default_factory=dict)


@dataclass
class DataBundle:
    ticker: str
    market: str        # "US" | "IN"
    as_of_date: str    # YYYY-MM-DD

    # Price and financial data
    prices: list[dict] = field(default_factory=list)
    financials: list[dict] = field(default_factory=list)
    ratios: dict = field(default_factory=dict)

    # Text data
    filing_text: str = ""   # 10-K (US) or annual report (India)
    mda_text: str = ""      # Latest 8-K MD&A (US) or quarterly filing (India)

    # News
    news_items: list[dict] = field(default_factory=list)

    # Institutional / insider — US fields are None for India tickers and vice versa
    insider_trades: Optional[list[dict]] = None       # US: SEC Form 4
    promoter_holdings: Optional[list[dict]] = None    # India: SEBI quarterly
    inst_flow_us: Optional[dict] = None               # 13F, FINRA SI, CBOE, dark pool
    inst_flow_india: Optional[dict] = None            # FII/DII daily, FII sector
    bulk_deals: Optional[list[dict]] = None           # India: NSE bulk/block deals

    # Analyst ratings (yfinance upgrades_downgrades → list of dicts)
    analyst_ratings: Optional[list[dict]] = None

    # Macro and config
    macro: dict = field(default_factory=dict)
    market_config: dict = field(default_factory=dict)


@dataclass
class TradingDecision:
    ticker: str
    action: str        # "buy" | "sell" | "hold" | "short" | "cover"
    quantity: int
    confidence: float
    price: float
    reasoning: str
    signals: dict = field(default_factory=dict)   # {engine_name: Signal}
    net_score: float = 0.0
    macro_regime: str = "neutral"
    narrative: Optional[str] = None


@dataclass
class RunResult:
    run_id: str
    decisions: dict = field(default_factory=dict)   # {ticker: TradingDecision}
    signals: dict = field(default_factory=dict)     # {ticker: {engine: Signal}}
    status: str = "success"
    error: Optional[str] = None


class BaseSignalEngine(ABC):
    """Base class for all signal engines. Implement compute() only."""

    name: str
    version: str = "1.0.0"
    weight: float

    @abstractmethod
    def compute(self, data: DataBundle) -> Signal:
        """Compute signal from DataBundle. Pure function — no DB, no side effects."""
        ...

    def validate_data(self, data: DataBundle) -> bool:
        """Return False to skip this engine gracefully. Skipped engines do not error."""
        return bool(data.prices and len(data.prices) >= 60)

    def initialize(self, config: dict) -> None:
        """Called once at startup before any compute() calls. Load models/files here."""
        pass

    def required_data_types(self) -> list[str]:
        """Declare which DataBundle fields this engine uses (for future optimization)."""
        return ["prices"]

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "weight": self.weight,
            "description": (self.__doc__ or "").strip(),
            "required_data": self.required_data_types(),
        }
