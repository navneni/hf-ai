# System Architecture — Write Engine & Plugin Protocol

> **Project:** HF-AI Engine | **Version:** 1.0 | **Date:** 2026-06-01
> **Database:** MongoDB `hf_ai_engine` (new, isolated DB — do not touch any existing DB)

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Write Engine — Core Runtime](#2-write-engine--core-runtime)
3. [Plugin Protocol — Signal Engine Contract](#3-plugin-protocol--signal-engine-contract)
4. [Standard Interfaces](#4-standard-interfaces)
5. [Data Bus](#5-data-bus)
6. [Monitoring Layer](#6-monitoring-layer)
7. [Backtest Framework](#7-backtest-framework)
8. [Configuration System](#8-configuration-system)
9. [MongoDB Integration](#9-mongodb-integration)
10. [Full System Diagram](#10-full-system-diagram)
11. [File Structure](#11-file-structure)

---

## 1. Design Philosophy

### 1.1 Core Principle

The **Write Engine** is the fixed, stable runtime. **Signal Engines** are interchangeable plugins. Any new analytical idea (a new investor screen, a new macro model, a new risk metric) can be added without modifying the Write Engine.

```
Write Engine  =  unchanging infrastructure
Signal Engine =  what you experiment with
```

This separation means:
- The data pipeline is written once and never duplicated
- Monitoring, persistence, and backtesting are built once and reused by all engines
- A new engine is a single Python file implementing one interface — nothing else changes

### 1.2 Three Hard Rules

1. **No engine reads from MongoDB directly.** Engines receive data via the DataBus and return a `Signal`. They never call a database.
2. **No engine knows about other engines.** Each engine operates in isolation. The Write Engine handles aggregation.
3. **The Write Engine never contains financial logic.** All signal computation lives in engines. The Write Engine only routes, stores, and orchestrates.

---

## 2. Write Engine — Core Runtime

### 2.1 Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WRITE ENGINE (Core)                          │
│                                                                     │
│  ┌──────────────────┐   ┌──────────────────┐   ┌────────────────┐  │
│  │  Engine Registry │   │   Config Manager  │   │  Audit Logger  │  │
│  │  - register()    │   │  - load_config()  │   │  - log_run()   │  │
│  │  - discover()    │   │  - get(key)       │   │  - log_event() │  │
│  │  - list_active() │   │  - hot_reload()   │   │  - log_error() │  │
│  └────────┬─────────┘   └────────┬──────────┘   └───────┬────────┘  │
│           │                      │                       │           │
│  ┌────────▼──────────────────────▼───────────────────────▼────────┐  │
│  │                        Orchestrator                             │  │
│  │  - run(tickers, date_range, engines)                           │  │
│  │  - run_backtest(config)                                        │  │
│  │  - run_scheduled(cron_expr)                                    │  │
│  └────────┬───────────────────────────────────────────────────────┘  │
│           │                                                           │
│  ┌────────▼─────────┐   ┌──────────────────┐   ┌────────────────┐   │
│  │    Data Bus       │   │  Monitor Layer   │   │  Result Store  │   │
│  │  - fetch(ticker)  │   │  - track_run()   │   │  - save_sig()  │   │
│  │  - cache_get()    │   │  - health_check()│   │  - save_dec()  │   │
│  │  - cache_set()    │   │  - emit_metric() │   │  - save_bt()   │   │
│  └────────┬──────────┘   └────────┬─────────┘   └───────┬────────┘   │
│           │                       │                      │            │
└───────────┼───────────────────────┼──────────────────────┼───────────┘
            │                       │                      │
            ▼                       ▼                      ▼
      [Data Sources]          [MongoDB: runs,        [MongoDB: signals,
      [yfinance,NSE,           monitoring_events,     decisions,
       FRED,screener.in]       audit_log]             backtest_results]
```

### 2.2 Orchestrator — Main Entry Point

```python
class WriteEngine:
    def __init__(self, config_path: str = "config/engine.yaml"):
        self.config   = ConfigManager(config_path)
        self.registry = EngineRegistry()
        self.data_bus = DataBus(self.config)
        self.monitor  = MonitorLayer(self.config)
        self.store    = ResultStore(self.config)
        self.db       = MongoDBClient(self.config.get("mongodb.uri"),
                                      db_name="hf_ai_engine")

    def run(self,
            tickers:    list[str],
            engines:    list[str] | None = None,
            as_of_date: str | None       = None,
            portfolio:  Portfolio | None = None) -> RunResult:

        run_id = self.monitor.start_run(tickers, engines, as_of_date)

        try:
            # Step 1: resolve engines
            active_engines = self.registry.resolve(engines or "all")

            # Step 2: fetch all data once (shared across all engines)
            data_bundles = {}
            for ticker in tickers:
                data_bundles[ticker] = self.data_bus.fetch(
                    ticker, as_of_date=as_of_date
                )
            self.monitor.checkpoint(run_id, "data_fetched")

            # Step 3: run each engine on each ticker
            all_signals: dict[str, dict[str, Signal]] = {}
            for ticker, data in data_bundles.items():
                all_signals[ticker] = {}
                for engine in active_engines:
                    if not engine.validate_data(data):
                        self.monitor.warn(run_id, f"{engine.name} skipped: insufficient data for {ticker}")
                        continue
                    signal = engine.compute(data)
                    all_signals[ticker][engine.name] = signal
                    self.store.save_signal(run_id, ticker, engine.name, signal)
            self.monitor.checkpoint(run_id, "signals_computed")

            # Step 4: risk + aggregation
            decisions = self._aggregate_and_decide(all_signals, data_bundles, portfolio)
            self.store.save_decisions(run_id, decisions)
            self.monitor.checkpoint(run_id, "decisions_made")

            result = RunResult(run_id=run_id, decisions=decisions, signals=all_signals)
            self.monitor.end_run(run_id, status="success")
            return result

        except Exception as e:
            self.monitor.end_run(run_id, status="error", error=str(e))
            raise

    def run_backtest(self, config: BacktestConfig) -> BacktestResult:
        """Delegate to BacktestFramework with the same engine stack."""
        bt = BacktestFramework(self, config)
        return bt.run()

    def register_engine(self, engine: SignalEngine) -> None:
        self.registry.register(engine)
```

### 2.3 Engine Registry

```python
class EngineRegistry:
    """
    Manages all registered signal engines.
    Engines auto-discover from signals/ directory.
    Can also be registered programmatically.
    """
    def __init__(self):
        self._engines: dict[str, SignalEngine] = {}

    def register(self, engine: SignalEngine) -> None:
        if engine.name in self._engines:
            raise ValueError(f"Engine '{engine.name}' already registered")
        self._engines[engine.name] = engine

    def discover(self, package_path: str = "signals") -> None:
        """Auto-discover engines in signals/ directory.
        Any class implementing SignalEngine protocol is auto-registered."""
        import importlib, pkgutil
        for finder, mod_name, _ in pkgutil.iter_modules([package_path]):
            module = importlib.import_module(f"{package_path}.{mod_name}")
            for attr in dir(module):
                obj = getattr(module, attr)
                if isinstance(obj, type) and issubclass(obj, BaseSignalEngine) and obj is not BaseSignalEngine:
                    self.register(obj())

    def resolve(self, names: list[str] | str) -> list[SignalEngine]:
        if names == "all":
            return list(self._engines.values())
        if isinstance(names, str):
            names = [names]
        return [self._engines[n] for n in names if n in self._engines]

    def list_active(self) -> list[dict]:
        return [{"name": e.name, "version": e.version, "weight": e.weight}
                for e in self._engines.values()]
```

---

## 3. Plugin Protocol — Signal Engine Contract

### 3.1 Base Class

Every signal engine MUST extend `BaseSignalEngine`. Nothing else required.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

@dataclass
class Signal:
    signal:     str    # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 – 100.0
    weight:     float  # contribution weight (set by engine, overridable by config)
    reasoning:  str    # one-line explanation
    metadata:   dict   # optional extra data (scores, sub-signals, etc.)

@dataclass
class DataBundle:
    ticker:          str
    market:          str            # "US" | "IN"
    as_of_date:      str            # YYYY-MM-DD
    prices:          list[dict]     # OHLCV
    financials:      list[dict]     # all periods
    ratios:          dict           # latest ratios
    news_items:      list[dict]     # scraped + sentiment-tagged
    insider_data:    list[dict]     # trades (US) or promoter (India)
    inst_flow:       dict           # 13F / FII-DII
    macro:           dict           # VIX, rates, sector ETFs
    filing_text:     str            # 10-K or annual report text
    market_config:   dict           # MarketConfig as dict

class BaseSignalEngine(ABC):
    """
    All signal engines extend this class.
    Implement compute() and that is the minimum requirement.
    All other methods have sensible defaults.
    """

    # --- Identity (MUST set as class attributes) ---
    name:    str   # unique snake_case identifier e.g. "buffett_screen"
    version: str   # semver e.g. "1.0.0"
    weight:  float # default signal weight in aggregation e.g. 0.20

    # --- Required: only this must be implemented ---
    @abstractmethod
    def compute(self, data: DataBundle) -> Signal:
        """Compute the signal. Pure function — no DB, no side effects."""
        ...

    # --- Optional overrides with defaults ---
    def validate_data(self, data: DataBundle) -> bool:
        """Return False if data is insufficient to compute. Engine is skipped, not errored."""
        return bool(data.prices and len(data.prices) >= 60)

    def initialize(self, config: dict) -> None:
        """Called once at startup. Override to load model weights, files, etc."""
        pass

    def get_metadata(self) -> dict:
        """Return engine metadata for registry and monitoring."""
        return {
            "name":        self.name,
            "version":     self.version,
            "weight":      self.weight,
            "description": self.__doc__ or "",
            "required_data": self.required_data_types(),
        }

    def required_data_types(self) -> list[str]:
        """Which DataBundle fields this engine uses. Used for optimization."""
        return ["prices"]   # default minimum; override to declare more
```

### 3.2 Minimal Engine Example

```python
# signals/my_custom_engine.py
from core.engine_base import BaseSignalEngine, Signal, DataBundle

class MyCustomEngine(BaseSignalEngine):
    """Signals based on price-to-book ratio only."""

    name    = "my_custom_engine"
    version = "1.0.0"
    weight  = 0.05

    def required_data_types(self):
        return ["prices", "ratios"]

    def validate_data(self, data: DataBundle) -> bool:
        return data.ratios.get("pb_ratio") is not None

    def compute(self, data: DataBundle) -> Signal:
        pb = data.ratios["pb_ratio"]
        threshold = data.market_config["pb_fair_value"]   # from MarketConfig
        if pb < threshold * 0.5:
            return Signal("bullish", 85.0, self.weight, f"P/B {pb:.2f} deeply below fair {threshold}", {})
        if pb > threshold * 1.5:
            return Signal("bearish", 75.0, self.weight, f"P/B {pb:.2f} significantly above fair {threshold}", {})
        return Signal("neutral", 50.0, self.weight, f"P/B {pb:.2f} near fair value {threshold}", {})
```

This is the ENTIRE implementation. One file, one class, one method. The Write Engine handles everything else.

### 3.3 Engine Weight Hierarchy

Weights can be set at three levels (higher wins):

```yaml
# config/engine.yaml
engines:
  buffett_screen:
    enabled: true
    weight: 0.02        # overrides engine default
  technical:
    enabled: true
    weight: 0.20
  my_custom_engine:
    enabled: false      # disabled without code change
```

---

## 4. Standard Interfaces

### 4.1 Data Interface Contract

```python
class DataBus:
    """
    Single data access point for all engines.
    Engines never call yfinance, MongoDB, or any API directly.
    DataBus handles: fetching, caching, validation, staleness checks.
    """

    def fetch(self, ticker: str, as_of_date: str | None = None) -> DataBundle:
        """
        Returns complete DataBundle for one ticker.
        Cache-first: checks MongoDB, falls back to live API.
        as_of_date enforces no-lookahead for backtesting.
        """
        market = get_market_config(ticker)

        # Layer 1: in-memory cache (same run)
        cache_key = f"{ticker}:{as_of_date}"
        if cached := self._mem_cache.get(cache_key):
            return cached

        # Layer 2: MongoDB (recent data within TTL)
        if stored := self._load_from_db(ticker, as_of_date):
            self._mem_cache[cache_key] = stored
            return stored

        # Layer 3: live fetch
        raw = self._fetcher.fetch_all(ticker, as_of_date, market)
        bundle = self._assemble_bundle(raw, ticker, market, as_of_date)

        # Persist to MongoDB for future runs
        self._save_to_db(bundle)
        self._mem_cache[cache_key] = bundle
        return bundle

    def prefetch(self, tickers: list[str], as_of_date: str) -> None:
        """Prefetch all tickers in parallel before engines run."""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda t: self.fetch(t, as_of_date), tickers))
```

### 4.2 Monitoring Interface Contract

```python
class MonitorLayer:
    """Standard monitoring for every run. No engine-specific code."""

    def start_run(self, tickers, engines, as_of_date) -> str:
        """Create run record, return run_id."""
        run_id = generate_run_id()
        self.db.runs.insert_one({
            "run_id":     run_id,
            "tickers":    tickers,
            "engines":    engines,
            "as_of_date": as_of_date,
            "started_at": now_utc(),
            "status":     "running",
            "checkpoints":[],
        })
        return run_id

    def checkpoint(self, run_id: str, stage: str) -> None:
        self.db.runs.update_one(
            {"run_id": run_id},
            {"$push": {"checkpoints": {"stage": stage, "at": now_utc()}}}
        )

    def end_run(self, run_id: str, status: str, error: str = None) -> None:
        self.db.runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": status, "ended_at": now_utc(), "error": error}}
        )

    def emit_metric(self, name: str, value: float, tags: dict = None) -> None:
        """Write metric to MongoDB monitoring_events collection."""
        self.db.monitoring_events.insert_one({
            "metric": name, "value": value,
            "tags": tags or {}, "at": now_utc()
        })

    def warn(self, run_id: str, message: str) -> None:
        self.db.audit_log.insert_one({
            "run_id": run_id, "level": "WARN",
            "message": message, "at": now_utc()
        })
```

### 4.3 Backtest Interface Contract

```python
class BacktestFramework:
    """
    Standard backtest runner. Uses the same Write Engine stack.
    Any engine that works in live mode works identically in backtest.
    No separate backtest code path needed.
    """

    def __init__(self, engine: WriteEngine, config: BacktestConfig):
        self.engine = engine
        self.config = config

    def run(self) -> BacktestResult:
        portfolio = Portfolio(cash=self.config.initial_cash)
        history   = []
        run_id    = self.engine.monitor.start_run(
            self.config.tickers, self.config.engines, "backtest"
        )

        for date in self._trading_calendar():
            # Identical to live run — only as_of_date changes
            result = self.engine.run(
                tickers    = self.config.tickers,
                engines    = self.config.engines,
                as_of_date = date,
                portfolio  = portfolio,
            )
            portfolio = self._execute_trades(result.decisions, portfolio, date)
            history.append({
                "date":  date,
                "value": self._mark_to_market(portfolio, date),
                "cash":  portfolio.cash,
            })

        metrics = self._compute_metrics(history)
        self.engine.store.save_backtest(run_id, history, metrics)
        return BacktestResult(run_id=run_id, history=history, metrics=metrics)

    def _trading_calendar(self) -> list[str]:
        """Returns trading days between start and end, respecting market."""
        market = get_market_config(self.config.tickers[0])
        return get_trading_days(
            self.config.start_date, self.config.end_date,
            market.country
        )
```

---

## 5. Data Bus

### 5.1 Data Flow

```
External Source                DataBus                  Engine
─────────────                  ───────                  ──────
yfinance         ──fetch──►    Assembler  ──DataBundle──► compute()
screener.in      ──fetch──►    Validator                     │
NSE portal       ──fetch──►    Cache                         │
FRED API         ──fetch──►    Persist                       ▼
MongoDB (cache)  ◄────────────────────────────────────   Signal
```

### 5.2 Cache Strategy

| Data Type | MongoDB TTL | Re-fetch Trigger |
|---|---|---|
| OHLCV prices | 6 hours | Market close + 1 hour |
| Financial statements | 90 days | New quarterly filing detected |
| Ratios (P/E, P/B, etc.) | 24 hours | Daily |
| News items | 1 hour | Continuous during market hours |
| Macro data (VIX, rates) | 1 hour | During market hours |
| FII/DII daily (India) | 24 hours | After 6 PM IST |
| Insider trades | 7 days | New Form 4 filing detected |
| Promoter holding (India) | 90 days | New SEBI disclosure |
| 10-K / filing text | 365 days | New annual filing detected |

### 5.3 Staleness Check

```python
def _is_stale(self, ticker: str, data_type: str, as_of_date: str) -> bool:
    """Check if cached data is too old to use."""
    record = self.db.data_cache.find_one(
        {"ticker": ticker, "data_type": data_type},
        sort=[("fetched_at", -1)]
    )
    if not record:
        return True
    ttl_seconds = DATA_TTL[data_type]
    age = (now_utc() - record["fetched_at"]).total_seconds()
    return age > ttl_seconds
```

---

## 6. Monitoring Layer

### 6.1 What Is Tracked Automatically

Every run automatically records:

| Event | When | MongoDB Collection |
|---|---|---|
| Run started | `start_run()` | `runs` |
| Data fetched | After DataBus.prefetch | `runs.checkpoints` |
| Per-engine signal | After each compute() | `signals` |
| Data fetch latency | Per ticker per source | `monitoring_events` |
| Engine compute time | Per engine per ticker | `monitoring_events` |
| Signal distribution | End of each run | `monitoring_events` |
| Run completed / errored | `end_run()` | `runs` |
| Data fetch failure | On exception | `audit_log` |
| Stale data warning | When cache TTL exceeded | `audit_log` |

### 6.2 Health Metrics

```python
class HealthMetrics:
    """Computable from MongoDB without any external monitoring tool."""

    def engine_accuracy(self, engine_name: str, lookback_days: int = 30) -> dict:
        """
        Computes: of signals that were bullish, what % of stocks were up next day?
        Uses stored signals + subsequent price data.
        """

    def data_freshness(self) -> dict:
        """Returns staleness % per data type per market."""

    def run_success_rate(self, lookback_days: int = 7) -> float:
        """% of runs that completed successfully in last N days."""

    def signal_distribution(self, engine_name: str) -> dict:
        """% bullish/bearish/neutral per engine over last 30 days."""

    def coverage_report(self) -> dict:
        """% of tickers with valid data per data type."""
```

---

## 7. Backtest Framework

### 7.1 BacktestConfig

```python
@dataclass
class BacktestConfig:
    tickers:           list[str]
    start_date:        str           # YYYY-MM-DD
    end_date:          str           # YYYY-MM-DD
    initial_cash:      float         # starting capital
    margin_requirement:float = 0.0   # 0 = no shorts
    engines:           list[str] | str = "all"
    rebalance_freq:    str = "daily" # "daily" | "weekly" | "monthly"
    slippage_bps:      float = 0.0   # basis points per trade
    commission:        float = 0.0   # flat commission per trade
    benchmark_ticker:  str = "^GSPC" # comparison benchmark
    save_to_db:        bool = True
```

### 7.2 Performance Metrics Computed

```python
@dataclass
class BacktestMetrics:
    total_return_pct:      float
    annualized_return_pct: float
    benchmark_return_pct:  float
    alpha_pct:             float    # vs benchmark
    max_drawdown_pct:      float
    sharpe_ratio:          float
    sortino_ratio:         float
    calmar_ratio:          float
    win_rate_pct:          float
    avg_win_pct:           float
    avg_loss_pct:          float
    profit_factor:         float    # gross wins / gross losses
    total_trades:          int
    avg_holding_days:      float
    best_trade_pct:        float
    worst_trade_pct:       float
    monthly_returns:       list[dict]  # [{month, return_pct}]
```

---

## 8. Configuration System

### 8.1 `config/engine.yaml` — Master Config

```yaml
# ─── MongoDB ─────────────────────────────────────────────────────────
mongodb:
  uri: "mongodb://localhost:27017"
  db_name: "hf_ai_engine"          # NEW isolated database
  pool_size: 10
  timeout_ms: 5000

# ─── Markets ─────────────────────────────────────────────────────────
markets:
  US:
    trading_days_per_year: 252
    benchmark: "^GSPC"
    vix_ticker: "^VIX"
    risk_free_rate_source: "FRED:FEDFUNDS"
    currency: "USD"
  IN:
    trading_days_per_year: 250
    benchmark: "^NSEI"
    vix_ticker: "INDIAVIX.NS"
    risk_free_rate_source: "RBI:REPO"
    currency: "INR"

# ─── Data Sources ────────────────────────────────────────────────────
data_sources:
  prices:      yfinance
  financials:  yfinance          # fallback: fmp
  ratios:      yfinance
  insider_us:  sec_edgar
  promoter_in: nse_portal
  fii_dii:     nse_portal
  bulk_deals:  nse_portal
  macro_us:    fred_api
  macro_in:    rbi_scraper
  news:        news_scraper      # Google News RSS + financial RSS feeds
  filing_text: sec_edgar         # US 10-K / India: bse_portal

# ─── News Scraper ────────────────────────────────────────────────────
news_scraper:
  google_news_rss: true
  yahoo_finance_news: true
  rss_feeds_us:
    - "https://feeds.finance.yahoo.com/rss/2.0/headline"
    - "https://www.wsj.com/xml/rss/3_7085.xml"
  rss_feeds_in:
    - "https://economictimes.indiatimes.com/markets/rss.cms"
    - "https://www.moneycontrol.com/rss/marketsindia.xml"
    - "https://www.business-standard.com/rss/markets-106.rss"
  max_articles_per_ticker: 50
  lookback_days: 90
  sentiment_engine: "vader_lm"   # "vader_lm" | "textblob" | "vader_only"

# ─── Engines ─────────────────────────────────────────────────────────
engines:
  technical:         { enabled: true,  weight: 0.20 }
  fundamental:       { enabled: true,  weight: 0.15 }
  valuation:         { enabled: true,  weight: 0.15 }
  earnings_quality:  { enabled: true,  weight: 0.10 }
  insider_sentiment: { enabled: true,  weight: 0.10 }
  news_sentiment:    { enabled: true,  weight: 0.10 }
  macro_context:     { enabled: true,  weight: null }  # null = multiplier, not vote
  institutional:     { enabled: true,  weight: 0.10 }
  buffett_screen:    { enabled: true,  weight: 0.016 }
  graham_screen:     { enabled: true,  weight: 0.016 }
  lynch_screen:      { enabled: true,  weight: 0.016 }
  fisher_screen:     { enabled: true,  weight: 0.016 }
  munger_screen:     { enabled: true,  weight: 0.016 }
  burry_screen:      { enabled: true,  weight: 0.016 }
  ackman_screen:     { enabled: true,  weight: 0.016 }
  wood_screen:       { enabled: true,  weight: 0.016 }
  druckenmiller:     { enabled: true,  weight: 0.016 }
  taleb_screen:      { enabled: true,  weight: 0.016 }
  damodaran_screen:  { enabled: true,  weight: 0.016 }
  pabrai_screen:     { enabled: true,  weight: 0.016 }
  jhunjhunwala:      { enabled: true,  weight: 0.016 }

# ─── Risk ────────────────────────────────────────────────────────────
risk:
  vol_lookback_days: 60
  vol_tiers:
    low:       { threshold: 0.15, max_alloc: 0.25 }
    medium_low:{ threshold: 0.22, max_alloc: 0.20 }
    medium:    { threshold: 0.30, max_alloc: 0.15 }
    high:      { threshold: 0.50, max_alloc: 0.125 }
    very_high: { threshold: 99.0, max_alloc: 0.10 }
  corr_high_threshold: 0.80
  corr_low_threshold:  0.30
  corr_high_multiplier:0.70
  corr_low_multiplier: 1.10
  min_confidence_to_trade: 40.0

# ─── Aggregator ──────────────────────────────────────────────────────
aggregator:
  buy_threshold:  0.15
  sell_threshold: 0.15
  macro_bearish_confidence_reduction: 0.80
  macro_bullish_confidence_boost:     1.10

# ─── Monitoring ──────────────────────────────────────────────────────
monitoring:
  log_level: INFO
  log_file: "logs/engine.log"
  metrics_enabled: true
  alert_on_run_failure: true
  alert_on_data_staleness: true

# ─── Ollama (Optional) ───────────────────────────────────────────────
ollama:
  enabled: false
  base_url: "http://localhost:11434"
  model: "llama3.2:3b"
```

### 8.2 Hot Reload

Config changes reload without restarting:

```python
class ConfigManager:
    def __init__(self, path: str):
        self._path = path
        self._data = self._load()
        self._watch_thread = threading.Thread(target=self._watch, daemon=True)
        self._watch_thread.start()

    def get(self, key: str, default=None):
        """Dot-notation access: config.get('mongodb.uri')"""
        parts = key.split(".")
        val = self._data
        for p in parts:
            val = val.get(p, {}) if isinstance(val, dict) else default
        return val if val != {} else default

    def _watch(self):
        """Reload config file if it changes on disk."""
        last_mtime = os.path.getmtime(self._path)
        while True:
            time.sleep(5)
            mtime = os.path.getmtime(self._path)
            if mtime != last_mtime:
                self._data = self._load()
                last_mtime = mtime
                logger.info("Config reloaded")
```

---

## 9. MongoDB Integration

### 9.1 Client Setup

```python
class MongoDBClient:
    """
    Wrapper around PyMongo.
    Database: hf_ai_engine (new isolated DB — never touches other DBs)
    """
    def __init__(self, uri: str, db_name: str = "hf_ai_engine"):
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db      = self._client[db_name]

        # Verify connection
        self._client.admin.command("ping")

        # Ensure all indexes exist on startup
        self._ensure_indexes()

    def _ensure_indexes(self):
        db = self.db
        db.prices_us.create_index([("ticker",1),("date",-1)])
        db.prices_in.create_index([("ticker",1),("date",-1)])
        db.financials.create_index([("ticker",1),("period",1),("date",-1)])
        db.signals.create_index([("run_id",1),("ticker",1),("engine",1)])
        db.decisions.create_index([("run_id",1),("ticker",1)])
        db.news_raw.create_index([("ticker",1),("published_at",-1)])
        db.news_sentiment.create_index([("ticker",1),("computed_at",-1)])
        db.runs.create_index([("run_id",1)], unique=True)
        db.runs.create_index([("started_at",-1)])
        db.backtest_results.create_index([("run_id",1),("date",1)])
        db.monitoring_events.create_index([("at",-1)])
        db.monitoring_events.create_index([("metric",1),("at",-1)])
        db.audit_log.create_index([("run_id",1),("at",-1)])
        db.fii_dii_daily.create_index([("date",-1)])
        db.bulk_deals.create_index([("ticker",1),("date",-1)])
        db.promoter_holdings.create_index([("ticker",1),("quarter",-1)])
        db.insider_trades.create_index([("ticker",1),("date",-1)])
        db.macro_us.create_index([("date",-1)])
        db.macro_in.create_index([("date",-1)])

    @property
    def prices_us(self):         return self.db["prices_us"]
    @property
    def prices_in(self):         return self.db["prices_in"]
    @property
    def financials(self):        return self.db["financials"]
    @property
    def ratios(self):            return self.db["ratios"]
    @property
    def signals(self):           return self.db["signals"]
    @property
    def decisions(self):         return self.db["decisions"]
    @property
    def runs(self):              return self.db["runs"]
    @property
    def backtest_results(self):  return self.db["backtest_results"]
    @property
    def news_raw(self):          return self.db["news_raw"]
    @property
    def news_sentiment(self):    return self.db["news_sentiment"]
    @property
    def macro_us(self):          return self.db["macro_us"]
    @property
    def macro_in(self):          return self.db["macro_in"]
    @property
    def fii_dii_daily(self):     return self.db["fii_dii_daily"]
    @property
    def bulk_deals(self):        return self.db["bulk_deals"]
    @property
    def promoter_holdings(self): return self.db["promoter_holdings"]
    @property
    def insider_trades(self):    return self.db["insider_trades"]
    @property
    def monitoring_events(self): return self.db["monitoring_events"]
    @property
    def audit_log(self):         return self.db["audit_log"]
    @property
    def engine_registry(self):   return self.db["engine_registry"]
    @property
    def configurations(self):    return self.db["configurations"]
    @property
    def data_cache_meta(self):   return self.db["data_cache_meta"]
```

---

## 10. Full System Diagram

```
CLI / API Call
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            WRITE ENGINE                                     │
│                                                                             │
│  ConfigManager ──── engine.yaml ──── hot reload                            │
│       │                                                                     │
│  EngineRegistry ─── auto-discover signals/*.py ─── manual register         │
│       │                                                                     │
│  Orchestrator.run(tickers, engines, as_of_date)                            │
│       │                                                                     │
│       ├── DataBus.prefetch(tickers)                                        │
│       │       ├── mem_cache check                                           │
│       │       ├── MongoDB cache check                                       │
│       │       └── Live fetch: yfinance / NSE / FRED / EDGAR / screener.in  │
│       │               └── NewsScraperModule.fetch(ticker)                  │
│       │                       ├── Google News RSS                           │
│       │                       ├── Yahoo Finance news                        │
│       │                       ├── Financial RSS feeds                       │
│       │                       └── PythonSentimentAnalyzer                  │
│       │                               ├── VADER                             │
│       │                               ├── LM Financial Dictionary           │
│       │                               └── Score aggregation                 │
│       │                                                                     │
│       ├── For each ticker × For each engine:                               │
│       │       engine.validate_data(bundle)                                  │
│       │       engine.compute(bundle) → Signal                               │
│       │       ResultStore.save_signal(run_id, ticker, engine, signal)      │
│       │                                                                     │
│       ├── RiskEngine.compute(all_signals, portfolio)                       │
│       ├── Aggregator.decide(signals, risk) → decisions                     │
│       ├── ResultStore.save_decisions(run_id, decisions)                    │
│       └── MonitorLayer.end_run(run_id)                                     │
│                                                                             │
└──────────────────────────────────┬──────────────────────────────────────── ┘
                                   │
                                   ▼
                        MongoDB: hf_ai_engine
                        ┌──────────────────────────────────────┐
                        │  prices_us     prices_in             │
                        │  financials    ratios                 │
                        │  news_raw      news_sentiment         │
                        │  macro_us      macro_in               │
                        │  fii_dii_daily bulk_deals             │
                        │  promoter_holdings insider_trades     │
                        │  signals       decisions              │
                        │  runs          backtest_results       │
                        │  monitoring_events  audit_log         │
                        │  engine_registry    configurations    │
                        └──────────────────────────────────────┘
```

---

## 11. File Structure

```
hf-ai/
│
├── core/                          # Write Engine — the stable runtime
│   ├── __init__.py
│   ├── engine_base.py             # BaseSignalEngine, Signal, DataBundle classes
│   ├── write_engine.py            # WriteEngine orchestrator
│   ├── engine_registry.py         # EngineRegistry
│   ├── data_bus.py                # DataBus — single data access point
│   ├── monitor.py                 # MonitorLayer
│   ├── result_store.py            # ResultStore — MongoDB writes
│   ├── aggregator.py              # Signal aggregation + decision logic
│   ├── risk_engine.py             # Risk engine (built into core, not a plugin)
│   └── backtest.py                # BacktestFramework
│
├── config/
│   ├── engine.yaml                # Master config (hot-reload enabled)
│   ├── us_thresholds.yaml         # US-specific screen thresholds
│   └── india_thresholds.yaml      # India-specific screen thresholds
│
├── data/
│   ├── __init__.py
│   ├── fetcher_us.py              # US data: yfinance, EDGAR, FINRA, CBOE, FRED
│   ├── fetcher_india.py           # India data: yfinance.NS, screener.in, NSE, RBI
│   ├── models.py                  # Pydantic models for all data types
│   └── market_config.py           # MarketConfig, US_CONFIG, INDIA_CONFIG
│
├── db/
│   ├── __init__.py
│   ├── client.py                  # MongoDBClient (hf_ai_engine DB only)
│   ├── schema.py                  # Collection schemas (for validation)
│   └── migrations/                # DB migration scripts
│       └── 001_initial_indexes.py
│
├── news/                          # News scraper module (standalone)
│   ├── __init__.py
│   ├── scraper.py                 # NewsScraperModule
│   ├── sources.py                 # Source implementations (Google, Yahoo, RSS)
│   └── sentiment.py              # PythonSentimentAnalyzer (VADER + LM dict)
│
├── signals/                       # All signal engines (pluggable)
│   ├── __init__.py
│   ├── technical.py
│   ├── fundamental.py
│   ├── valuation.py
│   ├── earnings_quality.py
│   ├── insider_sentiment.py
│   ├── news_sentiment.py          # Wraps news/ module as a signal engine
│   ├── macro_context.py
│   ├── institutional_flow.py
│   └── screens/                   # 13 investor screens
│       ├── __init__.py
│       ├── buffett.py
│       ├── graham.py
│       ├── lynch.py
│       ├── fisher.py
│       ├── munger.py
│       ├── burry.py
│       ├── ackman.py
│       ├── wood.py
│       ├── druckenmiller.py
│       ├── taleb.py
│       ├── damodaran.py
│       ├── pabrai.py
│       └── jhunjhunwala.py
│
├── engine.py                      # CLI entry point
├── pyproject.toml
├── .env.example
└── doc/
    ├── REQUIREMENTS.md
    ├── ARCHITECTURE.md            # This file
    ├── PHASES.md
    └── DB_SCHEMA.md
```

---

*Architecture v1.0 — 2026-06-01*
