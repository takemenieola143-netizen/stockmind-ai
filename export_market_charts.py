"""Build a stock-specific chart directory from the same scanner snapshot.

Does not fetch data, commit, or publish. NSE recovery diagnostics are excluded.
Public distribution is a separate, explicit operator decision.
"""
import argparse
import json
import math
import shutil
import tempfile
from datetime import date
from pathlib import Path

FIELDS = ("open", "high", "low", "close", "volume")


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def day(value):
    return isinstance(value, str) and date.fromisoformat(value).isoformat() == value


def chart_name(symbol):
    if not isinstance(symbol, str) or not symbol or len(symbol) > 80:
        raise ValueError("Invalid symbol")
    return symbol.encode("utf-8").hex() + ".json"


def valid_chart(chart, symbol):
    if chart.get("symbol") != symbol or not day(chart.get("price_date")):
        raise ValueError("Chart symbol/date mismatch")
    if chart.get("decision") != "WAIT":
        raise ValueError("Unexpected chart decision")
    if chart.get("recovered_candle") or chart.get("source") not in (None, "Shared scanner history", "Yahoo Finance"):
        raise ValueError("Non-scanner source is not eligible for this export")
    candles = chart.get("candles")
    if not isinstance(candles, list) or not 51 <= len(candles) <= 90:
        raise ValueError("Invalid history length")
    dates = []
    for c in candles:
        if not day(c.get("date")) or not all(finite(c.get(k)) for k in FIELDS):
            raise ValueError("Invalid candle")
        if not (0 < c["low"] <= min(c["open"], c["close"]) <=
                max(c["open"], c["close"]) <= c["high"] and c["volume"] >= 0):
            raise ValueError("Invalid OHLCV")
        dates.append(c["date"])
    if dates != sorted(set(dates)) or dates[-1] != chart["price_date"]:
        raise ValueError("Invalid candle dates")
    if not finite(chart.get("close")) or abs(chart["close"] - candles[-1]["close"]) > 1e-6:
        raise ValueError("Last close mismatch")


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False,
                               separators=(",", ":")), encoding="utf-8")


def build(market, report, destination, min_coverage=0.90):
    if str(market.get("version")) != "6.0" or market.get("completed_sessions_only") is not True:
        raise ValueError("Completed scanner snapshot required")
    if str(report.get("version")) != "7.1" or report.get("source") != "Shared scanner history":
        raise ValueError("Shared scanner chart report required")
    stocks = {}
    for s in market["stocks"]:
        symbol = s["symbol"]
        chart_name(symbol)
        if symbol in stocks:
            raise ValueError("Duplicate scanner symbol")
        stocks[symbol] = s
    if not stocks or report.get("stocks_scanned") != len(stocks):
        raise ValueError("Report population mismatch")
    if market.get("connected") != len(stocks):
        raise ValueError("Scanner count mismatch")
    if not isinstance(report.get("charts"), dict):
        raise ValueError("Missing charts")
    if report.get("charts_available") != len(report["charts"]):
        raise ValueError("Chart count mismatch")
    if not set(report["charts"]).issubset(stocks):
        raise ValueError("Chart outside scanner universe")
    latest = max(s["date"] for s in stocks.values() if day(s["date"]))
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Destination already exists; use a clean staging path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".charts-", dir=destination.parent))
    try:
        summaries = {}
        for symbol, raw in report["charts"].items():
            valid_chart(raw, symbol)
            s = stocks[symbol]
            if raw["price_date"] > s["date"]:
                raise ValueError("Chart newer than scanner")
            verified = (raw.get("freshness_verified") is True and raw["price_date"] == s["date"] == latest
                        and finite(s.get("price")) and abs(raw["close"] - s["price"]) <= 0.05)
            if raw.get("freshness_verified") is True and not verified:
                raise ValueError("False freshness claim")
            chart = dict(raw)
            chart["freshness_verified"] = verified
            chart["reference_plan"] = None
            chart["decision"] = "WAIT"
            chart["source"] = "Shared scanner history"
            chart["reason"] = "Historical research only; trade levels disabled."
            chart["snapshot_generated"] = market["generated"]
            name = chart_name(symbol)
            write_json(stage / name, chart)
            summaries[symbol] = {"file": name, "date": chart["price_date"], "verified": verified}
        if len(summaries) / len(stocks) < min_coverage:
            raise ValueError("Chart coverage below threshold")
        manifest = {"version": "7.2", "snapshot_generated": market["generated"],
                    "latest_scanner_date": latest, "stocks_scanned": len(stocks),
                    "charts_available": len(summaries),
                    "freshness_verified": sum(s["verified"] for s in summaries.values()),
                    "charts": summaries}
        write_json(stage / "manifest.json", manifest)
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print("CHART EXPORT VALIDATED")
    print("Charts exported:", len(summaries))
    print("Current snapshot matches:", manifest["freshness_verified"])
    print("Charts unavailable:", len(stocks)-len(summaries))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="market_data.json")
    parser.add_argument("--report", default="market_charts.json")
    parser.add_argument("--output", default="charts")
    args = parser.parse_args()
    build(json.loads(Path(args.market).read_text(encoding="utf-8")),
          json.loads(Path(args.report).read_text(encoding="utf-8")), args.output)
