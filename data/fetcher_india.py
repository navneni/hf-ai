"""
India market data fetcher.
Primary:       yfinance (NSE/BSE via .NS / .BO suffix).
Supplementary: screener.in HTML scraper (10-yr financials, promoter holdings).
India-specific: NSE FII/DII, bulk deals, promoter quarterly disclosures.
Macro:         India VIX, Nifty vs 200d MA, USD/INR 30d change, RBI repo rate.

All functions return [] / {} / None on failure — never raise.
"""
from __future__ import annotations
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
})

_NSE_HEADERS = {
    **_SESSION.headers,
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}


def _today_str() -> str:
    return str(date.today())


def _safe_float(val) -> Optional[float]:
    try:
        if val is None:
            return None
        f = float(str(val).replace(",", ""))
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    f = _safe_float(val)
    return int(f) if f is not None else None


def _symbol(ticker: str) -> str:
    """Strip .NS / .BO suffix → base symbol for screener.in and NSE APIs."""
    return ticker.replace(".NS", "").replace(".BO", "").upper()


def _is_historical(end_date: Optional[str]) -> bool:
    return end_date is not None and end_date < _today_str()


def _row(df, *keys):
    if df is None:
        return None
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _safe_val(row, col):
    if row is None:
        return None
    try:
        v = row[col] if hasattr(row, "__getitem__") else None
        return _safe_float(v)
    except Exception:
        return None


# ─────────────────────────────────────────────── prices (India)

def fetch_prices_india(ticker: str, end_date: Optional[str] = None) -> list[dict]:
    """
    Fetch 2 years of daily OHLCV for an Indian ticker via yfinance.
    Ticker must include .NS or .BO suffix.
    """
    end   = date.fromisoformat(end_date) if end_date else date.today()
    start = end - timedelta(days=730)
    today = _today_str()
    is_hist = _is_historical(end_date)

    try:
        hist = yf.Ticker(ticker).history(
            start=str(start), end=str(end + timedelta(days=1)),
            auto_adjust=True, actions=False,
        )
    except Exception as e:
        logger.warning("India price fetch failed for %s: %s", ticker, e)
        return []

    if hist is None or hist.empty:
        return []

    records = []
    for dt, row in hist.iterrows():
        dt_str = str(dt.date()) if hasattr(dt, "date") else str(dt)[:10]
        if end_date and dt_str > end_date:
            continue
        records.append({
            "ticker":       ticker,
            "date":         dt_str,
            "open":         round(float(row["Open"]),   2),
            "high":         round(float(row["High"]),   2),
            "low":          round(float(row["Low"]),    2),
            "close":        round(float(row["Close"]),  2),
            "adj_close":    round(float(row["Close"]),  2),
            "volume":       int(row["Volume"]),
            "source":       "yfinance",
            "is_historical": is_hist,
            "fetched_at":   datetime.now(tz=timezone.utc),
        })
    records.sort(key=lambda r: r["date"])
    logger.info("India prices: %d records for %s", len(records), ticker)
    return records


# ─────────────────────────────────────────────── financials (India)

def fetch_financials_india(
    ticker: str, end_date: Optional[str] = None
) -> list[dict]:
    """
    Annual financials for Indian ticker.
    Primary: yfinance (4 years). Supplement: screener.in (up to 10 years).
    """
    yf_records   = _yf_financials_india(ticker, end_date)
    scrn_records = _screener_financials(ticker, end_date)

    yf_periods = {r["period_end"] for r in yf_records}
    merged     = yf_records[:]
    for r in scrn_records:
        if r["period_end"] not in yf_periods:
            merged.append(r)

    merged.sort(key=lambda r: r["period_end"])
    logger.info("India financials: %d records for %s", len(merged), ticker)
    return merged


def _yf_financials_india(ticker: str, end_date: Optional[str]) -> list[dict]:
    is_hist = _is_historical(end_date)
    records = []
    try:
        t        = yf.Ticker(ticker)
        income   = t.financials
        balance  = t.balance_sheet
        cashflow = t.cashflow
    except Exception as e:
        logger.debug("yfinance India financials failed for %s: %s", ticker, e)
        return []

    if income is None or income.empty:
        return []

    for col in income.columns:
        period_end = str(col.date() if hasattr(col, "date") else col)[:10]
        if end_date and period_end > end_date:
            continue
        year = period_end[:4]

        def _v(df, *keys):
            row = _row(df, *keys)
            return _safe_val(row, col) if row is not None else None

        records.append({
            "ticker":              ticker,
            "market":              "IN",
            "period":              year,
            "period_end":          period_end,
            "revenue":             _v(income, "Total Revenue", "Revenue"),
            "gross_profit":        _v(income, "Gross Profit"),
            "operating_income":    _v(income, "Operating Income", "Ebit"),
            "net_income":          _v(income, "Net Income", "Net Income Common Stockholders"),
            "eps":                 _v(income, "Basic EPS", "Diluted EPS"),
            "ebitda":              _v(income, "EBITDA", "Normalized EBITDA"),
            "total_assets":        _v(balance, "Total Assets"),
            "total_debt":          _v(balance, "Long Term Debt"),
            "cash":                _v(balance, "Cash And Cash Equivalents",
                                      "Cash Cash Equivalents And Short Term Investments"),
            "equity":              _v(balance, "Stockholders Equity",
                                      "Total Equity Gross Minority Interest"),
            "current_assets":      _v(balance, "Current Assets"),
            "current_liabilities": _v(balance, "Current Liabilities"),
            "operating_cash_flow": _v(cashflow, "Operating Cash Flow"),
            "capex":               abs(_v(cashflow, "Capital Expenditure") or 0) or None,
            "free_cash_flow":      _v(cashflow, "Free Cash Flow"),
            "source":              "yfinance",
            "is_historical":       is_hist,
            "fetched_at":          datetime.now(tz=timezone.utc),
        })
    return records


def _screener_financials(
    ticker: str, end_date: Optional[str] = None
) -> list[dict]:
    """
    Scrape 10-year annual financials from screener.in.
    URL: https://www.screener.in/company/{SYMBOL}/consolidated/
    Returns [] on any failure — yfinance data is still used.
    """
    symbol  = _symbol(ticker)
    is_hist = _is_historical(end_date)
    url     = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        r = _SESSION.get(url, timeout=15)
        if r.status_code == 404:
            url = f"https://www.screener.in/company/{symbol}/"
            r   = _SESSION.get(url, timeout=15)
        if r.status_code != 200:
            return []

        from bs4 import BeautifulSoup
        soup    = BeautifulSoup(r.text, "lxml")
        records = _parse_screener_annual(soup, ticker, is_hist, end_date)
        logger.info("screener.in: %d annual records for %s", len(records), ticker)
        return records
    except Exception as e:
        logger.debug("screener.in financials failed for %s: %s", ticker, e)
        return []


def _parse_screener_annual(
    soup, ticker: str, is_hist: bool, end_date: Optional[str]
) -> list[dict]:
    """
    Parse the annual P&L section from screener.in HTML.
    Table id: 'profit-loss'
    """
    records = []
    try:
        section = soup.find("section", {"id": "profit-loss"})
        if not section:
            return []
        table = section.find("table", {"class": "data-table"})
        if not table:
            return []

        headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
        rows    = {}
        for tr in table.find("tbody").find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            rows[label] = [c.get_text(strip=True).replace(",", "").replace("₹", "") for c in cells[1:]]

        years = [h for h in headers[1:] if re.match(r"\d{4}", h)]
        now   = datetime.now(tz=timezone.utc)

        for i, year_str in enumerate(years):
            year = year_str[:4]
            period_end = f"{year}-03-31"   # Indian FY ends March 31
            if end_date and period_end > end_date:
                continue

            def _r(label: str) -> Optional[float]:
                vals = rows.get(label)
                if vals and i < len(vals):
                    return _safe_float(vals[i])
                return None

            # Convert Cr → actual (screener uses Crores)
            def _cr(label: str) -> Optional[float]:
                v = _r(label)
                return v * 1e7 if v is not None else None  # 1 Cr = 10M INR

            records.append({
                "ticker":              ticker,
                "market":              "IN",
                "period":              year,
                "period_end":          period_end,
                "revenue":             _cr("Revenue") or _cr("Sales"),
                "operating_income":    _cr("Operating Profit") or _cr("EBIT"),
                "net_income":          _cr("Net Profit"),
                "eps":                 _r("EPS in Rs"),
                "total_assets":        None,
                "equity":              None,
                "operating_cash_flow": _cr("Cash from Operating Activity"),
                "capex":               abs(_cr("Capital Expenditure") or 0) or None,
                "source":              "screener_in",
                "is_historical":       is_hist,
                "fetched_at":          now,
            })
    except Exception as e:
        logger.debug("screener.in table parse failed: %s", e)
    return records


# ─────────────────────────────────────────────── TTM financials (India)

def fetch_ttm_financials_india(
    ticker: str, end_date: Optional[str] = None
) -> Optional[dict]:
    """TTM financials from last 4 quarterly reports (same logic as US)."""
    is_hist = _is_historical(end_date)
    try:
        t          = yf.Ticker(ticker)
        q_income   = t.quarterly_financials
        q_balance  = t.quarterly_balance_sheet
        q_cashflow = t.quarterly_cashflow
    except Exception as e:
        logger.debug("India TTM fetch failed for %s: %s", ticker, e)
        return None

    if q_income is None or q_income.empty:
        return None

    cols = list(q_income.columns)
    if end_date:
        cols = [c for c in cols if str(c.date() if hasattr(c, "date") else c)[:10] <= end_date]
    if not cols:
        return None

    ttm_cols    = cols[:4]
    latest_date = str(ttm_cols[0].date() if hasattr(ttm_cols[0], "date") else ttm_cols[0])[:10]

    def _sum_row(df, *keys):
        for k in keys:
            if df is not None and k in df.index:
                row  = df.loc[k]
                vals = [_safe_float(row.get(c) if hasattr(row, "get") else (
                    row[c] if c in row.index else None)) for c in ttm_cols]
                vals = [v for v in vals if v is not None]
                return sum(vals) if vals else None
        return None

    def _latest(df, *keys):
        if not ttm_cols:
            return None
        c = ttm_cols[0]
        for k in keys:
            if df is not None and k in df.index:
                row = df.loc[k]
                return _safe_float(row.get(c) if hasattr(row, "get") else (
                    row[c] if c in row.index else None))
        return None

    op_cf  = _sum_row(q_cashflow, "Operating Cash Flow")
    capex_ = _sum_row(q_cashflow, "Capital Expenditure", "Purchase Of PPE")
    capex  = abs(capex_) if capex_ is not None else None
    fcf    = (op_cf - capex) if (op_cf is not None and capex is not None) else None

    return {
        "ticker":              ticker,
        "market":              "IN",
        "period":              "TTM",
        "period_end":          latest_date,
        "revenue":             _sum_row(q_income, "Total Revenue", "Revenue"),
        "gross_profit":        _sum_row(q_income, "Gross Profit"),
        "operating_income":    _sum_row(q_income, "Operating Income", "Ebit"),
        "net_income":          _sum_row(q_income, "Net Income", "Net Income Common Stockholders"),
        "total_assets":        _latest(q_balance, "Total Assets"),
        "equity":              _latest(q_balance, "Stockholders Equity",
                                       "Total Equity Gross Minority Interest"),
        "cash":                _latest(q_balance, "Cash And Cash Equivalents",
                                       "Cash Cash Equivalents And Short Term Investments"),
        "total_debt":          _latest(q_balance, "Long Term Debt"),
        "current_assets":      _latest(q_balance, "Current Assets"),
        "current_liabilities": _latest(q_balance, "Current Liabilities"),
        "operating_cash_flow": op_cf,
        "capex":               capex,
        "free_cash_flow":      fcf,
        "source":              "yfinance_ttm",
        "is_historical":       is_hist,
        "fetched_at":          datetime.now(tz=timezone.utc),
    }


# ─────────────────────────────────────────────── ratios (India)

def fetch_ratios_india(
    ticker: str,
    end_date: Optional[str] = None,
    financials: Optional[list[dict]] = None,
) -> dict:
    """
    Fetch latest ratios from yfinance.info for Indian ticker.
    Computes fallbacks from financials where yfinance data is missing.
    """
    today   = _today_str()
    as_of   = end_date or today
    is_hist = _is_historical(end_date)

    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}

    def _i(key, alt=None):
        v = info.get(key) or (info.get(alt) if alt else None)
        return _safe_float(v)

    pe   = _i("trailingPE")
    pb   = _i("priceToBook")
    roe  = _i("returnOnEquity")
    de   = _i("debtToEquity")
    if de is not None and de > 3:     # yfinance sometimes returns % for Indian stocks
        de = de / 100.0
    mktcap = _i("marketCap")
    ev     = _i("enterpriseValue")

    # Compute fallbacks from financials
    gross_m = op_m = net_m = fcf_yield = None
    if financials:
        ttm = next((f for f in reversed(financials) if f.get("period") == "TTM"), None)
        latest = ttm or (financials[-1] if financials else None)
        if latest:
            rev = latest.get("revenue")
            if rev and rev > 0:
                if gross_m is None and latest.get("gross_profit"):
                    gross_m = latest["gross_profit"] / rev
                if op_m is None and latest.get("operating_income"):
                    op_m = latest["operating_income"] / rev
                if net_m is None and latest.get("net_income"):
                    net_m = latest["net_income"] / rev
            if roe is None and latest.get("net_income") and latest.get("equity") and latest["equity"] > 0:
                roe = latest["net_income"] / latest["equity"]
        if mktcap and mktcap > 0 and ttm and ttm.get("free_cash_flow"):
            fcf_yield = ttm["free_cash_flow"] / mktcap

    sector  = info.get("sector")
    industry = info.get("industry")
    name     = info.get("shortName") or info.get("longName")

    return {
        "ticker":           ticker,
        "market":           "IN",
        "date":             as_of,
        "pe_ratio":         pe,
        "pb_ratio":         pb,
        "ps_ratio":         _i("priceToSalesTrailing12Months"),
        "ev_ebitda":        _i("enterpriseToEbitda"),
        "roe":              roe,
        "roa":              _i("returnOnAssets"),
        "roic":             None,
        "debt_to_equity":   de,
        "current_ratio":    _i("currentRatio"),
        "gross_margin":     gross_m,
        "operating_margin": op_m,
        "net_margin":       net_m,
        "fcf_yield":        fcf_yield,
        "dividend_yield":   _i("dividendYield"),
        "peg_ratio":        _i("trailingPegRatio"),
        "market_cap":       mktcap,
        "enterprise_value": ev,
        "sector":           sector,
        "sector_etf":       None,
        "sector_pe":        None,
        "industry":         industry,
        "company_name":     name,
        "source":           "yfinance",
        "is_historical":    is_hist,
        "fetched_at":       datetime.now(tz=timezone.utc),
    }


# ─────────────────────────────────────────────── FII / DII daily flow

def fetch_fii_dii(end_date: Optional[str] = None) -> dict:
    """
    Fetch FII/DII net investment data from NSE.
    Returns a dict with net_fii, net_dii, and last 5-day sums.
    Best-effort — returns empty dict on any failure.
    """
    today   = _today_str()
    as_of   = end_date or today
    is_hist = _is_historical(end_date)

    result: dict = {
        "as_of_date":    as_of,
        "net_fii_today": None,
        "net_dii_today": None,
        "net_fii_5d":    None,
        "net_dii_5d":    None,
        "fii_buy":       None,
        "fii_sell":      None,
        "dii_buy":       None,
        "dii_sell":      None,
        "source":        "nse_api",
        "is_historical": is_hist,
        "fetched_at":    datetime.now(tz=timezone.utc),
    }

    try:
        # NSE FII/DII API endpoint (requires Referer header)
        s = requests.Session()
        s.headers.update(_NSE_HEADERS)
        # First request to get cookies
        s.get("https://www.nseindia.com", timeout=10)
        resp = s.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"NSE API returned {resp.status_code}")
        data = resp.json()

        if isinstance(data, list) and data:
            # Data is list of records [{...}, ...], most recent first
            entry = data[0]
            result["net_fii_today"] = _safe_float(entry.get("netFII") or entry.get("FII_NET"))
            result["net_dii_today"] = _safe_float(entry.get("netDII") or entry.get("DII_NET"))
            result["fii_buy"]       = _safe_float(entry.get("fiiBuy")  or entry.get("FII_BUY"))
            result["fii_sell"]      = _safe_float(entry.get("fiiSell") or entry.get("FII_SELL"))
            result["dii_buy"]       = _safe_float(entry.get("diiBuy")  or entry.get("DII_BUY"))
            result["dii_sell"]      = _safe_float(entry.get("diiSell") or entry.get("DII_SELL"))

            # 5-day rolling net
            recent5 = data[:5]
            fii_nets = [_safe_float(r.get("netFII") or r.get("FII_NET")) for r in recent5]
            dii_nets = [_safe_float(r.get("netDII") or r.get("DII_NET")) for r in recent5]
            fii_nets = [v for v in fii_nets if v is not None]
            dii_nets = [v for v in dii_nets if v is not None]
            if fii_nets:
                result["net_fii_5d"] = round(sum(fii_nets), 2)
            if dii_nets:
                result["net_dii_5d"] = round(sum(dii_nets), 2)

    except Exception as e:
        logger.debug("FII/DII fetch failed: %s", e)

    return result


# ─────────────────────────────────────────────── promoter holdings

def fetch_promoter_holdings(
    ticker: str, end_date: Optional[str] = None
) -> list[dict]:
    """
    Fetch quarterly promoter holding % from screener.in shareholding section.
    Returns list of {quarter, promoter_pct, fii_pct, dii_pct, public_pct}.
    Best-effort — returns [] on failure.
    """
    symbol  = _symbol(ticker)
    is_hist = _is_historical(end_date)
    url     = f"https://www.screener.in/company/{symbol}/consolidated/#shareholding"
    records = []

    try:
        r = _SESSION.get(url, timeout=15)
        if r.status_code != 200:
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")

        # Find shareholding section
        section = (soup.find("section", {"id": "shareholding"}) or
                   soup.find("div", {"id": "shareholding"}))
        if not section:
            return []

        table = section.find("table", {"class": "data-table"})
        if not table:
            return []

        headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
        quarters = headers[1:]  # skip first col "Holder"

        # Build row dict
        row_data: dict[str, list[str]] = {}
        for tr in table.find("tbody").find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            vals  = [c.get_text(strip=True).replace("%", "") for c in cells[1:]]
            row_data[label] = vals

        now = datetime.now(tz=timezone.utc)
        for i, q in enumerate(quarters):
            if end_date and q > end_date[:7]:
                continue
            rec: dict = {
                "ticker":           ticker,
                "quarter":          q,
                "promoter_pct":     None,
                "fii_pct":          None,
                "dii_pct":          None,
                "public_pct":       None,
                "source":           "screener_in",
                "is_historical":    is_hist,
                "fetched_at":       now,
            }
            for label, vals in row_data.items():
                if i < len(vals):
                    v = _safe_float(vals[i])
                    label_l = label.lower()
                    if "promoter" in label_l:
                        rec["promoter_pct"] = v
                    elif "fii" in label_l or "foreign" in label_l:
                        rec["fii_pct"] = v
                    elif "dii" in label_l or "mutual" in label_l or "domestic" in label_l:
                        rec["dii_pct"] = v
                    elif "public" in label_l or "retail" in label_l:
                        rec["public_pct"] = v
            records.append(rec)

        logger.info("Promoter holdings: %d quarters for %s", len(records), ticker)
    except Exception as e:
        logger.debug("Promoter holdings failed for %s: %s", ticker, e)

    return records


# ─────────────────────────────────────────────── bulk deals

def fetch_bulk_deals(
    ticker: str, end_date: Optional[str] = None
) -> list[dict]:
    """
    Fetch recent bulk/block deals from NSE.
    Best-effort — returns [] on failure.
    """
    symbol  = _symbol(ticker)
    is_hist = _is_historical(end_date)
    records = []

    try:
        s = requests.Session()
        s.headers.update(_NSE_HEADERS)
        s.get("https://www.nseindia.com", timeout=10)
        resp = s.get(
            "https://www.nseindia.com/api/bulk-deal-order",
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"NSE bulk deal API {resp.status_code}")

        data = resp.json()
        deals = data if isinstance(data, list) else data.get("data", [])
        now   = datetime.now(tz=timezone.utc)

        for d in deals:
            sym = str(d.get("symbol", "")).upper()
            if sym != symbol:
                continue
            deal_date = str(d.get("date", "") or d.get("BD_DT_DATE", ""))[:10]
            if end_date and deal_date > end_date:
                continue
            records.append({
                "ticker":       ticker,
                "date":         deal_date,
                "client":       d.get("clientName", "") or d.get("BD_CLIENT_NAME", ""),
                "buy_sell":     d.get("buySell", "") or d.get("BD_BUY_SELL", ""),
                "quantity":     _safe_int(d.get("quantity") or d.get("BD_QTY_TRD")),
                "price":        _safe_float(d.get("tradePrice") or d.get("BD_TP_WATP")),
                "deal_type":    d.get("mktType", "bulk"),
                "source":       "nse_api",
                "is_historical": is_hist,
                "fetched_at":   now,
            })
    except Exception as e:
        logger.debug("Bulk deals fetch failed for %s: %s", ticker, e)

    logger.info("Bulk deals: %d records for %s", len(records), ticker)
    return records


# ─────────────────────────────────────────────── India macro

def fetch_macro_india(end_date: Optional[str] = None) -> dict:
    """
    Fetch India macro regime indicators via yfinance.
    India VIX, Nifty 50 vs 200d MA, USD/INR 30d change, RBI repo rate (best-effort).
    """
    today   = _today_str()
    as_of   = end_date or today
    end_dt  = date.fromisoformat(as_of)
    start   = str(end_dt - timedelta(days=410))
    is_hist = _is_historical(end_date)

    result: dict = {
        "date":              as_of,
        "india_vix":         None,
        "india_vix_5d_ma":   None,
        "india_vix_20d_ma":  None,
        "nifty_price":       None,
        "nifty_200d_ma":     None,
        "nifty_vs_200ma":    None,
        "usdinr":            None,
        "usdinr_30d_change": None,
        "rbi_repo_rate":     None,
        "net_fii_5d":        None,
        "market_breadth":    None,
        "is_historical":     is_hist,
        "fetched_at":        datetime.now(tz=timezone.utc),
    }

    # India VIX
    try:
        vix_h = yf.Ticker("INDIAVIX.NS").history(
            start=start, end=str(end_dt + timedelta(days=1)),
            auto_adjust=False, actions=False,
        )
        if vix_h is not None and not vix_h.empty:
            if end_date:
                vix_h = vix_h[vix_h.index.date <= end_dt]
            closes = vix_h["Close"].dropna()
            if not closes.empty:
                result["india_vix"] = round(float(closes.iloc[-1]), 2)
                if len(closes) >= 5:
                    result["india_vix_5d_ma"] = round(float(closes.iloc[-5:].mean()), 2)
                if len(closes) >= 20:
                    result["india_vix_20d_ma"] = round(float(closes.iloc[-20:].mean()), 2)
    except Exception as e:
        logger.debug("India VIX fetch failed: %s", e)

    # Nifty 50 vs 200d MA
    try:
        nifty_h = yf.Ticker("^NSEI").history(
            start=start, end=str(end_dt + timedelta(days=1)),
            auto_adjust=True, actions=False,
        )
        if nifty_h is not None and not nifty_h.empty:
            if end_date:
                nifty_h = nifty_h[nifty_h.index.date <= end_dt]
            closes = nifty_h["Close"].dropna()
            if not closes.empty:
                last = float(closes.iloc[-1])
                result["nifty_price"] = round(last, 2)
                if len(closes) >= 200:
                    ma200 = float(closes.iloc[-200:].mean())
                    result["nifty_200d_ma"] = round(ma200, 2)
                    result["nifty_vs_200ma"] = round((last - ma200) / ma200, 4)
    except Exception as e:
        logger.debug("Nifty macro fetch failed: %s", e)

    # USD/INR exchange rate (30-day change)
    try:
        fx_h = yf.Ticker("USDINR=X").history(
            start=str(end_dt - timedelta(days=60)),
            end=str(end_dt + timedelta(days=1)),
            auto_adjust=False, actions=False,
        )
        if fx_h is not None and not fx_h.empty:
            if end_date:
                fx_h = fx_h[fx_h.index.date <= end_dt]
            closes = fx_h["Close"].dropna()
            if not closes.empty:
                result["usdinr"] = round(float(closes.iloc[-1]), 4)
                if len(closes) >= 30:
                    past30 = float(closes.iloc[-30])
                    result["usdinr_30d_change"] = round(
                        (result["usdinr"] - past30) / past30, 4
                    )
    except Exception as e:
        logger.debug("USD/INR fetch failed: %s", e)

    # RBI Repo Rate (best-effort scrape; fallback to 6.5%)
    result["rbi_repo_rate"] = _fetch_rbi_repo_rate()

    # Market breadth: Nifty sectoral indices above 200d MA
    _BREADTH_TICKERS = ["NIFTYIT.NS", "NIFTYBANK.NS", "NIFTYPHARMA.NS", "NIFTYAUTO.NS"]
    above_200, total_n = 0, 0
    for sym in _BREADTH_TICKERS:
        try:
            h = yf.Ticker(sym).history(
                start=start, end=str(end_dt + timedelta(days=1)),
                auto_adjust=True, actions=False,
            )
            if h is not None and not h.empty:
                if end_date:
                    h = h[h.index.date <= end_dt]
                c = h["Close"].dropna()
                if len(c) >= 200:
                    if float(c.iloc[-1]) > float(c.iloc[-200:].mean()):
                        above_200 += 1
                    total_n += 1
        except Exception:
            pass
    if total_n > 0:
        result["market_breadth"] = round(above_200 / total_n, 3)

    logger.info(
        "India macro: VIX=%.1f nifty_vs_200=%s USDINR=%s",
        result["india_vix"] or 0,
        f"{(result['nifty_vs_200ma'] or 0)*100:.1f}%" if result["nifty_vs_200ma"] is not None else "N/A",
        f"{result['usdinr']:.2f}" if result["usdinr"] else "N/A",
    )
    return result


def _fetch_rbi_repo_rate() -> Optional[float]:
    """
    Best-effort scrape of RBI repo rate from RBI website.
    Falls back to 6.5% (approximate current rate) if scraping fails.
    """
    try:
        r = _SESSION.get(
            "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx",
            timeout=10,
        )
        if r.status_code != 200:
            return 0.065

        # Look for "repo rate" pattern in the HTML
        matches = re.findall(r"repo rate.*?(\d+\.?\d*)\s*per\s*cent", r.text, re.IGNORECASE)
        if matches:
            return round(float(matches[-1]) / 100.0, 4)
    except Exception as e:
        logger.debug("RBI repo rate scrape failed: %s", e)

    return 0.065   # fallback: current RBI repo rate
