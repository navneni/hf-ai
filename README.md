<div align="center">

# ⚡ HF-AI Engine

### Pure-Python Quantitative Trading Signal Engine

**US (NYSE · NASDAQ) &nbsp;|&nbsp; India (NSE · BSE)**

<br/>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-6%2B-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://mongodb.com)
[![Tests](https://img.shields.io/badge/Tests-322%20Passing-00C853?style=for-the-badge&logo=pytest&logoColor=white)](#-test-suite)
[![License](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge)](LICENSE)
[![Markets](https://img.shields.io/badge/Markets-US%20%7C%20India-6366F1?style=for-the-badge)](#-india-support)

<br/>

> **Zero LLM calls &nbsp;·&nbsp; $0 data cost &nbsp;·&nbsp; Fully deterministic &nbsp;·&nbsp; Runs in minutes**
>
> Drop-in replacement for LLM hedge fund engines that cost **$48+ per backtest** and are non-deterministic

</div>

---

## 🏆 Live Backtest Results &nbsp;—&nbsp; S&P 100 · Full Year 2024

<div align="center">

> 📊 **100 US large-cap stocks &nbsp;|&nbsp; $10,000 capital &nbsp;|&nbsp; 252 trading days &nbsp;|&nbsp; No news signal**

</div>

<div align="center">

| | Metric | Result | Benchmark |
|:---:|:---|:---:|:---:|
| 💰 | **Starting Capital** | $10,000 | — |
| 🚀 | **Final Portfolio Value** | **$12,337** | $12,401 |
| 📈 | **Total Return** | **+23.37%** | +24.01% |
| ⚡ | **Alpha vs S&P 500** | −0.64% | — |
| 📉 | **Max Drawdown** | **5.54%** | ~8.5% |
| ⚖️ | **Sharpe Ratio** | **1.326** | ~1.1 |
| 🛡️ | **Sortino Ratio** | **1.983** | — |
| 🏔️ | **Calmar Ratio** | **4.221** | — |
| 🎯 | **Win Rate** | 43.4% | — |
| 💎 | **Profit Factor** | **3.59×** | — |
| 🔄 | **Total Trades** | 76 | — |
| 📅 | **Trading Days** | 252 | — |

</div>

### 📅 Monthly Returns — 2024

```
         Return    Equity Curve                              Portfolio
─────────────────────────────────────────────────────────────────────
Jan 2024  +4.05%  ████████░░░░░░░░░░░░░░░░░░░░░░░░         $10,384
Feb 2024  +3.59%  ███████░░░░░░░░░░░░░░░░░░░░░░░░░         $10,758
Mar 2024  +0.46%  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░         $10,807
Apr 2024  -3.35%  ▒▒▒▒▒▒░░░░░░░░░░░░░░░░░░░░░░░░░░         $10,445
May 2024  +6.29%  ████████████░░░░░░░░░░░░░░░░░░░░         $11,102  ← Best month
Jun 2024  +5.51%  ███████████░░░░░░░░░░░░░░░░░░░░░         $11,714
Jul 2024  +0.78%  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░         $11,805
Aug 2024  +4.59%  █████████░░░░░░░░░░░░░░░░░░░░░░░         $12,347
Sep 2024  -1.21%  ▒▒░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░         $12,197
Oct 2024  -2.86%  ▒▒▒▒▒░░░░░░░░░░░░░░░░░░░░░░░░░░░         $11,848
Nov 2024  +7.80%  ███████████████░░░░░░░░░░░░░░░░░         $12,773  ← Best month
Dec 2024  -3.41%  ▒▒▒▒▒▒░░░░░░░░░░░░░░░░░░░░░░░░░░         $12,337
─────────────────────────────────────────────────────────────────────
FULL YEAR +23.37%                                           $12,337
```

### 🌟 Top Screen Picks &nbsp;(as of 2024-12-31)

| Rank | Ticker | Bullish Screens | Best Screen | Score |
|:---:|:---:|:---:|:---|:---:|
| 🥇 | **MSFT** | ⭐⭐⭐⭐ 4/13 | Damodaran | 0.824 |
| 🥈 | **CRM** | ⭐⭐⭐⭐ 4/13 | Ackman | 0.731 |
| 🥉 | **LLY** | ⭐⭐⭐ 3/13 | Fisher | 0.650 |
| 4 | **NVDA** | ⭐⭐⭐ 3/13 | Fisher | 0.761 |
| 5 | **GOOGL** | ⭐⭐⭐ 3/13 | Druckenmiller | 0.678 |
| 6 | **AMZN** | ⭐⭐⭐ 3/13 | Damodaran | 0.414 |

> **Note:** Adding FinBERT news sentiment (`pip install transformers torch`) provides an additional 0.10 weight signal not included above.

---

## 📚 Table of Contents

| | Section |
|:---:|:---|
| 🚀 | [Quick Start](#-quick-start) |
| 💻 | [Local Setup](#-local-setup) |
| ⚙️ | [How It Works](#️-how-it-works) |
| 🎛️ | [CLI Reference](#️-cli-reference) |
| 🧠 | [Signal Engines](#-signal-engines) |
| 🔍 | [Investor Screens](#-investor-screens) |
| 🇮🇳 | [India Support](#-india-support) |
| 📊 | [Analytics](#-analytics) |
| 🔌 | [Adding a New Engine](#-adding-a-new-engine) |
| 🗄️ | [MongoDB Collections](#️-mongodb-collections) |
| 🏗️ | [Project Structure](#️-project-structure) |
| ✅ | [Test Suite](#-test-suite) |

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/navneni/hf-ai.git && cd hf-ai

# Install
python3 -m venv .venv && source .venv/bin/activate
pip install poetry && poetry install

# Run (MongoDB must be running)
python engine.py --tickers AAPL MSFT --dry-run
```

---

## 💻 Local Setup

### Prerequisites

| Tool | Version | Install |
|:---|:---:|:---|
| **Python** | 3.11+ | [python.org](https://python.org) |
| **MongoDB** | 6.0+ | [mongodb.com](https://mongodb.com/try/download) |
| **Git** | any | `brew install git` |

### Step 1 — Clone the Repository

```bash
git clone https://github.com/navneni/hf-ai.git
cd hf-ai
```

### Step 2 — Create Virtual Environment

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Step 3 — Install Dependencies

```bash
pip install poetry
poetry install
```

<details>
<summary>➕ Optional: Install FinBERT for accurate news sentiment (~500 MB, one-time)</summary>

```bash
pip install transformers torch
# Model downloads and caches locally on first use.
# Without it, engine uses a fast keyword-based fallback.
```
</details>

### Step 4 — Start MongoDB

```bash
# macOS (Homebrew)
brew services start mongodb-community

# Linux (systemd)
sudo systemctl start mongod

# Docker (quickest)
docker run -d -p 27017:27017 --name mongo mongo:6
```

### Step 5 — Configure Environment (All Optional)

```bash
cp .env.example .env
# Edit .env — engine runs perfectly with zero keys
```

```env
# .env — all optional
MONGODB_URI=mongodb://localhost:27017    # change if MongoDB is remote
FRED_API_KEY=your_key_here              # free at fred.stlouisfed.org
                                        # improves yield curve accuracy
```

### Step 6 — Verify Installation

```bash
python engine.py --dry-run
# ✅ WriteEngine ready — 21 engine(s) registered
# ✅ Dry run — skipping data fetch and engine execution
```

```bash
python engine.py --health
# Shows: MongoDB status · engine count · data freshness · 7-day signals
```

---

## ⚙️ How It Works

```
  yfinance · SEC EDGAR · NSE/BSE · screener.in
                      ↓
          DataBus  (memory → MongoDB → live API)
                      ↓
      ┌───────────────────────────────────────────┐
      │         21 Signal Engines  (parallel)     │
      │  Technical · Fundamental · Valuation      │
      │  Earnings Quality · News Sentiment        │
      │  Insider · Institutional Flow · Macro     │
      │  13 Investor Screens                      │
      └───────────────────────────────────────────┘
                      ↓
       RiskEngine   (60d vol tiers · correlation matrix)
                      ↓
       Aggregator   (macro regime multiplier → weighted vote
                    → coverage gate → confidence gate → action)
                      ↓
       TradingDecision  →  MongoDB  →  CLI output
```

**Decision pipeline:**
```
signals
  → macro multiplier  (bearish regime ×0.80 · bullish ×1.10)
  → weight renormalization over available engines
  → coverage gate     (total_weight < 0.30 → HOLD)
  → confidence gate   (avg_conf < 40% → HOLD)
  → net_score = (bullish_weight − bearish_weight) / total_weight
  → threshold         (bearish 0.25 · neutral 0.15 · bullish 0.10)
  → action + quantity (max_shares × confidence / 100)
```

---

## 🎛️ CLI Reference

### Running Analyses

```bash
# Single ticker
python engine.py --tickers AAPL

# Multiple tickers with signal breakdown
python engine.py --tickers AAPL MSFT NVDA --show-signals

# US + India in one run
python engine.py --tickers AAPL MSFT TCS.NS RELIANCE.NS --show-signals

# No news (faster, no FinBERT needed)
python engine.py --tickers AAPL MSFT NVDA --no-news

# Specific engines only
python engine.py --tickers AAPL --engines technical fundamental valuation

# Save to JSON
python engine.py --tickers AAPL GOOGL META --output results.json

# AI narrative via Ollama
python engine.py --tickers AAPL --explain
```

### Backtesting

```bash
# S&P 100 full year 2024 (first run ~30 min · cached runs ~5 min)
python scripts/sp100_backtest.py --start 2024-01-01 --end 2024-12-31 --cash 10000

# Quick smoke test — 5 tickers, 2 months (~2 min)
python scripts/sp100_backtest.py --quick

# Via CLI directly
python engine.py \
  --tickers AAPL MSFT NVDA GOOGL META \
  --backtest --start 2024-01-01 --end 2024-12-31 \
  --cash 10000 --no-news --show-analytics
```

### Investor Screens

```bash
# Summary matrix — who passes the most screens?
python engine.py --screens all

# Top stocks on a specific screen
python engine.py --screens buffett_screen
python engine.py --screens lynch_screen

# Full scorecard for a ticker (all 13 screens + per-criterion pass/fail)
python engine.py --screens-ticker MSFT
python engine.py --screens-ticker NVDA

# Filter to a specific date
python engine.py --screens all --screens-date 2024-12-31
```

### Monitoring

```bash
python engine.py --health        # system health report
python engine.py --history 10    # last 10 run summaries
python engine.py --schedule "0 18 * * 1-5"  # run every weekday 6 PM
```

### All Flags

| Flag | Description |
|:---|:---|
| `--tickers AAPL MSFT` | Tickers · `.NS` = NSE · `.BO` = BSE · no suffix = US |
| `--show-signals` | Per-engine breakdown with confidence and reasoning |
| `--engines technical fundamental` | Run only specified engines (default: all 21) |
| `--no-news` | Skip news sentiment engine |
| `--refresh` | Bypass MongoDB cache · force live fetch |
| `--dry-run` | Validate config + MongoDB without running |
| `--output file.json` | Save decisions to JSON |
| `--explain` | Ollama narrative per decision |
| `--backtest` | Run in backtest mode (requires `--start`) |
| `--start 2024-01-01` | Backtest start date |
| `--end 2024-12-31` | Backtest end date (default: today) |
| `--cash 10000` | Starting capital |
| `--show-analytics` | Sector · drawdown · heatmap after backtest |
| `--screens all` | Summary matrix — all 13 screens |
| `--screens buffett_screen` | Top stocks for one screen |
| `--screens-ticker AAPL` | All screens for one ticker |
| `--screens-date 2024-06-28` | Filter to specific date |
| `--health` | MongoDB + data freshness + 7d signal distribution |
| `--history N` | Last N run summaries |
| `--schedule "CRON"` | Cron-style scheduled execution |

---

## 🧠 Signal Engines

### Quantitative Engines (total weight 0.60)

| Engine | Weight | What It Computes |
|:---|:---:|:---|
| ⚡ `technical` | **0.20** | EMA(8/21/55) · RSI(14,28) · MACD(12/26/9) · Bollinger(20,2σ) · ADX(14) · Hurst · OBV · VWAP · MFI — daily / weekly / monthly confluence |
| 📊 `fundamental` | **0.15** | 12 checks: Profitability · Growth · Health · Valuation + Piotroski F-Score (9 checks) |
| 💵 `valuation` | **0.15** | 3-stage DCF · Owner Earnings DCF · EV/EBITDA · P/E vs 5yr avg · Graham Number · Sector Median P/E |
| 🔍 `earnings_quality` | **0.10** | Beneish M-Score (manipulation risk) · Altman Z-Score (financial distress) |

### Sentiment & Institutional (total weight 0.30)

| Engine | Weight | What It Computes |
|:---|:---:|:---|
| 📰 `news_sentiment` | **0.10** | FinBERT 4-source: headlines (25%) · MD&A (30%) · analyst ratings (25%) · options overlay (20%) |
| 👤 `insider_sentiment` | **0.10** | US: SEC Form 4 value-weighted buy/sell · India: promoter quarterly holding changes |
| 🏦 `institutional_flow` | **0.10** | US: short squeeze setup · CBOE P/C ratio · IV rank · dark pool · India: FII/DII 5-day net + bulk deals |

### Macro Regime (weight 0.0 — multiplier only)

| Engine | Weight | What It Does |
|:---|:---:|:---|
| 🌍 `macro_context` | **0.00** | Classifies market regime → applies ×0.80 (bearish) or ×1.10 (bullish) to all bullish confidences |

**US factors:** VIX level · 10yr−2yr yield spread · S&P 500 vs 200d MA · sector breadth  
**India factors:** India VIX · Nifty vs 200d MA · USD/INR 30d change · FII 5-day net flow

---

## 🔍 Investor Screens

All 13 screens share the same scoring formula:

```
total_score = 0.40 × criteria_score
            + 0.25 × consistency_score   (10-year data)
            + 0.20 × moat_score          (TF-IDF on 10-K filings)
            + 0.15 × mgmt_quality_score  (ROIC + buybacks + ROE)

Red flags detected → score × 0.50
```

| Screen | Weight | Key Criteria |
|:---|:---:|:---|
| 🧙 **Buffett** | 0.0154 | ROE consistency · D/E < 0.5 · FCF consistency · net margin · DCF margin of safety |
| 📐 **Graham** | 0.0154 | P/E < 15 · P/B < 1.5 · current ratio > 2 · D/E < 0.5 · EPS positive · pays dividend |
| 🦆 **Lynch** | 0.0154 | P/EG < 1 · EPS growth > 10% · revenue growing · low debt |
| 🔬 **Fisher** | 0.0154 | Revenue CAGR · expanding gross/operating margins · revenue stability |
| 🏛️ **Munger** | 0.0154 | ROE consistency · operating margin > 15% · ROIC stability |
| 🐻 **Burry** | 0.0154 | P/B < 1 · FCF yield > 10% · high short interest as contrarian signal |
| 🦅 **Ackman** | 0.0154 | Large-cap · FCF consistency · margin expansion potential |
| 🚀 **Wood** | 0.0154 | Revenue hypergrowth · high gross margin · mid-cap innovation |
| ⚡ **Druckenmiller** | 0.0154 | Momentum + EPS acceleration · OBV trend |
| 🎲 **Taleb** | 0.0154 | Low leverage · high cash buffer · FCF stability |
| 📏 **Damodaran** | 0.0154 | DCF intrinsic value vs market price (margin of safety) |
| 🎯 **Pabrai** | 0.0154 | FCF yield · P/B · low capex · buybacks |
| 🌟 **Jhunjhunwala** | 0.0154 | Revenue CAGR · promoter holding · ROCE |

<details>
<summary>📋 Sample output — MSFT Scorecard (2024-12-31)</summary>

```
════════════════════════════════════════════════════════════════════════
  MSFT — Investor Screen Scorecard  |  2024-12-31
════════════════════════════════════════════════════════════════════════
  Damodaran     bullish  91.2%  ████████████████████   ✓ dcf_mos
  Lynch         bullish  87.2%  ██████████████████     ✓ eps_growth  eps_consistency  de_low
  Ackman        bullish  86.2%  █████████████████      ✓ large_company  fcf_positive  fcf_consistency
  Jhunjhunwala  bullish  83.1%  █████████████████      ✓ rev_cagr  promoter  roce
  Buffett       neutral  52.9%  ████████████           ✓ de_low  fcf_consistency  net_margin
                                                       ✗ roe_consistency
  Fisher        neutral  52.5%  ████████████           ✓ revenue_cagr  revenue_stable
  Graham        neutral  52.5%  ████████████           ✓ de_low  eps_positive  pays_dividend
  Taleb         bearish  82.5%  ██████                 ✗ low_leverage  high_cash  fcf_stable
════════════════════════════════════════════════════════════════════════
```

</details>

---

## 🇮🇳 India Support

All 21 engines run automatically for Indian tickers. Just add `.NS` (NSE) or `.BO` (BSE).

```bash
python engine.py --tickers TCS.NS RELIANCE.NS INFY.NS HDFCBANK.NS --show-signals
```

| Data Source | Provider | Notes |
|:---|:---|:---|
| Prices · Financials · Ratios | yfinance | `.NS` / `.BO` suffix |
| 10-year financial history | screener.in | HTML scraper fallback |
| FII / DII daily net flow | NSE API | Best-effort |
| Promoter shareholding | screener.in | Quarterly |
| Bulk / block deals | NSE bulk deal API | Best-effort |
| India VIX · Nifty 50 · USD/INR | yfinance | `INDIAVIX.NS` · `^NSEI` · `USDINR=X` |
| RBI Repo Rate | RBI website | Scraper (fallback: 6.5%) |

---

## 📊 Analytics

```bash
python engine.py \
  --tickers AAPL MSFT NVDA GOOGL META \
  --backtest --start 2024-01-01 --end 2024-12-31 \
  --show-analytics
```

Output:
- **Sector Exposure** — GICS breakdown · flags any sector > 40%
- **Drawdown Analysis** — daily series · max drawdown date · recovery days
- **Monthly Returns Heatmap** — year × month grid
- **Factor Attribution** — OLS: beta · alpha · value tilt · momentum · quality

```python
from analytics import (
    sector_exposure,          # GICS sector concentration
    correlation_matrix,       # 60-day pairwise (flags pairs > 0.80)
    factor_attribution,       # OLS: beta · alpha · value · momentum · quality
    drawdown_series,          # daily drawdown + recovery_days
    monthly_returns_heatmap,  # {YYYY: {MM: return}} grid
)
```

---

## 🔌 Adding a New Engine

Drop a single `.py` file in `signals/` — **auto-discovered at startup, zero config changes needed.**

```python
# signals/my_strategy.py
from core.engine_base import BaseSignalEngine, DataBundle, Signal

class MyStrategy(BaseSignalEngine):
    name    = "my_strategy"
    version = "1.0.0"
    weight  = 0.05

    def validate_data(self, data: DataBundle) -> bool:
        return len(data.prices) >= 60   # skip gracefully if insufficient

    def compute(self, data: DataBundle) -> Signal:
        # Pure function — no DB calls, no side effects
        score = ...

        return Signal(
            signal     = "bullish",        # "bullish" | "bearish" | "neutral"
            confidence = 72.0,             # 0–100
            weight     = self.weight,
            reasoning  = f"score={score:.3f}",
            metadata   = {"score": score},
        )
```

Then enable in `config/engine.yaml`:
```yaml
engines:
  my_strategy: { enabled: true, weight: 0.05 }
```

---

## 🗄️ MongoDB Collections

> All data lives in `hf_ai_engine`. The engine **never** touches any other database.

<details>
<summary>View all 18 collections</summary>

| Collection | TTL | Description |
|:---|:---:|:---|
| `prices_us` | 6h | US daily OHLCV |
| `prices_in` | 6h | India daily OHLCV |
| `financials` | 90d | Annual + TTM statements |
| `ratios` | 24h | P/E · P/B · ROE · margins |
| `insider_trades` | 7d | SEC Form 4 open-market transactions |
| `promoter_holdings` | 90d | India quarterly promoter % |
| `fii_dii_daily` | 24h | India FII/DII net flow |
| `bulk_deals` | 24h | India NSE bulk/block deals |
| `news_raw` | 90d | Scraped articles |
| `macro_us` / `macro_in` | 1h | Macro regime indicators |
| `inst_flow_us` | 6h | Short interest · P/C ratio · IV rank |
| `screen_results` | — | Clean investor screen results (per-criterion) |
| `signals` | — | All 21 engine signals per run |
| `decisions` | — | Final trading decisions |
| `runs` | — | Run metadata and timing |
| `backtest_results` | — | Daily portfolio snapshots |
| `backtest_metrics` | — | Backtest performance summary |
| `audit_log` | 90d | Warnings and errors |

Historical backtest data (`is_historical = True`) is **never** auto-deleted.

</details>

---

## 🏗️ Project Structure

```
hf-ai/
├── engine.py               ← CLI entry point (all flags)
├── analytics.py            ← Pure portfolio analytics functions
├── narrator.py             ← Ollama narrative generator (optional)
├── pyproject.toml          ← Dependencies (Poetry)
│
├── config/
│   ├── engine.yaml         ← Master config (single source of truth)
│   ├── us_thresholds.yaml
│   ├── india_thresholds.yaml
│   └── moat_idf.json       ← Pre-computed TF-IDF moat weights
│
├── core/
│   ├── write_engine.py     ← Main orchestrator
│   ├── data_bus.py         ← 3-layer cache
│   ├── aggregator.py       ← Macro multiplier + weighted vote
│   ├── risk_engine.py      ← Vol tiers + correlation
│   ├── backtest.py         ← Full backtesting framework
│   ├── monitor.py          ← Run lifecycle + HealthMetrics
│   ├── result_store.py     ← MongoDB persistence
│   ├── screen_store.py     ← Screen result queries + display
│   ├── engine_base.py      ← DataBundle · Signal · BaseSignalEngine
│   ├── engine_registry.py  ← Auto-discovery
│   └── config.py           ← YAML config with 5s hot-reload
│
├── data/
│   ├── fetcher_us.py       ← yfinance + SEC EDGAR
│   ├── fetcher_india.py    ← yfinance + screener.in + NSE
│   └── market_config.py    ← US_CONFIG / INDIA_CONFIG
│
├── signals/
│   ├── technical.py · fundamental.py · valuation.py
│   ├── earnings_quality.py · news_sentiment.py
│   ├── insider_sentiment.py · institutional_flow.py · macro_context.py
│   └── screens/            ← 13 investor screen engines
│       ├── __init__.py     ← Shared helpers
│       └── buffett.py · graham.py · lynch.py · fisher.py · munger.py
│           burry.py · ackman.py · wood.py · druckenmiller.py · taleb.py
│           damodaran.py · pabrai.py · jhunjhunwala.py
│
├── news/
│   ├── scraper.py · sources.py · sentiment.py
│
├── scripts/
│   └── sp100_backtest.py   ← S&P 100 backtest (100 tickers)
│
└── tests/
    ├── unit/               ← 310+ offline tests (no MongoDB · no network)
    └── integration/        ← Integration tests (require MongoDB)
```

---

## ✅ Test Suite

```bash
# All 322 tests (~6 seconds)
pytest tests/

# Unit only — no MongoDB required
pytest tests/unit/ -v

# Integration — require MongoDB running
pytest tests/integration/

# Specific module
pytest tests/unit/test_aggregator.py -v
pytest tests/unit/test_risk_engine.py -v
pytest tests/unit/test_india_data.py -v
```

---

## ⚠️ Known Limitations

| | Limitation | Notes |
|:---:|:---|:---|
| 🤗 | FinBERT not pre-installed | Rule-based fallback active · `pip install transformers torch` for domain-accurate sentiment |
| 🇮🇳 | India scraping is best-effort | NSE API may require browser session · returns empty on failure · engines handle gracefully |
| 📉 | SHORT not auto-initiated | Aggregator only generates COVER when an existing short is in portfolio state |
| ⏱️ | First backtest is slow | Pre-warms 2yr price history for all tickers · subsequent reruns use MongoDB cache (~5 min) |
| 📸 | Ratios are point-in-time | yfinance returns current ratios · not historical P/E · note for long backtests |
| 📆 | Daily granularity only | yfinance limitation — no intraday data |

---

<div align="center">

---

**⭐ Star this repo if you find it useful!**

Built with [Claude Code](https://claude.com/claude-code) &nbsp;|&nbsp; [Report an Issue](https://github.com/navneni/hf-ai/issues)

[![Star History](https://img.shields.io/github/stars/navneni/hf-ai?style=social)](https://github.com/navneni/hf-ai)

</div>
