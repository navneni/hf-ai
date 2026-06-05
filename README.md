# HF-AI Engine

**Pure-Python quantitative trading signal engine for US (NYSE/NASDAQ) and India (NSE/BSE) equities.**

Zero LLM calls for core logic. $0 data cost. Deterministic. Runs in minutes.

Built as a drop-in replacement for LLM-based hedge fund engines that cost $48+ per backtest run.

---

## What it does

The engine fetches market data, runs 21 signal engines in parallel, applies a macro regime multiplier, aggregates signals via weighted vote, and produces **BUY / SELL / HOLD / SHORT / COVER** decisions with confidence scores and position sizes. Results persist to MongoDB for audit, replay, and backtesting.

```
yfinance + SEC EDGAR + NSE
        ↓
   DataBus (3-layer cache: memory → MongoDB → live API)
        ↓
   21 Signal Engines  (auto-discovered from signals/)
        ↓
   RiskEngine  (vol tiers + correlation matrix)
        ↓
   Aggregator  (macro regime → weighted vote → action)
        ↓
   TradingDecision  →  MongoDB  →  CLI output
```

---

## Engines (21 total, weight sum ≈ 1.10)

| Category | Engine | Weight | Description |
|---|---|---|---|
| Quantitative | `technical` | 0.20 | EMA/RSI/MACD/ADX/Hurst/OBV/VWAP/MFI — multi-timeframe confluence |
| Quantitative | `fundamental` | 0.15 | 12 checks (Piotroski F-Score + profitability/growth/health/valuation) |
| Quantitative | `valuation` | 0.15 | 6 DCF + relative models (Graham Number, EV/EBITDA, Sector PE) |
| Quantitative | `earnings_quality` | 0.10 | Beneish M-Score + Altman Z-Score (manipulation + distress flags) |
| Sentiment | `news_sentiment` | 0.10 | FinBERT 4-source composite (headlines + MD&A + analyst ratings + options overlay) |
| Institutional | `insider_sentiment` | 0.10 | US: SEC Form 4 value-weighted · India: promoter holding changes |
| Institutional | `institutional_flow` | 0.10 | US: short interest + P/C ratio + IV rank + dark pool · India: FII/DII + bulk deals |
| Macro | `macro_context` | 0.00 | Regime classifier — not a vote, applies multiplier to all bullish confidences |
| Screens (×13) | `buffett_screen` … `jhunjhunwala` | 0.0154 each | All 13 investor screens (see below) |

### 13 Investor Screens

Buffett · Graham · Lynch · Fisher · Munger · Burry · Ackman · Wood · Druckenmiller · Taleb · Damodaran · Pabrai · Jhunjhunwala

Each screen evaluates criteria consistency, moat evidence (TF-IDF on 10-K filings), management quality (ROIC stability + buybacks), and screen-specific financial checks. Results stored in dedicated `screen_results` collection.

---

## Decision pipeline

```
signals → macro multiplier (bearish ×0.80 / bullish ×1.10)
       → weight renormalization over available engines
       → coverage gate (total_weight < 0.30 → HOLD)
       → confidence gate (avg_conf < 40% → HOLD)
       → net_score = (bullish_weight − bearish_weight) / total_weight
       → regime-adjusted threshold (bearish 0.25 / neutral 0.15 / bullish 0.10)
       → action + quantity (max_shares × confidence/100)
```

---

## Requirements

- Python 3.11+
- MongoDB 6+ running on `localhost:27017` (or set `MONGODB_URI` in `.env`)
- Internet access (yfinance, SEC EDGAR, NSE)

```bash
# Install with Poetry
poetry install

# Or pip
pip install -r requirements.txt   # generated from pyproject.toml
```

**Optional — improves news sentiment accuracy (~500 MB one-time download):**
```bash
pip install transformers torch     # enables FinBERT (ProsusAI/finbert)
```

Without FinBERT, the engine uses a fast rule-based keyword fallback.

---

## Quick start

```bash
# Copy environment file (all keys are optional)
cp .env.example .env

# Single ticker analysis
python engine.py --tickers AAPL TCS.NS --show-signals

# Multi-ticker (US + India in one run)
python engine.py --tickers AAPL MSFT NVDA TCS.NS RELIANCE.NS
```

---

## CLI reference

```
python engine.py [options]
```

| Flag | Description |
|---|---|
| `--tickers AAPL MSFT …` | Tickers to analyse. `.NS` = NSE, `.BO` = BSE, no suffix = US |
| `--show-signals` | Per-engine signal breakdown for each ticker |
| `--engines technical fundamental` | Run only specified engines (default: all) |
| `--no-news` | Skip the news sentiment engine |
| `--refresh` | Bypass MongoDB cache, force live fetch |
| `--dry-run` | Validate config and MongoDB connection without running engines |
| `--output results.json` | Save decisions to JSON file |
| `--explain` | Generate Ollama narrative per decision (requires Ollama running) |
| **Backtest** | |
| `--backtest` | Run over `--start` / `--end` date range |
| `--start 2024-01-01` | Backtest start date |
| `--end 2024-12-31` | Backtest end date (default: today) |
| `--cash 10000` | Initial portfolio capital (default: 100,000) |
| `--show-analytics` | Print sector exposure, drawdown, monthly heatmap after backtest |
| **Screens** | |
| `--screens all` | Summary matrix: which stocks pass the most screens |
| `--screens buffett_screen` | Top stocks for a specific investor screen |
| `--screens-ticker AAPL` | All 13 screen scores for one ticker |
| `--screens-date 2024-06-28` | Filter screens to a specific date |
| **Monitoring** | |
| `--health` | System health: MongoDB status, data freshness, signal distribution |
| `--history 10` | Last N run summaries |
| `--schedule "0 18 * * 1-5"` | Run on a cron schedule (6 PM Mon–Fri) |

---

## Backtesting

```bash
# S&P 100, full year 2024, $10k capital, no news
python scripts/sp100_backtest.py --start 2024-01-01 --end 2024-12-31 --cash 10000

# Quick smoke test — 5 tickers, 2 months
python scripts/sp100_backtest.py --quick

# Custom date range
python scripts/sp100_backtest.py --start 2023-01-01 --end 2023-12-31 --cash 50000
```

**Performance metrics computed:**
Total Return · Annualized Return · Alpha vs Benchmark · Max Drawdown · Sharpe · Sortino · Calmar · Win Rate · Profit Factor · Total Trades

**Results stored in MongoDB:**
- `hf_ai_engine.backtest_results` — daily portfolio snapshots
- `hf_ai_engine.backtest_metrics` — summary metrics + monthly returns

**S&P 100 backtest results (2024, $10k, no news):**
```
Final Value:        $12,337   (+23.37%)
Alpha vs S&P 500:    −0.64%   (benchmark-matched)
Max Drawdown:         5.54%
Sharpe Ratio:         1.326
Sortino Ratio:        1.983
Calmar Ratio:         4.221
Win Rate:            43.4%
Profit Factor:        3.59
Total Trades:            76
```

---

## Investor Screen results

Screens store clean results in `hf_ai_engine.screen_results` — one document per (ticker, screen, date):

```bash
# Who passes the most screens today?
python engine.py --screens all

# Top stocks on Buffett screen
python engine.py --screens buffett_screen

# Full scorecard for MSFT (all 13 screens + per-criterion pass/fail)
python engine.py --screens-ticker MSFT
```

**Sample output — MSFT scorecard (2024-12-31):**
```
Damodaran    bullish  91.2%  ████████████████  ✓ dcf_mos
Lynch        bullish  87.2%  ██████████████    ✓ eps_growth eps_consistency de_low revenue_growing
Ackman       bullish  86.2%  ██████████████    ✓ large_company fcf_positive fcf_consistency
Buffett      neutral  52.9%  ████████████      ✓ de_low fcf_consistency net_margin dcf_mos  ✗ roe_consistency
```

---

## India support

All 21 engines run for Indian tickers. Suffix `.NS` (NSE) or `.BO` (BSE) is detected automatically.

**India-specific data sources:**
| Data | Source |
|---|---|
| Prices, financials, ratios | yfinance `.NS` / `.BO` |
| 10-year financial history | screener.in HTML scraper (fallback) |
| FII/DII daily net flow | NSE API (best-effort) |
| Promoter shareholding | screener.in (quarterly) |
| Bulk / block deals | NSE bulk deal API (best-effort) |
| India macro | INDIAVIX.NS · ^NSEI · USDINR=X · RBI repo rate |

**India macro regime factors:**
- India VIX (bearish > 20 · bullish < 13)
- Nifty 50 vs 200d MA
- USD/INR 30-day change (INR weakening = bearish)
- FII 5-day net flow

**InsiderSentimentEngine — India path:** uses promoter holding quarterly change instead of SEC Form 4 (increasing = bullish, decreasing = bearish, stable > 70% = bullish tilt).

```bash
python engine.py --tickers TCS.NS RELIANCE.NS INFY.NS --show-signals
```

---

## MongoDB collections

All data lives in `hf_ai_engine` database. The engine never touches any other database.

| Collection | TTL | Description |
|---|---|---|
| `prices_us` | 6h | Daily OHLCV for US tickers |
| `prices_in` | 6h | Daily OHLCV for India tickers |
| `financials` | 90d | Annual + TTM financial statements |
| `ratios` | 24h | P/E, P/B, ROE, margins, etc. |
| `insider_trades` | 7d | SEC Form 4 open-market transactions |
| `promoter_holdings` | 90d | India quarterly promoter % |
| `fii_dii_daily` | 24h | India FII/DII net flow |
| `bulk_deals` | 24h | India NSE bulk/block deals |
| `news_raw` | 90d | Raw scraped articles |
| `macro_us` / `macro_in` | 1h | Macro regime indicators |
| `inst_flow_us` | 6h | Short interest, P/C, IV, dark pool |
| `signals` | — | All engine signals per run |
| `screen_results` | — | Clean investor screen results |
| `decisions` | — | Final trading decisions |
| `runs` | — | Run metadata and stats |
| `backtest_results` | — | Daily backtest portfolio snapshots |
| `backtest_metrics` | — | Backtest performance metrics |

Historical backtest data (`is_historical=True`) is never auto-deleted.

---

## Configuration

**`config/engine.yaml`** — single source of truth for all settings.

Key sections:

```yaml
mongodb:
  uri: "mongodb://localhost:27017"

markets:
  US:
    risk_free_rate: 0.053
    benchmark: "^GSPC"
  IN:
    risk_free_rate: 0.065
    benchmark: "^NSEI"

engines:
  technical:        { enabled: true, weight: 0.20 }
  macro_context:    { enabled: true, weight: null }   # null = regime only, not a vote

risk:
  vol_lookback_days: 60
  min_confidence_to_trade: 40.0
  min_coverage_weight: 0.30
  vol_tiers:
    low:        { threshold: 0.15, max_alloc: 0.25 }
    medium_low: { threshold: 0.22, max_alloc: 0.20 }
    medium:     { threshold: 0.30, max_alloc: 0.15 }
    high:       { threshold: 0.50, max_alloc: 0.125 }
    very_high:  { threshold: 999,  max_alloc: 0.10  }

macro:
  vix_bearish_threshold: 30
  vix_bullish_threshold: 20
  regime_multiplier_bearish: 0.80
  regime_multiplier_bullish: 1.10

ollama:
  enabled: false
  model: "llama3.2:3b"
  timeout_seconds: 10
```

**`.env`** — optional API keys (engine runs with zero keys):

```bash
MONGODB_URI=mongodb://localhost:27017   # override default
FRED_API_KEY=your_key                  # improves 2yr yield for macro regime
```

---

## Analytics

Available after a backtest run:

```python
from analytics import (
    sector_exposure,         # GICS sector concentration; flags > 40%
    correlation_matrix,      # 60-day pairwise correlation; flags pairs > 0.80
    factor_attribution,      # OLS: beta, alpha, value tilt, momentum, quality
    drawdown_series,         # daily drawdown + max_drawdown + recovery_days
    monthly_returns_heatmap, # {YYYY: {MM: return}} grid + yearly compound
)
```

Display via CLI:
```bash
python engine.py --tickers AAPL MSFT --backtest --start 2024-01-01 --end 2024-12-31 --show-analytics
```

---

## Scheduled runs

```bash
# Run every weekday at 6 PM
python engine.py --tickers AAPL MSFT TCS.NS --schedule "0 18 * * 1-5"

# View last 7 run summaries
python engine.py --history 7

# System health check
python engine.py --health
```

---

## Adding a new signal engine

Drop a `.py` file in `signals/` — it is auto-discovered at startup with no other changes required.

```python
# signals/my_engine.py
from core.engine_base import BaseSignalEngine, DataBundle, Signal

class MyEngine(BaseSignalEngine):
    name    = "my_engine"
    version = "1.0.0"
    weight  = 0.05

    def validate_data(self, data: DataBundle) -> bool:
        return len(data.prices) >= 60

    def compute(self, data: DataBundle) -> Signal:
        # Pure function — no DB, no side effects
        score = ...
        return Signal(
            signal="bullish",     # "bullish" | "bearish" | "neutral"
            confidence=72.0,      # 0–100
            weight=self.weight,
            reasoning="My engine: ...",
            metadata={"score": score},
        )
```

Enable and set weight in `config/engine.yaml`:
```yaml
engines:
  my_engine: { enabled: true, weight: 0.05 }
```

---

## Project structure

```
hf-ai/
├── engine.py                # CLI entry point
├── analytics.py             # Pure portfolio analytics functions
├── narrator.py              # Ollama narrative generator (optional)
├── config/
│   ├── engine.yaml          # Master config
│   ├── us_thresholds.yaml   # US screen thresholds
│   ├── india_thresholds.yaml
│   └── moat_idf.json        # Pre-computed TF-IDF weights for moat scoring
├── core/
│   ├── write_engine.py      # Main orchestrator
│   ├── data_bus.py          # 3-layer cache
│   ├── aggregator.py        # Weighted vote + macro multiplier
│   ├── risk_engine.py       # Vol tiers + correlation
│   ├── backtest.py          # Backtesting framework
│   ├── monitor.py           # Run lifecycle + HealthMetrics
│   ├── result_store.py      # MongoDB persistence
│   ├── screen_store.py      # Screen result queries + display
│   ├── engine_base.py       # DataBundle, Signal, BaseSignalEngine
│   ├── engine_registry.py   # Auto-discovery
│   └── config.py            # YAML config with hot reload
├── data/
│   ├── fetcher_us.py        # yfinance + SEC EDGAR (US)
│   ├── fetcher_india.py     # yfinance + screener.in + NSE (India)
│   └── market_config.py     # US_CONFIG / INDIA_CONFIG
├── db/
│   └── client.py            # MongoDBClient (hf_ai_engine only)
├── signals/
│   ├── technical.py
│   ├── fundamental.py
│   ├── valuation.py
│   ├── earnings_quality.py
│   ├── news_sentiment.py
│   ├── insider_sentiment.py
│   ├── institutional_flow.py
│   ├── macro_context.py
│   └── screens/             # 13 investor screen engines
│       ├── __init__.py      # Shared helpers (consistency, moat, mgmt, master_score)
│       ├── buffett.py
│       ├── graham.py
│       └── … (13 total)
├── news/
│   ├── scraper.py           # Multi-source orchestrator
│   ├── sources.py           # Google News RSS, financial RSS, Yahoo Finance
│   └── sentiment.py         # FinBERT + 4-source composite
├── scripts/
│   └── sp100_backtest.py    # S&P 100 backtest script
└── tests/
    ├── unit/                # 310+ unit tests (no MongoDB, no network)
    └── integration/         # Integration tests (require MongoDB)
```

---

## Test suite

```bash
# All tests (322 total, ~6 seconds)
pytest tests/

# Unit tests only (no MongoDB required)
pytest tests/unit/

# Integration tests (require MongoDB running)
pytest tests/integration/ -m integration
```

---

## Known limitations

| Limitation | Notes |
|---|---|
| **FinBERT not pre-installed** | Rule-based fallback active. `pip install transformers torch` for domain-accurate sentiment |
| **India scraping is best-effort** | NSE API requires browser session; FII/DII and bulk deals return empty if NSE changes endpoints. Engines handle gracefully (return neutral) |
| **SHORT not auto-initiated** | Aggregator generates SHORT/COVER only when a prior short position exists in portfolio state |
| **Backtesting is slow on first run** | Pre-warms 2yr price history for all tickers. Subsequent reruns use MongoDB cache (~5 min) |
| **Macro fetch is per-date** | 252 dates × 11 yfinance calls = ~2,700 calls for a full-year backtest. Cached in MongoDB after first run |
| **Daily granularity only** | yfinance limitation — no intraday data |
| **Ratios are point-in-time snapshots** | yfinance returns current ratios, not historical P/E for backtesting. Use with caution for long historical backtests |

---

## License

MIT License — free for personal and commercial use.
