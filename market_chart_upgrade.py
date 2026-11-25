
import ast
import json

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from chart_engine import (
    analyse_chart,
    verify_freshness
)

charts = {}
failures = {}

NOW = datetime.now(
    ZoneInfo("Asia/Kolkata")
)


def collect_chart(stock, df):

    symbol = stock["symbol"]

    try:

        chart = analyse_chart(
            symbol,
            df.sort_index().tail(150),
            NOW
        )

        market = {
            "completed_sessions_only": True,
            "stocks": [stock]
        }

        verified, reason = verify_freshness(
            chart, market, NOW
        )

        chart["freshness_verified"] = verified
        chart["freshness_reason"] = reason
        chart["decision"] = "WAIT"

        if not verified:
            chart["reference_plan"] = None
            chart["reason"] = (
                reason + ". Trade levels blocked."
            )
        else:
            chart["reason"] = (
                "Data matches scanner. "
                "Strategy validation pending."
            )

        json.dumps(chart, allow_nan=False)

        charts[symbol] = chart

    except Exception as error:

        failures[symbol] = str(error)


def write_chart_reports(results):

    verified = sum(
        c["freshness_verified"]
        for c in charts.values()
    )

    report = {
        "version": "7.1",
        "generated": NOW.isoformat(),
        "source": "Shared scanner history",
        "stocks_scanned": len(results),
        "charts_available": len(charts),
        "freshness_verified": verified,
        "freshness_unverified": (
            len(charts) - verified
        ),
        "failed": failures,
        "charts": charts
    }

    temporary = Path("market_charts.tmp")

    temporary.write_text(
        json.dumps(
            report,
            separators=(",", ":"),
            allow_nan=False
        ),
        encoding="utf-8"
    )

    temporary.replace("market_charts.json")

    print("FULL MARKET CHART REPORT")
    print("Stocks scanned:", len(results))
    print("Charts generated:", len(charts))
    print("Freshness verified:", verified)
    print("Chart failures:", len(failures))


def upgrade_scanner():

    path = Path("scanner.py")

    source = path.read_text(
        encoding="utf-8"
    )

    if "collect_chart(stock, df)" in source:
        print("Chart upgrade already active")
        return

    if '"version": "6.0"' not in source:
        raise RuntimeError(
            "Activate scanner 6.0 first"
        )

    def replace(old, new):

        nonlocal source

        if source.count(old) != 1:
            raise RuntimeError(
                "Unexpected scanner structure"
            )

        source = source.replace(old, new, 1)

    replace(
        "import yfinance as yf",
        """import yfinance as yf
from market_chart_upgrade import (
    collect_chart,
    write_chart_reports
)"""
    )

    replace(
        """results.append(
                    analyse(symbol, df)
                )""",
        """stock = analyse(symbol, df)
                results.append(stock)
                collect_chart(stock, df)"""
    )

    replace(
        'print("StockMind AI 6.0 scan completed")',
        '''write_chart_reports(results)
print("StockMind AI 7.1 chart scan completed")'''
    )

    ast.parse(source)

    path.write_text(
        source,
        encoding="utf-8"
    )

    print("Full-market chart upgrade activated")


if __name__ == "__main__":

    upgrade_scanner()
