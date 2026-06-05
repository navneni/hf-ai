"""
ScreenStore — query and display clean investor screen results.
Reads from hf_ai_engine.screen_results collection.

All 13 screen names:
  buffett_screen, graham_screen, lynch_screen, fisher_screen, munger_screen,
  burry_screen, ackman_screen, wood_screen, druckenmiller, taleb_screen,
  damodaran_screen, pabrai_screen, jhunjhunwala
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

ALL_SCREENS = [
    "buffett_screen", "graham_screen", "lynch_screen", "fisher_screen",
    "munger_screen", "burry_screen", "ackman_screen", "wood_screen",
    "druckenmiller", "taleb_screen", "damodaran_screen", "pabrai_screen",
    "jhunjhunwala",
]

_SCREEN_LABELS = {
    "buffett_screen":   "Buffett",
    "graham_screen":    "Graham",
    "lynch_screen":     "Lynch",
    "fisher_screen":    "Fisher",
    "munger_screen":    "Munger",
    "burry_screen":     "Burry",
    "ackman_screen":    "Ackman",
    "wood_screen":      "Wood",
    "druckenmiller":    "Druckenmiller",
    "taleb_screen":     "Taleb",
    "damodaran_screen": "Damodaran",
    "pabrai_screen":    "Pabrai",
    "jhunjhunwala":     "Jhunjhunwala",
}


class ScreenStore:
    """Query and format screen results from MongoDB."""

    def __init__(self, db):
        self._db = db

    # ─────────────────────────────────── top stocks per screen

    def top_stocks(
        self,
        screen: str,
        n: int = 20,
        as_of_date: Optional[str] = None,
        signal_filter: Optional[str] = None,   # "bullish" | "bearish" | "neutral" | None (all)
    ) -> list[dict]:
        """
        Top n stocks for a given screen ordered by total_score descending.
        as_of_date: filter to a specific date (default: latest available).
        signal_filter: restrict to "bullish", "bearish", or "neutral" only.
        """
        filt: dict = {"screen": screen}
        if as_of_date:
            filt["as_of_date"] = as_of_date
        else:
            # Use most recent date available for this screen
            latest = self._db.screen_results.find_one(
                {"screen": screen}, {"as_of_date": 1}, sort=[("as_of_date", -1)]
            )
            if latest:
                filt["as_of_date"] = latest["as_of_date"]
        if signal_filter:
            filt["signal"] = signal_filter

        return list(
            self._db.screen_results.find(filt, {"_id": 0})
            .sort("total_score", -1)
            .limit(n)
        )

    # ─────────────────────────────────── all screens for one ticker

    def ticker_scorecard(
        self,
        ticker: str,
        as_of_date: Optional[str] = None,
    ) -> list[dict]:
        """
        All screen results for a single ticker on a given date (latest if None).
        Returns list sorted by total_score descending.
        """
        filt: dict = {"ticker": ticker}
        if as_of_date:
            filt["as_of_date"] = as_of_date
        else:
            latest = self._db.screen_results.find_one(
                {"ticker": ticker}, {"as_of_date": 1}, sort=[("as_of_date", -1)]
            )
            if latest:
                filt["as_of_date"] = latest["as_of_date"]

        return list(
            self._db.screen_results.find(filt, {"_id": 0})
            .sort("total_score", -1)
        )

    # ─────────────────────────────────── cross-screen summary (matrix)

    def summary_matrix(
        self,
        tickers: Optional[list[str]] = None,
        as_of_date: Optional[str] = None,
        min_screens_passed: int = 1,
    ) -> dict:
        """
        Build a matrix {ticker: {screen: total_score}} for all tickers that pass
        at least `min_screens_passed` screens with signal == "bullish".

        Returns:
          {
            "date":    str,
            "matrix":  {ticker: {screen_label: score_or_None}},
            "summary": [{ticker, bullish_screens, avg_score, top_screen}],
          }
        """
        filt: dict = {}
        if as_of_date:
            filt["as_of_date"] = as_of_date
        else:
            latest = self._db.screen_results.find_one(
                {}, {"as_of_date": 1}, sort=[("as_of_date", -1)]
            )
            if latest:
                filt["as_of_date"] = latest["as_of_date"]
                as_of_date = latest["as_of_date"]

        if tickers:
            filt["ticker"] = {"$in": tickers}

        docs = list(self._db.screen_results.find(filt, {"_id": 0}))
        if not docs:
            return {"date": as_of_date, "matrix": {}, "summary": []}

        # Build matrix
        matrix: dict[str, dict[str, Optional[float]]] = {}
        for doc in docs:
            t  = doc["ticker"]
            s  = doc["screen"]
            sc = doc.get("total_score")
            matrix.setdefault(t, {})[s] = sc

        # Summary: count bullish screens, avg score
        summary = []
        for t, scores in matrix.items():
            bullish_docs = [
                d for d in docs
                if d["ticker"] == t and d.get("signal") == "bullish"
            ]
            if len(bullish_docs) < min_screens_passed:
                continue
            avg = sum(v for v in scores.values() if v is not None) / max(1, len(scores))
            top = max(scores.items(), key=lambda x: x[1] or 0, default=(None, 0))
            summary.append({
                "ticker":          t,
                "bullish_screens": len(bullish_docs),
                "total_screens":   len(scores),
                "avg_score":       round(avg, 4),
                "top_screen":      _SCREEN_LABELS.get(top[0], top[0]),
                "top_score":       round(top[1], 4) if top[1] else None,
            })

        summary.sort(key=lambda r: (-r["bullish_screens"], -r["avg_score"]))
        return {"date": as_of_date, "matrix": matrix, "summary": summary}

    # ─────────────────────────────────── criteria breakdown

    def criteria_detail(
        self, ticker: str, screen: str, as_of_date: Optional[str] = None
    ) -> Optional[dict]:
        """Full criteria pass/fail breakdown for one ticker + screen."""
        filt: dict = {"ticker": ticker, "screen": screen}
        if as_of_date:
            filt["as_of_date"] = as_of_date
        return self._db.screen_results.find_one(
            filt, {"_id": 0}, sort=[("as_of_date", -1)]
        )

    # ─────────────────────────────────── available dates

    def available_dates(self, screen: Optional[str] = None, n: int = 10) -> list[str]:
        filt = {"screen": screen} if screen else {}
        pipeline = [
            {"$match": filt},
            {"$group": {"_id": "$as_of_date"}},
            {"$sort": {"_id": -1}},
            {"$limit": n},
        ]
        return [doc["_id"] for doc in self._db.screen_results.aggregate(pipeline) if doc.get("_id")]

    # ─────────────────────────────────── formatted display

    def print_top_stocks(
        self,
        screen: str,
        n: int = 20,
        as_of_date: Optional[str] = None,
        signal_filter: Optional[str] = None,   # None = all signals, ordered by score
    ) -> None:
        G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; D = "\033[90m"; RST = "\033[0m"
        label = _SCREEN_LABELS.get(screen, screen)
        rows  = self.top_stocks(screen, n, as_of_date, signal_filter)

        if not rows:
            print(f"\n  No results for {label} screen.\n")
            return

        date_used = rows[0].get("as_of_date", "?")
        sig_label  = signal_filter.upper() if signal_filter else "ALL"
        print(f"\n{'='*72}")
        print(f"  {label} Screen  —  {sig_label} stocks  |  {date_used}")
        print(f"{'='*72}")
        print(f"  {'Ticker':8} {'Signal':8} {'Conf':6} {'Total':6} {'Criteria':9} {'Consist':8} {'Moat':6} {'Mgmt':6}  Checks")
        print(f"  {'-'*8} {'-'*8} {'-'*6} {'-'*6} {'-'*9} {'-'*8} {'-'*6} {'-'*6}  ------")

        for r in rows:
            sig    = r.get("signal", "?")
            color  = G if sig == "bullish" else (R if sig == "bearish" else Y)
            passed = r.get("checks_passed", 0)
            total  = r.get("checks_total", 0)
            checks_str = f"{passed}/{total}"
            print(
                f"  {r['ticker']:8} {color}{sig:8}{RST} "
                f"{r.get('confidence', 0):5.1f}% "
                f"{(r.get('total_score') or 0):6.3f} "
                f"{(r.get('criteria_score') or 0):9.3f} "
                f"{(r.get('consistency') or 0):8.3f} "
                f"{(r.get('moat_score') or 0):6.3f} "
                f"{(r.get('mgmt_score') or 0):6.3f}  "
                f"{checks_str}"
            )
        print(f"{'='*72}\n")

    def print_ticker_scorecard(self, ticker: str, as_of_date: Optional[str] = None) -> None:
        G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; RST = "\033[0m"; B = "\033[1m"
        rows = self.ticker_scorecard(ticker, as_of_date)

        if not rows:
            print(f"\n  No screen results for {ticker}.\n")
            return

        date_used = rows[0].get("as_of_date", "?")
        print(f"\n{'='*72}")
        print(f"  {B}{ticker}{RST} — Investor Screen Scorecard  |  {date_used}")
        print(f"{'='*72}")

        for r in rows:
            sig   = r.get("signal", "?")
            color = G if sig == "bullish" else (R if sig == "bearish" else Y)
            label = _SCREEN_LABELS.get(r["screen"], r["screen"])
            score = r.get("total_score") or 0
            bar   = "█" * int(score * 20)
            print(
                f"  {label:16} {color}{sig:8}{RST} "
                f"{r.get('confidence', 0):5.1f}%  "
                f"{score:.3f}  {color}{bar:<20}{RST}"
            )
            # Show criteria detail
            criteria = r.get("criteria", {})
            if criteria:
                passing = [k for k, v in criteria.items() if v]
                failing = [k for k, v in criteria.items() if not v]
                if passing:
                    print(f"    {G}✓{RST} " + "  ".join(passing))
                if failing:
                    print(f"    {R}✗{RST} " + "  ".join(failing))
        print(f"{'='*72}\n")

    def print_summary_matrix(
        self,
        tickers: Optional[list[str]] = None,
        as_of_date: Optional[str] = None,
        top_n: int = 30,
    ) -> None:
        G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; RST = "\033[0m"; B = "\033[1m"
        result = self.summary_matrix(tickers, as_of_date, min_screens_passed=1)
        summary = result["summary"][:top_n]

        if not summary:
            print("\n  No screen results available.\n")
            return

        date_used = result.get("date", "?")
        print(f"\n{'='*72}")
        print(f"  Screen Summary Matrix  |  {date_used}")
        print(f"  Showing top {len(summary)} stocks by bullish screens")
        print(f"{'='*72}")
        print(f"  {'Ticker':8} {'Bullish':8} {'Avg Score':10} {'Top Screen':16} {'Passes'}")
        print(f"  {'-'*8} {'-'*8} {'-'*10} {'-'*16} {'-'*20}")

        matrix = result["matrix"]
        for r in summary:
            t    = r["ticker"]
            bull = r["bullish_screens"]
            color = G if bull >= 4 else (Y if bull >= 2 else R)
            # Mini bar showing which screens pass (★ = bullish, · = not)
            passes = ""
            for s in ALL_SCREENS:
                score = matrix.get(t, {}).get(s)
                # Find signal for this screen
                screen_docs = [
                    d for d in self._db.screen_results.find(
                        {"ticker": t, "screen": s, "as_of_date": result["date"]},
                        {"signal": 1, "_id": 0}
                    )
                ]
                sig = screen_docs[0].get("signal") if screen_docs else None
                passes += (G + "★" + RST) if sig == "bullish" else "·"

            print(
                f"  {t:8} {color}{bull:2}{RST}/13      "
                f"{r['avg_score']:.3f}      "
                f"{r['top_screen']:16} {passes}"
            )
        print(f"\n  {G}★{RST} = bullish screen  · = neutral/bearish/missing")
        print(f"{'='*72}\n")
