HF-AI Engine — Complete Architecture Review
Version 2.0   |   Date: 2026-06-02   |   Status: Authoritative

This document supersedes ARCHITECTURE.md as the definitive architecture reference.
All gaps found across REQUIREMENTS, ARCHITECTURE, PHASES, and DB_SCHEMA are
resolved here. This is the single source of truth before coding begins.

================================================================================
PART 1 — GAP ANALYSIS
================================================================================

18 gaps were found across the four existing documents. Each is stated and
resolved below.

--------------------------------------------------------------------------------
GAP 1   DataBundle missing India-specific fields
--------------------------------------------------------------------------------

FOUND IN: ARCHITECTURE.md DataBundle definition
PROBLEM:  DataBundle has inst_flow: dict and insider_data: list[dict] but
          has no separate fields for bulk_deals, promoter_holdings, or
          fii_dii_flow — all required by India signal engines.

RESOLUTION: Expand DataBundle with explicit India fields. India-specific
            fields are None for US tickers; US engines never read them.

FINAL DataBundle fields:
  ticker              str
  market              str             "US" or "IN"
  as_of_date          str             YYYY-MM-DD
  prices              list[dict]      OHLCV, 2 years
  financials          list[dict]      all periods, 10yr annual + TTM
  ratios              dict            latest ratios
  news_items          list[dict]      scraped headlines, FinBERT-scored
  filing_text         str             10-K text (US) or annual report (India)
  mda_text            str             latest 8-K MD&A (US) or quarterly filing
  insider_trades      list[dict]      SEC Form 4 open-market trades (US only)
  promoter_holdings   list[dict]      SEBI quarterly promoter data (India only)
  inst_flow_us        dict            13F net flow, FINRA SI, CBOE P/C, dark pool
  inst_flow_india     dict            FII/DII daily, FII sector breakdown, bulk deals
  bulk_deals          list[dict]      NSE bulk/block deals (India only)
  macro               dict            VIX, rates, sector ETFs, regime
  market_config       dict            MarketConfig serialized to dict

--------------------------------------------------------------------------------
GAP 2   Sector Median P/E (6th valuation model) — no fetch mechanism
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 10 (added in refinement)
PROBLEM:  "compare ticker P/E vs median P/E of its sector ETF constituents"
          requires fetching P/E for dozens of ETF constituent stocks — slow,
          expensive API calls, fragile.

RESOLUTION: Use the sector ETF's own trailing P/E from yfinance as the
            sector P/E proxy. It is already computed and available via
            yfinance.Ticker(etf_ticker).info['trailingPE']. This is a sound
            approximation (ETF P/E tracks constituent median P/E closely).
            No new collection or fetch job needed. Cached with ratios TTL (24h).

UPDATED REQUIREMENT: Sector Median P/E = sector ETF trailing P/E from yfinance
(e.g., XLK for tech, NIFTYIT.NS for India tech). Skip and reweight if
trailingPE is not available for the ETF.

--------------------------------------------------------------------------------
GAP 3   moat_idf.json — referenced but never defined
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 16 (TF-IDF moat scoring)
PROBLEM:  File config/moat_idf.json is referenced but: its format is not
          defined, how it was generated is not documented, and it does not
          appear in any file structure.

RESOLUTION:
  - Format: JSON object mapping keyword string to IDF weight (float)
    Example: {"switching cost": 2.31, "proprietary": 1.84, "patent": 1.62}
  - Source: Pre-computed once from a corpus of 100 S&P 500 and Nifty 500
    annual reports. Script: scripts/build_moat_idf.py (one-time utility).
  - Shipped with the project as a static file — not regenerated at runtime.
  - Location: config/moat_idf.json
  - Updated: Annually by running the build script.
  - If file missing at startup: fall back to unweighted keyword count and
    log a WARN. Do not crash.

--------------------------------------------------------------------------------
GAP 4   MD&A text fetch — no task in Phase 2, filing_text has no fetcher
--------------------------------------------------------------------------------

FOUND IN: PHASES.md Phase 2 (no filing_text fetch task)
PROBLEM:  DataBundle has filing_text and mda_text fields. REQUIREMENTS.md
          references them in news sentiment (Source 2 — earnings call MD&A)
          and moat text mining (investor screens). But Phase 2 has no task
          to fetch these, and fetcher_us.py spec never mentions 8-K parsing.

RESOLUTION:
  US path:
    - filing_text: SEC EDGAR full-text search API — latest 10-K for the ticker
      URL: https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom
      Parse the Business Description + Risk Factors sections only (~5,000 words)
    - mda_text: SEC EDGAR EDGAR full-text — latest 8-K item 2.02 (earnings results)
      URL: https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=8-K
      Parse Item 2.02 section
    - Both: TTL 90 days; stored in collection filing_texts (new collection)

  India path:
    - filing_text: BSE corporate filings API — annual report PDF link
      Parse first 3,000 words as proxy for MD&A (PDF-to-text via pdfplumber)
    - mda_text: BSE quarterly results filing — Management Discussion section
    - Fallback: If PDF parsing fails, set field to empty string; engines skip.

  New Phase 2 task: T2.13 — Implement SEC EDGAR 10-K + 8-K text fetcher (2h)
  New DB collection: filing_texts (see Gap 12 / DB section)

--------------------------------------------------------------------------------
GAP 5   FINRA dark pool — URL and format not specified
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 15, PHASES.md Phase 6
PROBLEM:  Dark pool detection added as a signal but the data source is not
          actionable — no URL, no format, no update frequency.

RESOLUTION:
  FINRA ATS (Alternative Trading System) data — free, weekly:
    URL: https://otctransparency.finra.org/otctransparency/AtsIssueData
    Format: CSV download, columns include Symbol, ATS shares, date range
    Update frequency: Weekly (published each Friday for the prior week)
    Metric: dark_pool_pct = ATS_shares / (ATS_shares + exchange_shares)
    Source: FINRA also publishes exchange volume via the same portal

  Signal rule (unchanged from requirements):
    dark_pool_pct > 0.45 AND price rising over same period → confidence +10
    dark_pool_pct falling sharply (>10% drop) with price → distribution warning

  Caching: Store in collection dark_pool_us; TTL 7 days (weekly data)

--------------------------------------------------------------------------------
GAP 6   FII sector-wise breakdown — NSE endpoint not specified
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 15 (India path)
PROBLEM:  "NSE monthly FII sector breakdown" added to India institutional
          flow but the NSE endpoint is not specified and changes periodically.

RESOLUTION:
  NSE FII sector breakdown is published monthly in a PDF/Excel on the NSE
  website (not a stable API). Given the unstable URL, this signal is
  DEPRIORITIZED to a best-effort fetch:
    - Attempt to scrape from NSE FII/FPI statistics page monthly
    - If unavailable, skip sector divergence check without error
    - Do not block the engine on this signal
    - Implement as optional enhancement in Phase 9 (T9.12)

  The core FII/DII daily signal (ticker-level) remains fully specified and
  is the primary India institutional signal. Sector breakdown is a bonus.

--------------------------------------------------------------------------------
GAP 7   analytics.py — no specification
--------------------------------------------------------------------------------

FOUND IN: File structure in REQUIREMENTS.md and ARCHITECTURE.md
PROBLEM:  analytics.py is listed as a file but has no section in any doc.
          REQUIREMENTS.md Section 21 shows only a terminal display example
          without specifying what analytics.py computes or stores.

RESOLUTION — Full analytics.py specification:

  Input: backtest_results collection from MongoDB (or live portfolio state)
  Output: Structured dict returned to CLI for display; optionally saved to DB

  Functions:
    sector_exposure(portfolio, prices)
      Returns: dict of sector → % of total portfolio value
      Source:  yfinance sector tag per ticker; cached in ratios collection

    correlation_matrix(portfolio, prices, lookback_days=60)
      Returns: NxN matrix of % return correlations
      Flags: any pair with correlation > 0.80

    factor_attribution(portfolio, prices, benchmark_ticker)
      Returns: market_beta, value_tilt, momentum, quality scores
      Method:  OLS regression of portfolio daily returns on factor returns
               (beta vs benchmark; value = avg P/B rank; momentum = 6m return)

    drawdown_series(history)
      Returns: list of {date, drawdown_pct} for the full backtest period
      Includes: max_drawdown, recovery_days

    monthly_returns_heatmap(history)
      Returns: dict of {year: {month: return_pct}} for terminal display

  All functions are pure (input → output); no MongoDB writes from analytics.py.
  CLI calls analytics.py after a backtest run if --show-analytics flag is set.

--------------------------------------------------------------------------------
GAP 8   Weight renormalization when engines skip
--------------------------------------------------------------------------------

FOUND IN: ARCHITECTURE.md Aggregator, REQUIREMENTS.md Section 19
PROBLEM:  When validate_data() returns False for some engines, their weights
          are excluded but the remaining weights no longer sum to 1.0.
          The net_score formula divides by total_weight but this is not
          explicitly stated in the aggregation spec.

RESOLUTION — Explicit renormalization rule:

  active_signals = {name: sig for name, sig in signals.items()
                    if sig is not None}
  total_weight   = sum(s.weight for s in active_signals.values())

  If total_weight < 0.30:
    Return HOLD with confidence 0 and reasoning "Insufficient signal coverage"
    Log WARN to audit_log

  net_score = (bullish_weight - bearish_weight) / total_weight

  Minimum coverage threshold (0.30) ensures at least 30% of weights are
  present before a decision is made. This prevents spurious signals when
  most data is unavailable.

--------------------------------------------------------------------------------
GAP 9   Backtest TTL conflict — historical data must not expire
--------------------------------------------------------------------------------

FOUND IN: DB_SCHEMA.md (all TTL indexes), PHASES.md Phase 8
PROBLEM:  MongoDB TTL indexes delete documents based on fetched_at age.
          During a backtest, historical data (e.g., 2022 prices fetched today)
          would be deleted after 6 hours, forcing re-fetch on every run.
          This defeats the caching purpose for backtesting.

RESOLUTION:
  Add is_historical: bool field to all cached data documents.
  TTL index only applies when is_historical = false.

  Implementation: Replace TTL indexes with a scheduled cleanup job:
    - Documents with is_historical=false and fetched_at older than TTL → delete
    - Documents with is_historical=true → never deleted automatically
    - Cleanup runs on engine startup and after each live (non-backtest) run
    - Manual cleanup: python engine.py --purge-cache

  The TTL indexes in DB_SCHEMA.md are removed. Replaced by:
    db.prices_us.createIndex({"fetched_at": 1, "is_historical": 1})
  And a cleanup query run at startup:
    db.prices_us.deleteMany({"is_historical": false,
                              "fetched_at": {$lt: now - TTL_SECONDS}})

--------------------------------------------------------------------------------
GAP 10   Phase sequencing — India in Phase 6 conflicts with Phase 9
--------------------------------------------------------------------------------

FOUND IN: PHASES.md Phase 6 task T6.7c
PROBLEM:  Phase 6 adds T6.7c "FII sector breakdown for India" but the
          India data fetchers (fetcher_india.py, NSE scrapers) are built
          in Phase 9. Phase 6 cannot implement India paths without Phase 9.

RESOLUTION:
  Phase 6 = US only. Remove T6.7c from Phase 6.
  India institutional flow (FII/DII engine, bulk deals, FII sector breakdown)
  moves entirely to Phase 9 as originally intended.

  Phase 6 US-6.2 acceptance criteria: remove all India path bullets.
  Phase 9 adds India path to InstitutionalFlowEngine (routing via market_config).

--------------------------------------------------------------------------------
GAP 11   MarketConfig dual definition
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 5 (Python dataclass) vs
          ARCHITECTURE.md Section 8 (engine.yaml markets section)
PROBLEM:  MarketConfig is defined as a Python dataclass in REQUIREMENTS.md
          with hardcoded values. ARCHITECTURE.md puts market config in YAML.
          These are two representations of the same thing and can conflict.

RESOLUTION — Single-source rule:
  YAML is the source of values (configurable without code change).
  Python dataclass loads from YAML at startup.

  data/market_config.py contains:
    - MarketConfig dataclass definition (fields only, no hardcoded values)
    - get_market_config(ticker) function that reads from ConfigManager
    - US_CONFIG and INDIA_CONFIG are module-level singletons, loaded at import

  config/engine.yaml contains the actual threshold values under markets: section.
  config/us_thresholds.yaml and config/india_thresholds.yaml contain
  screen-specific thresholds (too many for engine.yaml).

  The Python dataclass in REQUIREMENTS.md Section 5 is kept as documentation
  of the field structure; actual values come from YAML.

--------------------------------------------------------------------------------
GAP 12   config/moat_idf.json absent from file structures
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md (references it), ARCHITECTURE.md file tree
PROBLEM:  The file is referenced but does not appear in the file structure
          in either REQUIREMENTS.md or ARCHITECTURE.md.

RESOLUTION: Add to config/ directory in the file structure (see Part 3).
  Also add scripts/build_moat_idf.py as a one-time utility script.

--------------------------------------------------------------------------------
GAP 13   tests/ directory never structured
--------------------------------------------------------------------------------

FOUND IN: All phases reference tests/ but no structure is defined
PROBLEM:  No test directory structure, no conftest.py spec, no fixtures,
          no separation between unit and integration tests.

RESOLUTION — Final tests/ structure:

  tests/
    conftest.py              shared fixtures: synthetic prices, financials, ratios
    fixtures/
      sample_prices.json     60 days of OHLCV data for AAPL
      sample_financials.json 5 years of annual financials
      sample_ratios.json     latest ratios
    unit/
      test_technical.py
      test_fundamental.py
      test_valuation.py
      test_earnings_quality.py
      test_insider.py
      test_news.py
      test_macro.py
      test_institutional.py
      test_screens.py        tests for all 13 screens
      test_risk_engine.py
      test_aggregator.py
      test_backtest.py
      test_data_bus.py
    integration/
      test_full_pipeline.py  end-to-end: fetch → signal → decision
      test_no_lookahead.py   backtesting data isolation test
      test_india_pipeline.py India-specific end-to-end

  Rule: Unit tests use synthetic data from fixtures/ only (no network calls).
        Integration tests may call live APIs but are marked @pytest.mark.slow
        and skipped in CI by default.

--------------------------------------------------------------------------------
GAP 14   Analyst ratings fallback for India tickers
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 13 (News Sentiment Source 3)
PROBLEM:  yfinance.upgrades_downgrades is often empty for Indian stocks.
          No fallback is specified.

RESOLUTION:
  India fallback for analyst ratings (in order of preference):
    1. yfinance upgrades_downgrades — try first
    2. NSE analyst consensus from screener.in company page (scrape "Analyst
       Recommendations" section if present)
    3. If both unavailable: analyst_score = None → weight redistributed
       to other 3 sources proportionally

  This is handled inside AnalystRatingScorer.score() with a market routing check.

--------------------------------------------------------------------------------
GAP 15   pyproject.toml missing dependencies
--------------------------------------------------------------------------------

FOUND IN: REQUIREMENTS.md Section 25 (Technical Stack)
PROBLEM:  pymongo, schedule, watchdog not listed. watchdog is needed for
          config hot-reload (ARCHITECTURE.md uses os.path.getmtime polling
          which is not robust on all platforms).

RESOLUTION — Final complete dependency list (see Part 3 Technical Stack).
  watchdog replaces the polling loop for config hot-reload.
  pymongo added to core dependencies.
  schedule added to core (used by --schedule CLI flag).

--------------------------------------------------------------------------------
GAP 16   narrator.py has no spec
--------------------------------------------------------------------------------

FOUND IN: File structure references; REQUIREMENTS.md Section 22 (brief)
PROBLEM:  narrator.py is listed but its behavior when Ollama is unavailable,
          its timeout, and its async/sync mode are never specified.

RESOLUTION — narrator.py full specification:
  Function: generate_narrative(decision, signals, config) -> str | None
  Behavior:
    - If config.ollama.enabled = false: return None immediately (no attempt)
    - If Ollama server unreachable: log WARN, return None (do not crash engine)
    - Timeout: 10 seconds. If exceeded: return None with WARN log.
    - Execution: Synchronous (blocking). The narrative is cosmetic and runs
      after the decision is finalized. The engine result is complete before
      narrator runs; a slow Ollama does not delay the decision.
    - The narrative is appended to TradingDecision.narrative field.
    - Prompt: fixed template (REQUIREMENTS.md Section 22). No dynamic prompting.

--------------------------------------------------------------------------------
GAP 17   Engine compute parallelism not specified
--------------------------------------------------------------------------------

FOUND IN: ARCHITECTURE.md (prefetch is parallel; compute loop is sequential)
PROBLEM:  The WriteEngine.run() loop iterates engines sequentially per ticker.
          With 21 engines × 5 tickers = 105 compute calls, sequential takes
          ~10-20s (mostly CPU). Parallelism would cut this to ~2-3s.

RESOLUTION:
  Two levels of parallelism:
    Level 1 — Data prefetch: ThreadPoolExecutor(max_workers=8)
              Fetch all tickers in parallel (IO-bound, benefits greatly)
    Level 2 — Engine compute: ThreadPoolExecutor(max_workers=4)
              Run all engines for a single ticker in parallel (CPU-bound,
              constrained to 4 workers to avoid GIL contention)

  Constraint: Engines MUST remain pure functions with no shared state.
              Any engine that mutates class state is not thread-safe.
              initialize() is called sequentially at startup (not in threads).

  Implementation in WriteEngine.run():
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(engine.compute, data): engine
                   for engine in active_engines
                   if engine.validate_data(data)}
        for future in as_completed(futures):
            signal = future.result()
            signals[engine.name] = signal

--------------------------------------------------------------------------------
GAP 18   BacktestConfig.rebalance_freq — weekly/monthly never implemented
--------------------------------------------------------------------------------

FOUND IN: ARCHITECTURE.md Section 7.1, PHASES.md Phase 8
PROBLEM:  BacktestConfig has rebalance_freq: "daily" | "weekly" | "monthly"
          but the backtest loop always runs daily and there is no logic
          for weekly/monthly rebalancing.

RESOLUTION — Simplify for v1:
  rebalance_freq is removed from BacktestConfig for v1.
  All backtests run daily (one signal computation per trading day).
  Weekly/monthly rebalancing is a v2 feature.
  Removing it prevents a half-implemented feature being silently wrong.

================================================================================
PART 2 — RESOLVED ARCHITECTURE DECISIONS
================================================================================

The following table summarizes every major architectural decision, why it
was made, and what it replaces or resolves.

DECISION                  CHOICE                     REASON
------------------------- -------------------------- --------------------------
LLM for core signals      No LLM                     Deterministic + $0 cost
LLM for news sentiment    FinBERT (local)            Domain-trained, free, fast
LLM for narrative         Ollama (optional)          Post-decision only, $0
Signal architecture       Plugin pattern             Add engine = 1 file
Data access               DataBus (3-layer cache)    No engine touches DB
Orchestration             ThreadPoolExecutor          No LangGraph needed
Config management         YAML + watchdog hot-reload Single source of values
MarketConfig source       YAML loaded into dataclass YAML configurable, Python typed
Database                  MongoDB hf_ai_engine only  Isolated, document store
TTL strategy              Scheduled cleanup job      Supports historical backtest
Signal weighting          Renormalize on skip        Always valid net_score
Sector P/E proxy          ETF trailing P/E (yfinance) Simple, cached, sufficient
Moat scoring              TF-IDF with static IDF file Ships with project
India FII sector           Best-effort, non-blocking  Unstable NSE endpoint
Backtest rebalance_freq   Daily only (v1)            Avoid half-implementation
Engine compute threads    4 workers per ticker        CPU-bound, GIL-aware
Narrator error handling   Return None on any failure Never blocks decision
Filing text source (US)   SEC EDGAR 10-K + 8-K       Free, structured, XBRL
Filing text source (India) BSE PDF + pdfplumber       No XBRL; PDF fallback

================================================================================
PART 3 — COMPLETE SYSTEM ARCHITECTURE
================================================================================

3.1  THREE-TIER OVERVIEW
--------------------------

TIER 1  DATA LAYER
  Input: ticker + as_of_date + MarketConfig
  US:    yfinance, SEC EDGAR, FINRA, CBOE, FRED API, Google News RSS
  India: yfinance (.NS/.BO), screener.in, NSE portal, RBI, ET/MC/BS RSS
  Cache: MongoDB hf_ai_engine (3-layer: in-memory, MongoDB, live API)

TIER 2  SIGNAL LAYER  (21 engines, pure functions, parallelizable)
  Technical        EMA/RSI/MACD/Bollinger/ADX/Hurst/OBV/VWAP/MFI, 3 timeframes
  Fundamental      12 ratio checks + Piotroski F-Score
  Valuation        6 models: 3-stage DCF, Owner Earnings DCF, EV/EBITDA,
                   P/E relative (5yr avg), Graham Number, Sector ETF P/E
  Earnings Quality Beneish M-Score + Altman Z-Score + Piotroski (from fundamental)
  Insider          SEC Form 4 weighted ratio (US) / Promoter holding delta (India)
  News Sentiment   FinBERT 4-source: headlines 25% + MD&A 30% + analyst 25% + options 20%
  Macro Context    VIX + yield curve + sector ETF rotation + FII 5d (India)
                   ROLE: multiplier on all signals, not a vote
  Institutional    13F + FINRA SI + CBOE P/C + dark pool (US)
                   FII/DII daily + bulk deals (India)
  13 Screens       Buffett, Graham, Lynch, Fisher, Munger, Burry, Ackman, Wood,
                   Druckenmiller, Taleb, Damodaran, Pabrai, Jhunjhunwala
                   Each: TF-IDF moat scoring + 10yr consistency + management quality

TIER 3  DECISION LAYER
  Risk Engine      60d rolling vol → position limit tier → correlation multiplier
  Aggregator       Renormalized weighted vote → macro regime multiplier → action
  Decision         TradingDecision{action, quantity, confidence, signals, narrative}


3.2  EXECUTION FLOW
--------------------

  config   = ConfigManager("config/engine.yaml")
  registry = EngineRegistry()
  registry.discover("signals")         # auto-loads all 21 engines

  For each run:
    run_id = monitor.start_run(tickers, as_of_date)

    Step 1: DataBus.prefetch(tickers)  [parallel, 8 workers, IO-bound]
      For each ticker: mem_cache → MongoDB → live API

    Step 2: For each ticker:
      data = DataBus.fetch(ticker, as_of_date)

      Step 2a: Engine compute  [parallel, 4 workers per ticker, CPU-bound]
        For each active engine:
          if engine.validate_data(data):
            signal = engine.compute(data)   # pure function, no side effects

      Step 2b: Renormalize weights for skipped engines

      Step 2c: MacroContextEngine returns MacroRegime (multiplier, not vote)
               Apply multiplier to all bullish confidences if regime = bearish

      Step 2d: RiskEngine.compute(data.prices, portfolio)
               → max_buy_shares, max_sell_shares, vol_tier, correlation_multiplier

      Step 2e: Aggregator.decide(signals, macro_regime, risk)
               → net_score → action → quantity → TradingDecision

      Step 2f: ResultStore.save(run_id, ticker, signals, decision)

    Step 3: monitor.end_run(run_id, status="success")

    Step 4 (optional): narrator.generate(decision) if --explain


3.3  SIGNAL WEIGHTS (final)
----------------------------

  Engine                Weight    Notes
  -------------------   ------    ------------------------------------------
  technical             0.20      Multi-timeframe consensus
  fundamental           0.15      Quality filter
  valuation             0.15      Value anchor
  earnings_quality      0.10      Manipulation / distress filter
  insider_sentiment     0.10      Smart money; excludes auto trades
  news_sentiment        0.10      4-source FinBERT composite
  institutional_flow    0.10      13F + dark pool / FII+bulk deals
  13 screens (avg)      0.20      0.20 / 13 = 0.01538 each
  macro_context         N/A       Multiplier only: bearish x0.80, bullish x1.10
  TOTAL                 1.00


3.4  SIGNAL AGGREGATION RULES (final)
---------------------------------------

  1. Collect all signals where validate_data() returned True
  2. If total_weight < 0.30: return HOLD, confidence=0 (insufficient coverage)
  3. Apply macro multiplier: if regime=bearish, bullish confidences x0.80
  4. net_score = (sum of bullish weights - sum of bearish weights) / total_weight
  5. Thresholds:
       macro=bearish:  BUY if net_score > 0.25, SELL/SHORT if < -0.25
       macro=neutral:  BUY if net_score > 0.15, SELL/SHORT if < -0.15
       macro=bullish:  BUY if net_score > 0.10, SELL/SHORT if < -0.10
  6. If confidence < 40: override to HOLD regardless of direction
  7. Action:
       bullish + has_short → COVER
       bullish + no_short  → BUY
       bearish + has_long  → SELL
       bearish + no_long   → SHORT (only if margin_requirement > 0)
       neutral             → HOLD


3.5  RISK ENGINE RULES (final)
--------------------------------

  Annual volatility tiers (60-day rolling std * sqrt(252 or 250)):
    < 15%   → max 25% of portfolio
    15-22%  → max 20%
    22-30%  → max 15%
    30-50%  → max 12.5%
    > 50%   → max 10% (hard cap)

  Correlation multiplier (computed across all current positions):
    avg_correlation >= 0.80  → multiply limit by 0.70 (reduce concentrated risk)
    avg_correlation <= 0.30  → multiply limit by 1.10 (allow more, diversified)
    between 0.30 and 0.80    → no adjustment

  Final limit:
    position_limit_usd = portfolio_value x tier_alloc x corr_multiplier
    max_shares = floor(position_limit_usd / current_price)
    quantity   = max(1, floor(max_shares x (confidence / 100)))


3.6  MARKET ROUTING
--------------------

  Routing is entirely driven by ticker suffix:
    ticker.endswith(".NS") or ".BO"  → INDIA_CONFIG
    all others                        → US_CONFIG

  Mixed-portfolio example:
    ["AAPL", "MSFT", "TCS.NS", "RELIANCE.NS"]
    AAPL, MSFT → US_CONFIG, USD, yfinance no suffix, SEC EDGAR
    TCS.NS, RELIANCE.NS → INDIA_CONFIG, INR, yfinance .NS, screener.in

  Correlation matrix uses % returns (currency-neutral).
  P&L is tracked in the ticker's native currency.
  Portfolio total value shown in base currency (configurable; default USD).


3.7  DATA FLOW PER TICKER
--------------------------

  DataBus.fetch(ticker, as_of_date)
    ↓
  [Layer 1] In-memory dict keyed by "{ticker}:{as_of_date}"
    ↓ miss
  [Layer 2] MongoDB query: all collections for this ticker
            Filter: date/period_end <= as_of_date (no-lookahead enforcement)
            Filter: is_historical=true OR fetched_at within TTL
    ↓ miss or stale
  [Layer 3] Live API fetch (market-routed)
            US:    yfinance + SEC EDGAR + FINRA + CBOE + FRED + Google News
            India: yfinance(.NS) + screener.in + NSE portal + RBI + ET/MC RSS
            Store to MongoDB with is_historical=(as_of_date < today)
    ↓
  Assemble DataBundle (all fields; missing fields = None, never KeyError)
    ↓
  Return to engine


3.8  THREADING MODEL
---------------------

  Main thread:
    WriteEngine.run() orchestration
    MongoDBClient (PyMongo is thread-safe)
    ConfigManager (watchdog listener runs in daemon thread)
    MonitorLayer (writes to MongoDB, thread-safe)

  Thread pool 1 — DataBus.prefetch():
    ThreadPoolExecutor(max_workers=8)
    IO-bound: each worker fetches one ticker
    All workers share the same MongoDBClient (PyMongo handles connection pool)

  Thread pool 2 — Engine compute (per ticker):
    ThreadPoolExecutor(max_workers=4)
    CPU-bound: each worker runs one engine's compute()
    Engines must be stateless in compute() — no mutation of self during compute
    initialize() is called sequentially before any threading begins

  FinBERT (NewsSentimentEngine):
    Model loaded once in initialize() as a class-level singleton
    compute() calls are read-only on the model — thread-safe with transformers


================================================================================
PART 4 — DATA SOURCES (COMPLETE AND RESOLVED)
================================================================================

  Data Type              US Source              India Source            TTL
  -------------------    -------------------    -------------------     -----
  OHLCV prices           yfinance               yfinance (.NS/.BO)      6h
  Financial statements   yfinance / SEC EDGAR   screener.in (scrape)    90d
  Financial ratios       yfinance               screener.in             24h
  Sector ETF P/E         yfinance (XLK etc.)    yfinance (NIFTYIT.NS)   24h
  Filing text (annual)   SEC EDGAR 10-K text    BSE PDF + pdfplumber    90d
  MD&A text (quarterly)  SEC EDGAR 8-K item2.02 BSE quarterly filing    90d
  Insider trades         SEC EDGAR Form 4       N/A                     7d
  Promoter holding       N/A                    NSE/BSE SEBI filing     90d
  13F institutional      SEC EDGAR 13F          N/A                     7d
  FII/DII daily          N/A                    NSE website CSV         24h
  FII sector breakdown   N/A                    NSE (best-effort, PDF)  30d
  Bulk/block deals       N/A                    NSE daily CSV           24h
  Short interest         FINRA biweekly CSV     NSE F&O OI (daily)      7d
  Dark pool (ATS)        FINRA OTC/ATS weekly   N/A                     7d
  Options P/C + IV       CBOE free download     NSE option chain JSON   6h
  VIX                    ^VIX (yfinance)        INDIAVIX.NS (yfinance)  1h
  Yield curve            FRED API (free key)    RBI G-Sec yields        24h
  Policy rate            FRED: FEDFUNDS         RBI Repo (scrape)       24h
  Sector ETF returns     yfinance (XLK etc.)    yfinance (NIFTYIT.NS)   1h
  Benchmark              ^GSPC (yfinance)       ^NSEI (yfinance)        1h
  News headlines         Google News RSS +      ET/MC/BS/Mint RSS       1h
                         Yahoo Finance RSS
  Analyst ratings        yfinance.upgrades      yfinance + screener.in  24h
  Total cost: $0 (all free sources)


================================================================================
PART 5 — COMPLETE FILE STRUCTURE
================================================================================

  hf-ai/
    engine.py                         CLI entry point (argparse)
    config/
      engine.yaml                     Master config (all settings)
      us_thresholds.yaml              US screen thresholds
      india_thresholds.yaml           India screen thresholds
      moat_idf.json                   Pre-computed TF-IDF weights for moat scoring
    core/
      __init__.py
      engine_base.py                  BaseSignalEngine, Signal, DataBundle
      write_engine.py                 WriteEngine orchestrator
      engine_registry.py              Auto-discovery + manual register
      data_bus.py                     3-layer cache + prefetch
      monitor.py                      MonitorLayer + HealthMetrics
      result_store.py                 MongoDB writes for signals/decisions/runs
      aggregator.py                   Weighted vote + macro multiplier + sizing
      risk_engine.py                  Volatility + correlation + position limits
      backtest.py                     BacktestFramework + trade execution + metrics
    data/
      __init__.py
      models.py                       All Pydantic dataclasses
      market_config.py                MarketConfig dataclass + get_market_config()
      fetcher_us.py                   yfinance + SEC EDGAR + FINRA + CBOE + FRED
      fetcher_india.py                yfinance(.NS) + screener.in + NSE + RBI
    db/
      __init__.py
      client.py                       MongoDBClient (hf_ai_engine only)
    news/
      __init__.py
      scraper.py                      NewsScraperModule
      sources.py                      GoogleNewsSource, RSSFeedSource, YahooFinanceSource
      sentiment.py                    FinBERTScorer, AnalystRatingScorer,
                                      OptionsSentimentOverlay, MDASentimentScorer,
                                      FourSourceComposite
    signals/
      __init__.py
      technical.py                    Multi-timeframe EMA/RSI/MACD/OBV
      fundamental.py                  12-check ratio scoring + Piotroski
      valuation.py                    6-model DCF + multiples + sector P/E
      earnings_quality.py             Beneish M + Altman Z + F-Score
      insider_sentiment.py            SEC Form 4 (US) / Promoter holding (India)
      news_sentiment.py               Plugin wrapping news/ module
      macro_context.py                VIX + rates + ETFs + FII — returns MacroRegime
      institutional_flow.py           13F + dark pool + FINRA + CBOE | FII/bulk (India)
      screens/
        __init__.py                   consistency_score, moat_text_score (TF-IDF),
                                      management_quality_score, master_screen_score
        buffett.py
        graham.py
        lynch.py
        fisher.py
        munger.py
        burry.py
        ackman.py
        wood.py
        druckenmiller.py
        taleb.py
        damodaran.py
        pabrai.py
        jhunjhunwala.py
    analytics.py                      Sector exposure, factor attribution, drawdown
    narrator.py                       Ollama post-decision narrative (optional)
    tests/
      conftest.py
      fixtures/
        sample_prices.json
        sample_financials.json
        sample_ratios.json
      unit/
        test_technical.py
        test_fundamental.py
        test_valuation.py
        test_earnings_quality.py
        test_insider.py
        test_news.py
        test_macro.py
        test_institutional.py
        test_screens.py
        test_risk_engine.py
        test_aggregator.py
        test_backtest.py
        test_data_bus.py
      integration/
        test_full_pipeline.py
        test_no_lookahead.py
        test_india_pipeline.py
    scripts/
      build_moat_idf.py               One-time utility: compute IDF weights
    pyproject.toml
    .env.example
    README.md
    doc/
      REQUIREMENTS.md
      ARCHITECTURE_REVIEW.md          This document
      PHASES.md
      DB_SCHEMA.md


================================================================================
PART 6 — COMPLETE MONGODB COLLECTIONS
================================================================================

  Collection              Purpose                           TTL Strategy
  ---------------------   ------------------------------    -----------------
  prices_us               US OHLCV                          cleanup job, 6h live
  prices_in               India OHLCV                       cleanup job, 6h live
  financials              All markets, all periods          cleanup job, 90d live
  ratios                  Latest ratios                     cleanup job, 24h live
  filing_texts            10-K, 8-K MD&A, annual reports   cleanup job, 90d live
  insider_trades          US SEC Form 4                     cleanup job, 7d live
  promoter_holdings       India SEBI quarterly              cleanup job, 90d live
  fii_dii_daily           India FII/DII daily flow          cleanup job, 24h live
  bulk_deals              India NSE bulk/block              cleanup job, 24h live
  dark_pool_us            FINRA OTC/ATS weekly              cleanup job, 7d live
  macro_us                US macro snapshot                 cleanup job, 1h live
  macro_in                India macro snapshot              cleanup job, 1h live
  news_raw                Scraped headlines                 cleanup job, 90d live
  news_sentiment          Aggregated sentiment per ticker   cleanup job, 1h live
  signals                 Per-engine signals per run        never expire
  decisions               Final trading decisions           never expire
  runs                    Run records + status              never expire
  backtest_results        Daily portfolio snapshots         never expire
  backtest_metrics        Final backtest performance        never expire
  monitoring_events       System metrics                    cleanup job, 30d
  audit_log               All WARN/ERROR events             cleanup job, 90d
  engine_registry         Registered engine metadata        never expire
  configurations          Config snapshots                  never expire
  data_cache_meta         Staleness tracking per ticker     cleanup job, 90d

  Note: filing_texts is a new collection resolving Gap 4. All other
  collections are unchanged from DB_SCHEMA.md.

  New collection schema — filing_texts:
    ticker          "AAPL"
    market          "US"
    filing_type     "10-K" | "8-K-MDA" | "annual_report" | "quarterly_mda"
    period_end      "2024-09-30"
    text            full extracted text (up to 5,000 words)
    word_count      integer
    source          "sec_edgar" | "bse_portal"
    is_historical   bool
    fetched_at      ISODate
  Index: { ticker: 1, filing_type: 1, period_end: -1 }  (unique)


================================================================================
PART 7 — COMPLETE TECHNICAL STACK
================================================================================

  CORE (always required)
  Library             Version    Purpose
  ---------------     -------    -----------------------------------------------
  Python              3.11+      Runtime
  yfinance            0.2+       Primary data source (prices, ratios, news)
  pandas              2.1+       DataFrames, time-series, rolling windows
  numpy               1.24+      Numerical computation
  scipy               1.11+      percentileofscore, OLS regression (analytics)
  pydantic            2.4+       Data validation for all models
  pymongo             4.6+       MongoDB driver
  requests            2.31+      HTTP calls (NSE, FINRA, FRED, screener.in)
  beautifulsoup4      4.12+      HTML parsing (screener.in, NSE pages)
  feedparser          6.0+       RSS feed parsing (news sources)
  pdfplumber          0.10+      PDF text extraction (India annual reports)
  pyyaml              6.0+       YAML config parsing
  python-dotenv       1.0+       .env loading
  watchdog            3.0+       Config file hot-reload (replaces polling)
  schedule            1.2+       --schedule CLI flag for daily runs
  tabulate            0.9+       CLI table output
  colorama            0.4+       Colored terminal output
  tqdm                4.66+      Progress bar for backtest runs

  NEWS SENTIMENT (required for default operation)
  transformers        4.40+      HuggingFace pipeline for FinBERT
  torch               2.2+       CPU-only inference (~500 MB one-time download)

  OPTIONAL
  Library             When needed
  ---------------     -------------------------------------------------
  newsapi-python      NEWS_API_KEY set (additional news source)
  Ollama              --explain flag (local LLM narrative, free)
  pytest              Running the test suite

  REMOVED (vs original)
  langgraph, langchain-*, fastapi, sqlalchemy, alembic, openai


================================================================================
PART 8 — ENVIRONMENT CONFIGURATION (.env)
================================================================================

  REQUIRED: none (engine runs with zero keys)

  RECOMMENDED:
    FRED_API_KEY        Free instant registration at fred.stlouisfed.org
                        Enables yield curve data for macro module

  OPTIONAL:
    NEWS_API_KEY        newsapi.org free tier (100 req/day extra headlines)
    FMP_API_KEY         Financial Modeling Prep — better India fundamentals fallback
    ALPHA_VANTAGE_KEY   Fallback if yfinance unavailable
    OPENAI_API_KEY      Only if --news-engine=llm (not recommended; FinBERT is free)
    ANTHROPIC_API_KEY   Same as above
    MONGODB_URI         Default: mongodb://localhost:27017
                        Override for remote MongoDB Atlas


================================================================================
PART 9 — NON-FUNCTIONAL REQUIREMENTS (FINAL)
================================================================================

  Requirement        Specification
  ----------------   ----------------------------------------------------------
  Determinism        Same input data → identical output (except --news-engine=llm)
  Performance        < 5s per ticker for full signal suite (21 engines, parallel)
  Backtest speed     < 5 minutes for 10 tickers × 1 year
  Cost               $0 for full US + India operation
  Lookahead safety   as_of_date enforced at DataBus layer on every query
  Reliability        None-safe defaults everywhere; validate_data() guards all engines
  Thread safety      All engines are pure functions; MongoDBClient connection pool
  Portability        macOS + Linux + Windows; no OS-specific dependencies
  Testability        Every engine is a pure function; synthetic fixtures in tests/
  Extensibility      New engine = 1 file in signals/ with 1 method; zero other changes
  Observability      --show-signals exposes every engine's signal, confidence, reasoning
  Recoverability     KeyboardInterrupt during backtest → partial results saved and shown
  Security           All keys in .env; never hardcoded; .env in .gitignore


================================================================================
PART 10 — WHAT CHANGES IN EXISTING DOCS AFTER THIS REVIEW
================================================================================

  Document           Changes Required
  ---------------    ---------------------------------------------------------
  REQUIREMENTS.md    Section 24 file structure: already updated
                     Section 10 Valuation: already says "Six Models"
                     Section 16 moat scoring: already uses TF-IDF reference
                     Add: DataBundle field list update (Gap 1)
                     Add: Sector P/E resolution (Gap 2)
                     Add: Backtest TTL resolution (Gap 9)
                     Stack (Section 25): add pymongo, watchdog, schedule, pdfplumber

  PHASES.md          Phase 6: remove India task T6.7c (Gap 10)
                     Phase 2: add T2.13 filing text fetch task (Gap 4)
                     Phase 8: remove rebalance_freq implementation (Gap 18)
                     Phase 9: confirm India institutional flow in Phase 9

  ARCHITECTURE.md    Superseded by this document for all architectural decisions.
                     Keep as a shorter reference pointing to this review for detail.

  DB_SCHEMA.md       Add filing_texts collection (Gap 4)
                     Update TTL section: replace TTL indexes with cleanup job note
                     Add dark_pool_us collection (Gap 5)


================================================================================

HF-AI Engine — Architecture Review v2.0 — 2026-06-02

================================================================================
