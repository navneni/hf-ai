"""Pydantic v2 models for all data types. Used for validation during fetch."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, field_validator


class Price(BaseModel):
    ticker: str
    date: str               # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: int
    adj_close: Optional[float] = None
    source: str = "yfinance"


class Financials(BaseModel):
    ticker: str
    market: str             # "US" | "IN"
    period: str             # "TTM" | "2024" | "2023" | ...
    period_end: str         # YYYY-MM-DD

    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    ebitda: Optional[float] = None

    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    retained_earnings: Optional[float] = None
    ppe: Optional[float] = None                     # net PP&E
    receivables: Optional[float] = None
    sga_expense: Optional[float] = None

    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None                   # always positive (abs value)
    free_cash_flow: Optional[float] = None
    dividends_paid: Optional[float] = None
    depreciation_amortization: Optional[float] = None
    shares_outstanding: Optional[int] = None

    ebit: Optional[float] = None

    source: str = "yfinance"


class Ratios(BaseModel):
    ticker: str
    market: str
    date: str               # as-of date

    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    fcf_yield: Optional[float] = None
    dividend_yield: Optional[float] = None
    peg_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None

    sector: Optional[str] = None
    industry: Optional[str] = None
    company_name: Optional[str] = None
    source: str = "yfinance"


class InsiderTrade(BaseModel):
    ticker: str
    filing_date: str
    transaction_date: str
    transaction_type: str   # "buy" | "sell"
    shares: int
    price: float
    value: float
    insider_name: str
    title: str
    is_open_market: bool = True
    source: str = "yfinance"


class FilingText(BaseModel):
    ticker: str
    market: str
    filing_type: str        # "10-K" | "8-K-MDA" | "annual_report" | "quarterly_mda"
    period_end: str
    text: str
    word_count: int
    source: str = "sec_edgar"
