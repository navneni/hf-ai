# MongoDB Schema — hf_ai_engine Database

> **Database:** `hf_ai_engine` (new, isolated — do NOT touch any existing database)
> **Driver:** PyMongo | **Version:** MongoDB 6.0+
> **Date:** 2026-06-01

---

## Setup

```python
# Connection
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["hf_ai_engine"]   # ONLY this database — never others
```

```bash
# Create database (MongoDB creates it on first write)
# Run once to verify connection:
mongosh --eval "db.adminCommand('ping')"

# Check database exists after first run:
mongosh hf_ai_engine --eval "show collections"
```

---

## Collections — Complete Schema

### 1. `prices_us` — US OHLCV Price Data

```javascript
{
  _id:        ObjectId,
  ticker:     "AAPL",          // string, NSE-style suffix NOT used here
  date:       "2024-01-15",    // YYYY-MM-DD, trading day
  open:       184.21,
  high:       186.40,
  low:        183.50,
  close:      185.92,
  volume:     52341200,
  adj_close:  185.92,          // split/dividend adjusted
  fetched_at: ISODate(),       // when this row was written to DB
  source:     "yfinance"
}

// Indexes:
db.prices_us.createIndex({ ticker: 1, date: -1 }, { unique: true })
db.prices_us.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 21600 })  // TTL 6h
```

### 2. `prices_in` — India OHLCV Price Data

```javascript
{
  _id:        ObjectId,
  ticker:     "TCS.NS",        // always includes .NS or .BO suffix
  date:       "2024-01-15",
  open:       3841.00,
  high:       3892.50,
  low:        3820.00,
  close:      3875.20,
  volume:     1823400,
  adj_close:  3875.20,
  fetched_at: ISODate(),
  source:     "yfinance"
}

// Indexes:
db.prices_in.createIndex({ ticker: 1, date: -1 }, { unique: true })
```

### 3. `financials` — Financial Statements (All Markets)

```javascript
{
  _id:          ObjectId,
  ticker:       "AAPL",
  market:       "US",          // "US" | "IN"
  period:       "TTM",         // "TTM" | "2024" | "2023" | ... | "2015" | "Q1-2024"
  period_end:   "2024-09-30",  // fiscal period end date
  revenue:           391035000000,
  gross_profit:      170782000000,
  operating_income:  123212000000,
  net_income:        100912000000,
  eps:               6.43,
  total_assets:      352583000000,
  total_debt:        101304000000,
  cash:              29965000000,
  equity:            56950000000,
  current_assets:    152987000000,
  current_liabilities:145308000000,
  operating_cash_flow:118254000000,
  capex:             9447000000,
  free_cash_flow:    108807000000,
  dividends_paid:    14756000000,
  shares_outstanding:15204137000,
  depreciation_amortization:11445000000,
  retained_earnings: -19154000000,
  ebit:              123212000000,
  receivables:       33410000000,
  ppe:               45680000000,
  sga_expense:       26097000000,
  fetched_at:        ISODate(),
  source:            "yfinance"  // "yfinance" | "screener_in" | "sec_edgar"
}

// Indexes:
db.financials.createIndex({ ticker: 1, period: 1, period_end: -1 }, { unique: true })
db.financials.createIndex({ ticker: 1, market: 1, period_end: -1 })
db.financials.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 7776000 })  // TTL 90d
```

### 4. `ratios` — Financial Ratios

```javascript
{
  _id:              ObjectId,
  ticker:           "AAPL",
  market:           "US",
  date:             "2024-01-15",      // as-of date
  pe_ratio:         29.8,
  pb_ratio:         44.2,
  ps_ratio:         7.9,
  ev_ebitda:        23.1,
  roe:              1.474,             // 147.4%
  roa:              0.286,
  roic:             0.531,
  debt_to_equity:   1.779,
  current_ratio:    1.053,
  gross_margin:     0.437,
  operating_margin: 0.315,
  net_margin:       0.258,
  fcf_yield:        0.028,
  dividend_yield:   0.005,
  market_cap:       2910000000000,
  enterprise_value: 2970000000000,
  peg_ratio:        2.3,
  fetched_at:       ISODate(),
  source:           "yfinance"
}

// Indexes:
db.ratios.createIndex({ ticker: 1, date: -1 })
db.ratios.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 86400 })  // TTL 24h
```

### 5. `signals` — Per-Engine Per-Ticker Signals

```javascript
{
  _id:        ObjectId,
  run_id:     "run_a1b2c3d4",
  ticker:     "AAPL",
  market:     "US",
  engine:     "buffett_screen",
  as_of_date: "2024-01-15",
  signal:     "bullish",          // "bullish" | "bearish" | "neutral"
  confidence: 82.5,               // 0.0 – 100.0
  weight:     0.016,              // contribution weight in aggregation
  reasoning:  "5/6 Buffett criteria passed — strong FCF, low D/E, MoS 28%",
  metadata: {                     // engine-specific sub-scores
    roe_ok:          true,
    de_ok:           true,
    fcf_ok:          true,
    net_margin_ok:   true,
    dcf_mos:         0.28,
    consistency_10yr:0.90,
    moat_score:      0.65,
    mgmt_score:      0.80,
    total_score:     0.74,
    criteria_passed: 5,
    criteria_total:  6
  },
  computed_at: ISODate()
}

// Indexes:
db.signals.createIndex({ run_id: 1, ticker: 1, engine: 1 }, { unique: true })
db.signals.createIndex({ ticker: 1, engine: 1, as_of_date: -1 })
db.signals.createIndex({ as_of_date: -1 })
```

### 6. `decisions` — Final Trading Decisions

```javascript
{
  _id:        ObjectId,
  run_id:     "run_a1b2c3d4",
  ticker:     "AAPL",
  market:     "US",
  as_of_date: "2024-01-15",
  action:     "buy",              // "buy" | "sell" | "hold" | "short" | "cover"
  quantity:   38,
  confidence: 74.2,
  price:      185.92,             // price at time of decision
  position_limit_usd: 14800.0,
  net_score:  0.31,               // aggregated signal score
  macro_regime: "neutral",
  reasoning:  "Strong fundamental quality + technical bullish; macro neutral",
  signals_summary: {              // condensed per-engine
    "technical":       { signal: "bullish", confidence: 82.0, weight: 0.20 },
    "fundamental":     { signal: "bullish", confidence: 71.0, weight: 0.15 },
    "valuation":       { signal: "neutral", confidence: 55.0, weight: 0.15 },
    "earnings_quality":{ signal: "bullish", confidence: 88.0, weight: 0.10 },
    "news_sentiment":  { signal: "bullish", confidence: 60.0, weight: 0.10 },
    "buffett_screen":  { signal: "bullish", confidence: 82.5, weight: 0.016 }
    // ... all engines
  },
  narrative:  null,               // Ollama-generated text if --explain used
  decided_at: ISODate()
}

// Indexes:
db.decisions.createIndex({ run_id: 1, ticker: 1 }, { unique: true })
db.decisions.createIndex({ ticker: 1, as_of_date: -1 })
db.decisions.createIndex({ action: 1, as_of_date: -1 })
```

### 7. `runs` — Execution Run Records

```javascript
{
  _id:          ObjectId,
  run_id:       "run_a1b2c3d4",    // UUID4
  run_type:     "analysis",         // "analysis" | "backtest" | "scheduled"
  tickers:      ["AAPL", "MSFT", "TCS.NS"],
  engines:      ["technical", "fundamental", "buffett_screen"],  // null = all
  as_of_date:   "2024-01-15",       // null for live runs
  started_at:   ISODate(),
  ended_at:     ISODate(),          // null if still running
  status:       "success",          // "running" | "success" | "error"
  error:        null,               // error message if status=error
  checkpoints: [
    { stage: "data_fetched",      at: ISODate() },
    { stage: "signals_computed",  at: ISODate() },
    { stage: "decisions_made",    at: ISODate() }
  ],
  stats: {
    tickers_processed: 3,
    engines_run: 21,
    signals_computed: 63,
    decisions_made: 3,
    duration_seconds: 14.2
  }
}

// Indexes:
db.runs.createIndex({ run_id: 1 }, { unique: true })
db.runs.createIndex({ started_at: -1 })
db.runs.createIndex({ status: 1, started_at: -1 })
```

### 8. `backtest_results` — Daily Backtest Portfolio Snapshots

```javascript
{
  _id:           ObjectId,
  run_id:        "bt_x1y2z3w4",
  date:          "2023-06-15",
  portfolio_value:108420.50,
  cash:          35200.00,
  positions: {
    "AAPL": { long_shares: 38, cost_basis: 178.20, market_value: 73350.0, pnl: 2826.0 },
    "MSFT": { long_shares: 0,  cost_basis: 0, market_value: 0, pnl: 0 }
  },
  trades_today: [
    { ticker: "AAPL", action: "buy", quantity: 10, price: 185.92, value: 1859.20 }
  ],
  metrics_snapshot: {
    total_return_pct:  8.42,
    drawdown_pct:      -3.21,
    running_sharpe:    1.34
  }
}

// Indexes:
db.backtest_results.createIndex({ run_id: 1, date: 1 }, { unique: true })
db.backtest_results.createIndex({ run_id: 1 })
```

### 9. `backtest_metrics` — Final Backtest Performance Summary

```javascript
{
  _id:                   ObjectId,
  run_id:                "bt_x1y2z3w4",
  config: {
    tickers:             ["AAPL", "MSFT"],
    start_date:          "2023-01-01",
    end_date:            "2023-12-31",
    initial_cash:        100000,
    engines:             "all",
    slippage_bps:        0,
    commission:          0
  },
  metrics: {
    total_return_pct:      22.4,
    annualized_return_pct: 22.4,
    benchmark_return_pct:  24.2,   // S&P 500 same period
    alpha_pct:             -1.8,
    max_drawdown_pct:      -8.4,
    sharpe_ratio:          1.41,
    sortino_ratio:         2.12,
    calmar_ratio:          2.67,
    win_rate_pct:          58.2,
    avg_win_pct:           4.3,
    avg_loss_pct:          -2.1,
    profit_factor:         1.84,
    total_trades:          67,
    avg_holding_days:      8.2,
    best_trade_pct:        12.4,
    worst_trade_pct:       -5.8
  },
  monthly_returns: [
    { month: "2023-01", return_pct: 6.2 },
    { month: "2023-02", return_pct: -1.4 }
    // ...
  ],
  computed_at: ISODate()
}

// Indexes:
db.backtest_metrics.createIndex({ run_id: 1 }, { unique: true })
db.backtest_metrics.createIndex({ computed_at: -1 })
```

### 10. `news_raw` — Scraped Raw News Articles

```javascript
{
  _id:          ObjectId,
  ticker:       "AAPL",
  market:       "US",
  headline:     "Apple Beats Q1 Earnings Expectations with Record Services Revenue",
  source:       "Reuters",
  url:          "https://...",
  published_at: ISODate(),
  scraped_at:   ISODate(),
  scrape_source:"google_news_rss",   // "google_news_rss" | "yahoo_finance" | "rss_et" | ...
  sentiment:    null,                 // null until PythonSentimentAnalyzer runs
  sentiment_score: null,             // -1.0 to +1.0
  sentiment_computed_at: null
}

// Indexes:
db.news_raw.createIndex({ ticker: 1, published_at: -1 })
db.news_raw.createIndex({ url: 1 }, { unique: true })
db.news_raw.createIndex({ scraped_at: 1 }, { expireAfterSeconds: 7776000 })  // TTL 90d
```

### 11. `news_sentiment` — Aggregated Sentiment Per Ticker

```javascript
{
  _id:             ObjectId,
  ticker:          "AAPL",
  market:          "US",
  as_of_date:      "2024-01-15",
  article_count:   23,
  articles_used:   20,          // after dedup + min confidence filter
  weighted_score:  0.34,        // -1.0 to +1.0, recency-weighted
  signal:          "bullish",
  confidence:      51.0,
  breakdown: {
    positive_count:  14,
    negative_count:   3,
    neutral_count:    3,
    avg_vader_score:  0.42,
    avg_lm_adjustment:0.08,
    top_positive_headline: "Apple Beats Q1 Earnings...",
    top_negative_headline: "Apple Faces Antitrust Probe..."
  },
  computed_at: ISODate()
}

// Indexes:
db.news_sentiment.createIndex({ ticker: 1, as_of_date: -1 })
db.news_sentiment.createIndex({ ticker: 1, computed_at: -1 })
```

### 12. `macro_us` — US Macro Data

```javascript
{
  _id:                    ObjectId,
  date:                   "2024-01-15",
  vix:                    13.8,
  vix_5d_ma:              14.2,
  vix_20d_ma:             15.1,
  vix_trend:              "declining",      // "rising" | "declining" | "flat"
  yield_10yr:             4.12,
  yield_2yr:              4.38,
  yield_spread:           -0.26,            // 10yr - 2yr; negative = inverted
  sp500_price:            4783.5,
  sp500_200d_ma:          4512.0,
  sp500_vs_200ma:         "above",
  fed_funds_rate:         5.33,
  fed_trend:              "hold",           // "hiking" | "cutting" | "hold"
  sector_returns_3m: {
    XLK:  0.18,   XLF: 0.09,  XLE: -0.04,
    XLV:  0.06,   XLY: 0.14,  XLI:  0.11
  },
  macro_regime:           "neutral",        // derived: "bullish" | "bearish" | "neutral"
  fetched_at:             ISODate()
}

// Indexes:
db.macro_us.createIndex({ date: -1 }, { unique: true })
db.macro_us.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 3600 })  // TTL 1h
```

### 13. `macro_in` — India Macro Data

```javascript
{
  _id:                ObjectId,
  date:               "2024-01-15",
  india_vix:          12.4,
  nifty_price:        21731.4,
  nifty_200d_ma:      19842.0,
  nifty_vs_200ma:     "above",
  rbi_repo_rate:      6.50,
  rbi_trend:          "hold",
  gsec_10yr:          7.18,
  usdinr:             83.12,
  usdinr_30d_change:  0.008,        // % change; positive = INR weakening
  fii_net_5d_cr:      12450.0,      // crore INR; positive = buying
  macro_regime:       "bullish",
  sector_returns_3m: {
    "NIFTYIT.NS":     0.14,
    "NIFTYBANK.NS":   0.08,
    "NIFTYPHARMA.NS": 0.11
  },
  fetched_at: ISODate()
}

// Indexes:
db.macro_in.createIndex({ date: -1 }, { unique: true })
```

### 14. `fii_dii_daily` — India FII/DII Daily Flow

```javascript
{
  _id:               ObjectId,
  date:              "2024-01-15",
  fii_net_equity:    3240.50,     // crore INR; positive = net buying
  fii_gross_buy:     12840.00,
  fii_gross_sell:    9599.50,
  dii_net_equity:    -821.30,     // negative = net selling
  dii_gross_buy:     6432.10,
  dii_gross_sell:    7253.40,
  combined_net:      2419.20,
  market_direction:  "bullish",   // derived from combined net
  source:            "nse_portal",
  fetched_at:        ISODate()
}

// Indexes:
db.fii_dii_daily.createIndex({ date: -1 }, { unique: true })
db.fii_dii_daily.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 86400 })  // TTL 24h
```

### 15. `bulk_deals` — India NSE Bulk & Block Deals

```javascript
{
  _id:              ObjectId,
  date:             "2024-01-15",
  ticker:           "TCS.NS",
  deal_type:        "bulk",        // "bulk" | "block"
  client_name:      "Motilal Oswal MF",
  transaction_type: "buy",
  quantity:         1250000,
  price:            3875.20,
  value_cr:         484.40,        // value in crore INR
  source:           "nse_portal",
  fetched_at:       ISODate()
}

// Indexes:
db.bulk_deals.createIndex({ ticker: 1, date: -1 })
db.bulk_deals.createIndex({ date: -1 })
db.bulk_deals.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 86400 })
```

### 16. `promoter_holdings` — India Promoter Holding Disclosures

```javascript
{
  _id:                ObjectId,
  ticker:             "RELIANCE.NS",
  quarter:            "Q3-FY2024",  // quarter of disclosure
  disclosure_date:    "2024-01-10",
  promoter_pct:       50.32,        // % held by promoters
  promoter_prev_pct:  50.28,        // prior quarter
  promoter_change:    0.04,         // quarter-over-quarter change
  pledge_pct:         0.00,         // % of promoter shares pledged
  pledge_prev_pct:    0.00,
  pledge_change:      0.00,
  public_pct:         49.68,
  fii_pct:            24.12,
  dii_pct:            8.42,
  signal:             "neutral",    // derived
  source:             "nse_portal",
  fetched_at:         ISODate()
}

// Indexes:
db.promoter_holdings.createIndex({ ticker: 1, quarter: -1 }, { unique: true })
db.promoter_holdings.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 7776000 })  // 90d
```

### 17. `insider_trades` — US SEC Form 4 Insider Transactions

```javascript
{
  _id:              ObjectId,
  ticker:           "AAPL",
  filing_date:      "2024-01-12",
  transaction_date: "2024-01-10",
  transaction_type: "buy",         // "buy" | "sell"
  shares:           10000,
  price:            184.92,
  value:            1849200.0,
  insider_name:     "COOK TIMOTHY D",
  title:            "CEO",
  is_open_market:   true,          // false = RSU/ESPP/auto
  form_type:        "4",
  source:           "sec_edgar",
  fetched_at:       ISODate()
}

// Indexes:
db.insider_trades.createIndex({ ticker: 1, transaction_date: -1 })
db.insider_trades.createIndex({ ticker: 1, is_open_market: 1, transaction_date: -1 })
db.insider_trades.createIndex({ fetched_at: 1 }, { expireAfterSeconds: 604800 })  // 7d
```

### 18. `monitoring_events` — System Metrics & Events

```javascript
{
  _id:    ObjectId,
  metric: "engine.compute.duration_ms",
  value:  142.3,
  tags: {
    run_id: "run_a1b2c3d4",
    ticker: "AAPL",
    engine: "technical"
  },
  at: ISODate()
}

// Also used for:
// "data.fetch.duration_ms"  — data fetch latency
// "run.signal_count"        — signals per run
// "data.cache.hit"          — cache hit (value: 1)
// "data.cache.miss"         — cache miss (value: 1)
// "engine.signal.bullish"   — 1 per bullish signal emitted
// "engine.signal.bearish"   — 1 per bearish signal emitted

// Indexes:
db.monitoring_events.createIndex({ at: -1 })
db.monitoring_events.createIndex({ metric: 1, at: -1 })
db.monitoring_events.createIndex({ "tags.run_id": 1 })
db.monitoring_events.createIndex({ at: 1 }, { expireAfterSeconds: 2592000 })  // TTL 30d
```

### 19. `audit_log` — All System Events

```javascript
{
  _id:     ObjectId,
  run_id:  "run_a1b2c3d4",   // null for system-level events
  level:   "WARN",            // "DEBUG" | "INFO" | "WARN" | "ERROR"
  ticker:  "AAPL",            // null for non-ticker events
  engine:  "technical",       // null for non-engine events
  message: "Insufficient data for engine 'valuation': no EPS available",
  stack:   null,              // Python traceback for ERROR level
  at:      ISODate()
}

// Indexes:
db.audit_log.createIndex({ run_id: 1, at: -1 })
db.audit_log.createIndex({ level: 1, at: -1 })
db.audit_log.createIndex({ at: 1 }, { expireAfterSeconds: 7776000 })  // TTL 90d
```

### 20. `engine_registry` — Registered Engine Metadata

```javascript
{
  _id:         ObjectId,
  name:        "buffett_screen",
  version:     "1.0.0",
  weight:      0.016,
  enabled:     true,
  description: "Warren Buffett quality + value screen",
  required_data: ["prices", "financials", "ratios", "filing_text"],
  registered_at: ISODate(),
  last_run_at:  ISODate(),
  run_count:    847,
  avg_signal_distribution: {
    bullish: 0.31,
    bearish: 0.28,
    neutral: 0.41
  }
}

// Indexes:
db.engine_registry.createIndex({ name: 1 }, { unique: true })
```

### 21. `configurations` — External Configuration Snapshots

```javascript
{
  _id:        ObjectId,
  config_key: "engine_yaml_snapshot",
  value:      { /* full YAML parsed to dict */ },
  valid_from: ISODate(),
  valid_to:   null,          // null = currently active
  applied_by: "system",
  at:         ISODate()
}

// Indexes:
db.configurations.createIndex({ config_key: 1, valid_from: -1 })
```

### 22. `data_cache_meta` — Cache Staleness Tracking

```javascript
{
  _id:         ObjectId,
  ticker:      "AAPL",
  data_type:   "prices",       // "prices" | "financials" | "ratios" | "news" | ...
  market:      "US",
  last_fetched:ISODate(),
  ttl_seconds: 21600,
  is_stale:    false,
  record_count:504
}

// Indexes:
db.data_cache_meta.createIndex({ ticker: 1, data_type: 1, market: 1 }, { unique: true })
db.data_cache_meta.createIndex({ last_fetched: -1 })
```

---

## Index Summary

```python
# Run once at startup via MongoDBClient._ensure_indexes()

INDEXES = {
    "prices_us":          [("ticker",1),("date",-1)],
    "prices_in":          [("ticker",1),("date",-1)],
    "financials":         [("ticker",1),("period",1),("period_end",-1)],
    "ratios":             [("ticker",1),("date",-1)],
    "signals":            [("run_id",1),("ticker",1),("engine",1)],
    "decisions":          [("run_id",1),("ticker",1)],
    "runs":               [("run_id",1)],            # unique
    "backtest_results":   [("run_id",1),("date",1)],
    "news_raw":           [("ticker",1),("published_at",-1)],
    "news_raw_url":       [("url",1)],               # unique
    "news_sentiment":     [("ticker",1),("as_of_date",-1)],
    "macro_us":           [("date",-1)],              # unique
    "macro_in":           [("date",-1)],              # unique
    "fii_dii_daily":      [("date",-1)],              # unique
    "bulk_deals":         [("ticker",1),("date",-1)],
    "promoter_holdings":  [("ticker",1),("quarter",-1)],
    "insider_trades":     [("ticker",1),("transaction_date",-1)],
    "monitoring_events":  [("metric",1),("at",-1)],
    "audit_log":          [("run_id",1),("at",-1)],
    "engine_registry":    [("name",1)],               # unique
    "data_cache_meta":    [("ticker",1),("data_type",1),("market",1)],  # unique
}
```

---

## Common Queries

```python
# Get last 60 days of prices for backtesting
prices = list(db.prices_us.find(
    {"ticker": "AAPL", "date": {"$lte": as_of_date}},
    sort=[("date", -1)], limit=60
))

# Get all annual financials for last 10 years
financials = list(db.financials.find(
    {"ticker": "AAPL", "period": {"$regex": "^20"}, "period_end": {"$lte": as_of_date}},
    sort=[("period_end", -1)], limit=10
))

# Get latest signals for a run
signals = list(db.signals.find({"run_id": run_id, "ticker": "AAPL"}))

# Get signal history for an engine (last 30 days)
from datetime import datetime, timedelta
cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
history = list(db.signals.find(
    {"engine": "buffett_screen", "as_of_date": {"$gte": cutoff}},
    sort=[("as_of_date", -1)]
))

# Get last N run summaries
runs = list(db.runs.find(
    {"run_type": "analysis"},
    sort=[("started_at", -1)], limit=7
))

# Engine accuracy: bullish signals where next day close > today close
# (requires joining signals with prices — done in Python, not MongoDB aggregation)

# Get FII/DII last 5 trading days (India)
fii_5d = list(db.fii_dii_daily.find({}, sort=[("date", -1)], limit=5))

# Get promoter holding for a ticker (latest quarter)
promoter = db.promoter_holdings.find_one(
    {"ticker": "RELIANCE.NS"},
    sort=[("quarter", -1)]
)
```

---

## TTL Summary

| Collection | TTL | Rationale |
|---|---|---|
| `prices_us`, `prices_in` | 6 hours | Refresh after market close |
| `financials` | 90 days | Quarterly earnings |
| `ratios` | 24 hours | Daily market prices affect ratios |
| `news_raw` | 90 days | News history useful for sentiment trends |
| `insider_trades` | 7 days | SEC filings are infrequent |
| `promoter_holdings` | 90 days | Quarterly disclosures |
| `fii_dii_daily` | 24 hours | Published daily |
| `bulk_deals` | 24 hours | Published daily |
| `macro_us`, `macro_in` | 1 hour | VIX changes during market hours |
| `monitoring_events` | 30 days | Operational data, rotate |
| `audit_log` | 90 days | Compliance lookback |
| Runs, signals, decisions | Never expire | Permanent historical record |
| backtest_results | Never expire | Permanent historical record |

---

*DB Schema v1.0 — 2026-06-01*
