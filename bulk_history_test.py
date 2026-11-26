"""Bulk historical research validation. Personal use only; no raw data export.
Data: TejHQ (tejhq.dev), sourced from NSE public bhavcopy.
Terms: https://tejhq.dev/data-terms; exchange terms apply independently.
"""
import json
from collections import Counter
from datetime import date
from pathlib import Path
import tempfile
import pandas as pd
from huggingface_hub import hf_hub_download
from research_engine_v8 import empirical_ranges, backtest, validate_ranges, integrate
from export_market_charts import valid_chart

def run():
    existing=json.loads(Path("market_data.json").read_text())
    expected=date.fromisoformat(max(s["date"] for s in existing["stocks"]))
    columns=["date","symbol","series","isin","open","high","low","close","volume","adj_close"]
    frames=[]
    with tempfile.TemporaryDirectory() as cache:
        for year in range(expected.year-4,expected.year+1):
            path=hf_hub_download("tejhq/indian-markets",
                f"prices_adjusted/nse_{year}.parquet",repo_type="dataset",cache_dir=cache)
            frames.append(pd.read_parquet(path,columns=columns))
        df=pd.concat(frames,ignore_index=True)
    df["date"]=pd.to_datetime(df["date"]).dt.date
    df=df[(df["series"]=="EQ") & (df["date"]<=expected)].dropna(subset=columns)
    assert df["date"].max()==expected,"Provider history does not reach scanner session"
    latest=df[df["date"]==expected]
    assert latest["symbol"].is_unique and latest["isin"].is_unique,"Ambiguous identity"
    assert len(latest)>=2000,"Insufficient latest equity coverage"
    print("Bulk dataset session:",expected,"equity universe:",len(latest),flush=True)
    old={s["symbol"]:s for s in existing["stocks"]}
    counts=Counter()
    market={"completed_sessions_only":True,"stocks":[],"ai_diagnostics":{}}
    charts={}
    historical={}
    by_isin={k:g for k,g in df.groupby("isin",sort=False)}
    for row in latest.itertuples(index=False):
        symbol=row.symbol
        counts["universe"]+=1
        if symbol in old and old[symbol]["date"]==expected.isoformat():
            counts["same_date_reference"]+=1
            if abs(float(row.close)-old[symbol]["price"])<=.05:
                counts["reference_price_matches"]+=1
            else:
                counts["reference_price_mismatches"]+=1
        market["stocks"].append({"symbol":symbol,"date":expected.isoformat(),"price":float(row.close)})
        frame=by_isin[row.isin].sort_values("date").tail(1250)
        if frame["date"].duplicated().any() or frame.iloc[-1]["symbol"]!=symbol:
            counts["ambiguous_history"]+=1;continue
        try:
            raw=[];adjusted=[]
            last_factor=float(frame.iloc[-1]["adj_close"])/float(frame.iloc[-1]["close"])
            for b in frame.itertuples(index=False):
                factor=float(b.adj_close)/float(b.close)/last_factor
                c={"date":b.date.isoformat(),**{k:float(getattr(b,k)) for k in ("open","high","low","close","volume")}}
                raw.append(c)
                adjusted.append({"date":c["date"],**{k:c[k]*factor for k in ("open","high","low","close")}})
            chart={"symbol":symbol,"price_date":expected.isoformat(),"close":float(row.close),
                   "candles":raw[-90:],"decision":"WAIT","freshness_verified":True}
            valid_chart(chart,symbol)
            # In this independent data test the flag means internal date/price agreement only.
            charts[symbol]=chart
            historical[symbol]={"symbol":symbol,"date":expected.isoformat(),
                "historical_ranges":empirical_ranges(adjusted,expected),
                "backtest":backtest(adjusted,expected),"range_validation":validate_ranges(adjusted,expected)}
            counts["history_valid"]+=1
        except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError):
            counts["history_invalid_or_short"]+=1
        if counts["universe"]%250==0:
            print("Research histories checked:",counts["universe"],flush=True)
    result=integrate(market,charts,{}, {},expected,historical)
    assert len(result["stocks"])==len(latest)
    assert all(s["decision"]=="WAIT" and s["research_rank"] is None for s in result["stocks"])
    json.dumps(result,allow_nan=False)
    counts["historical_backtests"]=sum(r["backtest"]["status"]=="HISTORICAL_ONLY" for r in result["stocks"])
    for h in ("1","5","10","20"):
        diag=[r["range_validation"].get(h,{}) for r in result["stocks"]]
        counts[f"{h}d_diagnostics"]=sum(d.get("status")=="HISTORICAL_DIAGNOSTIC" for d in diag)
        counts[f"{h}d_screen_passed"]=sum(d.get("screen_passed") is True for d in diag)
    print("BULK HISTORICAL VALIDATION COUNTS",json.dumps(dict(counts),sort_keys=True))
    assert counts["history_valid"]/counts["universe"]>=.90,"Insufficient valid historical coverage"
    print("Bulk research integration passed; no data published, no profitability claim")
if __name__=="__main__": run()
