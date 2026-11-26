"""Read-only integration checks. No vendor data is published or stored.
Full-universe capacity is tested with clearly synthetic candles; separately
probe a documented keyless personal-research API with two requests.
"""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from research_engine_v8 import integrate

def full_scale():
    market=json.loads(Path("market_data.json").read_text(encoding="utf-8"))
    assert market["completed_sessions_only"] is True
    asof=date.fromisoformat(max(s["date"] for s in market["stocks"]))
    stocks=market["stocks"]
    assert len(stocks)>=2000
    # Preserve the actual listed universe but do not treat synthetic prices as real.
    charts={}
    for s in stocks:
        p=s["price"]
        if not isinstance(p,(float,int)) or p<=0: continue
        candles=[{"date":(asof-timedelta(days=89-i)).isoformat(),
                  "open":p*(.91+i*.001),"close":p*(.911+i*.001),
                  "high":p*(.92+i*.001),"low":p*(.90+i*.001)}
                 for i in range(90)]
        charts[s["symbol"]]={"symbol":s["symbol"],"price_date":asof.isoformat(),
                             "close":p,"freshness_verified":False,"candles":candles}
    output=integrate(market,charts,{}, {},asof)
    assert len(output["stocks"])==len(stocks)
    assert len({s["symbol"] for s in output["stocks"]})==len(stocks)
    assert all(s["decision"]=="WAIT" and s["research_rank"] is None for s in output["stocks"])
    json.dumps(output,allow_nan=False)
    print("FULL UNIVERSE CAPACITY: actual scanner symbols",len(stocks))
    print("Synthetic unverified charts:",len(charts))
    print("No false ranks or trade recommendations")

def fetch(path,params):
    url="https://api.tejhq.dev"+path+"?"+urlencode(params)
    with urlopen(Request(url,headers={"Accept":"application/json","User-Agent":"StockMind-research-test/8.0"}),timeout=45) as r:
        body=r.read(20_000_001)
    if len(body)>20_000_000: raise ValueError("Response too large")
    data=json.loads(body)
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):
        raise ValueError("Unexpected documented response envelope")
    return data

def provider_probe():
    market=json.loads(Path("market_data.json").read_text())
    session=max(s["date"] for s in market["stocks"])
    snapshot=fetch("/v1/snapshot/nse",{"date":session})
    rows=snapshot["data"]
    meta=snapshot.get("meta",{})
    print("Snapshot row count:",len(rows),"metadata fields:",sorted(meta))
    assert meta.get("date",meta.get("trading_date"))==session, "Snapshot session not confirmed by provider metadata"
    equities=[r for r in rows if r.get("series")=="EQ" and r.get("date",session)==session]
    assert len(equities)>=2000, "Insufficient same-session NSE EQ snapshot rows"
    assert len({r["symbol"] for r in equities})==len(equities)
    print("Provider same-session EQ rows:",len(equities))
    envelope=fetch("/v1/ohlcv/nse/RELIANCE",{"from":(date.fromisoformat(session)-timedelta(days=120)).isoformat(),"to":session})
    history=envelope["data"]
    assert envelope.get("meta",{}).get("symbol")=="RELIANCE"
    assert len(history)>=51 and all(r.get("symbol","RELIANCE")=="RELIANCE" for r in history)
    assert max(r["date"] for r in history)==session
    print("Provider sample history rows:",len(history))
    print("Provider probe passed; no raw data saved")

if __name__=="__main__":
    import sys
    if "--provider" in sys.argv: provider_probe()
    else: full_scale()
