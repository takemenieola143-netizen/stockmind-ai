"""Prospective paper simulator. Input is an independently verified event feed, never scanner rankings."""
import json, math, pathlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parent
CATEGORIES=("intraday","short","long")
def stamp(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("timezone required")
    return d
def positive(x):
    return type(x) in (int,float) and math.isfinite(x) and x>0
def advance(state, feed, now):
    if not feed or feed.get("verified") is not True:
        state["status"]="Blocked: no verified execution feed"
        return state
    events=sorted(feed["events"],key=lambda e:stamp(e["time"]))
    for e in events:
        t=stamp(e["time"])
        if t>now or (now-t).total_seconds()>900: continue
        if not ("2026-11-27"<=t.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()<="2026-12-26"): continue
        if e.get("verified") is not True or not e.get("source") or not e.get("id"): continue
        if e["id"] in state["seen"]: continue
        cat,sym=e.get("category"),e.get("symbol")
        p=e.get("price")
        if cat not in CATEGORIES or not isinstance(sym,str) or not positive(p): continue
        key=cat+":"+sym
        pos=state["open"].get(key)
        if pos and t<=stamp(pos["last_time"]): continue
        state["seen"].append(e["id"])
        if pos:
            pos["mark"]=p
            pos["last_time"]=e["time"]
            reason=("stop" if p<=pos["stop"] else "target" if p>=pos["target"] else "exit signal" if e.get("action")=="SELL" else "session close" if cat=="intraday" and e.get("session_close") is True else None)
            if reason:
                proceeds=pos["qty"]*p*.998
                state["closed"].append(dict(pos,exit=p,exit_time=e["time"],exit_source=e["source"],reason=reason,pnl=round(proceeds-pos["cost"],2)))
                del state["open"][key]
        elif e.get("action")=="BUY" and positive(e.get("stop")) and positive(e.get("target")) and e["stop"]<p<e["target"] and e.get("signal_time") and stamp(e["signal_time"])<t and not e.get("session_close"):
            qty=int(10000/(p*1.002))
            if qty:
                state["open"][key]=dict(symbol=sym,category=cat,qty=qty,entry=p,mark=p,cost=qty*p*1.002,stop=e["stop"],target=e["target"],entry_time=e["time"],last_time=e["time"],source=e["source"])
    state["status"]="Verified-feed events processed; coverage limited to supplied observations"
    return state
def main():
    path=ROOT/"auto_paper_state.json"
    state=json.loads(path.read_text()) if path.exists() else {"open":{},"closed":[],"seen":[]}
    feedpath=ROOT/"verified_paper_feed.json"
    now=datetime.now(timezone.utc)
    try:
        feed=json.loads(feedpath.read_text()) if feedpath.exists() else None
        state=advance(state,feed,now)
    except (ValueError,KeyError,TypeError) as exc:
        # discard partial changes on malformed input
        state=json.loads(path.read_text()) if path.exists() else {"open":{},"closed":[],"seen":[]}
        state["status"]="Blocked: invalid feed"
    state["checked_at"]=now.isoformat()
    path.write_text(json.dumps(state,indent=2)+"\n")
if __name__=="__main__": main()
