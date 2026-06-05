# Development Phases — User Stories & Tasks

> **Project:** HF-AI Engine | **Total Phases:** 10 | **Date:** 2026-06-01
> **Methodology:** Each phase delivers a working, testable increment.
> **Phase completion criterion:** All acceptance criteria pass + data persists correctly in `hf_ai_engine` MongoDB.

---

## Phase Overview

| Phase | Name | Duration | Delivers |
|---|---|---|---|
| 1 | Core Engine Scaffold | Week 1 | Write Engine + Plugin Protocol + MongoDB |
| 2 | Data Layer — US | Week 2 | Full US data fetch pipeline |
| 3 | Signal Engines — Quantitative | Week 3–4 | Technical, Fundamental, Valuation, Earnings Quality |
| 4 | News Scraper & Sentiment | Week 4 | Python-based news pipeline, no LLM |
| 5 | Investor Screens | Week 5 | All 13 screens as pluggable engines |
| 6 | Macro & Institutional Flow | Week 6 | Macro context + 13F/FINRA/CBOE engines |
| 7 | Risk Engine & Aggregator | Week 7 | Risk math + decision aggregation |
| 8 | Backtesting Framework | Week 8 | Full backtest with MongoDB persistence |
| 9 | India Data Layer | Week 9 | NSE/BSE/RBI/FII-DII/Promoter data |
| 10 | Monitoring, CLI & Polish | Week 10 | Production CLI, health checks, audit log |

---

## Phase 1 — Core Engine Scaffold

**Goal:** Build the Write Engine runtime, plugin protocol, MongoDB connection, and configuration system. No signal logic yet — just the stable foundation everything else builds on.

**Delivers:** `python engine.py --tickers AAPL --dry-run` runs, shows "no engines registered", writes a run record to MongoDB.

---

### User Stories

#### US-1.1 — Engine Registry
**As a** developer adding a new signal engine,
**I want** to drop a Python file into `signals/` and have it auto-discovered at startup,
**So that** I never have to modify the Write Engine or any other file to add a new engine.

**Acceptance Criteria:**
- [ ] `EngineRegistry.discover("signals")` finds all classes extending `BaseSignalEngine`
- [ ] A new `.py` file added to `signals/` is picked up on next engine start without code change
- [ ] Duplicate engine name raises `ValueError` with clear message
- [ ] `EngineRegistry.list_active()` returns correct count and metadata

#### US-1.2 — Plugin Contract
**As a** developer,
**I want** a minimal base class that requires only one method to implement,
**So that** adding a new engine is as simple as possible.

**Acceptance Criteria:**
- [ ] `BaseSignalEngine` exists in `core/engine_base.py`
- [ ] Only `compute(data: DataBundle) -> Signal` is `@abstractmethod`
- [ ] `validate_data()` has a sensible default (returns True if ≥60 days of prices)
- [ ] `Signal` dataclass has: `signal`, `confidence`, `weight`, `reasoning`, `metadata`
- [ ] `DataBundle` has all fields: `ticker`, `market`, `as_of_date`, `prices`, `financials`, `ratios`, `news_items`, `filing_text`, `mda_text`, `insider_trades`, `promoter_holdings`, `inst_flow_us`, `inst_flow_india`, `bulk_deals`, `macro`, `market_config`
- [ ] All India-specific fields (`promoter_holdings`, `inst_flow_india`, `bulk_deals`) are `None` for US tickers — no engine crashes on missing India data

#### US-1.3 — MongoDB Connection
**As a** system operator,
**I want** the engine to connect to a new isolated MongoDB database called `hf_ai_engine`,
**So that** it never touches any existing database.

**Acceptance Criteria:**
- [ ] `MongoDBClient` connects to `hf_ai_engine` database only
- [ ] Connection verified with `ping` at startup
- [ ] If connection fails, engine exits with clear error (not silent failure)
- [ ] All required indexes created on first run via `_ensure_indexes()`
- [ ] `db/client.py` never references any other database name

#### US-1.4 — Configuration System
**As a** system operator,
**I want** all engine settings in a single YAML file that reloads without restart,
**So that** I can tune thresholds and toggle engines without downtime.

**Acceptance Criteria:**
- [ ] `config/engine.yaml` is the single source of truth for all settings
- [ ] `ConfigManager.get("mongodb.uri")` works with dot-notation
- [ ] Config file changes are detected and reloaded within 5 seconds
- [ ] Missing required keys raise `ConfigError` with key name at startup
- [ ] Sensitive values (passwords, API keys) loaded from `.env` not YAML

#### US-1.5 — Orchestrator Run Record
**As a** system operator,
**I want** every run to create a MongoDB record with status and timing,
**So that** I can audit what ran, when, and whether it succeeded.

**Acceptance Criteria:**
- [ ] Every `WriteEngine.run()` call creates a record in `hf_ai_engine.runs`
- [ ] Record contains: `run_id`, `tickers`, `engines`, `as_of_date`, `started_at`, `status`
- [ ] Status updates to `"success"` or `"error"` with `ended_at` on completion
- [ ] `run_id` is globally unique (UUID4)
- [ ] `--dry-run` CLI flag runs without fetching data or writing signals

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T1.1 | Create `Signal` and `DataBundle` dataclasses | `core/engine_base.py` | 1h |
| T1.2 | Implement `BaseSignalEngine` abstract class | `core/engine_base.py` | 1h |
| T1.3 | Implement `EngineRegistry` with auto-discover | `core/engine_registry.py` | 2h |
| T1.4 | Implement `MongoDBClient` with index setup | `db/client.py` | 2h |
| T1.5 | Implement `ConfigManager` with hot reload | `core/config.py` → `config/` | 2h |
| T1.6 | Implement `MonitorLayer.start_run()` and `end_run()` | `core/monitor.py` | 1.5h |
| T1.7 | Implement `WriteEngine.__init__()` and `run()` skeleton | `core/write_engine.py` | 2h |
| T1.8 | Create `engine.py` CLI entry point with `--dry-run` | `engine.py` | 1h |
| T1.9 | Create `config/engine.yaml` (master config — source of truth for MarketConfig values) | `config/engine.yaml` | 1h |
| T1.10 | Write unit tests for registry, config, and DB connection | `tests/unit/` | 2h |
| T1.11 | Create `pyproject.toml` with full dependency list: yfinance, pandas, numpy, scipy, pydantic, pymongo, requests, beautifulsoup4, feedparser, pdfplumber, pyyaml, python-dotenv, watchdog, schedule, tabulate, colorama, tqdm, transformers, torch | `pyproject.toml` | 0.5h |
| T1.12 | Create `.env.example` with all optional keys | `.env.example` | 0.5h |
| T1.13 | Verify MongoDB `hf_ai_engine` DB is created on first run | manual test | 0.5h |

**Phase 1 Total Estimate:** ~16.5 hours

---

## Phase 2 — Data Layer — US Market

**Goal:** Implement the DataBus with full US market data fetching, MongoDB caching, and staleness management. At the end, calling `DataBus.fetch("AAPL")` returns a complete DataBundle with all fields populated.

**Delivers:** `python engine.py --tickers AAPL MSFT NVDA --fetch-only` fetches and stores data to MongoDB.

---

### User Stories

#### US-2.1 — OHLCV Price Data
**As an** engine developer,
**I want** `data.prices` to contain 2 years of daily OHLCV data,
**So that** technical indicators have enough history to compute.

**Acceptance Criteria:**
- [ ] `prices` contains at least 252 records for US large-caps
- [ ] Each record has: `date`, `open`, `high`, `low`, `close`, `volume`
- [ ] Data stored in `hf_ai_engine.prices_us` with ticker + date index
- [ ] TTL = 6 hours; stale data triggers re-fetch
- [ ] Splits and dividends adjusted (use `auto_adjust=True` in yfinance)

#### US-2.2 — Financial Statements (10-Year History)
**As an** engine developer,
**I want** 10 years of annual financial statements in `data.financials`,
**So that** investor screens can check 10-year consistency.

**Acceptance Criteria:**
- [ ] Annual periods for last 10 fiscal years returned when available
- [ ] TTM period always included
- [ ] Each record has all fields defined in `Financials` Pydantic model
- [ ] Missing fields are `None`, not omitted (no KeyError in engines)
- [ ] Stored in `hf_ai_engine.financials` with (ticker, period, date) index
- [ ] TTL = 90 days (financial statements change quarterly)

#### US-2.3 — Financial Ratios
**As an** engine developer,
**I want** `data.ratios` to contain latest computed/fetched ratios,
**So that** engines don't re-derive P/E, P/B, ROE from raw statements.

**Acceptance Criteria:**
- [ ] `ratios` contains all fields in `Ratios` Pydantic model
- [ ] If yfinance ratio is missing, attempt to compute from financials
- [ ] TTL = 24 hours
- [ ] Stored in `hf_ai_engine.ratios`

#### US-2.4 — Insider Trade Data
**As an** engine developer,
**I want** `data.insider_data` to contain 1 year of SEC Form 4 transactions,
**So that** the insider sentiment engine can compute buy/sell ratios.

**Acceptance Criteria:**
- [ ] Fetches from SEC EDGAR insider trading endpoint
- [ ] Filters to open-market transactions only (excludes RSU vesting, ESPP)
- [ ] Each record has: `date`, `transaction_type`, `shares`, `price`, `value`, `insider_name`, `title`
- [ ] Stored in `hf_ai_engine.insider_trades`
- [ ] TTL = 7 days

#### US-2.5 — DataBus Caching
**As a** system operator,
**I want** the DataBus to serve data from MongoDB cache when fresh,
**So that** running the engine multiple times per day doesn't re-fetch from external APIs.

**Acceptance Criteria:**
- [ ] Second call for same ticker + date serves from MongoDB, not live API
- [ ] In-memory cache prevents duplicate DB reads within the same run
- [ ] `prefetch()` fetches all tickers in parallel (ThreadPoolExecutor, 8 workers)
- [ ] Cache miss logs to `audit_log` at DEBUG level
- [ ] Force refresh via `--refresh` CLI flag bypasses all caches

#### US-2.6 — No-Lookahead Enforcement
**As a** backtesting user,
**I want** `DataBus.fetch("AAPL", as_of_date="2023-06-15")` to return ONLY data available on that date,
**So that** backtesting results are free of lookahead bias.

**Acceptance Criteria:**
- [ ] All fetch functions accept and enforce `end_date = as_of_date`
- [ ] Prices only include dates ≤ `as_of_date`
- [ ] Financial statements only include periods with `date ≤ as_of_date`
- [ ] Unit test: fetching 2023-06-15 returns no data from 2023-06-16 or later
- [ ] MongoDB queries filter by date before returning

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T2.1 | Implement all Pydantic models | `data/models.py` | 2h |
| T2.2 | Implement `MarketConfig` + `US_CONFIG` / `INDIA_CONFIG` | `data/market_config.py` | 1.5h |
| T2.3 | Implement `yfinance` price fetcher with adjustment | `data/fetcher_us.py` | 1.5h |
| T2.4 | Implement `yfinance` financials fetcher (10yr annual) | `data/fetcher_us.py` | 2h |
| T2.5 | Implement `yfinance` ratios fetcher with compute fallback | `data/fetcher_us.py` | 1.5h |
| T2.6 | Implement SEC EDGAR Form 4 insider trade fetcher | `data/fetcher_us.py` | 2h |
| T2.7 | Implement `DataBus` with 3-layer cache (mem, MongoDB, live) | `core/data_bus.py` | 3h |
| T2.8 | Implement cleanup-job TTL (replaces MongoDB TTL indexes); add `is_historical` flag | `core/data_bus.py` | 1.5h |
| T2.9 | Implement `prefetch()` with ThreadPoolExecutor (8 workers) | `core/data_bus.py` | 1h |
| T2.10 | Add `as_of_date` enforcement to all fetch functions | `data/fetcher_us.py` | 1h |
| T2.11 | Implement SEC EDGAR 10-K text fetcher + 8-K MD&A parser | `data/fetcher_us.py` | 2h |
| T2.12 | Write integration test: fetch AAPL, verify DataBundle fields | `tests/integration/` | 2h |
| T2.13 | Write no-lookahead test: verify as_of_date cutoff works | `tests/integration/` | 1h |

**Phase 2 Total Estimate:** ~22 hours

---

## Phase 3 — Signal Engines — Quantitative (US)

**Goal:** Implement Technical, Fundamental, Valuation, and Earnings Quality engines as independent pluggable modules. Each reads only from `DataBundle` and returns a `Signal`.

**Delivers:** Four engines auto-discovered, computing signals on US tickers, stored to `hf_ai_engine.signals`.

---

### User Stories

#### US-3.1 — Technical Signal Engine
**As a** trader,
**I want** a technical signal computed across daily, weekly, and monthly timeframes,
**So that** I get high-confidence signals only when multiple timeframes agree.

**Acceptance Criteria:**
- [ ] Computes EMA (8/21/55), RSI (14, 28), MACD (12/26/9), Bollinger (20,2σ), ADX (14), Hurst, OBV, VWAP, MFI
- [ ] Runs on daily, weekly, and monthly price series independently
- [ ] Confluence rule: all 3 agree → confidence ×1.30; only 1 agrees → neutral capped at 55%
- [ ] Returns `Signal` with `metadata` containing per-indicator sub-scores
- [ ] `validate_data()` returns False if < 60 days of prices
- [ ] Engine name: `"technical"`, weight: 0.20

#### US-3.2 — Fundamental Signal Engine
**As a** fundamental investor,
**I want** a signal based on profitability, growth, health, and valuation checks,
**So that** I can identify fundamentally strong companies.

**Acceptance Criteria:**
- [ ] Scores 12 checks across 4 categories (3 each): Profitability, Growth, Health, Valuation
- [ ] Piotroski F-Score (9 checks) integrated and included in metadata
- [ ] Signal: bullish ≥9/12 pass; bearish ≤4/12; neutral otherwise
- [ ] Uses `market_config` thresholds (US vs India differ)
- [ ] `validate_data()` returns False if no TTM financials available
- [ ] Engine name: `"fundamental"`, weight: 0.15

#### US-3.3 — Valuation Signal Engine
**As a** value investor,
**I want** a signal based on 6 valuation models averaged together,
**So that** no single model dominates and outliers are smoothed.

**Acceptance Criteria:**
- [ ] Computes: 3-stage DCF, Owner Earnings DCF, EV/EBITDA relative, P/E relative (5yr avg), Graham Number, Sector Median P/E
- [ ] Sector Median P/E: compare ticker P/E vs median P/E of its sector ETF constituents (via yfinance); skip and reweight if unavailable
- [ ] Margin of safety: mean of all available model gaps (min 3 models required)
- [ ] Signal: bullish >20% undervalued; bearish >20% overvalued; neutral otherwise
- [ ] WACC = `risk_free_rate` from `market_config` + 4.5–6% equity risk premium
- [ ] `validate_data()` returns False if no EPS or no market_cap
- [ ] Engine name: `"valuation"`, weight: 0.15

#### US-3.4 — Earnings Quality Engine
**As a** risk-aware investor,
**I want** a signal that flags manipulation risk and financial distress,
**So that** I don't buy value traps with deteriorating earnings quality.

**Acceptance Criteria:**
- [ ] Computes Beneish M-Score (all 8 components)
- [ ] Computes Altman Z-Score (standard for manufacturing; Z' for services)
- [ ] Sources Piotroski F-Score from Fundamental engine metadata (not recomputed)
- [ ] Bearish if ANY: M-Score > −1.78 OR Z-Score < 1.81 OR F-Score ≤ 3
- [ ] Bullish only if ALL three pass
- [ ] `validate_data()` returns False if < 2 years of annual financials
- [ ] Engine name: `"earnings_quality"`, weight: 0.10

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T3.1 | Implement `TechnicalEngine` with multi-timeframe | `signals/technical.py` | 3h |
| T3.2 | Add volume analysis (OBV, VWAP, MFI) to technical | `signals/technical.py` | 1.5h |
| T3.3 | Write unit tests for technical (synthetic price data) | `tests/unit/test_technical.py` | 1.5h |
| T3.4 | Implement `FundamentalEngine` with 12-check scoring | `signals/fundamental.py` | 2h |
| T3.5 | Integrate Piotroski F-Score into fundamental | `signals/fundamental.py` | 1.5h |
| T3.6 | Write unit tests for fundamental | `tests/unit/test_fundamental.py` | 1h |
| T3.7 | Implement `ValuationEngine` with 6 models (sector P/E = sector ETF trailingPE via yfinance) | `signals/valuation.py` | 3.5h |
| T3.8 | Write unit tests for valuation (known DCF scenarios) | `tests/unit/test_valuation.py` | 1.5h |
| T3.9 | Implement `EarningsQualityEngine` (Beneish + Altman) | `signals/earnings_quality.py` | 2.5h |
| T3.10 | Write unit tests for earnings quality | `tests/unit/test_earnings_quality.py` | 1h |
| T3.11 | Run all 4 engines on AAPL/MSFT/NVDA; verify MongoDB write | `tests/integration/` | 1.5h |
| T3.12 | Verify auto-discovery picks up all 4 engines | `tests/integration/` | 0.5h |

**Phase 3 Total Estimate:** ~20.5 hours

---

## Phase 4 — News Scraper & Sentiment Module

**Goal:** Build a standalone news scraper that fetches articles from Google News RSS and financial RSS feeds, then scores sentiment using FinBERT (`ProsusAI/finbert`) — a domain-trained BERT model that runs locally with no API key. FinBERT is the primary scorer. The full signal is a 4-source composite: FinBERT headlines (25%) + earnings call MD&A (30%) + analyst rating changes (25%) + options sentiment overlay (20%).

**Delivers:** `news_sentiment` engine produces signals. Raw articles and sentiment stored in `hf_ai_engine.news_raw` and `hf_ai_engine.news_sentiment`.

**Dependency:** `pip install transformers torch` (CPU-only torch is ~500 MB one-time download; runs on any machine without a GPU).

---

### User Stories

#### US-4.1 — Google News RSS Scraper
**As a** trader,
**I want** recent news articles about a ticker fetched automatically from Google News,
**So that** news sentiment reflects the most current market narrative.

**Acceptance Criteria:**
- [ ] Fetches from `https://news.google.com/rss/search?q={ticker}+stock&hl=en-US`
- [ ] Also queries `{company_name}` to capture company-name headlines
- [ ] Returns: `date`, `headline`, `source`, `url`, `ticker`
- [ ] Deduplicates articles by URL
- [ ] Respects lookback window from config (`lookback_days: 90`)
- [ ] Stored in `hf_ai_engine.news_raw`
- [ ] TTL = 1 hour; re-fetches during market hours

#### US-4.2 — Financial RSS Feed Scraper
**As a** trader,
**I want** news from domain-specific financial outlets,
**So that** sentiment reflects expert financial coverage, not general media.

**Acceptance Criteria:**
- [ ] Fetches from configurable RSS feed list (see `config/engine.yaml`)
- [ ] US feeds: Yahoo Finance, WSJ Markets (configured)
- [ ] India feeds: Economic Times, Moneycontrol, Business Standard (configured)
- [ ] Filters to articles mentioning the ticker or company name
- [ ] Merges with Google News results, deduplicates
- [ ] `feedparser` used for all RSS parsing

#### US-4.3 — FinBERT Sentiment Scorer
**As a** trader,
**I want** sentiment scoring using a model trained on financial language,
**So that** domain-specific phrases ("earnings beat", "SEC investigation", "dividend cut") are classified accurately.

**Acceptance Criteria:**
- [ ] Uses `ProsusAI/finbert` via HuggingFace `transformers.pipeline("text-classification")`
- [ ] Model loaded once at engine `initialize()` — not reloaded per ticker
- [ ] Each headline truncated to 512 tokens before scoring
- [ ] Returns label (`positive` / `negative` / `neutral`) and confidence score (0.0–1.0)
- [ ] Model cached locally after first download (~500 MB); no network call after that
- [ ] Deterministic — no sampling, same headline always returns same result
- [ ] Mapped to internal score: `positive` → +confidence, `negative` → −confidence, `neutral` → 0

#### US-4.4 — 4-Source Composite Signal
**As a** trader,
**I want** the news signal to draw from multiple sources beyond just headlines,
**So that** management guidance and analyst consensus also inform the signal.

**Acceptance Criteria:**
- [ ] Source 1 — FinBERT on headlines (weight 25%): recency-weighted average of FinBERT scores across all scraped headlines
- [ ] Source 2 — Earnings call MD&A (weight 30%): FinBERT applied to MD&A section from latest SEC 8-K (US) or BSE filing (India); if unavailable → skip and reweight
- [ ] Source 3 — Analyst rating changes (weight 25%): `yfinance.upgrades_downgrades`; upgrade → +0.7, downgrade → −0.7, initiation → +0.3; decayed by age; India fallback: scrape screener.in analyst section; if both empty → skip, reweight other sources
- [ ] Source 4 — Options sentiment overlay (weight 20%): uses `pc_ratio` and `iv_rank` from Institutional Flow module's data; pc_ratio > 1.5 → contrarian bullish (+0.4); iv_rank > 80 → caution (−0.2)
- [ ] If any source is unavailable, its weight is redistributed proportionally to available sources
- [ ] Final composite score: −1.0 to +1.0

#### US-4.5 — Recency-Weighted Aggregation
**As a** trader,
**I want** recent news to count more than old news,
**So that** a headline from yesterday outweighs a similar one from 60 days ago.

**Acceptance Criteria:**
- [ ] Weight formula: `w = 1 / (1 + days_ago / 30)`
- [ ] Applied to FinBERT headline scores before averaging
- [ ] Min 3 articles required; return `neutral` with confidence 30 if fewer
- [ ] Stored in `hf_ai_engine.news_sentiment` with computed score and source breakdown

#### US-4.6 — News Sentiment Signal Engine
**As a** signal engine developer,
**I want** the news module to expose a standard `SignalEngine` interface,
**So that** the Write Engine can treat it identically to any other engine.

**Acceptance Criteria:**
- [ ] `NewsSentimentEngine` extends `BaseSignalEngine`
- [ ] `initialize()` loads FinBERT model once at startup
- [ ] `compute()` runs 4-source composite on the ticker's DataBundle
- [ ] `validate_data()` returns False if < 3 articles in last 30 days
- [ ] Engine name: `"news_sentiment"`, weight: 0.10
- [ ] Signal: bullish if composite_score > 0.10; bearish < −0.10; neutral otherwise
- [ ] Confidence: `abs(composite_score) * 100`, capped at 95
- [ ] `metadata` contains per-source scores and article count

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T4.1 | Implement `GoogleNewsSource` with RSS parsing | `news/sources.py` | 2h |
| T4.2 | Implement `RSSFeedSource` for financial RSS feeds | `news/sources.py` | 1.5h |
| T4.3 | Implement `YahooFinanceNewsSource` via yfinance | `news/sources.py` | 1h |
| T4.4 | Implement `NewsScraperModule` orchestrating all sources | `news/scraper.py` | 1.5h |
| T4.5 | Add deduplication and headline cleaning | `news/scraper.py` | 1h |
| T4.6 | Implement `FinBERTScorer` with model load + batch scoring | `news/sentiment.py` | 2h |
| T4.7 | Implement recency-weighted FinBERT headline aggregation | `news/sentiment.py` | 1h |
| T4.8 | Implement analyst rating change scorer (yfinance) | `news/sentiment.py` | 1.5h |
| T4.9 | Implement options sentiment overlay (reads inst. flow data) | `news/sentiment.py` | 1h |
| T4.10 | Implement MD&A text scorer (SEC 8-K / BSE filing) | `news/sentiment.py` | 2h |
| T4.11 | Implement `FourSourceComposite` combining all four with reweighting | `news/sentiment.py` | 1.5h |
| T4.12 | Implement `NewsSentimentEngine` wrapping the module | `signals/news_sentiment.py` | 1h |
| T4.13 | Implement MongoDB persistence for raw and sentiment | `news/scraper.py` | 1h |
| T4.14 | Write unit tests with fixed headlines (known FinBERT output) | `tests/unit/test_news.py` | 2h |
| T4.15 | Integration test: fetch news for AAPL, verify 4-source output | `tests/integration/` | 1h |

**Phase 4 Total Estimate:** ~21 hours

---

## Phase 5 — Investor Screens (13 Engines)

**Goal:** Implement all 13 investor screens as separate pluggable engines in `signals/screens/`. Each is independent, shares common helpers (10yr consistency, moat text mining, management quality), and extends `BaseSignalEngine`.

**Delivers:** 13 new engines auto-discovered. Combined weight = 0.20 in aggregator.

---

### User Stories

#### US-5.1 — Shared Screen Infrastructure
**As a** screen engine developer,
**I want** shared helpers for 10-year consistency, moat text mining, and management quality scoring,
**So that** I implement them once and every screen uses the same logic.

**Acceptance Criteria:**
- [ ] `screens/__init__.py` exports: `consistency_score()`, `moat_text_score()`, `management_quality_score()`, `master_screen_score()`
- [ ] `consistency_score(metric_series, threshold)` returns 0.0–1.0 (% of years passing)
- [ ] `moat_text_score(filing_text)` returns 0.0–1.0 using MOAT_EVIDENCE keyword dict
- [ ] `management_quality_score(financials_list, insider_pct)` returns 0.0–1.0
- [ ] `master_screen_score(criteria, consistency, moat, mgmt)` applies weights (0.40/0.25/0.20/0.15)
- [ ] Red flag detected in filing_text → final score ×0.50

#### US-5.2 — Individual Screen Engines
**As a** multi-strategy investor,
**I want** each investor screen to be independently togglable,
**So that** I can run only Buffett + Graham + Lynch without the others.

**Acceptance Criteria (per screen):**
- [ ] Each screen file in `signals/screens/{name}.py` extends `BaseSignalEngine`
- [ ] Screen can be enabled/disabled in `config/engine.yaml` without code change
- [ ] Each uses `master_screen_score()` with screen-specific criteria
- [ ] India threshold overrides applied from `INDIA_CONFIG` when `data.market == "IN"`
- [ ] `metadata` in returned Signal contains per-criteria pass/fail dict
- [ ] `validate_data()` returns False if < 5 years of annual financials available

**Screens to implement (13 total):**
Buffett, Graham, Lynch, Fisher, Munger, Burry, Ackman, Wood, Druckenmiller, Taleb, Damodaran, Pabrai, Jhunjhunwala

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T5.0 | Add `config/moat_idf.json` (pre-computed IDF weights) + `scripts/build_moat_idf.py` (one-time utility) to project | `config/`, `scripts/` | 0.5h |
| T5.1 | Implement `consistency_score()` helper | `signals/screens/__init__.py` | 1h |
| T5.2 | Implement `moat_text_score()` TF-IDF weighted; load IDF weights from `config/moat_idf.json`; fall back to unweighted count if file missing | `signals/screens/__init__.py` | 2.5h |
| T5.3 | Implement `management_quality_score()` | `signals/screens/__init__.py` | 1.5h |
| T5.4 | Implement `master_screen_score()` with weights | `signals/screens/__init__.py` | 1h |
| T5.5 | Implement `BuffettScreen` engine | `signals/screens/buffett.py` | 1h |
| T5.6 | Implement `GrahamScreen` engine | `signals/screens/graham.py` | 1h |
| T5.7 | Implement `LynchScreen` engine | `signals/screens/lynch.py` | 0.5h |
| T5.8 | Implement `FisherScreen` engine | `signals/screens/fisher.py` | 0.5h |
| T5.9 | Implement `MungerScreen` engine | `signals/screens/munger.py` | 0.5h |
| T5.10 | Implement `BurryScreen` engine | `signals/screens/burry.py` | 0.5h |
| T5.11 | Implement `AckmanScreen` engine | `signals/screens/ackman.py` | 0.5h |
| T5.12 | Implement `WoodScreen` engine | `signals/screens/wood.py` | 0.5h |
| T5.13 | Implement `DruckenmillerScreen` engine | `signals/screens/druckenmiller.py` | 0.5h |
| T5.14 | Implement `TalebScreen` engine | `signals/screens/taleb.py` | 0.5h |
| T5.15 | Implement `DamodaranScreen` (delegates to valuation) | `signals/screens/damodaran.py` | 0.5h |
| T5.16 | Implement `PabraiScreen` engine | `signals/screens/pabrai.py` | 0.5h |
| T5.17 | Implement `JhunjhunwalaScreen` with promoter check | `signals/screens/jhunjhunwala.py` | 1h |
| T5.18 | Write unit tests for Buffett, Graham, Lynch screens | `tests/unit/test_screens.py` | 2h |
| T5.19 | Integration test: all 13 engines discovered and run on AAPL | `tests/integration/` | 1h |

**Phase 5 Total Estimate:** ~18 hours

---

## Phase 6 — Macro Context & Institutional Flow

**Goal:** Implement the Macro Context module (regime multiplier) and Institutional Flow engine (13F, FINRA short interest, CBOE options). Both engines are US-first; India variants added in Phase 9.

**Delivers:** Macro regime affects all signal confidences. Institutional flow signal added to MongoDB.

---

### User Stories

#### US-6.1 — Macro Context Module
**As a** portfolio manager,
**I want** the engine to recognize bull/bear market regimes and adjust signal thresholds,
**So that** bullish signals in a VIX=40, inverted yield curve environment require higher conviction.

**Acceptance Criteria:**
- [ ] Fetches: VIX level + 5d/20d MA trend, 10yr−2yr yield spread (FRED), sector ETF 3m return, S&P 500 vs 200 MA, market breadth
- [ ] `MacroContext` is NOT a signal vote — it returns a `MacroRegime` object with `regime` and `multiplier`
- [ ] `regime = "bearish"` → all bullish confidences ×0.80; buy threshold raised to 0.25
- [ ] `regime = "bullish"` → bullish confidences ×1.10; buy threshold lowered to 0.10
- [ ] `regime = "neutral"` → no adjustment
- [ ] Macro data stored in `hf_ai_engine.macro_us`
- [ ] Aggregator reads `MacroRegime` before aggregating signals

#### US-6.2 — Institutional Flow Engine
**As a** market microstructure analyst,
**I want** a signal based on 13F changes, short interest, options positioning, and dark pool activity,
**So that** smart money positioning is reflected in the final decision.

**Acceptance Criteria:**
- [ ] 13F: counts net new institutional buyers vs. sellers (SEC EDGAR)
- [ ] FINRA short interest: `si_pct = short_shares/float`, `days_to_cover`, `biweekly_change`
- [ ] Squeeze signal: `si_pct > 15%` AND `si_change < −5%` → bullish
- [ ] CBOE P/C ratio: put_vol / call_vol; > 1.5 → contrarian bullish; < 0.5 → caution
- [ ] IV rank: `(current_iv - 52w_low) / (52w_high - 52w_low)`; > 80% → expensive options
- [ ] Dark pool (FINRA OTC/ATS weekly report — free): `dark_pool_pct = otc_vol / total_vol`; rising dark_pool_pct with rising price → +10 confidence
- [ ] India path: FII sector-wise monthly flow breakdown (NSE); flag divergence if sector inflow contradicts ticker-level FII signal
- [ ] Signal: weighted combination of all sub-signals
- [ ] Engine name: `"institutional_flow"`, weight: 0.10

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T6.1 | Implement FRED API macro data fetcher | `data/fetcher_us.py` | 2h |
| T6.2 | Implement `MacroContextEngine` (returns `MacroRegime`) | `signals/macro_context.py` | 2h |
| T6.3 | Update `Aggregator` to apply `MacroRegime` multiplier | `core/aggregator.py` | 1.5h |
| T6.4 | Implement 13F institutional change fetcher (SEC EDGAR) | `data/fetcher_us.py` | 2.5h |
| T6.5 | Implement FINRA short interest CSV fetcher + parser | `data/fetcher_us.py` | 2h |
| T6.6 | Implement CBOE P/C ratio and IV data fetcher | `data/fetcher_us.py` | 2h |
| T6.7a | Implement FINRA OTC/ATS dark pool fetcher + dark_pool_pct signal (US only) | `data/fetcher_us.py` | 1.5h |
| T6.7b | Implement `InstitutionalFlowEngine` — US path only (India added in Phase 9) | `signals/institutional_flow.py` | 2h |
| T6.8 | Write unit tests for macro regime classification | `tests/unit/test_macro.py` | 1h |
| T6.9 | Integration test: verify macro multiplier applied to aggregation | `tests/integration/` | 1h |

**Phase 6 Total Estimate:** ~17.5 hours

---

## Phase 7 — Risk Engine & Signal Aggregator

**Goal:** Implement the full risk engine (volatility + correlation + position limits) and signal aggregator (weighted vote + action determination + quantity sizing). Both live in `core/` — not plugins.

**Delivers:** End-to-end pipeline: fetch data → run engines → risk → aggregate → decision. Write to `hf_ai_engine.decisions`.

---

### User Stories

#### US-7.1 — Volatility-Based Position Limits
**As a** risk manager,
**I want** position sizes automatically adjusted based on realized volatility,
**So that** a high-volatility stock never gets the same allocation as a low-volatility one.

**Acceptance Criteria:**
- [ ] 60-day rolling standard deviation of daily returns → annualized (×√trading_days)
- [ ] Vol percentile computed against 30-day rolling history
- [ ] Position limit % determined by vol tier (5 tiers from config)
- [ ] Final position limit in dollars = portfolio_value × tier_alloc × corr_multiplier
- [ ] Correlation matrix computed across all tickers in portfolio

#### US-7.2 — Signal Aggregation & Decision
**As a** portfolio manager,
**I want** the final action (BUY/SELL/HOLD/SHORT/COVER) to be derived deterministically from signal weights,
**So that** the same data always produces the same decision.

**Acceptance Criteria:**
- [ ] Engine compute calls run in parallel: `ThreadPoolExecutor(max_workers=4)` per ticker
- [ ] Weights renormalized over available signals only: `total_weight = sum(s.weight for s in active_signals)`
- [ ] If `total_weight < 0.30`: return HOLD with confidence 0 and log WARN (insufficient coverage)
- [ ] Macro regime multiplier applied before vote
- [ ] `net_score = (bullish_weight − bearish_weight) / total_weight`
- [ ] Thresholds: bearish regime 0.25 / neutral 0.15 / bullish 0.10
- [ ] Confidence < 40% → always HOLD
- [ ] Quantity = `max_shares × (confidence / 100)`, minimum 1
- [ ] Engine weights overridable from `config/engine.yaml`
- [ ] Decision stored in `hf_ai_engine.decisions`

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T7.1 | Implement `RiskEngine.compute()` (vol + correlation) | `core/risk_engine.py` | 3h |
| T7.2 | Implement vol tier logic from config | `core/risk_engine.py` | 1h |
| T7.3 | Implement correlation multiplier | `core/risk_engine.py` | 1h |
| T7.4 | Implement `Aggregator.aggregate_signals()` with weight renormalization + 0.30 coverage floor | `core/aggregator.py` | 2h |
| T7.5 | Implement `Aggregator.determine_action()` with regime-adjusted thresholds | `core/aggregator.py` | 1h |
| T7.6 | Implement `Aggregator.size_quantity()` | `core/aggregator.py` | 1h |
| T7.7 | Wire `RiskEngine` + `Aggregator` into `WriteEngine.run()` with `ThreadPoolExecutor(max_workers=4)` for engine compute | `core/write_engine.py` | 2h |
| T7.8 | Implement `ResultStore.save_decision()` | `core/result_store.py` | 1h |
| T7.9 | End-to-end test: full run on 3 tickers → verify decision in MongoDB | `tests/integration/test_full_pipeline.py` | 2h |
| T7.10 | Write unit tests for risk engine (known vol inputs) | `tests/unit/test_risk_engine.py` | 1.5h |
| T7.11 | Write unit tests for aggregator (renormalization + regime thresholds) | `tests/unit/test_aggregator.py` | 1h |

**Phase 7 Total Estimate:** ~16.5 hours

---

## Phase 8 — Backtesting Framework

**Goal:** Implement `BacktestFramework` that runs the full Write Engine stack over a historical date range. Results stored in MongoDB. Performance metrics computed and stored.

**Delivers:** `python engine.py --tickers AAPL MSFT --backtest --start 2022-01-01 --end 2024-12-31` runs and stores results.

---

### User Stories

#### US-8.1 — Historical Date Iteration
**As a** quant researcher,
**I want** to run the full engine stack across each trading day in a date range,
**So that** I can measure historical strategy performance.

**Acceptance Criteria:**
- [ ] Trading calendar generated for US (252 days/yr) or India (250 days/yr)
- [ ] Each date: `WriteEngine.run(as_of_date=date)` called — identical to live mode
- [ ] All data fetched during backtest stored with `is_historical=True` — never auto-deleted by cleanup job
- [ ] No data beyond `as_of_date` accessible (enforced by DataBus)
- [ ] `KeyboardInterrupt` handled gracefully — partial results saved and shown
- [ ] Progress displayed: "Day 45 of 252 | 2022-02-15 | portfolio: $104,200"
- [ ] `BacktestConfig` has no `rebalance_freq` field — all backtests run daily (v1)

#### US-8.2 — Simulated Trade Execution
**As a** backtesting user,
**I want** decisions executed against a simulated portfolio,
**So that** I see realistic P&L accounting.

**Acceptance Criteria:**
- [ ] Buy: cash -= qty × close_price; long_shares += qty
- [ ] Sell: cash += qty × close_price; long_shares -= qty; record P&L
- [ ] Short: cash -= qty × price × margin_req; short_shares += qty
- [ ] Cover: return margin; record P&L
- [ ] Hold: no change
- [ ] Commission and slippage from `BacktestConfig` applied to each trade

#### US-8.3 — Performance Metrics
**As a** quant researcher,
**I want** a comprehensive performance report after each backtest,
**So that** I can compare strategy variants objectively.

**Acceptance Criteria:**
- [ ] Computes: Total Return, Annualized Return, Alpha vs. benchmark, Max Drawdown, Sharpe Ratio, Sortino Ratio, Calmar Ratio, Win Rate, Avg Win, Avg Loss, Profit Factor, Total Trades
- [ ] Monthly returns breakdown
- [ ] All metrics stored in `hf_ai_engine.backtest_results`
- [ ] CLI displays formatted summary table after run

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T8.1 | Implement trading calendar generator (US + India) | `core/backtest.py` | 1.5h |
| T8.2 | Implement `BacktestFramework.run()` date iteration loop | `core/backtest.py` | 2h |
| T8.3 | Implement simulated trade execution for all 5 actions | `core/backtest.py` | 2h |
| T8.4 | Implement mark-to-market portfolio valuation | `core/backtest.py` | 1h |
| T8.5 | Implement all performance metric calculations | `core/backtest.py` | 3h |
| T8.6 | Implement `ResultStore.save_backtest()` | `core/result_store.py` | 1h |
| T8.7 | Add `--backtest` CLI flag and `BacktestConfig` (no rebalance_freq; daily only) | `engine.py` | 1h |
| T8.8 | Add benchmark comparison (fetch benchmark prices) | `core/backtest.py` | 1h |
| T8.9 | Run 1-year backtest on AAPL + MSFT; verify metrics in MongoDB | `tests/integration/` | 2h |
| T8.10 | Write unit tests for P&L calculation and metrics | `tests/unit/test_backtest.py` | 2h |

**Phase 8 Total Estimate:** ~17 hours

---

## Phase 9 — India Data Layer

**Goal:** Add full India market support via `data/fetcher_india.py`. Plug India-specific signals into the existing engine stack. All India data stored in the same `hf_ai_engine` MongoDB.

**Delivers:** `python engine.py --tickers TCS.NS RELIANCE.NS --show-signals` runs with India data.

---

### User Stories

#### US-9.1 — India OHLCV + Fundamentals
**As a** trader,
**I want** Indian stock data fetched from `yfinance` using the `.NS` suffix,
**So that** NSE-listed stocks work with all the same signal engines.

**Acceptance Criteria:**
- [ ] `fetcher_india.py` wraps yfinance with `.NS` / `.BO` suffix handling
- [ ] Prices stored in `hf_ai_engine.prices_in`
- [ ] Financials stored in `hf_ai_engine.financials` (same collection, `market: "IN"` field)
- [ ] `screener.in` HTML scraper as fallback for 10-yr financial history
- [ ] Graceful degradation: if screener.in unavailable, use yfinance only

#### US-9.2 — India-Exclusive Signals: FII/DII + Promoter + Bulk Deals
**As a** trader,
**I want** India-specific institutional signals available as engine data,
**So that** the engine reflects institutional flows that have no US equivalent.

**Acceptance Criteria:**
- [ ] `FIIDIIFetcher` fetches NSE daily CSV; stores in `hf_ai_engine.fii_dii_daily`
- [ ] `PromoterHoldingFetcher` parses NSE/BSE quarterly disclosure; stores in `hf_ai_engine.promoter_holdings`
- [ ] `BulkDealFetcher` fetches NSE daily bulk deal CSV; stores in `hf_ai_engine.bulk_deals`
- [ ] `InsiderSentimentEngine` routes to promoter holding path when `market == "IN"`
- [ ] `InstitutionalFlowEngine` routes to FII/DII + bulk deal path when `market == "IN"`

#### US-9.3 — India Macro
**As a** trader,
**I want** India-specific macro signals (RBI Repo Rate, India VIX, INR/USD, FII net 5-day),
**So that** the macro regime correctly reflects Indian market conditions.

**Acceptance Criteria:**
- [ ] `MacroContextEngine` routes to India macro path when `market == "IN"`
- [ ] Fetches: `INDIAVIX.NS`, `^NSEI` vs 200 MA, `USDINR=X` 30d change, FII net 5-day (from stored data)
- [ ] RBI Repo Rate fetched from RBI website (monthly scrape)
- [ ] India macro stored in `hf_ai_engine.macro_in`

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T9.1 | Implement `IndiaFetcher` wrapping yfinance `.NS` | `data/fetcher_india.py` | 2h |
| T9.2 | Implement `screener.in` HTML scraper for 10yr financials | `data/fetcher_india.py` | 3h |
| T9.3 | Implement `FIIDIIFetcher` from NSE website | `data/fetcher_india.py` | 2h |
| T9.4 | Implement `PromoterHoldingFetcher` from NSE/BSE filings | `data/fetcher_india.py` | 2h |
| T9.5 | Implement `BulkDealFetcher` from NSE daily CSV | `data/fetcher_india.py` | 1.5h |
| T9.6 | Update `InsiderSentimentEngine` for India path (promoter) | `signals/insider_sentiment.py` | 1h |
| T9.7 | Update `InstitutionalFlowEngine` India path: FII/DII daily + bulk deals + best-effort FII sector breakdown | `signals/institutional_flow.py` | 2h |
| T9.8 | Implement India macro fetcher (India VIX + USDINR + RBI) | `data/fetcher_india.py` | 2h |
| T9.9 | Update `MacroContextEngine` for India path | `signals/macro_context.py` | 1h |
| T9.10 | Add India news RSS feeds to `NewsScraperModule` | `news/sources.py` | 0.5h |
| T9.11 | Add India analyst rating fallback: try screener.in if yfinance empty | `news/sentiment.py` | 1h |
| T9.12 | Integration test: full run on TCS.NS, RELIANCE.NS, INFY.NS | `tests/integration/test_india_pipeline.py` | 2h |
| T9.13 | Test cross-market portfolio: AAPL + TCS.NS in one run | `tests/integration/` | 1h |

**Phase 9 Total Estimate:** ~21 hours

---

## Phase 10 — Monitoring, CLI & Production Polish

**Goal:** Complete the CLI interface, implement health monitoring queries, add structured logging, and ensure the system is production-ready.

**Delivers:** Full CLI with all flags. Health check command. Structured logs. System ready for daily scheduled use.

---

### User Stories

#### US-10.1 — Full CLI Interface
**As a** user,
**I want** to run the engine with a single command and intuitive flags,
**So that** I can analyze stocks without understanding the internals.

**Acceptance Criteria:**
- [ ] `python engine.py --tickers AAPL MSFT TCS.NS` runs full analysis
- [ ] `--backtest --start 2023-01-01 --end 2024-12-31` runs backtest
- [ ] `--show-signals` prints per-engine breakdown for each ticker
- [ ] `--engines technical fundamental valuation` runs only specified engines
- [ ] `--no-news` skips news scraper
- [ ] `--refresh` bypasses MongoDB cache, forces live fetch
- [ ] `--dry-run` validates config and connection without running engines
- [ ] `--health` prints health report from MongoDB
- [ ] `--output results.json` saves decisions to JSON file
- [ ] `--explain` triggers Ollama narrative (if enabled in config)
- [ ] Colored terminal output: green=bullish, red=bearish, yellow=neutral

#### US-10.2 — Health Check Command
**As a** system operator,
**I want** a single command to see the health of all data sources and recent runs,
**So that** I can diagnose issues without digging into MongoDB manually.

**Acceptance Criteria:**
- [ ] `python engine.py --health` prints: last run status, data freshness per type, engine count, MongoDB connection status
- [ ] Shows "STALE" warning if any data type exceeds TTL
- [ ] Shows "FAIL" if last run errored
- [ ] Shows signal distribution for last 7 days per engine

#### US-10.3 — Structured Logging
**As a** developer,
**I want** all engine events logged with consistent structure,
**So that** I can filter logs by run_id, engine name, or severity.

**Acceptance Criteria:**
- [ ] All log lines include: `timestamp`, `level`, `run_id`, `ticker`, `engine`, `message`
- [ ] Log level configurable in `config/engine.yaml`
- [ ] Logs written to file (`logs/engine.log`) and stdout
- [ ] Errors always include full stack trace
- [ ] No print() statements in production code — only logger calls

#### US-10.4 — Scheduled Daily Run
**As a** trader,
**I want** the engine to run automatically every day at market close,
**So that** I have fresh signals ready when I review positions in the evening.

**Acceptance Criteria:**
- [ ] `python engine.py --schedule "0 18 * * 1-5"` schedules daily runs (cron syntax)
- [ ] Runs at 6 PM local time Mon–Fri
- [ ] Results stored to MongoDB automatically
- [ ] Run history viewable via `--history 7` (last 7 runs)

#### US-10.5 — Portfolio Analytics
**As a** portfolio manager,
**I want** a breakdown of sector exposure, factor attribution, correlation, and drawdown after a backtest,
**So that** I can understand portfolio risk composition at a glance.

**Acceptance Criteria:**
- [ ] `analytics.py` exposes pure functions: `sector_exposure()`, `correlation_matrix()`, `factor_attribution()`, `drawdown_series()`, `monthly_returns_heatmap()`
- [ ] `sector_exposure()` uses yfinance sector tag per ticker; flags any sector > 40%
- [ ] `correlation_matrix()` uses 60-day % returns; flags any pair > 0.80
- [ ] `factor_attribution()` runs OLS regression: beta, value tilt (avg P/B rank), momentum (6m return), quality (avg ROE rank)
- [ ] `drawdown_series()` returns `[{date, drawdown_pct}]` + max_drawdown + recovery_days
- [ ] All functions are pure (input → output); no MongoDB writes
- [ ] Displayed via `--show-analytics` CLI flag after a backtest run

---

### Tasks

| # | Task | File | Estimate |
|---|---|---|---|
| T10.1 | Implement full `argparse` CLI with all flags | `engine.py` | 2h |
| T10.2 | Implement colored table output (tabulate + colorama) | `engine.py` | 1.5h |
| T10.3 | Implement `--show-signals` detailed breakdown display | `engine.py` | 1.5h |
| T10.4 | Implement `--health` command querying MongoDB | `engine.py` | 2h |
| T10.5 | Implement `HealthMetrics` class for MongoDB queries | `core/monitor.py` | 2h |
| T10.6 | Implement structured logging with run_id context | `core/monitor.py` | 1.5h |
| T10.7 | Implement `--schedule` with `schedule` Python package | `engine.py` | 1.5h |
| T10.8 | Implement `--history N` to display last N run summaries | `engine.py` | 1h |
| T10.9 | Implement `ResultStore.save_signal()` and `save_decision()` | `core/result_store.py` | 1h |
| T10.10 | Implement `narrator.py`: 10s timeout, returns None if Ollama unreachable, synchronous, never blocks decision | `narrator.py` | 1.5h |
| T10.11 | Implement `analytics.py`: sector_exposure, correlation_matrix, factor_attribution, drawdown_series, monthly_returns_heatmap | `analytics.py` | 3h |
| T10.12 | Add `--show-analytics` CLI flag; display analytics after backtest | `engine.py` | 1h |
| T10.13 | Replace all print() with logger calls across codebase | all files | 1h |
| T10.14 | Full end-to-end production test: 5 US + 3 India tickers | `tests/integration/test_full_pipeline.py` | 2h |
| T10.15 | Write setup/installation instructions in README | `README.md` | 1h |

**Phase 10 Total Estimate:** ~22 hours

---

## Summary

| Phase | Name | Est. Hours | Key Output |
|---|---|---|---|
| 1 | Core Engine Scaffold | 16.5h | Write Engine + MongoDB + Config + pyproject.toml |
| 2 | Data Layer — US | 22h | DataBus + full US data + filing text + is_historical TTL |
| 3 | Quantitative Signal Engines | 20.5h | Technical, Fundamental, Valuation (6 models), Earnings Quality |
| 4 | News Scraper & Sentiment | 21h | FinBERT 4-source + India analyst fallback |
| 5 | Investor Screens | 18h | All 13 screens + TF-IDF moat scoring + moat_idf.json |
| 6 | Macro & Institutional | 17.5h | Macro regime + dark pool (US only) |
| 7 | Risk Engine & Aggregator | 16.5h | Parallel compute + renormalization + full decision pipeline |
| 8 | Backtesting Framework | 17h | Full backtest, daily-only, is_historical flag |
| 9 | India Data Layer | 21h | Full India market + institutional flow + analyst fallback |
| 10 | Monitoring, CLI & Polish | 22h | Analytics + narrator spec + production CLI |
| **Total** | | **~192 hours** | **Full dual-market engine at 93%** |

At 4 productive hours/day with Claude: **~48 calendar days** (~10 weeks)
At 6 productive hours/day: **~32 calendar days** (~6.5 weeks)

---

*Phases v1.0 — 2026-06-01*
