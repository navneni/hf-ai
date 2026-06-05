"""
S&P 100 Backtest — HF-AI Engine
Capital: $10,000  |  No news  |  Full year 2024

Usage (from project root):
    python scripts/sp100_backtest.py                        # full 2024
    python scripts/sp100_backtest.py --start 2024-06-01 --end 2024-12-31
    python scripts/sp100_backtest.py --quick               # 5 tickers, 30 days (smoke test)

Output:
    logs/sp100_backtest_YYYYMMDD.json   — full metrics + monthly returns
    MongoDB: hf_ai_engine.backtest_results + backtest_metrics
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure project root is on the path when run from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/engine.log", mode="a"),
    ],
)
logger = logging.getLogger("sp100_backtest")

# ─────────────────────────────────────────────── S&P 100 tickers (2024)

SP100 = [
    # Technology (22)
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "AVGO", "ORCL",
    "ADBE", "CRM", "AMD", "QCOM", "TXN", "INTC", "INTU", "IBM",
    "NOW", "AMAT", "MU", "CSCO", "ACN", "KLAC",
    # Healthcare (14)
    "UNH", "JNJ", "LLY", "ABT", "ABBV", "MRK", "TMO", "PFE",
    "DHR", "AMGN", "MDT", "GILD", "CVS", "ISRG",
    # Financials (13)
    "BRK-B", "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW",
    "AXP", "C", "COF", "SPGI", "MCO",
    # Consumer Discretionary (8)
    "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TGT", "BKNG",
    # Consumer Staples (7)
    "WMT", "COST", "PG", "KO", "PEP", "MO", "PM",
    # Communication Services (6)
    "NFLX", "DIS", "T", "VZ", "CMCSA", "CHTR",
    # Energy (6)
    "XOM", "CVX", "COP", "EOG", "SLB", "OXY",
    # Industrials (9)
    "RTX", "HON", "BA", "CAT", "GE", "UPS", "FDX", "LMT", "DE",
    # Financials/Insurance (3)
    "MET", "AIG", "ALL",
    # Utilities (4)
    "NEE", "D", "SO", "DUK",
    # Materials (3)
    "LIN", "APD", "SHW",
    # Payments (2)
    "V", "MA",
    # Pharma/Biotech add (3)
    "BMY", "BIIB", "REGN",
]
# deduplicate preserving order
seen = set()
SP100 = [t for t in SP100 if not (t in seen or seen.add(t))]

QUICK_TICKERS = ["AAPL", "MSFT", "NVDA", "JNJ", "XOM"]   # 5-sector smoke test


# ─────────────────────────────────────────────── main

def main() -> None:
    parser = argparse.ArgumentParser(description="S&P 100 Backtest — HF-AI Engine")
    parser.add_argument("--start",  default="2024-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end",    default="2024-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--cash",   type=float, default=10_000.0, help="Initial capital")
    parser.add_argument("--quick",  action="store_true", help="Smoke test: 5 tickers, 30 days")
    parser.add_argument("--output", default=None, help="Output JSON path (default: logs/)")
    args = parser.parse_args()

    if args.quick:
        tickers    = QUICK_TICKERS
        start_date = "2024-11-01"
        end_date   = "2024-12-31"
        logger.info("Quick smoke test: %d tickers, %s → %s", len(tickers), start_date, end_date)
    else:
        tickers    = SP100
        start_date = args.start
        end_date   = args.end
        logger.info("Full S&P 100 backtest: %d tickers, %s → %s", len(tickers), start_date, end_date)

    logger.info("Capital: $%.0f | No news", args.cash)
    logger.info("Tickers: %s", ", ".join(tickers))

    # ── Build engine (connects to MongoDB, discovers all signal engines)
    from core.write_engine import WriteEngine
    from core.backtest import BacktestConfig, BacktestFramework

    engine = WriteEngine(
        config_path="config/engine.yaml",
        force_refresh=False,
        no_news=True,          # skip news per user request
    )
    logger.info("Engine ready — %d signal engines registered", len(engine.registry))

    # ── Backtest config
    bt_config = BacktestConfig(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        initial_cash=args.cash,
        commission_pct=0.001,   # 0.1% per side (E*Trade / Schwab typical)
        slippage_pct=0.001,     # 0.1% market impact
        market="US",
        engines=None,           # all engines
        benchmark="^GSPC",
    )

    # ── Run backtest
    framework = BacktestFramework(engine, engine.store, bt_config)
    result    = framework.run()

    # ── Display results
    m   = result.metrics
    cfg = result.config
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  S&P 100 Backtest  {cfg.start_date} → {cfg.end_date}")
    print(f"  {len(tickers)} tickers  |  Capital: ${cfg.initial_cash:,.0f}")
    print(sep)
    print(f"  Final Value:         ${m.get('final_value', 0):>13,.2f}")
    print(f"  Total Return:        {m.get('total_return', 0)*100:>13.2f}%")
    print(f"  Annualized Return:   {m.get('annualized_return', 0)*100:>13.2f}%")
    print(f"  Alpha vs S&P 500:    {m.get('alpha', 0)*100:>13.2f}%")
    print(f"  Max Drawdown:        {m.get('max_drawdown', 0)*100:>13.2f}%")
    print(f"  Sharpe Ratio:        {m.get('sharpe_ratio', 0):>13.3f}")
    sortino = m.get('sortino_ratio')
    calmar  = m.get('calmar_ratio')
    print(f"  Sortino Ratio:       {f'{sortino:.3f}' if sortino else 'N/A':>13}")
    print(f"  Calmar Ratio:        {f'{calmar:.3f}' if calmar else 'N/A':>13}")
    print(f"  Win Rate:            {m.get('win_rate', 0)*100:>13.1f}%")
    pf = m.get('profit_factor')
    print(f"  Profit Factor:       {f'{pf:.3f}' if pf else 'N/A':>13}")
    print(f"  Total Trades:        {m.get('total_trades', 0):>13}")
    print(f"  Trading Days:        {m.get('n_trading_days', 0):>13}")
    print(sep)

    if result.monthly_returns:
        print("\n  Monthly Returns:")
        for row in result.monthly_returns:
            ret  = row["return"] * 100
            sign = "+" if ret >= 0 else ""
            bar  = ("▓" * min(20, int(abs(ret) * 2))) if ret >= 0 else ("░" * min(20, int(abs(ret) * 2)))
            print(f"    {row['month']}  {sign}{ret:6.2f}%  {bar}  ${row['end_value']:>10,.0f}")
        print()

    # ── Analytics
    if result.history:
        from analytics import drawdown_series, monthly_returns_heatmap
        dd = drawdown_series(result.history)
        print(f"  Max Drawdown Date:   {dd['max_dd_date']}")
        recovery = dd["recovery_days"]
        print(f"  Recovery:            {'%d days' % recovery if recovery else 'Not recovered in period'}")

    # ── Save to JSON
    output_path = args.output or f"logs/sp100_backtest_{date.today().strftime('%Y%m%d')}.json"
    Path(output_path).parent.mkdir(exist_ok=True)
    output_data = {
        "run_id":          result.run_id,
        "generated_at":    datetime.now().isoformat(),
        "config": {
            "tickers":      tickers,
            "n_tickers":    len(tickers),
            "start_date":   start_date,
            "end_date":     end_date,
            "initial_cash": args.cash,
            "no_news":      True,
        },
        "metrics":          m,
        "monthly_returns":  result.monthly_returns,
        "total_trades":     len(result.trades),
        "trades":           result.trades[:500],  # cap at 500 to keep file manageable
    }
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}")
    print(f"  MongoDB run_id: {result.run_id}\n")


if __name__ == "__main__":
    main()
