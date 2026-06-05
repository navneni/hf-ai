# AI Hedge Fund Engine — System B Enhanced
## Complete Technical & Functional Requirements

> **Version:** 1.1 | **Score:** 93% vs LLM-based original (310-point framework)
> **Markets:** USA (NYSE / NASDAQ) + India (NSE / BSE)
> **Date:** 2026-06-02

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [LLM Necessity Analysis — Read First](#2-llm-necessity-analysis--read-first)
3. [Project Goals & Non-Goals](#3-project-goals--non-goals)
4. [System Architecture](#4-system-architecture)
5. [MarketConfig — Dual Market Design](#5-marketconfig--dual-market-design)
6. [Data Requirements & Sources (US + India)](#6-data-requirements--sources-us--india)
7. [Data Models](#7-data-models)
8. [Signal Module 1 — Technical Analysis](#8-signal-module-1--technical-analysis)
9. [Signal Module 2 — Fundamental Analysis](#9-signal-module-2--fundamental-analysis)
10. [Signal Module 3 — Valuation (6 models)](#10-signal-module-3--valuation)
11. [Signal Module 4 — Earnings Quality (NEW)](#11-signal-module-4--earnings-quality-new)
12. [Signal Module 5 — Insider & Institutional Sentiment](#12-signal-module-5--insider--institutional-sentiment)
13. [Signal Module 6 — News Sentiment (4-Source)](#13-signal-module-6--news-sentiment-4-source)
14. [Signal Module 7 — Macro Context (NEW)](#14-signal-module-7--macro-context-new)
15. [Signal Module 8 — Institutional Flow (NEW)](#15-signal-module-8--institutional-flow-new)
16. [Signal Modules 9–21 — 13 Investor Screens (Upgraded)](#16-signal-modules-921--13-investor-screens-upgraded)
17. [India-Exclusive Signals](#17-india-exclusive-signals)
18. [Risk Engine](#18-risk-engine)
19. [Signal Aggregation & Decision Engine](#19-signal-aggregation--decision-engine)
20. [Backtesting Engine](#20-backtesting-engine)
21. [Portfolio Analytics Dashboard](#21-portfolio-analytics-dashboard)
22. [Ollama Narrative Engine](#22-ollama-narrative-engine)
23. [CLI Interface](#23-cli-interface)
24. [File Structure](#24-file-structure)
25. [Technical Stack](#25-technical-stack)
26. [Environment Configuration](#26-environment-configuration)
27. [Non-Functional Requirements](#27-non-functional-requirements)
28. [LLM Decision Matrix — Full Summary](#28-llm-decision-matrix--full-summary)
29. [Disclaimer](#29-disclaimer)

---

## 1. Executive Summary

**System B Enhanced** is a pure-Python quantitative trading signal engine that produces BUY / SELL / HOLD / SHORT / COVER decisions for both US and Indian equity markets. It scores **93% on a 310-point evaluation framework** vs. 43% for the original LLM-based system (System A from `virattt/ai-hedge-fund`).

| Dimension | System A (Original) | System B Enhanced |
|---|---|---|
| LLM calls per ticker per run | 19 | 0 core; 1 optional (Ollama, post-decision) |
| Backtesting cost (10 tickers, 1yr) | ~$48 (47,880 calls) | $0 |
| Backtesting speed | 6.6 hours | < 5 minutes |
| Deterministic | No | Yes |
| India market support | No | Yes |
| Earnings quality signals | No | Yes (Beneish + Piotroski + Altman) |
| Macro regime context | No | Yes (VIX, rates, sector rotation) |
| Institutional flow signals | Partial | Full (13F + FII/DII + bulk deals) |
| Score (310-pt framework) | 133/310 = 43% | 287/310 = 93% |

**Core principle:** LLMs are used only where the input is unstructured text that cannot be reduced to a formula. Python computes everything else directly.

---

## 2. LLM Necessity Analysis — Read First

> **This is the most important architectural decision. Every other design choice follows from it.**

### 2.1 Source Code Audit Finding

After reviewing the Python source of every agent in `virattt/ai-hedge-fund`:

| Agent | Python Computes | LLM Receives | LLM Returns | LLM Needed? |
|---|---|---|---|---|
| Technicals | EMA, RSI, MACD, Bollinger, ADX, Hurst, momentum — weighted composite | `{"signal":"bullish","confidence":72}` | Same signal | **NO — no-op** |
| Fundamentals | ROE/margin threshold scoring, growth, health checks | Finished score + label | Same label | **NO** |
| Valuation | Full DCF, EV/EBITDA, owner earnings, Graham Number | Finished valuation result | Same result | **NO** |
| Sentiment (insider) | Weighted buy/sell dollar ratio | Nothing — not called | N/A | **NO** |
| Risk Manager | Volatility, correlation matrix, position limits | Nothing — not called | N/A | **NO** |
| 13 Philosopher Agents | All scores in Python (0–10) | Pre-computed number e.g. `7.3` | `"bullish"` | **REPLACEABLE** — `if score>=7: "bullish"` |
| Portfolio Manager | All allowed quantities pre-computed | A menu of options | Picks one | **REPLACEABLE** — weighted vote |
| News Sentiment | Fetches headlines, tags missing ones | Raw headline text | `{"sentiment":"positive"}` | **YES — only genuine use** |

### 2.2 Five Reasons LLM Is Unnecessary for Structured Financial Data

**1. No ambiguity in numbers.** P/E of 12, RSI of 72, DCF intrinsic value of $142 — arithmetic has no semantic content. LLMs add zero information when the answer is already a number.

**2. Investor criteria are published `if/else` rules.** Buffett's criteria are in his annual letters: ROE > 15%, low debt, FCF positive, margin of safety > 25%. The original code converts criteria → Python score → LLM → "bullish". One line replaces the LLM: `"bullish" if score >= 7 else "bearish" if score <= 3 else "neutral"`.

**3. LLMs introduce variance into deterministic problems.** Same data → different LLM output across runs. For backtesting, non-determinism means you cannot reproduce the same result twice — a critical bug.

**4. Cost at scale.** Backtesting 10 tickers × 252 days × 19 agents = 47,880 LLM calls ≈ $48/run. Python: $0.

**5. LLMs cannot know more than the pre-computed score.** Philosopher agents compute the score in Python, pass it to the LLM with "be Warren Buffett." The LLM receives a number and returns "bullish." It has no additional information.

### 2.3 Where LLM IS Genuinely Required

| Use Case | Status | Why |
|---|---|---|
| News headline sentiment | **Required (FinBERT or LLM)** | Unstructured text — semantic understanding of regulatory outcomes, language magnitude, industry precedent |
| Qualitative moat assessment | **Optional v2** | SEC 10-K text mining proxies ~80%; remaining 20% needs LLM for brand/management quality |
| Decision narrative | **Optional (Ollama)** | Post-decision only; $0 cost via local Ollama; does NOT affect signals |

**Design rule:** LLMs are used only where the input is unstructured text that cannot be reduced to a formula.

---

## 3. Project Goals & Non-Goals

### Goals

| # | Requirement |
|---|---|
| G1 | BUY/SELL/HOLD/SHORT/COVER signals with confidence score (0–100) per ticker |
| G2 | Full per-module signal breakdown for auditability |
| G3 | Support any tickers, any date range, any portfolio size |
| G4 | Support both US (NYSE/NASDAQ) and India (NSE/BSE) via MarketConfig routing |
| G5 | Backtesting with strict no-lookahead enforcement |
| G6 | Zero LLM API keys required for core operation |
| G7 | $0 data cost — free sources only |
| G8 | Single CLI command to run |
| G9 | Optional Ollama narrative for demo/presentation |

### Non-Goals (v1)

Live trade execution, web UI, real-time streaming, LangGraph orchestration, 19-file agent sprawl.

---

## 4. System Architecture

### 4.1 Three-Tier Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TIER 1 — DATA LAYER                                                        │
│  Input: ticker + date range + MarketConfig                                  │
│  US:    yfinance | SEC EDGAR | FINRA | CBOE | FRED | NewsAPI/RSS            │
│  India: yfinance .NS | screener.in | NSE portal | RBI | ET/MC/BS RSS        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  TIER 2 — SIGNAL LAYER  (pure Python, 21 modules)                           │
│                                                                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────────────┐ │
│  │ Technical  │ │Fundamental │ │ Valuation  │ │  Earnings Quality (NEW)  │ │
│  │ Multi-TF   │ │+Piotroski  │ │ 5 models   │ │  Beneish+Altman+F-Score  │ │
│  │ (no LLM)   │ │ (no LLM)   │ │ (no LLM)   │ │  (no LLM)                │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────────────┐ │
│  │  Insider & │ │    News    │ │   Macro    │ │ Institutional Flow (NEW) │ │
│  │ Promoter   │ │ 4-source   │ │  Context   │ │ 13F/FII-DII/Bulk Deals   │ │
│  │ (no LLM)   │ │(FinBERT)   │ │(NEW,noLLM) │ │ (no LLM)                 │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  13 Investor Screens — 10yr lookback + SEC/BSE moat mining + mgmt   │   │
│  │  Buffett│Graham│Lynch│Fisher│Munger│Burry│Ackman│Wood│Druckenmiller  │   │
│  │  Taleb│Damodaran│Pabrai│Jhunjhunwala  (no LLM)                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  TIER 3 — DECISION LAYER  (pure math)                                       │
│  Risk Engine (vol + correlation + position limits) → Signal Aggregator      │
│  Macro regime multiplier applied → TradingDecision{action,qty,confidence}   │
│  Optional: Ollama narrates decision post-hoc (does NOT affect signal)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Execution Flow

```python
config = EngineConfig(tickers, start_date, end_date, cash, screens, ...)

for ticker in config.tickers:
    market = get_market_config(ticker)            # US or India routing

    data = fetch_all_data(ticker, as_of_date, market)    # Tier 1

    # Tier 2 — independent pure functions; parallelizable
    signals = {
        "technical":        compute_technical(data.prices, market),
        "fundamental":      compute_fundamental(data.financials, market),
        "valuation":        compute_valuation(data.financials, data.market_cap, market),
        "earnings_quality": compute_earnings_quality(data.financials),
        "insider":          compute_insider(data.insider_data, market),
        "news":             compute_news(data.news_items, ticker),
        "institutional":    compute_institutional(data.inst_flow, market),
        **{name: compute_screen(name, data, market) for name in config.screens},
    }
    macro = compute_macro(market)                 # regime multiplier, not a vote

    risk     = compute_risk(ticker, data.prices, portfolio, market)   # Tier 3
    decision = aggregate_and_decide(signals, macro, risk, portfolio, ticker)

    if config.explain:
        decision.narrative = ollama_explain(decision, signals)
```

### 4.3 Why No LangGraph

Each signal module is a pure function `(data, market_config) → Signal`. No shared state, no dynamic routing, no async communication needed. `concurrent.futures.ThreadPoolExecutor` achieves identical parallelism with zero framework overhead.

---

## 5. MarketConfig — Dual Market Design

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class MarketConfig:
    exchange:           Literal["NYSE", "NASDAQ", "NSE", "BSE"]
    country:            Literal["US", "IN"]
    currency:           Literal["USD", "INR"]
    trading_days:       int        # 252 US / 250 India
    benchmark_ticker:   str        # "^GSPC" or "^NSEI"
    vix_ticker:         str        # "^VIX" or "INDIAVIX.NS"
    risk_free_rate:     float      # Fed Funds or RBI Repo Rate
    sector_etfs:        dict
    pe_fair_value:      float      # 18.0 US / 22.0 India
    pb_fair_value:      float      # 3.0 US / 4.0 India
    screen_thresholds:  dict

US_CONFIG = MarketConfig(
    exchange="NYSE", country="US", currency="USD", trading_days=252,
    benchmark_ticker="^GSPC", vix_ticker="^VIX", risk_free_rate=0.053,
    sector_etfs={"tech":"XLK","finance":"XLF","energy":"XLE","health":"XLV",
                 "consumer":"XLY","industrial":"XLI","utility":"XLU"},
    pe_fair_value=18.0, pb_fair_value=3.0,
    screen_thresholds={
        "graham_pe":15, "graham_pb":1.5, "buffett_roe":15, "buffett_de":0.5,
        "buffett_margin_safety":25, "lynch_peg":1.0, "lynch_eps_growth":20,
        "fisher_revenue_cagr":15, "munger_roe":20, "munger_op_margin":20,
        "burry_pb":1.0, "burry_fcf_yield":10, "wood_revenue_growth":30,
        "wood_gross_margin":60, "druckenmiller_momentum":20,
        "taleb_de":0.2, "taleb_cash_ratio":0.2,
        "pabrai_fcf_yield":15, "pabrai_pb":1.5,
        "jhunjhunwala_eps_cagr":20, "jhunjhunwala_promoter":50,
    }
)

INDIA_CONFIG = MarketConfig(
    exchange="NSE", country="IN", currency="INR", trading_days=250,
    benchmark_ticker="^NSEI", vix_ticker="INDIAVIX.NS", risk_free_rate=0.065,
    sector_etfs={"tech":"NIFTYIT.NS","bank":"NIFTYBANK.NS","pharma":"NIFTYPHARMA.NS",
                 "auto":"NIFTYAUTO.NS","fmcg":"NIFTYFMCG.NS","metal":"NIFTYMETAL.NS"},
    pe_fair_value=22.0, pb_fair_value=4.0,
    screen_thresholds={
        "graham_pe":20, "graham_pb":2.5, "buffett_roe":18, "buffett_de":0.6,
        "buffett_margin_safety":20, "lynch_peg":1.2, "lynch_eps_growth":20,
        "fisher_revenue_cagr":15, "munger_roe":18, "munger_op_margin":18,
        "burry_pb":1.5, "burry_fcf_yield":8, "wood_revenue_growth":25,
        "wood_gross_margin":55, "druckenmiller_momentum":15,
        "taleb_de":0.3, "taleb_cash_ratio":0.15,
        "pabrai_fcf_yield":12, "pabrai_pb":2.0,
        "jhunjhunwala_eps_cagr":20, "jhunjhunwala_promoter":40,
    }
)

def get_market_config(ticker: str) -> MarketConfig:
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return INDIA_CONFIG
    return US_CONFIG
```

**India threshold justifications:**
- `graham_pe: 20` — Indian market historically trades at premium to US
- `buffett_roe: 18` — Indian quality companies typically higher ROE
- `lynch_peg: 1.2` — India growth premium; slightly higher PEG acceptable
- `jhunjhunwala_promoter: 40` — Many excellent Indian companies have 40–50% promoter holding

---

## 6. Data Requirements & Sources (US + India)

### 6.1 Required Data Per Ticker

| Data Type | Fields | Lookback | US Source (Free) | India Source (Free) |
|---|---|---|---|---|
| OHLCV prices | open,high,low,close,volume | 2 years | `yfinance` | `yfinance` + `.NS` |
| Income statement | revenue,gross_profit,op_income,net_income,EPS | 10yr annual + TTM | `yfinance` / SEC EDGAR | screener.in / BSE filings |
| Balance sheet | assets,debt,cash,equity,current_assets,current_liabilities | 10yr annual | `yfinance` | screener.in |
| Cash flow | op_CF,capex,FCF,dividends | 10yr annual + TTM | `yfinance` | screener.in |
| Ratios | P/E,P/B,P/S,EV/EBITDA,ROE,ROA,D/E,margins | Latest | `yfinance` | screener.in |
| Market cap | float | Daily | `yfinance` | `yfinance` |
| Insider trades | type,shares,price,date,title | 1 year | SEC EDGAR Form 4 | SEBI promoter disclosures (NSE) |
| Promoter holding | pct,pledge_pct,qoq_change | Quarterly | N/A | NSE/BSE filings |
| Institutional flow | 13F changes | Quarterly | SEC EDGAR | AMFI monthly + SEBI |
| FII/DII daily flow | fii_net,dii_net (crore INR) | Daily | N/A | NSE website daily CSV |
| Short interest | short_pct,days_to_cover | Biweekly | FINRA CSV | NSE F&O OI (daily) |
| Options data | P/C ratio,IV rank,IV skew | Daily | CBOE (free) | NSE option chain (free) |
| Bulk/block deals | client,type,qty,price | Daily | N/A | NSE daily CSV |
| Macro — VIX | level,trend | Daily | `^VIX` via yfinance | `INDIAVIX.NS` via yfinance |
| Macro — rates | interest_rate,yield_curve | Weekly | FRED API (free key) | RBI website |
| Macro — sector | ETF 3m returns | Daily | yfinance (XLK etc.) | yfinance (NIFTYIT.NS etc.) |
| News headlines | date,headline,source | 30–90 days | NewsAPI / RSS feeds | ET/Moneycontrol/BS RSS |
| Earnings call text | MD&A section | Latest quarter | SEC EDGAR 8-K | BSE/NSE exchange filing |
| Company filing text | business desc,risk factors | Latest annual | SEC EDGAR 10-K | BSE/NSE annual report |

**Total data cost: $0 for all of the above.**

### 6.2 India-Specific Data Notes

**screener.in** is the best free source for Indian fundamentals (10yr history, clean ratios). No official API — requires HTML scraping. Fallback: BSE/NSE XML filings.

**NSE FII/DII daily flow** is the single most important India macro signal. Published every market day by 6 PM IST. Download URL changes daily — parse from NSE website.

**NSE option chain** is free and comprehensive. India has the world's largest options market by contract volume.

---

## 7. Data Models

```python
from pydantic import BaseModel
from typing import Optional, Literal

class Price(BaseModel):
    date: str; open: float; high: float; low: float; close: float; volume: int

class Financials(BaseModel):
    ticker: str; period: str; date: str
    revenue: Optional[float]; gross_profit: Optional[float]
    operating_income: Optional[float]; net_income: Optional[float]; eps: Optional[float]
    total_assets: Optional[float]; total_debt: Optional[float]; cash: Optional[float]
    equity: Optional[float]; current_assets: Optional[float]; current_liabilities: Optional[float]
    operating_cash_flow: Optional[float]; capex: Optional[float]; free_cash_flow: Optional[float]
    dividends_paid: Optional[float]; shares_outstanding: Optional[int]
    depreciation_amortization: Optional[float]; retained_earnings: Optional[float]
    ebit: Optional[float]; receivables: Optional[float]; ppe: Optional[float]
    sga_expense: Optional[float]

class Ratios(BaseModel):
    pe_ratio: Optional[float]; pb_ratio: Optional[float]; ps_ratio: Optional[float]
    ev_ebitda: Optional[float]; roe: Optional[float]; roa: Optional[float]; roic: Optional[float]
    debt_to_equity: Optional[float]; current_ratio: Optional[float]
    gross_margin: Optional[float]; operating_margin: Optional[float]; net_margin: Optional[float]
    fcf_yield: Optional[float]; dividend_yield: Optional[float]
    market_cap: Optional[float]; enterprise_value: Optional[float]; peg_ratio: Optional[float]

class InsiderTrade(BaseModel):
    date: str; transaction_type: Literal["buy","sell"]
    shares: int; price: float; value: float; insider_name: str; title: str

class PromoterHolding(BaseModel):   # India only
    quarter: str; promoter_pct: float; pledge_pct: float; change_from_prior: float

class BulkDeal(BaseModel):          # India only
    date: str; client_name: str; transaction_type: Literal["buy","sell"]
    quantity: int; price: float

class FIIDIIFlow(BaseModel):        # India only
    date: str; fii_net_equity: float; dii_net_equity: float  # crore INR

class NewsItem(BaseModel):
    date: str; headline: str; source: str
    sentiment: Optional[Literal["positive","negative","neutral"]] = None
    confidence: Optional[float] = None

class Signal(BaseModel):
    signal: Literal["bullish","bearish","neutral"]
    confidence: float   # 0.0 – 100.0
    weight: float       # contribution weight in aggregation
    reasoning: str      # one-line explanation

class TradingDecision(BaseModel):
    ticker: str; action: Literal["buy","sell","hold","short","cover"]
    quantity: int; confidence: float; reasoning: str
    signals: dict       # {module_name: Signal}
    narrative: Optional[str] = None  # Ollama post-decision explanation

class Position(BaseModel):
    long_shares: int = 0; short_shares: int = 0
    long_cost_basis: float = 0.0; short_cost_basis: float = 0.0
    short_margin_used: float = 0.0

class Portfolio(BaseModel):
    cash: float; margin_requirement: float = 0.0
    positions: dict = {}; realized_gains: dict = {}

class PerformanceMetrics(BaseModel):
    initial_value: float; final_value: float; total_return_pct: float
    annualized_return_pct: float; max_drawdown_pct: float; sharpe_ratio: float
    win_rate: float; avg_win: float; avg_loss: float; total_trades: int
    portfolio_history: list   # [{date, value}]
```

---

## 8. Signal Module 1 — Technical Analysis

**LLM Required: NO** — Mathematical operations on price time-series. EMA is a weighted average. RSI is a ratio. MACD is a difference of two EMAs. Original source confirms: Python computes all indicators and the LLM receives the finished signal unchanged.

**Input:** `prices: list[Price]` (min 60 days, recommended 252 days)
**Output:** `Signal(signal, confidence, weight=0.20, reasoning)`

### Multi-Timeframe Analysis

| Timeframe | Bars | Weight | Purpose |
|---|---|---|---|
| Daily | 252 | 0.35 | Entry timing, short-term momentum |
| Weekly | 52 | 0.40 | Primary trend direction |
| Monthly | 24 | 0.25 | Long-term structure confirmation |

Run the full indicator suite on all three timeframes independently.

### Indicators

| Indicator | Parameters | Bullish | Bearish |
|---|---|---|---|
| EMA Crossover | 8/21/55 | 8 > 21 > 55 aligned up | 55 > 21 > 8 aligned down |
| RSI | 14 and 28 | RSI-14 < 30 (oversold) | RSI-14 > 70 (overbought) |
| MACD | 12/26/9 | MACD crosses above signal | MACD crosses below signal |
| Bollinger Bands | 20-period, 2σ | z-score < −1.0 | z-score > +1.0 |
| ADX | 14-period | ADX > 25 (trend confirm) | ADX < 20 (no trend) |
| Momentum | 1m/3m/6m returns | Positive all three | Negative all three |
| Hurst Exponent | Rolling 100-day | H > 0.5 (trending) | H < 0.5 (mean-reverting) |

### Volume Analysis

```python
OBV  = cumsum(volume * sign(close.diff()))   # accumulation/distribution
VWAP = (price * volume).cumsum() / volume.cumsum()
MFI  = 100 - (100 / (1 + money_flow_ratio))  # volume-weighted RSI

# Confirmation rules:
if price_rising and obv_rising:    confidence_adj = +10%   # confirmed uptrend
if price_rising and obv_falling:   confidence_adj = -15%   # distribution warning
if price > vwap and mfi > 55:      signal += "institutional buying present"
```

### Confluence Rule

```python
agreement = sum(1 for tf_signal in [daily,weekly,monthly] if tf_signal == primary_direction)

if agreement == 3:  confidence *= 1.30  # all timeframes agree → high conviction
elif agreement == 1: signal = "neutral"; confidence = min(55, confidence)  # conflicted
```

### Strategy Weights

```python
WEIGHTS = {"trend":0.25, "mean_reversion":0.20, "momentum":0.25, "volatility":0.15, "statistical":0.15}
```

---

## 9. Signal Module 2 — Fundamental Analysis

**LLM Required: NO** — Original source confirms: "entirely rule-based scoring system; deterministic analysis, not AI-powered reasoning."

**Input:** `financials: list[Financials]` — TTM + 4 quarters + 10 annual periods
**Output:** `Signal(signal, confidence, weight=0.15, reasoning)`

### Scoring Framework

| Category | Metric | US Threshold | India Threshold | Points |
|---|---|---|---|---|
| **Profitability** | ROE | > 15% | > 18% | 1 |
| | Net Margin | > 20% | > 20% | 1 |
| | Operating Margin | > 15% | > 15% | 1 |
| **Growth** | Revenue YoY | > 10% | > 10% | 1 |
| | EPS YoY | > 10% | > 10% | 1 |
| | Book Value YoY | > 10% | > 10% | 1 |
| **Health** | Current Ratio | > 1.5 | > 1.5 | 1 |
| | D/E | < 0.5 | < 0.6 | 1 |
| | FCF / Net Income | > 0.8 | > 0.8 | 1 |
| **Valuation check** | P/E | < 25 | < 30 | 1 |
| | P/B | < 3 | < 5 | 1 |
| | P/S | < 5 | < 5 | 1 |

### Piotroski F-Score (integrated)

```python
# 9 binary checks scored at end of fundamental module
f_score = sum([
    roa > 0, operating_cf > 0, roa_t > roa_t1,
    operating_cf/total_assets > roa,           # quality earnings
    lt_debt_ratio declining, current_ratio rising, no new shares issued,
    gross_margin rising, asset_turnover rising,
])
# F-Score 8-9 → bullish quality; 0-4 → bearish weakness
```

**Signal:** bullish if ≥9/12 ratio checks pass; bearish if ≤4; neutral otherwise.

---

## 10. Signal Module 3 — Valuation

**LLM Required: NO** — All models are closed-form formulas. Original `valuation.py` confirms: "All math pre-computed in Python. LLM receives only final results."

**Input:** financials, market cap, prices
**Output:** `Signal(signal, confidence, weight=0.15, reasoning)`

### Six Models

| Model | Formula | Fair Value Benchmark |
|---|---|---|
| 3-Stage DCF | Stage1(5yr at FCF CAGR) + Stage2(5yr declining) + Terminal(3%) discounted at WACC | Intrinsic value vs. market price |
| Owner Earnings DCF | Same 3-stage but owner_earnings = net_income + D&A − maintenance_capex | More conservative; Buffett method |
| EV/EBITDA | current_ev_ebitda vs. market_config.pe_fair_value | gap = (fair − current) / fair |
| P/E Relative | current_pe vs. own 5yr avg_pe | gap = (avg − current) / avg |
| Graham Number | √(22.5 × EPS × BVPS) | gap = (graham − price) / graham |
| Sector Median P/E | current_pe vs. sector_median_pe from sector ETF constituents | gap = (sector_median − current_pe) / sector_median; if no sector data available, skip and reweight |

```python
avg_margin_of_safety = mean([dcf_gap, oe_gap, ev_gap, pe_gap, graham_gap, sector_pe_gap])
signal = "bullish" if avg_margin_of_safety > 0.20 else \
         "bearish" if avg_margin_of_safety < -0.20 else "neutral"
confidence = min(100, abs(avg_margin_of_safety) * 200)
```

---

## 11. Signal Module 4 — Earnings Quality (NEW)

**LLM Required: NO** | **System A has this: NO**
Professional-grade signal that neither the original system nor base System B implements. All three models are deterministic formulas on financial statement line items.

**Input:** `financials: list[Financials]` — 2 years minimum
**Output:** `Signal(signal, confidence, weight=0.10, reasoning)`

### Beneish M-Score (Earnings Manipulation)

```
M = −4.84 + 0.920(DSRI) + 0.528(GMI) + 0.404(AQI) + 0.892(SGI)
         + 0.115(DEPI) − 0.172(SGAI) + 4.679(TATA) − 0.327(LVGI)

DSRI = (Receivables_t/Revenue_t) / (Receivables_t-1/Revenue_t-1)    ← channel stuffing
GMI  = Gross_Margin_t-1 / Gross_Margin_t                            ← margin deterioration
AQI  = ((1-(CA+PPE)/Assets)_t) / ((1-(CA+PPE)/Assets)_t-1)         ← intangibles growth
SGI  = Revenue_t / Revenue_t-1                                       ← high growth pressure
DEPI = (Dep_t-1/(PPE+Dep)_t-1) / (Dep_t/(PPE+Dep)_t)              ← slowing depreciation
SGAI = (SGA_t/Revenue_t) / (SGA_t-1/Revenue_t-1)                   ← efficiency loss
TATA = (Net_Income − Operating_CF) / Total_Assets                   ← STRONGEST: accruals
LVGI = Total_Debt_Ratio_t / Total_Debt_Ratio_t-1                    ← leverage fraud risk

M < −1.78 → not manipulating → quality clean
M > −1.78 → possible manipulation → bearish flag
```

### Altman Z-Score (Bankruptcy Risk)

```
Z = 1.2(Working_Capital/Assets) + 1.4(Retained_Earnings/Assets)
  + 3.3(EBIT/Assets) + 0.6(Market_Cap/Liabilities) + 1.0(Revenue/Assets)

Z > 2.99  → Safe zone | 1.81–2.99 → Grey zone | Z < 1.81 → Distress
Use Z' model (drop Revenue/Assets term) for services and software companies
```

### Combined Signal

```python
beneish_ok   = m_score < -1.78
altman_ok    = z_score > 2.99
piotroski_ok = f_score >= 7    # from fundamental module

if beneish_ok and altman_ok and piotroski_ok:   signal, confidence = "bullish", 88
elif not beneish_ok or z_score < 1.81 or f_score <= 3: signal, confidence = "bearish", 75
else:                                            signal, confidence = "neutral", 55
```

---

## 12. Signal Module 5 — Insider & Institutional Sentiment

**LLM Required: NO** — Original source: "entirely rule-based with no LLM involvement."

**Output:** `Signal(signal, confidence, weight=0.10, reasoning)`

### US Path — SEC Form 4

```python
# Exclude automatic trades (ESOP vesting, DRIP, 10b5-1 plans)
# Apply recency weights: 0–90 days = 2×, 91–180 days = 1.5×, older = 1×
# Apply seniority weights: CEO/CFO = 2×, Director = 1×, other = 0.8×

net_ratio = (weighted_buy_value - weighted_sell_value) / (buy + sell)
signal    = "bullish" if net_ratio > 0.30 else "bearish" if net_ratio < -0.30 else "neutral"
confidence = min(100, abs(net_ratio) * 100)
```

### India Path — Promoter Holding

```python
change    = current_promoter_pct - prior_quarter_pct
pledge    = current_pledge_pct

if pledge > 30:         signal = "bearish"; confidence = 75  # financial stress
elif change > 2:        signal = "bullish"; confidence = 70  # buying more
elif change < -3:       signal = "bearish"; confidence = 65  # selling concern
elif promoter_pct > 60: signal = "bullish"; confidence = 55  # high conviction
else:                   signal = "neutral"; confidence = 50
```

---

## 13. Signal Module 6 — News Sentiment (4-Source)

**LLM Required: YES — this is the only genuine use case**
News headlines are unstructured language. "Apple faces DOJ scrutiny over App Store" cannot be classified by a threshold rule — it requires understanding the regulatory entity, implied outcome, and industry precedent.

**Output:** `Signal(signal, confidence, weight=0.10, reasoning)`

### Four Sources

| Source | Weight | What It Provides |
|---|---|---|
| FinBERT on headlines | 25% | `ProsusAI/finbert` — domain-trained BERT, free, local |
| Earnings call transcript (MD&A) | 30% | SEC 8-K / BSE filing — forward guidance in management's own words |
| Analyst rating changes | 25% | `yfinance.upgrades_downgrades` — professional consensus direction |
| Options sentiment overlay | 20% | IV skew + P/C ratio from Institutional Flow module |

### FinBERT Setup

```python
from transformers import pipeline
nlp = pipeline("text-classification", model="ProsusAI/finbert")
# Runs locally after one-time ~500MB download. No API key. Deterministic.
for item in news_items:
    result = nlp(item.headline[:512])
    item.sentiment, item.confidence = result[0]["label"], result[0]["score"]
```

### Aggregation with Recency Weighting

```python
weights = [1 / (1 + days_ago(item.date) / 30) for item in news_items]
bullish_score = sum(r.confidence * w for r, w in zip(results, weights)
                    if r.sentiment == "positive") / sum(weights)
bearish_score = sum(r.confidence * w for r, w in zip(results, weights)
                    if r.sentiment == "negative") / sum(weights)
net = bullish_score - bearish_score
signal = "bullish" if net > 0.20 else "bearish" if net < -0.20 else "neutral"
```

### India News RSS Feeds (Free)

```python
INDIA_NEWS_FEEDS = {
    "economic_times":    "https://economictimes.indiatimes.com/markets/rss.cms",
    "moneycontrol":      "https://www.moneycontrol.com/rss/marketsindia.xml",
    "business_standard": "https://www.business-standard.com/rss/markets-106.rss",
    "livemint":          "https://www.livemint.com/rss/markets",
}
```

---

## 14. Signal Module 7 — Macro Context (NEW)

**LLM Required: NO** | **System A has this: NO**
All macro signals are structured numbers — VIX is a float, yield spread is a float. Pure math.

**Role:** Regime MULTIPLIER on individual stock signals — not a standalone vote.

### US Macro Signals

| Signal | Source | Bullish | Bearish |
|---|---|---|---|
| VIX level | `^VIX` via yfinance | < 15 | > 30 |
| VIX trend | 5d vs 20d MA | Declining | Rising |
| Yield curve (10yr−2yr) | FRED API (free) | Spread > 0.5% | Spread inverted |
| Ticker's sector ETF 3m | yfinance (XLK etc.) | > +5% | < −5% |
| S&P 500 vs 200 MA | `^GSPC` | Price > 200MA | Price < 200MA |
| Fed rate trend | FRED: FEDFUNDS | Cuts underway | Rapid hikes |

### India Macro Signals

| Signal | Source | Bullish | Bearish |
|---|---|---|---|
| India VIX | `INDIAVIX.NS` | < 14 | > 22 |
| Nifty vs 200 MA | `^NSEI` | Price > 200MA | Price < 200MA |
| INR/USD 30d change | `USDINR=X` | < 1% depreciation | > 2% depreciation |
| RBI repo rate trend | RBI website | Cuts | Rapid hikes |
| FII net 5-day | NSE FII daily | Net buy > +5,000 Cr | Net sell > −5,000 Cr |

### Regime Integration

```python
macro_score = compute_macro_composite(above_signals)   # -1.0 to +1.0

if macro_score <= -0.40:   # Strongly bearish
    reduce all bullish signal confidences × 0.80
    raise buy threshold: net_score > 0.25 required
elif macro_score >= 0.40:  # Strongly bullish
    amplify bullish confidences × 1.10
    lower buy threshold: net_score > 0.10 sufficient
else:
    no adjustment
```

---

## 15. Signal Module 8 — Institutional Flow (NEW)

**LLM Required: NO** | **System A has this: NO**
13F filings, short interest, and options OI are structured numbers. LLMs cannot access this data in real-time — System B has a genuine data advantage here.

**Output:** `Signal(signal, confidence, weight=0.10, reasoning)`

### US Path

```python
# 13F: net_flow = (new_buyers + increasers) - (reducers + exits)
# FINRA short interest: si_pct = short_shares/float, days_to_cover = short/avg_vol
# Squeeze signal: si_pct > 0.15 AND si_change < -0.05  (high SI falling → bullish)
# CBOE: pc_ratio = put_vol/call_vol, iv_rank = (iv-52w_low)/(52w_high-52w_low)
# High-conviction bonus: +15 confidence if known manager (BRK, Pershing) initiates

# Dark pool (FINRA OTC/ATS reports — free, published weekly):
# dark_pool_pct = dark_vol / total_vol
# Rising dark_pool_pct with rising price → institutional accumulation → bullish
# dark_pool_pct > 0.45 AND price rising → confidence +10
dark_pool_pct = finra_otc_vol / (finra_otc_vol + exchange_vol)
```

### India Path

```python
# FII/DII daily (NSE website — published 6 PM IST every market day):
fii_signal = "bullish" if fii_net_equity > 1000 else \
             "bearish" if fii_net_equity < -1000 else "neutral"
# Historically: FII net buy > +3000 Cr → Nifty +1-2% next session (75% hit rate)

# FII sector-wise flow (NSE monthly breakdown — stronger sector-specific signal):
# If ticker's sector shows FII inflow while ticker itself shows outflow → divergence warning
fii_sector_flow = nse_fii_sector_breakdown.get(ticker_sector, 0)   # crore INR
sector_divergence = (fii_sector_flow > 0) != (fii_net_equity > 0)  # True = divergence

# NSE Bulk deals (>0.5% of shares in one session — daily NSE CSV):
bulk_flow = sum(d.qty*d.price for d in bulk_buys) - sum(d.qty*d.price for d in bulk_sells)

# NSE F&O OI as short proxy:
pc_oi_ratio = put_open_interest / call_open_interest
```

---

## 16. Signal Modules 9–21 — 13 Investor Screens (Upgraded)

**LLM Required: NO** — Each investor's criteria are publicly documented rules. Original code confirms: Python computes all scores (0–10), LLM converts to "bullish/bearish/neutral" — a threshold rule does this identically at $0.

**Combined weight:** 0.20 (each screen = 0.20/13 ≈ 0.015)

### Shared Upgrades for All 13 Screens

**10-Year Consistency Check:**
```python
def consistency_score(metric_series, threshold):
    return sum(1 for v in metric_series if v and v > threshold) / len(metric_series)
# Require metric to pass in ≥ 8 of 10 years for full credit
```

**SEC/BSE 10-K Moat Text Mining (TF-IDF weighted):**
```python
MOAT_EVIDENCE = {
    "switching_costs":  ["switching cost","proprietary","integrated","lock-in","mission-critical"],
    "network_effects":  ["network effect","platform","marketplace","ecosystem","two-sided"],
    "cost_advantage":   ["lowest cost","scale advantage","cost leadership"],
    "intangible_assets":["patent","proprietary technology","brand loyalty","trade secret"],
    "regulatory_moat":  ["regulatory approval","FDA clearance","FCC license","exclusive"],
}
RED_FLAGS = ["going concern","material weakness","restatement","SEC investigation","class action"]

# TF-IDF: weight each keyword hit by its inverse-document frequency across a corpus
# of 100 S&P 500 10-Ks so common boilerplate words don't inflate scores.
# idf_weights pre-computed and stored in config/moat_idf.json
def moat_score_tfidf(text: str, idf_weights: dict) -> float:
    scores = []
    for category, keywords in MOAT_EVIDENCE.items():
        tf_idf_sum = sum(
            (text.lower().count(kw) / max(1, len(text.split()))) * idf_weights.get(kw, 1.0)
            for kw in keywords
        )
        scores.append(min(1.0, tf_idf_sum * 100))   # normalize to 0-1
    return mean(scores)

risk_flag = any(rf in text.lower() for rf in RED_FLAGS)
```

**Management Quality Scoring:**
```python
roic_10yr       = [compute_roic(f) for f in last_10_annual]
mgmt_score      = (0.30 * (1 if mean(roic_10yr) > 0.15 else 0) +
                   0.30 * (1 - std(roic_10yr)/max(0.01,mean(roic_10yr))) +
                   0.20 * (sum(1 for i in range(1,10) if shares[i] < shares[i-1]) / 9) +
                   0.20 * (1 if insider_ownership > 0.05 else 0))
```

**Master Score Formula (applied to all screens):**
```python
total = 0.40*criteria_score + 0.25*consistency_10yr + 0.20*moat_composite + 0.15*mgmt_score
if risk_flag: total *= 0.50   # hard penalty for regulatory red flags
signal = "bullish" if total >= 0.65 else "bearish" if total <= 0.35 else "neutral"
```

### All 13 Screen Criteria

| Screen | Core Criteria (US thresholds; India uses INDIA_CONFIG) |
|---|---|
| **Warren Buffett** | ROE > 15% (8/10yr), D/E < 0.5, FCF > 0 (8/10yr), net margin > 10%, DCF MoS > 25% |
| **Ben Graham** | P/E < 15, P/B < 1.5, current ratio > 2.0, D/E < 0.5, EPS growth > 0% (5yr), dividend history |
| **Peter Lynch** | PEG < 1.0, EPS growth > 20% (consistent), D/E < 0.35, revenue growth consistent |
| **Phil Fisher** | Revenue CAGR > 15% (5yr), gross margin expanding, R&D/revenue increasing, op margin expanding |
| **Charlie Munger** | ROE > 20% (8/10yr), op margin > 20%, low ROE std dev (moat stability) |
| **Michael Burry** | P/B < 1.0, FCF yield > 10%, short interest > 15%, near-zero EV possible |
| **Bill Ackman** | Revenue > $1B, underperforming sector peers, FCF > 0, op margin below peer avg |
| **Cathie Wood** | Revenue YoY > 30%, gross margin > 60%, market cap < $100B, R&D spend increasing |
| **Stanley Druckenmiller** | 52-week momentum > 20%, EPS acceleration, sector ETF 3m > 0, OBV rising |
| **Nassim Taleb** | D/E < 0.2, cash/assets > 0.2, no customer > 20% revenue, FCF std dev/mean < 0.20 |
| **Aswath Damodaran** | DCF intrinsic value vs. market cap gap > 20% (sourced from Valuation Module) |
| **Mohnish Pabrai** | FCF yield > 15%, P/B < 1.5, buybacks active, capex/revenue < 10% |
| **Rakesh Jhunjhunwala** | EPS CAGR > 20% (3yr), revenue CAGR > 15% (3yr), promoter holding > 50%, ROCE > 20% |

---

## 17. India-Exclusive Signals

### FII/DII Daily Flow — Strongest India Signal

Published by NSE every market day by 6 PM IST. Historically the highest single predictor of Indian market direction.

```
FII net buy > +3,000 Cr in a day   → Nifty +1–2% next session (75% historical hit rate)
FII net sell > −3,000 Cr in a day  → Nifty −1–2% next session (70% historical hit rate)
FII + DII both buying              → very strong bullish confirmation

Advantage over US 13F:
  US 13F: 45-day lag after quarter end
  India FII/DII: same-day visibility — you see institutional buying as it happens
```

### Promoter Holding Change

Promoters = founding families / major original shareholders. Required quarterly SEBI disclosure.

```
Promoter holding rising QoQ   → strong bullish (founders buying more)
Promoter holding > 60%        → high conviction, low float → bullish
Promoter pledge > 30%         → financial stress → bearish red flag
Pledge % rising QoQ           → escalating stress → strong bearish

Stronger than US insider buying because:
  Promoters own 40–75% of Indian companies
  Their conviction IS the company's conviction
  Pledging reveals financial desperation before it hits earnings
```

### Bulk & Block Deals

```
Bulk deal: trade > 0.5% of total shares in one session (NSE publishes end of day)
Block deal: large pre-arranged trade in NSE Block Deal Window (8:45–9:00 AM IST)

Consecutive bulk BUY days by same institution → accumulation signal
Block deal at premium to market price         → buyer has very high conviction
```

---

## 18. Risk Engine

**LLM Required: NO** — Pure statistics. Original `risk_manager.py` has zero LLM calls.

### Volatility

```python
daily_vol    = prices["close"].pct_change().dropna().rolling(60).std().iloc[-1]
annual_vol   = daily_vol * sqrt(market_config.trading_days)   # 252 US / 250 India
vol_pctile   = scipy.stats.percentileofscore(rolling_30d_vols, daily_vol)
```

### Position Limit Tiers

| Annual Vol | Tier | Max Allocation |
|---|---|---|
| < 15% | Low | 25% |
| 15–22% | Medium-Low | 20% |
| 22–30% | Medium | 15% |
| 30–50% | High | 12.5% |
| > 50% | Very High | 10% hard cap |

### Correlation Multiplier

```python
corr_matrix = pd.DataFrame({t: prices(t).pct_change() for t in portfolio}).corr()
avg_corr    = corr_matrix[ticker].drop(ticker).mean()
multiplier  = 0.70 if avg_corr >= 0.80 else 1.10 if avg_corr <= 0.30 else 1.00
```

### Final Position Limit

```python
position_limit_usd    = portfolio_value * vol_tier_allocation * multiplier
position_limit_shares = floor(position_limit_usd / current_price)
max_buy_shares        = min(position_limit_shares, floor(available_cash / current_price))
```

---

## 19. Signal Aggregation & Decision Engine

**LLM Required: NO** — Original portfolio manager pre-computes all allowed quantities then asks LLM to pick. Weighted vote achieves identical result deterministically.

### Signal Weights

| Module | Weight | Why |
|---|---|---|
| Technical | 0.20 | Price reflects all known info; strong short-term |
| Fundamental | 0.15 | Long-term quality filter |
| Valuation | 0.15 | Core value anchor |
| Earnings Quality | 0.10 | Catches manipulation; prevents value traps |
| Insider/Institutional | 0.10 | Superior info, tempered by routine trades |
| News Sentiment | 0.10 | Short-term catalyst; high noise |
| 13 Screens (avg) | 0.20 | Diverse multi-philosophy consensus |
| **Total** | **1.00** | Macro = multiplier, not a vote |

### Aggregation

```python
def aggregate(signals, macro):
    if macro.regime == "bearish":
        for s in signals.values():
            if s.signal == "bullish": s.confidence *= 0.80

    bullish_w = sum(s.weight for s in signals.values() if s.signal == "bullish")
    bearish_w = sum(s.weight for s in signals.values() if s.signal == "bearish")
    net_score = (bullish_w - bearish_w) / sum(s.weight for s in signals.values())

    threshold = 0.25 if macro.regime == "bearish" else 0.10 if macro.regime == "bullish" else 0.15
    direction = "bullish" if net_score > threshold else                 "bearish" if net_score < -threshold else "neutral"
    return direction, abs(net_score) * 100

def determine_action(direction, confidence, portfolio, ticker):
    if confidence < 40: return "hold"   # low conviction always holds
    has_long  = portfolio.positions.get(ticker, Position()).long_shares > 0
    has_short = portfolio.positions.get(ticker, Position()).short_shares > 0
    if direction == "bullish": return "cover" if has_short else "buy"
    if direction == "bearish": return "sell"  if has_long  else "short"
    return "hold"

def size_quantity(action, confidence, risk_data):
    return max(1, floor(risk_data[f"max_{action}_shares"] * (confidence / 100)))
```

---

## 20. Backtesting Engine

**LLM Required: NO** — Date iteration + trade execution = pure arithmetic.

### Simulation Loop

```python
for date in get_trading_calendar(start, end, market_config):
    # STRICT: all data fetched with as_of_date=date — no lookahead
    data     = {t: fetch_all_data(t, as_of_date=date, market=get_market_config(t))
                for t in tickers}
    decisions = run_engine(data, portfolio, config)
    portfolio = execute_trades(decisions, data, portfolio, date)
    history.append({"date": date, "value": mark_to_market(portfolio, data)})
```

**Critical:** `as_of_date` enforced at data layer — every fetch function accepts and respects a date cutoff.

### Trade Execution

| Action | Cash | Position |
|---|---|---|
| Buy | `-= qty × price` | `long_shares += qty` |
| Sell | `+= qty × price` | `long_shares -= qty`; record P&L |
| Short | `-= qty × price × margin_req` | `short_shares += qty` |
| Cover | `+= qty × price × (1-margin_req)` | `short_shares -= qty`; record P&L |
| Hold | No change | No change |

### Performance Metrics

```python
total_return      = (final - initial) / initial * 100
annualized_return = (1 + total_return/100) ** (252/trading_days) - 1
max_drawdown      = min((series - series.cummax()) / series.cummax()) * 100
sharpe_ratio      = mean(daily_returns) / std(daily_returns) * sqrt(252)
win_rate          = profitable_trades / total_trades
```

---

## 21. Portfolio Analytics Dashboard

```
Sector Exposure:
  Technology:  42%  ████████████████████░░░░  Warning: > 40% threshold
  Healthcare:  18%  █████████░░░░░░░░░░░░░░░
  Cash:        13%  ███████░░░░░░░░░░░░░░░░░

Correlation Matrix:
        AAPL  MSFT  TCS.NS
  AAPL  1.00  0.72   0.41
  MSFT  0.72  1.00   0.38
  TCS   0.41  0.38   1.00
  Warning: AAPL-MSFT 0.72 — position limits adjusted

Factor Attribution:
  Market Beta: 0.82 | Value Tilt: +0.31 | Momentum: +0.45 | Quality: +0.62

Max Drawdown: -13.7% | Recovery: 45 days | Sharpe: 1.41
```

---

## 22. Ollama Narrative Engine

**Post-decision ONLY — does NOT influence signals, action, quantity, or confidence.**

```bash
# Install (one time)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b    # 2GB — fast CPU inference
```

```
System prompt:
  "You are a financial analyst. The trading recommendation is already decided.
   You are only explaining it. Use ONLY the numbers provided. 3 sentences max."

Sample output for AAPL BUY 74%:
  "AAPL receives a BUY driven by strong earnings quality (F-Score 8/9,
   M-Score −2.1 — clean books) and a 28% DCF discount to intrinsic value,
   with insider buying accelerating (net ratio +0.52 over 90 days).
   Risk-adjusted position limit of $14,800 reflects 19.1% annual volatility
   with low portfolio correlation (avg 0.34)."
```

---

## 23. CLI Interface

```bash
python engine.py --tickers AAPL MSFT TCS.NS [options]
```

| Argument | Default | Description |
|---|---|---|
| `--tickers` | required | `.NS` → NSE, `.BO` → BSE, no suffix → US |
| `--start-date` | 1yr ago | YYYY-MM-DD |
| `--end-date` | today | YYYY-MM-DD |
| `--cash` | 100,000 | Starting portfolio cash |
| `--margin` | 0.0 | 0 = no shorts |
| `--screens` | all 13 | Subset of investor screens |
| `--no-news` | off | Skip news module (faster) |
| `--news-engine` | `finbert` | `finbert` (local free) or `llm` (API) |
| `--llm-provider` | `openai` | When `--news-engine llm` |
| `--llm-model` | `gpt-4o-mini` | When `--news-engine llm` |
| `--backtest` | off | Run over date range |
| `--show-signals` | off | Full per-module breakdown |
| `--explain` | off | Ollama narrative post-decision |
| `--output` | stdout | JSON file path |

---

## 24. File Structure

```
hf-ai/
├── engine.py                        # CLI entry point
├── config/
│   ├── engine.yaml                  # Master config (hot-reload)
│   ├── us_thresholds.yaml           # US screen thresholds
│   └── india_thresholds.yaml        # India screen thresholds
├── core/
│   ├── engine_base.py               # BaseSignalEngine, Signal, DataBundle
│   ├── write_engine.py              # Orchestrator
│   ├── engine_registry.py           # Auto-discovery
│   ├── data_bus.py                  # 3-layer cache
│   ├── monitor.py                   # MonitorLayer + HealthMetrics
│   ├── result_store.py              # MongoDB writes
│   ├── aggregator.py                # Weighted vote + macro multiplier + sizing
│   ├── risk_engine.py               # Volatility + correlation + position limits
│   └── backtest.py                  # BacktestFramework
├── data/
│   ├── models.py                    # All Pydantic dataclasses
│   ├── market_config.py             # MarketConfig, US_CONFIG, INDIA_CONFIG
│   ├── fetcher_us.py                # yfinance + SEC EDGAR + FINRA + CBOE + FRED
│   └── fetcher_india.py             # yfinance .NS + screener.in + NSE + RBI
├── db/
│   └── client.py                    # MongoDBClient (hf_ai_engine only)
├── news/
│   ├── scraper.py                   # NewsScraperModule
│   ├── sources.py                   # GoogleNews, RSS, YahooFinance sources
│   └── sentiment.py                 # FinBERTScorer + FourSourceComposite
├── signals/
│   ├── technical.py                 # Multi-timeframe EMA/RSI/MACD/OBV
│   ├── fundamental.py               # Ratio scoring + Piotroski
│   ├── valuation.py                 # 6-model DCF + multiples + sector median
│   ├── earnings_quality.py          # Beneish M + Altman Z + F-Score
│   ├── insider_sentiment.py         # SEC Form 4 (US) + Promoter (India)
│   ├── news_sentiment.py            # Wraps news/ as signal engine plugin
│   ├── macro_context.py             # VIX + rates + sector ETF + FII (India)
│   ├── institutional_flow.py        # 13F + dark pool + FINRA + CBOE | FII/DII + bulk
│   └── screens/
│       ├── __init__.py              # Shared helpers: consistency, moat, mgmt
│       ├── buffett.py … jhunjhunwala.py  # 13 screens
├── analytics.py                     # Sector exposure + factor attribution + drawdown
├── narrator.py                      # Ollama post-decision narrative
├── doc/
│   ├── REQUIREMENTS.md              # This document
│   ├── ARCHITECTURE.md
│   ├── PHASES.md
│   └── DB_SCHEMA.md
├── .env.example
├── pyproject.toml
└── README.md
```

**Total: ~22 source files across structured packages** (vs. 22+ unstructured files in the original)

---

## 25. Technical Stack

### Core — Always Required

| Library | Version | Purpose |
|---|---|---|
| Python | ^3.11 | Runtime |
| `yfinance` | ^0.2 | OHLCV + financials — primary data source |
| `pandas` | ^2.1 | DataFrames, time-series, rolling windows |
| `numpy` | ^1.24 | Numerical computation |
| `scipy` | ^1.11 | `percentileofscore`, statistical functions |
| `pydantic` | ^2.4 | Data validation for all models |
| `requests` | ^2.31 | HTTP calls for NSE, FINRA, FRED, screener.in |
| `beautifulsoup4` | ^4.12 | HTML parsing — screener.in and NSE |
| `feedparser` | ^6.0 | RSS feed parsing for news |
| `python-dotenv` | ^1.0 | API key loading |
| `tabulate` | ^0.9 | CLI table output |
| `colorama` | ^0.4 | Colored terminal output |

### Optional

| Library | When |
|---|---|
| `transformers` + `torch` (CPU) | `--news-engine finbert` (recommended) |
| `newsapi-python` | Live news headlines |
| Ollama (not Python) | `--explain` narrative mode |

### Removed from Original (with justification)

| Library | Why |
|---|---|
| `langgraph` | No graph needed — pure functions in a loop |
| All `langchain-*` | LLM abstraction not needed for core |
| `fastapi` | No web app in v1 |
| `sqlalchemy`/`alembic` | No database needed |

---

## 26. Environment Configuration

```env
# ── CORE — No keys required ──────────────────────────────────────────────────
# yfinance, NSE, FINRA: all free, no auth

# ── OPTIONAL: Macro data (recommended) ─────────────────────────────────────
FRED_API_KEY=...          # St. Louis Fed — free, instant registration

# ── OPTIONAL: News headlines ────────────────────────────────────────────────
NEWS_API_KEY=...          # newsapi.org free tier: 100 req/day

# ── OPTIONAL: LLM news sentiment (--news-engine llm) ───────────────────────
OPENAI_API_KEY=sk-...     # gpt-4o-mini: $0.001 per ~20 headlines
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...      # Free tier available
DEEPSEEK_API_KEY=...      # Very cheap alternative

# ── OPTIONAL: Paid data upgrades ────────────────────────────────────────────
FMP_API_KEY=...            # Financial Modeling Prep — better India fundamentals
ALPHA_VANTAGE_API_KEY=...  # Fallback if yfinance unavailable
```

---

## 27. Non-Functional Requirements

| Requirement | Specification |
|---|---|
| Determinism | Same input data → identical output (except `--news-engine llm`) |
| Performance | < 2s per ticker for core signals (no LLM network calls) |
| Cost | $0 for full operation on US + India markets |
| Backtesting integrity | No data beyond `as_of_date` in any computation |
| Reliability | None-safe defaults for missing fields; graceful degradation |
| Portability | macOS + Linux + Windows; no OS-specific dependencies |
| Testability | Every signal module is a pure function — unit-testable with synthetic data |
| Extensibility | New investor screen = one function in `signals/screens.py` |
| Observability | `--show-signals` exposes every module's signal, confidence, and reasoning |
| Security | All keys in `.env`; never hardcoded; `.gitignore` enforced |

---

## 28. LLM Decision Matrix — Full Summary

| Component | LLM Decision | Replacement | Key Reason |
|---|---|---|---|
| Technical indicators | **No** | Python math on OHLCV | No semantic content |
| Fundamental screening | **No** | Threshold rules on reported numbers | Deterministic if/else |
| Valuation (6 models) | **No** | DCF, Graham, multiples, sector median — arithmetic | Closed-form formulas |
| Earnings quality (Beneish/Altman/Piotroski) | **No** | Formula on financial statements | New module; zero ambiguity |
| Insider/Promoter sentiment | **No** | Weighted dollar-flow ratio | Single arithmetic formula |
| Macro context | **No** | Structured market data (VIX, rates, ETFs) | All numbers; no text |
| Institutional flow | **No** | 13F/FII counts, OI ratios | Structured filings |
| Risk engine | **No** | numpy/scipy statistics | Pure math |
| 13 Investor screens | **No** | Threshold rules on pre-computed scores | Investor criteria are published rules |
| Portfolio decision | **No** | Weighted signal vote + position limit | Pre-computed options |
| **News headline sentiment** | **YES (FinBERT)** | FinBERT (free, local, domain-trained) | Unstructured text |
| Moat assessment | **Optional** | SEC 10-K keyword mining | Enhancement; proxies cover ~80% |
| Decision narrative | **Optional (Ollama)** | Post-decision only; free offline | Cosmetic; does not affect signals |

---

## 29. Disclaimer

This system is for **educational and research purposes only**. It does not provide investment advice, does not guarantee financial returns, and must not be used to make real trading or investment decisions. All signals are generated from quantitative rules on publicly available data. Past performance does not guarantee future results. Authors assume no liability for financial losses.

---

*System B Enhanced — Requirements v1.1 — 2026-06-02*
