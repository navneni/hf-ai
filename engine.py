"""
HF-AI Engine — CLI entry point.

Usage:
    python engine.py --tickers AAPL MSFT TCS.NS
    python engine.py --tickers AAPL --dry-run
    python engine.py --tickers AAPL MSFT --backtest --start 2023-01-01 --end 2024-12-31
    python engine.py --health
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

# ------------------------------------------------------------------ logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)
_file_handler = logging.FileHandler(_LOG_DIR / "engine.log")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger("engine")


# ------------------------------------------------------------------ CLI

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="engine.py",
        description="HF-AI Engine — Quantitative trading signal engine (US + India)",
    )
    p.add_argument("--tickers", nargs="+", metavar="TICKER",
                   help="Tickers to analyse. Suffix .NS = NSE, .BO = BSE, no suffix = US")
    p.add_argument("--start", dest="start_date", metavar="YYYY-MM-DD",
                   help="Start date (backtesting)")
    p.add_argument("--end", dest="end_date", metavar="YYYY-MM-DD",
                   help="End date (backtesting, default: today)")
    p.add_argument("--cash", type=float, default=100_000,
                   help="Starting portfolio cash (default: 100000)")
    p.add_argument("--margin", type=float, default=0.0,
                   help="Margin requirement 0.0–1.0 (0 = no shorts)")
    p.add_argument("--engines", nargs="+", metavar="ENGINE",
                   help="Run only these engines (default: all)")
    p.add_argument("--backtest", action="store_true",
                   help="Run over --start/--end date range")
    p.add_argument("--show-signals", action="store_true",
                   help="Print per-engine signal breakdown")
    p.add_argument("--show-analytics", action="store_true",
                   help="Print portfolio analytics after backtest")
    p.add_argument("--no-news", action="store_true",
                   help="Skip the news sentiment engine")
    p.add_argument("--fetch-only", action="store_true",
                   help="Fetch and cache data without running engines")
    p.add_argument("--refresh", action="store_true",
                   help="Bypass MongoDB cache, force live fetch")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate config and connection without running engines")
    p.add_argument("--explain", action="store_true",
                   help="Generate Ollama narrative after each decision")
    p.add_argument("--health", action="store_true",
                   help="Show system health report and exit")
    p.add_argument("--history", type=int, metavar="N",
                   help="Show last N run summaries and exit")
    p.add_argument("--screens", metavar="SCREEN",
                   help='Show top stocks for a screen (e.g. buffett_screen) or "all" for summary matrix')
    p.add_argument("--screens-ticker", metavar="TICKER",
                   help="Show all screen scores for a specific ticker")
    p.add_argument("--screens-date", metavar="YYYY-MM-DD",
                   help="Filter screen results to a specific date")
    p.add_argument("--schedule", metavar="CRON",
                   help='Schedule daily runs, e.g. "0 18 * * 1-5"')
    p.add_argument("--output", metavar="FILE",
                   help="Save decisions to JSON file")
    p.add_argument("--config", default="config/engine.yaml",
                   help="Path to engine.yaml (default: config/engine.yaml)")
    return p


# ------------------------------------------------------------------ commands

def _cmd_health(engine) -> None:
    from core.monitor import HealthMetrics
    db  = engine.db
    hm  = HealthMetrics(db)
    G   = "\033[32m"
    R   = "\033[31m"
    Y   = "\033[33m"
    RST = "\033[0m"

    print(f"\n{'='*56}")
    print("  HF-AI Engine — Health Report")
    print(f"{'='*56}")

    # MongoDB
    try:
        db._client.admin.command("ping")
        print(f"  MongoDB:        {G}CONNECTED{RST}  ({db.DB_NAME})")
    except Exception:
        print(f"  MongoDB:        {R}FAIL{RST}")
        return

    print(f"  Engines:        {len(engine.registry)} registered")

    # Last run
    lr = hm.last_run_status()
    if lr["status"] == "no_runs":
        print(f"  Last run:       (none)")
    else:
        color = G if lr["status"] == "success" else R
        tickers = ", ".join(lr.get("tickers") or [])
        print(f"  Last run:       {color}{lr['status']:8}{RST}  {lr['started_at']}  [{tickers}]")
        if lr.get("error"):
            print(f"  Error:          {R}{lr['error'][:80]}{RST}")

    # Data freshness
    freshness = hm.data_freshness()
    if freshness:
        print(f"\n  Data freshness ({len(freshness)} cached entries):")
        stale = [r for r in freshness if r["is_stale"]]
        fresh = [r for r in freshness if not r["is_stale"]]
        for r in stale[:8]:
            age = f"{r['age_hours']:.1f}h" if r["age_hours"] is not None else "?"
            print(f"    {Y}STALE{RST}  {r['ticker']:10} {r['data_type']:12} age={age} ttl={r['ttl_hours']:.0f}h")
        if len(fresh) > 0:
            print(f"    {G}OK{RST}     {len(fresh)} entries within TTL")

    # Signal distribution (last 7d)
    dist = hm.signal_distribution_7d()
    if dist:
        print(f"\n  Signal distribution (last 7 days):")
        for eng, counts in sorted(dist.items()):
            b = counts.get("bullish", 0)
            n = counts.get("neutral", 0)
            br = counts.get("bearish", 0)
            total = b + n + br
            bar   = (G + "█" * b + RST + Y + "█" * n + RST + R + "█" * br + RST)
            print(f"    {eng:30} {bar}  {G}{b}↑{RST} {Y}{n}→{RST} {R}{br}↓{RST}  ({total} signals)")

    # Collection counts
    counts = hm.collection_counts()
    print(f"\n  Collection counts:")
    for col, cnt in counts.items():
        print(f"    {col:20} {cnt:>8,}")

    print(f"{'='*56}\n")


def _cmd_history(engine, n: int) -> None:
    from pymongo import DESCENDING
    runs = list(engine.db.runs.find({}, sort=[("started_at", DESCENDING)], limit=n))
    print(f"\n=== Last {n} Runs ===\n")
    for r in runs:
        status = r.get("status", "?")
        tickers = ", ".join(r.get("tickers", []))
        started = str(r.get("started_at", "?"))[:19]
        color = "\033[32m" if status == "success" else "\033[31m"
        reset = "\033[0m"
        print(f"  {r['run_id']}  {color}{status:8}{reset}  {started}  [{tickers}]")
    print()


def _display_results(result, show_signals: bool) -> None:
    from colorama import Fore, Style, init
    init(autoreset=True)

    print(f"\n{'='*60}")
    print(f"  Run: {result.run_id}  |  Status: {result.status}")
    print(f"{'='*60}\n")

    for ticker, decision in result.decisions.items():
        action = decision.action.upper()
        color = {
            "BUY": Fore.GREEN, "COVER": Fore.GREEN,
            "SELL": Fore.RED,  "SHORT": Fore.RED,
            "HOLD": Fore.YELLOW,
        }.get(action, "")
        print(f"  {ticker:12}  {color}{action:6}{Style.RESET_ALL}  "
              f"qty={decision.quantity:5}  conf={decision.confidence:5.1f}%  "
              f"{decision.reasoning}")

        if show_signals and decision.signals:
            for eng_name, sig in sorted(decision.signals.items()):
                sig_color = Fore.GREEN if sig.signal == "bullish" else \
                            Fore.RED if sig.signal == "bearish" else Fore.YELLOW
                print(f"    {eng_name:30} {sig_color}{sig.signal:8}{Style.RESET_ALL} "
                      f"conf={sig.confidence:5.1f}  {sig.reasoning}")
        if decision.narrative:
            print(f"\n  Narrative: {decision.narrative}\n")
    print()


def _display_backtest_results(result) -> None:
    m = result.metrics
    cfg = result.config
    print(f"\n{'='*62}")
    print(f"  Backtest: {cfg.start_date} → {cfg.end_date}  |  {', '.join(cfg.tickers)}")
    print(f"{'='*62}")
    print(f"  Initial Cash:        ${cfg.initial_cash:>13,.2f}")
    print(f"  Final Value:         ${m.get('final_value', 0):>13,.2f}")
    print(f"  Total Return:        {m.get('total_return', 0)*100:>13.2f}%")
    print(f"  Annualized Return:   {m.get('annualized_return', 0)*100:>13.2f}%")
    print(f"  Alpha vs Benchmark:  {m.get('alpha', 0)*100:>13.2f}%")
    print(f"  Max Drawdown:        {m.get('max_drawdown', 0)*100:>13.2f}%")
    print(f"  Sharpe Ratio:        {m.get('sharpe_ratio', 0):>13.3f}")
    sortino = m.get('sortino_ratio')
    print(f"  Sortino Ratio:       {f'{sortino:.3f}' if sortino is not None else 'N/A':>13}")
    calmar = m.get('calmar_ratio')
    print(f"  Calmar Ratio:        {f'{calmar:.3f}' if calmar is not None else 'N/A':>13}")
    print(f"  Annualized Vol:      {m.get('annualized_vol', 0)*100:>13.2f}%")
    print(f"  Win Rate:            {m.get('win_rate', 0)*100:>13.1f}%")
    pf = m.get('profit_factor')
    print(f"  Profit Factor:       {f'{pf:.3f}' if pf is not None else 'N/A':>13}")
    print(f"  Total Trades:        {m.get('total_trades', 0):>13}")
    print(f"  Trading Days:        {m.get('n_trading_days', 0):>13}")
    print(f"{'='*62}\n")

    monthly = result.monthly_returns
    if monthly:
        print("  Monthly Returns:")
        for row in monthly:
            ret = row["return"] * 100
            sign = "+" if ret >= 0 else ""
            print(f"    {row['month']}   {sign}{ret:.2f}%   ${row['end_value']:,.0f}")
        print()


def _display_analytics(result) -> None:
    """Print portfolio analytics after a backtest run."""
    from analytics import drawdown_series, monthly_returns_heatmap, sector_exposure

    print(f"\n{'='*56}")
    print("  Portfolio Analytics")
    print(f"{'='*56}")

    # Sector exposure
    try:
        se = sector_exposure(result.config.tickers)
        print("\n  Sector Exposure:")
        for sector, pct in sorted(se["sectors"].items(), key=lambda x: -x[1]):
            flag = "  ⚠ >40%" if pct > 0.40 else ""
            print(f"    {sector:30} {pct*100:5.1f}%{flag}")
        if se["unknown"]:
            print(f"    Unknown: {', '.join(se['unknown'])}")
    except Exception as e:
        logger.debug("Sector exposure failed: %s", e)

    # Drawdown series (max drawdown + recovery)
    if result.history:
        dd = drawdown_series(result.history)
        print(f"\n  Drawdown Analysis:")
        print(f"    Max Drawdown:   {dd['max_drawdown']*100:.2f}%  (on {dd['max_dd_date']})")
        if dd["recovery_days"] is not None:
            print(f"    Recovery:       {dd['recovery_days']} days")
        else:
            print(f"    Recovery:       not yet recovered within backtest period")

    # Monthly returns heatmap
    if result.monthly_returns:
        hm = monthly_returns_heatmap(result.monthly_returns)
        print(f"\n  Monthly Returns Heatmap:")
        months = ["01","02","03","04","05","06","07","08","09","10","11","12"]
        header = "      " + "  ".join(m for m in months)
        print(f"  {header}")
        for year in sorted(hm["grid"].keys()):
            row = ""
            for mm in months:
                ret = hm["grid"][year].get(mm)
                if ret is None:
                    row += "   -- "
                else:
                    pct = ret * 100
                    col = "\033[32m" if pct > 0 else "\033[31m"
                    row += f" {col}{pct:+4.1f}\033[0m"
            yr_ret = hm["yearly"].get(year, 0) * 100
            print(f"  {year}  {row}   {yr_ret:+5.1f}%")

    print(f"{'='*56}\n")


def _cmd_schedule(engine, cron_expr: str, tickers: list, engines_filter, no_news: bool) -> None:
    """Run the engine on a cron schedule using the `schedule` package."""
    import schedule as sched
    import time

    def _parse_cron(expr: str) -> tuple[str, list[str]]:
        """Parse 'M H * * DOW' → (time_str, [day_names]). Basic patterns only."""
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Expected 5-part cron expression, got: {expr!r}")
        minute, hour = parts[0], parts[1]
        dow = parts[4]
        time_str = f"{int(hour):02d}:{int(minute):02d}"

        _DOW = {
            "0": "sunday", "7": "sunday", "sun": "sunday",
            "1": "monday",   "mon": "monday",
            "2": "tuesday",  "tue": "tuesday",
            "3": "wednesday","wed": "wednesday",
            "4": "thursday", "thu": "thursday",
            "5": "friday",   "fri": "friday",
            "6": "saturday", "sat": "saturday",
        }
        if dow == "*":
            days = list(_DOW.values())[:7]
        else:
            days_raw = dow.replace("-", ",")
            expanded = []
            for part in days_raw.split(","):
                if "-" in part:
                    lo, hi = part.split("-")
                    expanded += [str(i) for i in range(int(lo), int(hi) + 1)]
                else:
                    expanded.append(part)
            days = [_DOW[d.lower()] for d in expanded if d.lower() in _DOW]
        return time_str, list(dict.fromkeys(days))   # unique, preserving order

    def _run_job():
        try:
            result = engine.run(tickers=tickers, engines=engines_filter)
            logger.info("Scheduled run complete: %s", result.run_id)
        except Exception as e:
            logger.error("Scheduled run failed: %s", e)

    time_str, days = _parse_cron(cron_expr)
    logger.info("Scheduling at %s on: %s", time_str, ", ".join(days))
    print(f"\n  Scheduled: {', '.join(days)} at {time_str}")
    print(f"  Tickers:   {', '.join(tickers)}")
    print("  Press Ctrl+C to stop.\n")

    _DAY_OBJ = {
        "monday": sched.every().monday, "tuesday": sched.every().tuesday,
        "wednesday": sched.every().wednesday, "thursday": sched.every().thursday,
        "friday": sched.every().friday, "saturday": sched.every().saturday,
        "sunday": sched.every().sunday,
    }
    for day in days:
        _DAY_OBJ[day].at(time_str).do(_run_job)

    try:
        while True:
            sched.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n  Scheduler stopped.")


def _save_backtest_output(result, path: str) -> None:
    import json
    data = {
        "run_id":          result.run_id,
        "config":          {
            "tickers":    result.config.tickers,
            "start_date": result.config.start_date,
            "end_date":   result.config.end_date,
        },
        "metrics":         result.metrics,
        "monthly_returns": result.monthly_returns,
        "total_trades":    len(result.trades),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Backtest results saved to %s", path)


def _save_output(result, path: str) -> None:
    import json
    from dataclasses import asdict
    data = {
        "run_id": result.run_id,
        "status": result.status,
        "decisions": {
            t: {
                "action": d.action,
                "quantity": d.quantity,
                "confidence": d.confidence,
                "reasoning": d.reasoning,
            }
            for t, d in result.decisions.items()
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Results saved to %s", path)


# ------------------------------------------------------------------ main

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        from core.write_engine import WriteEngine
        engine = WriteEngine(config_path=args.config, force_refresh=args.refresh)
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    # --screens-ticker TICKER
    if args.screens_ticker:
        from core.screen_store import ScreenStore
        ss = ScreenStore(engine.db)
        ss.print_ticker_scorecard(args.screens_ticker.upper(), args.screens_date)
        return

    # --screens SCREEN | all
    if args.screens:
        from core.screen_store import ScreenStore, ALL_SCREENS
        ss = ScreenStore(engine.db)
        if args.screens.lower() == "all":
            ticker_list = args.tickers or None
            ss.print_summary_matrix(ticker_list, args.screens_date)
        else:
            screen_name = args.screens.lower()
            if screen_name not in ALL_SCREENS:
                close = [s for s in ALL_SCREENS if args.screens.lower() in s]
                if close:
                    screen_name = close[0]
                    logger.info("Matched '%s' → '%s'", args.screens, screen_name)
                else:
                    print(f"\n  Unknown screen '{args.screens}'. Available:\n  " +
                          "\n  ".join(ALL_SCREENS) + "\n")
                    return
            ss.print_top_stocks(screen_name, n=25, as_of_date=args.screens_date)
        return

    # --health
    if args.health:
        _cmd_health(engine)
        return

    # --history N
    if args.history:
        _cmd_history(engine, args.history)
        return

    if not args.tickers and not args.dry_run:
        parser.print_help()
        sys.exit(0)

    tickers = args.tickers or []

    # --fetch-only
    if getattr(args, "fetch_only", False):
        engine.fetch_only(tickers, args.end_date)
        logger.info("Data fetched and cached. Run without --fetch-only to analyse.")
        return

    # Filter engines
    selected_engines = args.engines
    if args.no_news and selected_engines is None:
        all_meta = engine.registry.list_active()
        selected_engines = [e["name"] for e in all_meta if e["name"] != "news_sentiment"]

    # --backtest
    if args.backtest:
        if not args.start_date:
            logger.error("--backtest requires --start YYYY-MM-DD")
            sys.exit(1)
        from datetime import date as _date
        from core.backtest import BacktestConfig, BacktestFramework
        bt_config = BacktestConfig(
            tickers=tickers,
            start_date=args.start_date,
            end_date=args.end_date or str(_date.today()),
            initial_cash=args.cash,
            engines=selected_engines,
        )
        framework = BacktestFramework(engine, engine.store, bt_config)
        try:
            bt_result = framework.run()
        except Exception as e:
            logger.error("Backtest failed: %s", e)
            sys.exit(1)
        _display_backtest_results(bt_result)
        if args.show_analytics:
            _display_analytics(bt_result)
        if args.output:
            _save_backtest_output(bt_result, args.output)
        return

    # --schedule
    if args.schedule:
        _cmd_schedule(engine, args.schedule, tickers, selected_engines, args.no_news)
        return

    # Standard analysis run
    result = engine.run(
        tickers=tickers,
        engines=selected_engines,
        as_of_date=args.end_date,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        # Generate Ollama narratives if --explain requested
        if args.explain:
            from narrator import generate_narrative
            for decision in result.decisions.values():
                narrative = generate_narrative(decision, engine.config._data)
                if narrative:
                    decision.narrative = narrative

        _display_results(result, show_signals=args.show_signals)

        if args.output:
            _save_output(result, args.output)


if __name__ == "__main__":
    main()
