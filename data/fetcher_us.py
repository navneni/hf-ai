"""
US market data fetcher.
Primary source: yfinance.
Extended financial history: SEC EDGAR XBRL (best-effort).
Insider trades: yfinance + SEC EDGAR Form 4.
Filing text: SEC EDGAR full-text search.
Macro: VIX, Treasury yields, S&P 500 vs 200d MA.
Institutional flow: short interest, options P/C, 13F proxy, dark pool.
"""
from __future__ import annotations
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "hf-ai-engine research@example.com",
    "Accept-Encoding": "gzip, deflate",
})

_EDGAR_BASE = "https://data.sec.gov"
_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"

# Cache CIK lookup in memory for the process lifetime
_cik_cache: dict[str, Optional[int]] = {}


# ─────────────────────────────────────────────── helpers

def _safe_float(val) -> Optional[float]:
    try:
        if val is None:
            return None
        f = float(val)
        return None if (f != f) else f   # NaN check
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    f = _safe_float(val)
    return int(f) if f is not None else None


def _get(df, *keys):
    """Try multiple possible row names in a DataFrame; return first match."""
    if df is None:
        return None
    for k in keys:
        if k in df.index:
            return df
    return None


def _row(df, *keys):
    """Return a Series from the first matching row key."""
    if df is None:
        return None
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _today_str() -> str:
    return str(date.today())


def _retry(fn, retries=3, wait=2):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            logger.debug("Retry %d/%d after error: %s", i + 1, retries, e)
            time.sleep(wait)


# ─────────────────────────────────────────────── prices

def fetch_prices(ticker: str, end_date: Optional[str] = None) -> list[dict]:
    """
    Fetch 2 years of daily OHLCV adjusted for splits/dividends.
    Returns list of dicts sorted by date ascending.
    """
    end = date.fromisoformat(end_date) if end_date else date.today()
    start = end - timedelta(days=730)

    try:
        hist = _retry(lambda: yf.Ticker(ticker).history(
            start=str(start), end=str(end + timedelta(days=1)),
            auto_adjust=True, actions=False
        ))
    except Exception as e:
        logger.warning("Price fetch failed for %s: %s", ticker, e)
        return []

    if hist is None or hist.empty:
        logger.warning("No price data for %s", ticker)
        return []

    records = []
    for dt, row in hist.iterrows():
        dt_str = str(dt.date()) if hasattr(dt, "date") else str(dt)[:10]
        if end_date and dt_str > end_date:
            continue
        records.append({
            "ticker":      ticker,
            "date":        dt_str,
            "open":        round(float(row["Open"]), 4),
            "high":        round(float(row["High"]), 4),
            "low":         round(float(row["Low"]), 4),
            "close":       round(float(row["Close"]), 4),
            "adj_close":   round(float(row["Close"]), 4),
            "volume":      int(row["Volume"]),
            "source":      "yfinance",
            "is_historical": end_date is not None and end_date < _today_str(),
            "fetched_at":  datetime.now(tz=timezone.utc),
        })

    records.sort(key=lambda r: r["date"])
    logger.info("Fetched %d price records for %s", len(records), ticker)
    return records


# ─────────────────────────────────────────────── financials

def _parse_yf_financials(ticker: str, t: yf.Ticker, end_date: Optional[str]) -> list[dict]:
    """Parse yfinance income/balance/cashflow into our schema."""
    records = []
    try:
        income  = t.financials        # annual, ~4 years
        balance = t.balance_sheet
        cashflow = t.cashflow
    except Exception as e:
        logger.warning("yfinance financials failed for %s: %s", ticker, e)
        return []

    if income is None or income.empty:
        return []

    is_hist = end_date is not None and end_date < _today_str()

    for col in income.columns:
        period_end = str(col.date()) if hasattr(col, "date") else str(col)[:10]
        if end_date and period_end > end_date:
            continue

        year = period_end[:4]

        def _v(df, *keys):
            row = _row(df, *keys)
            if row is None:
                return None
            return _safe_float(row.get(col) if hasattr(row, "get") else row[col] if col in row.index else None)

        # Income statement
        revenue        = _v(income,   "Total Revenue", "Revenue")
        gross_profit   = _v(income,   "Gross Profit")
        op_income      = _v(income,   "Operating Income", "Ebit", "EBIT")
        net_income     = _v(income,   "Net Income", "Net Income Common Stockholders")
        eps            = _v(income,   "Basic EPS", "Diluted EPS", "EPS")
        ebitda         = _v(income,   "EBITDA", "Normalized EBITDA")
        sga            = _v(income,   "Selling General And Administration", "Selling General Administrative")
        da             = _v(income,   "Depreciation And Amortization", "Reconciled Depreciation")

        # Balance sheet
        total_assets   = _v(balance,  "Total Assets")
        lt_debt        = _v(balance,  "Long Term Debt", "Long Term Debt And Capital Lease Obligation")
        st_debt        = _v(balance,  "Current Debt", "Short Term Debt", "Current Debt And Capital Lease Obligation")
        total_debt     = _safe_float((lt_debt or 0) + (st_debt or 0)) if (lt_debt or st_debt) else None
        cash           = _v(balance,  "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
        equity         = _v(balance,  "Stockholders Equity", "Total Equity Gross Minority Interest")
        cur_assets     = _v(balance,  "Current Assets")
        cur_liab       = _v(balance,  "Current Liabilities")
        retained       = _v(balance,  "Retained Earnings")
        ppe            = _v(balance,  "Net PPE", "Properties")
        receivables    = _v(balance,  "Receivables", "Accounts Receivable")
        shares         = _v(balance,  "Share Issued", "Ordinary Shares Number")

        # Cash flow
        op_cf          = _v(cashflow, "Operating Cash Flow", "Cash Flow From Operations")
        capex_raw      = _v(cashflow, "Capital Expenditure", "Purchase Of PPE")
        capex          = abs(capex_raw) if capex_raw is not None else None
        fcf            = _v(cashflow, "Free Cash Flow")
        if fcf is None and op_cf is not None and capex is not None:
            fcf = op_cf - capex
        divs           = _v(cashflow, "Cash Dividends Paid", "Dividends And Other Cash Distributions", "Common Stock Dividend Paid")
        if divs is not None:
            divs = abs(divs)

        records.append({
            "ticker":                    ticker,
            "market":                    "US",
            "period":                    year,
            "period_end":                period_end,
            "revenue":                   revenue,
            "gross_profit":              gross_profit,
            "operating_income":          op_income,
            "net_income":                net_income,
            "eps":                       eps,
            "ebitda":                    ebitda,
            "total_assets":              total_assets,
            "total_debt":                total_debt,
            "cash":                      cash,
            "equity":                    equity,
            "current_assets":            cur_assets,
            "current_liabilities":       cur_liab,
            "retained_earnings":         retained,
            "ppe":                       ppe,
            "receivables":               receivables,
            "sga_expense":               sga,
            "depreciation_amortization": da,
            "shares_outstanding":        _safe_int(shares),
            "operating_cash_flow":       op_cf,
            "capex":                     capex,
            "free_cash_flow":            fcf,
            "dividends_paid":            divs,
            "ebit":                      op_income,
            "source":                    "yfinance",
            "is_historical":             is_hist,
            "fetched_at":                datetime.now(tz=timezone.utc),
        })

    return records


def _parse_edgar_xbrl(ticker: str, cik: int, end_date: Optional[str]) -> list[dict]:
    """
    Fetch extended financial history (up to 10 years) from SEC EDGAR XBRL.
    Returns records not already covered by yfinance (i.e., older than 4 years).
    Best-effort — returns [] on any failure.
    """
    try:
        url = f"{_EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json"
        r = _SESSION.get(url, timeout=15)
        r.raise_for_status()
        facts = r.json().get("facts", {}).get("us-gaap", {})
    except Exception as e:
        logger.debug("EDGAR XBRL fetch failed for %s: %s", ticker, e)
        return []

    def _xbrl_annual(concept: str) -> dict[str, float]:
        """Return {period_end: value} for annual 10-K filings."""
        data = {}
        entries = facts.get(concept, {}).get("units", {})
        for unit_vals in entries.values():
            for entry in unit_vals:
                if entry.get("form") == "10-K" and "end" in entry:
                    end = entry["end"]
                    if end_date and end > end_date:
                        continue
                    data[end] = entry["val"]
        return data

    # Collect all period_ends with revenue data
    revenues = _xbrl_annual("Revenues") or _xbrl_annual("RevenueFromContractWithCustomerExcludingAssessedTax")
    if not revenues:
        return []

    gross    = _xbrl_annual("GrossProfit")
    op_inc   = _xbrl_annual("OperatingIncomeLoss")
    net_inc  = _xbrl_annual("NetIncomeLoss")
    assets   = _xbrl_annual("Assets")
    equity   = _xbrl_annual("StockholdersEquity")
    cur_a    = _xbrl_annual("AssetsCurrent")
    cur_l    = _xbrl_annual("LiabilitiesCurrent")
    op_cf    = _xbrl_annual("NetCashProvidedByUsedInOperatingActivities")
    capex_d  = _xbrl_annual("PaymentsToAcquirePropertyPlantAndEquipment")
    lt_debt  = _xbrl_annual("LongTermDebt")
    cash     = _xbrl_annual("CashAndCashEquivalentsAtCarryingValue")

    is_hist = end_date is not None and end_date < _today_str()
    records = []
    for period_end, rev in revenues.items():
        year = period_end[:4]
        capex_v = capex_d.get(period_end)
        capex_abs = abs(capex_v) if capex_v is not None else None
        op_cf_v = op_cf.get(period_end)
        fcf = (op_cf_v - capex_abs) if (op_cf_v is not None and capex_abs is not None) else None
        records.append({
            "ticker":              ticker,
            "market":              "US",
            "period":              year,
            "period_end":          period_end,
            "revenue":             _safe_float(rev),
            "gross_profit":        _safe_float(gross.get(period_end)),
            "operating_income":    _safe_float(op_inc.get(period_end)),
            "net_income":          _safe_float(net_inc.get(period_end)),
            "total_assets":        _safe_float(assets.get(period_end)),
            "equity":              _safe_float(equity.get(period_end)),
            "current_assets":      _safe_float(cur_a.get(period_end)),
            "current_liabilities": _safe_float(cur_l.get(period_end)),
            "total_debt":          _safe_float(lt_debt.get(period_end)),
            "cash":                _safe_float(cash.get(period_end)),
            "operating_cash_flow": _safe_float(op_cf_v),
            "capex":               capex_abs,
            "free_cash_flow":      _safe_float(fcf),
            "source":              "sec_edgar_xbrl",
            "is_historical":       is_hist,
            "fetched_at":          datetime.now(tz=timezone.utc),
        })

    logger.info("EDGAR XBRL: %d annual records for %s", len(records), ticker)
    return records


def fetch_financials(ticker: str, end_date: Optional[str] = None) -> list[dict]:
    """
    Fetch annual financial statements. yfinance primary (~4yr).
    SEC EDGAR XBRL fills in older history up to 10 years.
    """
    t = yf.Ticker(ticker)
    yf_records = _parse_yf_financials(ticker, t, end_date)

    # Try EDGAR for extended history
    cik = _get_cik(ticker)
    edgar_records = []
    if cik:
        edgar_records = _parse_edgar_xbrl(ticker, cik, end_date)

    # Merge: prefer yfinance for recent data; EDGAR fills gaps
    yf_periods = {r["period_end"] for r in yf_records}
    merged = yf_records[:]
    for r in edgar_records:
        if r["period_end"] not in yf_periods:
            merged.append(r)

    merged.sort(key=lambda r: r["period_end"])
    logger.info("Fetched %d financial records for %s", len(merged), ticker)
    return merged


# ─────────────────────────────────────────────── TTM financials

def fetch_ttm_financials(ticker: str, end_date: Optional[str] = None) -> Optional[dict]:
    """
    Build TTM (trailing 12 months) financials from last 4 quarterly reports.
    """
    try:
        t = yf.Ticker(ticker)
        q_income  = t.quarterly_financials
        q_balance = t.quarterly_balance_sheet
        q_cashflow = t.quarterly_cashflow
    except Exception as e:
        logger.warning("TTM fetch failed for %s: %s", ticker, e)
        return None

    if q_income is None or q_income.empty:
        return None

    # Filter columns to those <= end_date
    cols = list(q_income.columns)
    if end_date:
        cols = [c for c in cols if str(c.date() if hasattr(c, "date") else c)[:10] <= end_date]

    if not cols:
        return None

    # TTM = sum of last 4 quarters
    ttm_cols = cols[:4]
    latest_date = str(ttm_cols[0].date() if hasattr(ttm_cols[0], "date") else ttm_cols[0])[:10]
    is_hist = end_date is not None and end_date < _today_str()

    def _sum_row(df, *keys):
        row = _row(df, *keys)
        if row is None:
            return None
        vals = [_safe_float(row.get(c) if hasattr(row, "get") else
                (row[c] if c in row.index else None)) for c in ttm_cols]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None

    def _latest_row(df, *keys):
        row = _row(df, *keys)
        if row is None or not ttm_cols:
            return None
        c = ttm_cols[0]
        return _safe_float(row.get(c) if hasattr(row, "get") else
                           (row[c] if c in row.index else None))

    revenue    = _sum_row(q_income,   "Total Revenue", "Revenue")
    gross      = _sum_row(q_income,   "Gross Profit")
    op_income  = _sum_row(q_income,   "Operating Income", "Ebit")
    net_income = _sum_row(q_income,   "Net Income", "Net Income Common Stockholders")
    op_cf      = _sum_row(q_cashflow, "Operating Cash Flow")
    capex_raw  = _sum_row(q_cashflow, "Capital Expenditure", "Purchase Of PPE")
    capex      = abs(capex_raw) if capex_raw is not None else None
    fcf        = (op_cf - capex) if (op_cf is not None and capex is not None) else None

    total_assets = _latest_row(q_balance, "Total Assets")
    equity       = _latest_row(q_balance, "Stockholders Equity")
    cash         = _latest_row(q_balance, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
    lt_debt      = _latest_row(q_balance, "Long Term Debt")
    st_debt      = _latest_row(q_balance, "Current Debt", "Short Term Debt")
    total_debt   = _safe_float((lt_debt or 0) + (st_debt or 0)) if (lt_debt or st_debt) else None
    cur_assets   = _latest_row(q_balance, "Current Assets")
    cur_liab     = _latest_row(q_balance, "Current Liabilities")

    return {
        "ticker":              ticker,
        "market":              "US",
        "period":              "TTM",
        "period_end":          latest_date,
        "revenue":             revenue,
        "gross_profit":        gross,
        "operating_income":    op_income,
        "net_income":          net_income,
        "total_assets":        total_assets,
        "equity":              equity,
        "cash":                cash,
        "total_debt":          total_debt,
        "current_assets":      cur_assets,
        "current_liabilities": cur_liab,
        "operating_cash_flow": op_cf,
        "capex":               capex,
        "free_cash_flow":      fcf,
        "source":              "yfinance_ttm",
        "is_historical":       is_hist,
        "fetched_at":          datetime.now(tz=timezone.utc),
    }


# ─────────────────────────────────────────────── ratios

def fetch_ratios(ticker: str, end_date: Optional[str] = None,
                 financials: Optional[list[dict]] = None) -> dict:
    """
    Fetch latest ratios from yfinance.info, compute fallbacks from financials.
    """
    today = _today_str()
    as_of = end_date or today
    is_hist = end_date is not None and end_date < today

    try:
        info = _retry(lambda: yf.Ticker(ticker).info)
    except Exception as e:
        logger.warning("Ratios fetch failed for %s: %s", ticker, e)
        info = {}

    def _i(key, alt=None):
        val = info.get(key) or (info.get(alt) if alt else None)
        return _safe_float(val)

    pe        = _i("trailingPE")
    pb        = _i("priceToBook")
    ps        = _i("priceToSalesTrailing12Months")
    ev_ebitda = _i("enterpriseToEbitda")
    roe       = _i("returnOnEquity")
    roa       = _i("returnOnAssets")
    de        = _i("debtToEquity")
    if de is not None:
        de = de / 100.0     # yfinance returns D/E as percentage
    cur_ratio = _i("currentRatio")
    gross_m   = _i("grossMargins")
    op_m      = _i("operatingMargins")
    net_m     = _i("profitMargins")
    mktcap    = _i("marketCap")
    ev        = _i("enterpriseValue")
    div_y     = _i("dividendYield")
    peg       = _i("trailingPegRatio")
    sector    = info.get("sector")
    industry  = info.get("industry")
    name      = info.get("shortName") or info.get("longName")

    # Sector ETF P/E — used as sector-median proxy in ValuationEngine
    _SECTOR_ETF_MAP = {
        "Technology": "XLK", "Financial Services": "XLF", "Energy": "XLE",
        "Healthcare": "XLV", "Consumer Cyclical": "XLY", "Industrials": "XLI",
        "Utilities": "XLU", "Communication Services": "XLC",
        "Basic Materials": "XLB", "Real Estate": "XLRE", "Consumer Defensive": "XLP",
    }
    sector_etf = _SECTOR_ETF_MAP.get(sector or "")
    sector_pe = None
    if sector_etf:
        try:
            sector_pe = _safe_float(yf.Ticker(sector_etf).info.get("trailingPE"))
        except Exception:
            pass

    # Compute fallbacks from financials if missing
    if financials:
        ttm = next((f for f in reversed(financials) if f.get("period") == "TTM"), None)
        latest = ttm or (financials[-1] if financials else None)
        if latest:
            if gross_m is None and latest.get("revenue") and latest.get("gross_profit"):
                gross_m = latest["gross_profit"] / latest["revenue"]
            if op_m is None and latest.get("revenue") and latest.get("operating_income"):
                op_m = latest["operating_income"] / latest["revenue"]
            if net_m is None and latest.get("revenue") and latest.get("net_income"):
                net_m = latest["net_income"] / latest["revenue"]
            if roe is None and latest.get("net_income") and latest.get("equity") and latest["equity"] > 0:
                roe = latest["net_income"] / latest["equity"]
            if de is None and latest.get("total_debt") and latest.get("equity") and latest["equity"] > 0:
                de = latest["total_debt"] / latest["equity"]

    # FCF yield
    fcf_yield = None
    if financials and mktcap and mktcap > 0:
        ttm = next((f for f in reversed(financials) if f.get("period") == "TTM"), None)
        if ttm and ttm.get("free_cash_flow"):
            fcf_yield = ttm["free_cash_flow"] / mktcap

    return {
        "ticker":           ticker,
        "market":           "US",
        "date":             as_of,
        "pe_ratio":         pe,
        "pb_ratio":         pb,
        "ps_ratio":         ps,
        "ev_ebitda":        ev_ebitda,
        "roe":              roe,
        "roa":              roa,
        "roic":             None,       # computed in signal engine
        "debt_to_equity":   de,
        "current_ratio":    cur_ratio,
        "gross_margin":     gross_m,
        "operating_margin": op_m,
        "net_margin":       net_m,
        "fcf_yield":        fcf_yield,
        "dividend_yield":   div_y,
        "peg_ratio":        peg,
        "market_cap":       mktcap,
        "enterprise_value": ev,
        "sector":           sector,
        "sector_etf":       sector_etf,
        "sector_pe":        sector_pe,
        "industry":         industry,
        "company_name":     name,
        "source":           "yfinance",
        "is_historical":    is_hist,
        "fetched_at":       datetime.now(tz=timezone.utc),
    }


# ─────────────────────────────────────────────── analyst ratings

def fetch_analyst_ratings(ticker: str, end_date: Optional[str] = None) -> list[dict]:
    """
    Fetch analyst upgrade/downgrade history from yfinance.
    Returns list of {date, firm, action, from_grade, to_grade, direction}.
    India fallback: returns [] if empty (screener.in scraping added in Phase 9).
    """
    today = _today_str()
    cutoff = str(date.fromisoformat(end_date or today) - timedelta(days=180))
    is_hist = end_date is not None and end_date < today
    records = []

    try:
        t = yf.Ticker(ticker)
        df = t.upgrades_downgrades
        if df is None or df.empty:
            return []
        if hasattr(df.index, 'tz_localize'):
            df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index

        for idx, row in df.iterrows():
            dt_str = str(idx)[:10]
            if dt_str < cutoff:
                continue
            if end_date and dt_str > end_date:
                continue

            action_raw = str(row.get("Action", "")).lower()
            if "up" in action_raw or "upgrade" in action_raw:
                direction = "upgrade"
            elif "down" in action_raw or "downgrade" in action_raw:
                direction = "downgrade"
            elif "init" in action_raw or "start" in action_raw:
                direction = "initiate"
            else:
                direction = "reiterate"

            records.append({
                "date":       dt_str,
                "firm":       str(row.get("Firm", "")),
                "action":     action_raw,
                "from_grade": str(row.get("FromGrade", "")),
                "to_grade":   str(row.get("ToGrade", "")),
                "direction":  direction,
                "is_historical": is_hist,
                "fetched_at": datetime.now(tz=timezone.utc),
            })
    except Exception as e:
        logger.debug("Analyst ratings fetch failed for %s: %s", ticker, e)

    logger.info("Fetched %d analyst ratings for %s", len(records), ticker)
    return records


# ─────────────────────────────────────────────── insider trades

def fetch_insider_trades(ticker: str, end_date: Optional[str] = None) -> list[dict]:
    """
    Fetch insider trades from yfinance (primary) and SEC EDGAR Form 4 (supplement).
    Filters to open-market transactions only.
    """
    today = _today_str()
    cutoff_start = str(date.fromisoformat(end_date or today) - timedelta(days=365))
    is_hist = end_date is not None and end_date < today
    records = []

    # --- yfinance primary
    try:
        t = yf.Ticker(ticker)
        df = t.insider_transactions
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                tx_date = str(row.get("Start Date", row.get("Date", "")))[:10]
                if not tx_date or tx_date < cutoff_start:
                    continue
                if end_date and tx_date > end_date:
                    continue

                text = str(row.get("Text", row.get("Transaction", ""))).lower()
                # Exclude automatic transactions
                if any(x in text for x in ("automatic", "rule 10b5-1", "option exercise",
                                            "gift", "tax", "vesting", "conversion")):
                    continue

                tx_type_raw = str(row.get("Transaction", row.get("Text", ""))).lower()
                if "sale" in tx_type_raw or "sell" in tx_type_raw:
                    tx_type = "sell"
                elif "purchase" in tx_type_raw or "buy" in tx_type_raw or "acqui" in tx_type_raw:
                    tx_type = "buy"
                else:
                    continue  # skip ambiguous

                shares = _safe_int(row.get("Shares"))
                value  = _safe_float(row.get("Value"))
                price  = round(value / shares, 2) if (shares and value and shares > 0) else 0.0

                records.append({
                    "ticker":           ticker,
                    "filing_date":      tx_date,
                    "transaction_date": tx_date,
                    "transaction_type": tx_type,
                    "shares":           shares or 0,
                    "price":            price,
                    "value":            value or 0.0,
                    "insider_name":     str(row.get("Insider", row.get("Name", "Unknown"))),
                    "title":            str(row.get("Position", row.get("Relationship", ""))),
                    "is_open_market":   True,
                    "source":           "yfinance",
                    "is_historical":    is_hist,
                    "fetched_at":       datetime.now(tz=timezone.utc),
                })
    except Exception as e:
        logger.warning("yfinance insider fetch failed for %s: %s", ticker, e)

    # --- SEC EDGAR supplement (adds transactions yfinance may miss)
    cik = _get_cik(ticker)
    if cik:
        edgar_records = _fetch_edgar_form4(ticker, cik, cutoff_start, end_date, is_hist)
        existing_keys = {(r["transaction_date"], r["insider_name"], r["shares"]) for r in records}
        for r in edgar_records:
            key = (r["transaction_date"], r["insider_name"], r["shares"])
            if key not in existing_keys:
                records.append(r)

    records.sort(key=lambda r: r["transaction_date"], reverse=True)
    logger.info("Fetched %d insider trades for %s", len(records), ticker)
    return records


def _fetch_edgar_form4(ticker: str, cik: int, start_date: str, end_date: Optional[str], is_hist: bool) -> list[dict]:
    """Fetch Form 4 filings from SEC EDGAR and extract open-market transactions."""
    try:
        params = {
            "q":          f'"{ticker}"',
            "forms":      "4",
            "dateRange":  "custom",
            "startdt":    start_date,
            "enddt":      end_date or _today_str(),
        }
        r = _SESSION.get(_EDGAR_SEARCH, params=params, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
    except Exception as e:
        logger.debug("EDGAR Form4 search failed for %s: %s", ticker, e)
        return []

    records = []
    for hit in hits[:20]:   # limit to most recent 20 filings
        src = hit.get("_source", {})
        accession_raw = hit.get("_id", "")
        accession = accession_raw.replace("-", "")
        cik_str = f"{cik:010d}"
        xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession_raw}.xml"

        try:
            xr = _SESSION.get(xml_url, timeout=10)
            if xr.status_code != 200:
                continue
            records.extend(_parse_form4_xml(xr.text, ticker, is_hist))
        except Exception:
            continue

    return records


def _parse_form4_xml(xml_text: str, ticker: str, is_hist: bool) -> list[dict]:
    """Extract open-market buy/sell transactions from Form 4 XML."""
    records = []
    # Find nonDerivativeTransaction blocks
    tx_blocks = re.findall(
        r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>",
        xml_text, re.DOTALL
    )
    # Also check derivativeTransaction for completeness
    insider_name = re.search(r"<rptOwnerName>(.*?)</rptOwnerName>", xml_text)
    insider_name = insider_name.group(1).strip() if insider_name else "Unknown"
    title_match  = re.search(r"<officerTitle>(.*?)</officerTitle>", xml_text)
    title = title_match.group(1).strip() if title_match else ""

    for block in tx_blocks:
        code_match  = re.search(r"<transactionCode>(.*?)</transactionCode>", block)
        code = code_match.group(1).strip() if code_match else ""
        # P = open market purchase, S = open market sale
        if code not in ("P", "S"):
            continue

        date_match   = re.search(r"<transactionDate>.*?<value>(.*?)</value>", block, re.DOTALL)
        shares_match = re.search(r"<transactionShares>.*?<value>(.*?)</value>", block, re.DOTALL)
        price_match  = re.search(r"<transactionPricePerShare>.*?<value>(.*?)</value>", block, re.DOTALL)

        tx_date  = date_match.group(1).strip() if date_match else ""
        shares   = _safe_int(shares_match.group(1).strip() if shares_match else None)
        price    = _safe_float(price_match.group(1).strip() if price_match else None)

        if not tx_date or not shares:
            continue

        records.append({
            "ticker":           ticker,
            "filing_date":      tx_date,
            "transaction_date": tx_date,
            "transaction_type": "buy" if code == "P" else "sell",
            "shares":           shares,
            "price":            price or 0.0,
            "value":            round((price or 0.0) * shares, 2),
            "insider_name":     insider_name,
            "title":            title,
            "is_open_market":   True,
            "source":           "sec_edgar_form4",
            "is_historical":    is_hist,
            "fetched_at":       datetime.now(tz=timezone.utc),
        })
    return records


# ─────────────────────────────────────────────── filing text

def fetch_filing_text(ticker: str, end_date: Optional[str] = None) -> tuple[str, str]:
    """
    Returns (filing_text, mda_text).
    filing_text: Business + Risk Factors from latest 10-K (~3,000 words max)
    mda_text:    MD&A section from latest 8-K (Item 2.02) (~2,000 words max)
    Both are empty string on failure — engines handle this gracefully.
    """
    cik = _get_cik(ticker)
    if not cik:
        return "", ""

    filing_text = _fetch_10k_text(cik, end_date)
    mda_text    = _fetch_8k_mda(cik, end_date)
    return filing_text, mda_text


def _fetch_10k_text(cik: int, end_date: Optional[str]) -> str:
    try:
        params = {
            "q":         f"CIK:{cik:010d}",
            "forms":     "10-K",
            "dateRange": "custom",
            "startdt":   "2010-01-01",
            "enddt":     end_date or _today_str(),
        }
        r = _SESSION.get(_EDGAR_SEARCH, params=params, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        if not hits:
            return ""

        # Most recent 10-K
        hit = hits[0]
        accession_raw = hit.get("_id", "")
        accession     = accession_raw.replace("-", "")
        idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession_raw}-index.htm"
        idx_r   = _SESSION.get(idx_url, timeout=10)
        if idx_r.status_code != 200:
            return ""

        # Find .htm document link
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(idx_r.text, "lxml")
        doc_link = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".htm") and "10k" in href.lower() or "annual" in href.lower():
                doc_link = "https://www.sec.gov" + href
                break
        if not doc_link:
            # fallback: first .htm in the table
            for a in soup.find_all("a", href=True):
                if a["href"].endswith(".htm"):
                    doc_link = "https://www.sec.gov" + a["href"]
                    break

        if not doc_link:
            return ""

        doc_r = _SESSION.get(doc_link, timeout=20)
        doc_soup = BeautifulSoup(doc_r.text, "lxml")
        text = doc_soup.get_text(separator=" ", strip=True)
        # Extract first 3000 words
        words = text.split()[:3000]
        return " ".join(words)
    except Exception as e:
        logger.debug("10-K text fetch failed: %s", e)
        return ""


def _fetch_8k_mda(cik: int, end_date: Optional[str]) -> str:
    try:
        params = {
            "q":         f"CIK:{cik:010d}",
            "forms":     "8-K",
            "dateRange": "custom",
            "startdt":   str(date.fromisoformat(end_date or _today_str()) - timedelta(days=180)),
            "enddt":     end_date or _today_str(),
        }
        r = _SESSION.get(_EDGAR_SEARCH, params=params, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        if not hits:
            return ""

        hit = hits[0]
        accession_raw = hit.get("_id", "")
        accession = accession_raw.replace("-", "")
        idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession_raw}-index.htm"
        idx_r   = _SESSION.get(idx_url, timeout=10)
        if idx_r.status_code != 200:
            return ""

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(idx_r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".htm"):
                doc_url = "https://www.sec.gov" + href
                doc_r = _SESSION.get(doc_url, timeout=20)
                doc_text = BeautifulSoup(doc_r.text, "lxml").get_text(separator=" ", strip=True)
                # Look for Management Discussion section
                lower = doc_text.lower()
                idx = lower.find("management")
                if idx >= 0:
                    snippet = doc_text[idx:idx + 8000]
                    return " ".join(snippet.split()[:2000])
                return " ".join(doc_text.split()[:2000])
        return ""
    except Exception as e:
        logger.debug("8-K MD&A fetch failed: %s", e)
        return ""


# ─────────────────────────────────────────────── CIK lookup

def _get_cik(ticker: str) -> Optional[int]:
    global _cik_cache
    ticker_upper = ticker.upper().split(".")[0]   # strip .NS / .BO
    if ticker_upper in _cik_cache:
        return _cik_cache[ticker_upper]

    try:
        r = _SESSION.get(
            "https://www.sec.gov/files/company_tickers.json",
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                cik = int(entry["cik_str"])
                _cik_cache[ticker_upper] = cik
                return cik
    except Exception as e:
        logger.debug("CIK lookup failed for %s: %s", ticker, e)

    _cik_cache[ticker_upper] = None
    return None


# ─────────────────────────────────────────────── macro (US)

def fetch_macro_us(end_date: Optional[str] = None) -> dict:
    """
    Fetch US macro regime indicators.
    Primary: yfinance (VIX, 10yr Treasury, S&P 500, sector breadth).
    Supplement: FRED API for 2yr yield when FRED_API_KEY is set.
    Returns a dict stored in DataBundle.macro for MacroContextEngine.
    """
    today = _today_str()
    as_of = end_date or today
    end_dt = date.fromisoformat(as_of)
    start_hist = str(end_dt - timedelta(days=410))

    result: dict = {
        "date":             as_of,
        "vix":              None,
        "vix_5d_ma":        None,
        "vix_20d_ma":       None,
        "yield_10yr":       None,
        "yield_2yr":        None,
        "yield_spread":     None,
        "sp500_price":      None,
        "sp500_200d_ma":    None,
        "sp500_vs_200ma":   None,
        "market_breadth":   None,
        "is_historical":    end_date is not None and end_date < today,
        "fetched_at":       datetime.now(tz=timezone.utc),
    }

    # VIX level and moving averages
    try:
        vix_h = _retry(lambda: yf.Ticker("^VIX").history(
            start=start_hist, end=str(end_dt + timedelta(days=1)),
            auto_adjust=False, actions=False,
        ))
        if vix_h is not None and not vix_h.empty:
            if end_date:
                vix_h = vix_h[vix_h.index.date <= end_dt]
            closes = vix_h["Close"].dropna()
            if not closes.empty:
                result["vix"] = round(float(closes.iloc[-1]), 2)
                if len(closes) >= 5:
                    result["vix_5d_ma"] = round(float(closes.iloc[-5:].mean()), 2)
                if len(closes) >= 20:
                    result["vix_20d_ma"] = round(float(closes.iloc[-20:].mean()), 2)
    except Exception as e:
        logger.debug("VIX fetch failed: %s", e)

    # 10-yr Treasury yield (^TNX is already in percent, e.g. 4.35 = 4.35%)
    try:
        tnx_h = _retry(lambda: yf.Ticker("^TNX").history(
            start=start_hist, end=str(end_dt + timedelta(days=1)),
            auto_adjust=False, actions=False,
        ))
        if tnx_h is not None and not tnx_h.empty:
            if end_date:
                tnx_h = tnx_h[tnx_h.index.date <= end_dt]
            closes = tnx_h["Close"].dropna()
            if not closes.empty:
                result["yield_10yr"] = round(float(closes.iloc[-1]) / 100.0, 5)
    except Exception as e:
        logger.debug("10yr yield fetch failed: %s", e)

    # 2-yr yield — FRED API preferred; fall back to ^FVX (5yr proxy)
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        try:
            fred_url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id=DGS2&api_key={fred_key}&file_type=json"
                f"&observation_start={start_hist}&observation_end={as_of}"
            )
            r = _SESSION.get(fred_url, timeout=10)
            r.raise_for_status()
            obs = [o for o in r.json().get("observations", [])
                   if o.get("value") not in (".", "")]
            if obs:
                result["yield_2yr"] = round(float(obs[-1]["value"]) / 100.0, 5)
        except Exception as e:
            logger.debug("FRED 2yr yield failed: %s", e)

    if result["yield_2yr"] is None:
        try:
            fvx_h = _retry(lambda: yf.Ticker("^FVX").history(
                start=start_hist, end=str(end_dt + timedelta(days=1)),
                auto_adjust=False, actions=False,
            ))
            if fvx_h is not None and not fvx_h.empty:
                if end_date:
                    fvx_h = fvx_h[fvx_h.index.date <= end_dt]
                closes = fvx_h["Close"].dropna()
                if not closes.empty:
                    result["yield_2yr"] = round(float(closes.iloc[-1]) / 100.0, 5)
        except Exception as e:
            logger.debug("5yr yield fallback failed: %s", e)

    if result["yield_10yr"] is not None and result["yield_2yr"] is not None:
        result["yield_spread"] = round(result["yield_10yr"] - result["yield_2yr"], 5)

    # S&P 500 vs 200d MA
    try:
        sp_h = _retry(lambda: yf.Ticker("^GSPC").history(
            start=start_hist, end=str(end_dt + timedelta(days=1)),
            auto_adjust=True, actions=False,
        ))
        if sp_h is not None and not sp_h.empty:
            if end_date:
                sp_h = sp_h[sp_h.index.date <= end_dt]
            closes = sp_h["Close"].dropna()
            if not closes.empty:
                last_price = float(closes.iloc[-1])
                result["sp500_price"] = round(last_price, 2)
                if len(closes) >= 200:
                    ma200 = float(closes.iloc[-200:].mean())
                    result["sp500_200d_ma"] = round(ma200, 2)
                    result["sp500_vs_200ma"] = round((last_price - ma200) / ma200, 4)
    except Exception as e:
        logger.debug("S&P 500 macro fetch failed: %s", e)

    # Market breadth: fraction of key sector ETFs trading above their 200d MA
    _BREADTH_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLU"]
    above_200, total_etfs = 0, 0
    for etf in _BREADTH_ETFS:
        try:
            h = _retry(lambda t=etf: yf.Ticker(t).history(
                start=start_hist, end=str(end_dt + timedelta(days=1)),
                auto_adjust=True, actions=False,
            ))
            if h is not None and not h.empty:
                if end_date:
                    h = h[h.index.date <= end_dt]
                c = h["Close"].dropna()
                if len(c) >= 200:
                    if float(c.iloc[-1]) > float(c.iloc[-200:].mean()):
                        above_200 += 1
                    total_etfs += 1
        except Exception:
            pass
    if total_etfs > 0:
        result["market_breadth"] = round(above_200 / total_etfs, 3)

    logger.info(
        "Macro US: VIX=%.1f spread=%s sp_vs_200=%s breadth=%s",
        result["vix"] or 0,
        f"{result['yield_spread']:.4f}" if result["yield_spread"] is not None else "N/A",
        f"{(result['sp500_vs_200ma'] or 0) * 100:.1f}%" if result["sp500_vs_200ma"] is not None else "N/A",
        f"{(result['market_breadth'] or 0) * 100:.0f}%" if result["market_breadth"] is not None else "N/A",
    )
    return result


# ─────────────────────────────────────────────── institutional flow (US)

def fetch_inst_flow_us(ticker: str, end_date: Optional[str] = None) -> dict:
    """
    Fetch US institutional flow signals for a ticker.
    Sources: yfinance (short interest + inst. holders), yfinance options (P/C + IV),
             FINRA weekly short-sale report (dark pool proxy, best-effort).
    All sub-signals are None on failure — engine handles gracefully.
    """
    today = _today_str()
    is_hist = end_date is not None and end_date < today

    result: dict = {
        "ticker":             ticker,
        "as_of_date":         end_date or today,
        "si_pct":             None,
        "si_days_to_cover":   None,
        "si_biweekly_change": None,
        "inst_ownership_pct": None,
        "inst_buyers_13f":    None,
        "inst_sellers_13f":   None,
        "pc_ratio":           None,
        "iv_rank":            None,
        "dark_pool_pct":      None,
        "dark_pool_trend":    None,
        "source":             "yfinance",
        "is_historical":      is_hist,
        "fetched_at":         datetime.now(tz=timezone.utc),
    }

    # Short interest (yfinance.info)
    try:
        info = _retry(lambda: yf.Ticker(ticker).info)
        si_pct = _safe_float(info.get("shortPercentOfFloat"))
        if si_pct is not None and si_pct > 1.0:
            si_pct /= 100.0   # some yfinance versions return 0–100
        result["si_pct"] = si_pct
        result["si_days_to_cover"] = _safe_float(info.get("shortRatio"))
    except Exception as e:
        logger.debug("Short interest fetch failed for %s: %s", ticker, e)

    # Institutional ownership proxy via yfinance institutional_holders
    try:
        t = yf.Ticker(ticker)
        holders = t.institutional_holders
        if holders is not None and not holders.empty:
            pct_col = next(
                (c for c in holders.columns if "%" in str(c) or "out" in str(c).lower()),
                None,
            )
            if pct_col:
                result["inst_ownership_pct"] = round(float(holders[pct_col].sum()), 4)
    except Exception as e:
        logger.debug("Institutional holders fetch failed for %s: %s", ticker, e)

    # Options P/C ratio and IV rank
    result.update(_fetch_options_sentiment(ticker))

    # FINRA weekly report: dark pool proxy
    result.update(_fetch_dark_pool_pct(ticker, end_date))

    logger.info(
        "Inst flow %s: SI=%.1f%% PC=%s IV=%s",
        ticker,
        (result["si_pct"] or 0) * 100,
        f"{result['pc_ratio']:.2f}" if result["pc_ratio"] is not None else "N/A",
        f"{result['iv_rank']:.0f}" if result["iv_rank"] is not None else "N/A",
    )
    return result


def _fetch_options_sentiment(ticker: str) -> dict:
    """Compute P/C ratio and IV rank from near-term yfinance options chain."""
    try:
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return {"pc_ratio": None, "iv_rank": None}

        chain = t.option_chain(exps[0])
        calls, puts = chain.calls, chain.puts

        call_vol = float(calls["volume"].fillna(0).sum()) if not calls.empty and "volume" in calls.columns else 0.0
        put_vol  = float(puts["volume"].fillna(0).sum())  if not puts.empty  and "volume" in puts.columns  else 0.0
        pc_ratio = round(put_vol / call_vol, 3) if call_vol > 0 else None

        all_iv: list[float] = []
        for df in [calls, puts]:
            if "impliedVolatility" in df.columns:
                all_iv.extend(df["impliedVolatility"].dropna().head(5).tolist())

        iv_rank = None
        if all_iv:
            cur_iv = sum(all_iv) / len(all_iv)
            # Rank within typical 15%–80% IV range
            iv_rank = round(min(100.0, max(0.0, (cur_iv - 0.15) / 0.65 * 100)), 1)

        return {"pc_ratio": pc_ratio, "iv_rank": iv_rank}
    except Exception as e:
        logger.debug("Options sentiment failed for %s: %s", ticker, e)
        return {"pc_ratio": None, "iv_rank": None}


def _fetch_dark_pool_pct(ticker: str, end_date: Optional[str] = None) -> dict:
    """
    Fetch FINRA weekly short-sale volume as a proxy for off-exchange/dark pool activity.
    File: https://cdn.finra.org/equity/regsho/weekly/CNMSshvol{YYYYMMDD}.txt
    Returns dark_pool_pct (OTC short vol / total vol) or None on any failure.
    """
    try:
        today = _today_str()
        as_of_dt = date.fromisoformat(end_date or today)
        # Align to the previous full week's report (Monday-dated)
        days_since_mon = as_of_dt.weekday()
        report_monday = as_of_dt - timedelta(days=days_since_mon + 7)
        date_str = report_monday.strftime("%Y%m%d")
        url = f"https://cdn.finra.org/equity/regsho/weekly/CNMSshvol{date_str}.txt"

        r = _SESSION.get(url, timeout=10)
        if r.status_code != 200:
            return {"dark_pool_pct": None, "dark_pool_trend": None}

        ticker_upper = ticker.upper().split(".")[0]
        for line in r.text.splitlines():
            parts = line.split("|")
            if len(parts) < 5 or parts[0] != ticker_upper:
                continue
            total_vol = _safe_float(parts[4])
            short_vol = _safe_float(parts[2])
            if total_vol and total_vol > 0 and short_vol is not None:
                return {
                    "dark_pool_pct": round(short_vol / total_vol, 4),
                    "dark_pool_trend": None,
                }
            break

        return {"dark_pool_pct": None, "dark_pool_trend": None}
    except Exception as e:
        logger.debug("Dark pool fetch failed for %s: %s", ticker, e)
        return {"dark_pool_pct": None, "dark_pool_trend": None}
