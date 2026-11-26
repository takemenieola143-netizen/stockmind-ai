"""StockMind 8.0 research engine. No orders, network calls or publication.
Inputs are explicitly supplied, point-in-time research data. Missing inputs fail closed.
"""
import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HORIZONS = (1, 5, 10, 20)


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def dated_record(r, asof, max_age):
    try:
        available = date.fromisoformat(r["available_date"])
        return 0 <= (asof - available).days <= max_age and bool(r.get("source_url", "").startswith("https://"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def fundamentals(record, peers, asof):
    if not isinstance(record, dict) or not dated_record(record, asof, 180):
        return {"status": "UNKNOWN", "score": None, "reason": "Current sourced financials unavailable"}
    sector = record.get("sector")
    if not isinstance(sector, str) or not sector.strip():
        return {"status": "UNKNOWN", "score": None, "reason": "Sector unavailable"}
    # Compare similar businesses, never use universal debt thresholds for banks.
    metrics = {"roe_pct": 1, "roce_pct": 1, "revenue_growth_pct": 1,
               "profit_growth_pct": 1, "free_cash_flow_yield_pct": 1,
               "pe": -1, "pb": -1, "debt_to_equity": -1}
    if record.get("financial_company") is True:
        metrics = {k:v for k,v in metrics.items() if k not in
                   ("roce_pct", "free_cash_flow_yield_pct", "debt_to_equity")}
    values = {}
    for key, direction in metrics.items():
        v = num(record.get(key))
        if v is None or (key in ("pe", "pb") and v <= 0) or (key == "debt_to_equity" and v < 0):
            continue
        sample = [num(p.get(key)) for p in peers if p.get("sector") == sector
                  and p.get("financial_company") == record.get("financial_company")
                  and dated_record(p, asof, 180)]
        sample = [x for x in sample if x is not None and
                  (key not in ("pe","pb") or x > 0) and
                  (key != "debt_to_equity" or x >= 0)]
        if len(sample) < 10:
            continue
        values[key] = round(100 * sum((x*direction < v*direction) +
                            0.5*(x == v) for x in sample)/len(sample), 2)
    if len(values) < 4:
        return {"status": "UNKNOWN", "score": None, "reason": "Insufficient sector peer evidence",
                "metrics": values}
    return {"status": "AVAILABLE", "score": round(statistics.mean(values.values()), 2),
            "metrics": values, "source_url": record["source_url"],
            "available_date": record["available_date"], "sector": sector}


def news_review(records, asof):
    # Only dated sourced announcements; no invented sentiment or assumption that silence is good.
    items = [r for r in records if isinstance(r, dict) and dated_record(r, asof, 14)
             and isinstance(r.get("headline"), str) and r["headline"].strip()]
    unique = {(r["available_date"], r["source_url"], r["headline"]): r for r in items}
    items = list(unique.values())
    if not items:
        return {"status": "UNKNOWN", "items": [], "reason": "No verified current announcements supplied"}
    flags = sorted({r["category"] for r in items if r.get("category") in
                    ("fraud", "default", "regulatory_action", "auditor_resignation")})
    return {"status": "REVIEW_REQUIRED", "risk_flags": flags,
            "items": [{k:r[k] for k in ("headline","source_url","available_date")} for r in
                      sorted(items, key=lambda x:x["available_date"], reverse=True)[:10]],
            "reason": "Read disclosures; headline sentiment is not a validated trading signal"}


def quantile(values, q):
    a = sorted(values)
    i = (len(a)-1)*q
    lo = int(i)
    hi = min(lo+1,len(a)-1)
    return a[lo] + (a[hi]-a[lo])*(i-lo)


def clean_candles(candles, asof):
    result = []
    previous = None
    for c in candles:
        d = date.fromisoformat(c["date"])
        if previous is not None and d <= previous:
            raise ValueError("Duplicate or unordered candle")
        previous = d
        if d > asof:
            continue
        o,h,l,close = [num(c.get(k)) for k in ("open","high","low","close")]
        if any(v is None for v in (o,h,l,close)) or not 0 < l <= min(o,close) <= max(o,close) <= h:
            raise ValueError("Invalid OHLC")
        result.append(c)
    return result


def empirical_ranges(candles, asof):
    # Non-overlapping backward returns. Empirical scenarios, NOT calibrated forecasts.
    c = clean_candles(candles, asof)
    output = {}
    for h in HORIZONS:
        returns = [c[i]["close"]/c[i-h]["close"]-1
                   for i in range(len(c)-1,h-1,-h)]
        if len(returns) < 20 or not c or c[-1]["date"] != asof.isoformat():
            output[str(h)] = {"status": "UNKNOWN", "samples": len(returns)}
            continue
        p = c[-1]["close"]
        output[str(h)] = {"status": "HISTORICAL_SCENARIO", "samples": len(returns),
                          "low": round(p*(1+quantile(returns,.1)),2),
                          "median": round(p*(1+quantile(returns,.5)),2),
                          "high": round(p*(1+quantile(returns,.9)),2),
                          "anchor_date": asof.isoformat()}
    return output


def backtest(candles, asof, cost_bps=20):
    # Fixed rule; signals use only prior closes; next open entry and same-day close exit.
    # Chronological last 30% holdout; not portfolio-level or survivorship-bias corrected.
    c = clean_candles(candles, asof)
    if len(c) < 200:
        return {"status": "UNKNOWN", "reason": "At least 200 daily candles required"}
    start = max(50, int(len(c)*.7))
    cost = cost_bps / 10000
    wealth = peak = benchmark = 1.0
    drawdown = 0.0
    trades = 0
    for i in range(start,len(c)):
        prior = [x["close"] for x in c[i-50:i]]
        signal = prior[-1] > statistics.mean(prior[-20:]) > statistics.mean(prior)
        day_ret = c[i]["close"]/c[i]["open"]-1
        benchmark *= (1+day_ret)*(1-cost)
        if signal:
            wealth *= (1+day_ret)*(1-cost)
            trades += 1
        peak = max(peak,wealth)
        drawdown = min(drawdown,wealth/peak-1)
    return {"status": "HISTORICAL_ONLY", "trades": trades,
            "return_pct": round((wealth-1)*100,2),
            "daily_entry_benchmark_pct": round((benchmark-1)*100,2),
            "max_drawdown_pct": round(drawdown*100,2),
            "holdout_start": c[start]["date"], "cost_bps_round_trip": cost_bps,
            "reason": "No forward validation or delisted-stock universe"}


def integrate(market, charts, financials, news, asof):
    if market.get("completed_sessions_only") is not True:
        raise ValueError("Completed session report required")
    records = []
    peers = list(financials.values())
    for s in market["stocks"]:
        symbol = s["symbol"]
        c = charts.get(symbol, {})
        f = fundamentals(financials.get(symbol), peers, asof)
        n = news_review(news.get(symbol, []), asof)
        fresh = (s.get("date") == asof.isoformat() == c.get("price_date")
                 and c.get("symbol") == symbol and c.get("freshness_verified") is True
                 and num(s.get("price")) is not None and num(c.get("close")) is not None
                 and abs(s["price"]-c["close"]) <= .05)
        diagnostics = market.get("ai_diagnostics", {})
        probabilities = {}
        for h in HORIZONS:
            p = s.get("prediction_"+str(h)+"d", {})
            v = num(p.get("up_probability"))
            probabilities[str(h)] = v if fresh and p.get("status") == "Available" and diagnostics.get(str(h),{}).get("reliable") is True and v is not None and 0 <= v <= 100 else None
        ranges = empirical_ranges(c.get("candles",[]),asof) if fresh else {}
        bt = backtest(c.get("candles",[]),asof) if fresh else {"status":"UNKNOWN","reason":"Current chart unavailable"}
        blocks = []
        if not fresh: blocks.append("Chart freshness unverified")
        if f["status"] != "AVAILABLE": blocks.append("Fundamentals incomplete")
        if n["status"] != "REVIEW_REQUIRED": blocks.append("News unavailable")
        else: blocks.append("Announcement review required")
        if all(v is None for v in probabilities.values()): blocks.append("No validated model estimates")
        if bt["status"] != "HISTORICAL_ONLY": blocks.append("Insufficient backtest history")
        blocks.append("Forward and portfolio strategy validation pending")
        # Research ranking is not a buy recommendation; unknown data not imputed.
        score = num(s.get("score"))
        rank = round((score+f["score"])/2,2) if fresh and score is not None and 0<=score<=100 and f["score"] is not None else None
        records.append({"symbol":symbol,"date":s.get("date"),"fundamental":f,"news":n,
                        "probabilities":probabilities,"historical_ranges":ranges,"backtest":bt,
                        "research_rank":rank,"decision":"WAIT","blocks":blocks})
    records.sort(key=lambda r:(r["research_rank"] is not None,r["research_rank"] or 0),reverse=True)
    return {"version":"8.0-preview","as_of":asof.isoformat(),
            "generated":datetime.now(timezone.utc).isoformat(),
            "mode":"Research only; no trade signals","stocks":records}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--as-of",required=True)
    p.add_argument("--market",default="market_data.json")
    p.add_argument("--charts",default="market_charts.json")
    p.add_argument("--financials")
    p.add_argument("--news")
    p.add_argument("--output",default="research_v8.json")
    a=p.parse_args()
    load=lambda x:json.loads(Path(x).read_text(encoding="utf-8"))
    report=integrate(load(a.market),load(a.charts)["charts"],
                     load(a.financials) if a.financials else {},
                     load(a.news) if a.news else {},date.fromisoformat(a.as_of))
    Path(a.output).write_text(json.dumps(report,allow_nan=False,separators=(",",":")),encoding="utf-8")
    print("8.0 research records:",len(report["stocks"]))
    print("Research ranks available:",sum(x["research_rank"] is not None for x in report["stocks"]))
