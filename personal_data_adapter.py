"""Personal research source adapter. Not a redistribution license.

Uses yfinance only for current, observed provider data. No historical availability
dates are invented, no raw provider payloads are saved, and no trading signals
are created. Run only under terms permitting your own research use.
"""
import argparse
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def number(v):
    return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) else None

def https(url):
    try:
        return isinstance(url,str) and urlsplit(url).scheme=="https" and bool(urlsplit(url).hostname)
    except ValueError:
        return False

def financial_record(info, symbol, observed):
    if not isinstance(info,dict) or info.get("symbol") != symbol+".NS" or info.get("quoteType")!="EQUITY":
        return None
    sector=info.get("sector")
    if not isinstance(sector,str) or not sector:
        return None
    record={"available_date":observed.isoformat(),"source_url":"https://finance.yahoo.com/quote/"+quote(symbol+".NS",safe="")+"/key-statistics/",
            "source_kind":"provider_snapshot","sector":sector,"financial_company":sector=="Financial Services",
            "metric_basis":"Provider ratios observed today; not audited filing verification"}
    for dst,src,scale in (
        ("pe","trailingPE",1),("pb","priceToBook",1),("roe_pct","returnOnEquity",100),
        ("revenue_growth_pct","revenueGrowth",100),("profit_growth_pct","earningsGrowth",100),
        ("debt_to_equity","debtToEquity",.01)):
        v=number(info.get(src))
        if v is not None: record[dst]=v*scale
    cap,fcf=number(info.get("marketCap")),number(info.get("freeCashflow"))
    if cap is not None and cap>0 and fcf is not None and info.get("currency")==info.get("financialCurrency")=="INR":
        record["free_cash_flow_yield_pct"]=100*fcf/cap
    return record if any(k in record for k in ("pe","pb","roe_pct","revenue_growth_pct","profit_growth_pct","debt_to_equity","free_cash_flow_yield_pct")) else None

def news_records(payload,symbol,observed):
    results=[]
    for item in payload or []:
        if not isinstance(item,dict): continue
        c=item.get("content",{})
        if not isinstance(c,dict): continue
        # Require explicit ticker relevance from provider; do not infer from headline.
        tickers=(c.get("finance") or {}).get("stockTickers") or []
        relevant=any(isinstance(t,dict) and t.get("symbol")==symbol+".NS" for t in tickers)
        if not relevant: continue
        title=c.get("title")
        link=(c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
        try:
            stamp=datetime.fromisoformat(c["pubDate"].replace("Z","+00:00"))
            if stamp.tzinfo is None: continue
            published=stamp.astimezone(IST).date()
        except (KeyError,ValueError,TypeError,AttributeError): continue
        if not 0<=(observed-published).days<=14 or not isinstance(title,str) or not title.strip() or not https(link): continue
        results.append({"available_date":published.isoformat(),"source_url":link,"headline":title[:400],
                        "source_kind":"provider_news","category":"unclassified"})
    return results[:20]

def collect(symbols, ticker_factory, delay=1.5):
    today=datetime.now(IST).date()
    financials,news={},{}
    stats={"requested":len(symbols),"financial_records":0,"news_records":0,"failed_financials":0,"failed_news":0}
    for symbol in symbols:
        if not re.fullmatch(r"[A-Z0-9&_.-]{1,40}",symbol): continue
        ticker=ticker_factory(symbol+".NS")
        try:
            r=financial_record(ticker.get_info(),symbol,today)
            if r: financials[symbol]=r
            else: stats["failed_financials"]+=1
        except Exception: stats["failed_financials"]+=1
        time.sleep(delay)
        try:
            r=news_records(ticker.get_news(count=10),symbol,today)
            if r: news[symbol]=r
        except Exception: stats["failed_news"]+=1
        time.sleep(delay)
    stats["financial_records"]=len(financials)
    stats["news_records"]=sum(map(len,news.values()))
    return financials,news,stats

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--personal-use",action="store_true",help="Confirm applicable data terms permit this personal research use")
    p.add_argument("--symbols",nargs="+",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--delay",type=float,default=1.5)
    args=p.parse_args()
    if not args.personal_use: p.error("Confirm permitted personal use before requesting provider data")
    import yfinance as yf
    symbols=list(dict.fromkeys(s.upper() for s in args.symbols))
    f,n,stats=collect(symbols,yf.Ticker,max(1.5,args.delay))
    dest=Path(args.output_dir)
    dest.mkdir(parents=True,exist_ok=True)
    for name,data in (("financials.json",f),("announcements.json",n)):
        (dest/name).write_text(json.dumps(data,allow_nan=False),encoding="utf-8")
    print(json.dumps(stats))
if __name__=="__main__": main()
