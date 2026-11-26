import copy
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from export_market_charts import build, chart_name


def fixture():
    stocks = [{"symbol": s, "date": d, "price": 105}
              for s, d in [("TCS", "2026-11-25"), ("M&M", "2026-11-23")]]
    market = {"version": "6.0", "completed_sessions_only": True,
              "connected": 2, "generated": "2026-11-26T00:00:00Z", "stocks": stocks}
    charts = {}
    for s in stocks:
        end = date.fromisoformat(s["date"])
        candles = [{"date": (end - timedelta(days=2*i)).isoformat(), "open": 102,
                    "high": 106, "low": 100, "close": 105, "volume": 1000}
                   for i in reversed(range(51))]
        charts[s["symbol"]] = {"symbol": s["symbol"], "price_date": s["date"],
                              "close": 105, "candles": candles, "decision": "WAIT",
                              "freshness_verified": s["symbol"] == "TCS",
                              "reference_plan": {"entry_trigger": 107}}
    report = {"version": "7.1", "source": "Shared scanner history",
              "stocks_scanned": 2, "charts_available": 2, "charts": charts}
    return market, report


class ExportTests(unittest.TestCase):
    def test_export_and_stale_block(self):
        market, report = fixture()
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "charts"
            manifest = build(market, report, target)
            self.assertEqual(manifest["charts_available"], 2)
            self.assertEqual(manifest["freshness_verified"], 1)
            self.assertEqual(chart_name("TCS"), "544353.json")
            for symbol in ("TCS", "M&M"):
                c = json.loads((target / chart_name(symbol)).read_text())
                self.assertEqual(c["symbol"], symbol)
                self.assertEqual(c["snapshot_generated"], market["generated"])
                self.assertIsNone(c["reference_plan"])
                self.assertEqual(c["decision"], "WAIT")
            with self.assertRaises(FileExistsError):
                build(market, report, target)

    def test_reject_invalid_reports_without_partial_output(self):
        for mode in ("wrong_symbol", "bad_price", "duplicate_date", "false_fresh",
                     "recovered", "missing_coverage", "unknown_symbol", "wrong_source"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                market, report = fixture()
                c = report["charts"]["TCS"]
                if mode == "wrong_symbol": c["symbol"] = "DIXON"
                elif mode == "bad_price": c["candles"][-1]["high"] = 1
                elif mode == "duplicate_date": c["candles"][1]["date"] = c["candles"][0]["date"]
                elif mode == "false_fresh": report["charts"]["M&M"]["freshness_verified"] = True
                elif mode == "recovered": c["recovered_candle"] = True
                elif mode == "missing_coverage":
                    report["charts"].pop("TCS")
                    report["charts_available"] = 1
                elif mode == "unknown_symbol":
                    report["charts"]["OTHER"] = report["charts"].pop("TCS")
                elif mode == "wrong_source": report["source"] = "NSE Bhavcopy"
                target = Path(d) / "charts"
                with self.assertRaises(ValueError):
                    build(market, report, target)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
