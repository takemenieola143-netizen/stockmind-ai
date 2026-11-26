/* Daily research shortlist. Not an investment recommendation or live signal. */
(function(root,factory){const api=factory();if(typeof module==="object"&&module.exports)module.exports=api;else root.StockMindDaily=api;})(typeof globalThis!=="undefined"?globalThis:this,function(){
"use strict";
const finite=x=>typeof x==="number"&&Number.isFinite(x);
const date=x=>typeof x==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(x)&&Number.isFinite(Date.parse(x))&&new Date(x).toISOString().slice(0,10)===x;
const clamp=x=>Math.max(0,Math.min(100,x));
const round=x=>Math.round(x*100)/100;
const configs={
 intraday:{label:"Intraday preparation",horizon:"Next session only",minTurnover:50000000,atrMax:5},
 short:{label:"Short-term technical research",horizon:"5–20 trading days",minTurnover:20000000,atrMax:6},
 long:{label:"Long-term preliminary screening",horizon:"1–3 years",minTurnover:10000000,atrMax:8}
};
function ist(now){const p=new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(now);const get=k=>p.find(x=>x.type===k).value;return {day:get("year")+"-"+get("month")+"-"+get("day"),hour:+get("hour"),minute:+get("minute")};}
function expectedWeekday(now){
 const t=ist(now);let d=new Date(t.day+"T00:00:00Z");
 if(t.hour<16)d.setUTCDate(d.getUTCDate()-1);
 while([0,6].includes(d.getUTCDay()))d.setUTCDate(d.getUTCDate()-1);
 return d.toISOString().slice(0,10);
}
function validateMarket(m,now=new Date()){
 if(!m||m.completed_sessions_only!==true||!Array.isArray(m.stocks)||!finite(m.requested)||m.requested<2000||m.stocks.length<2000||m.stocks.length/m.requested<.9)throw Error("Scanner coverage or completed-session validation failed");
 const observed=Date.parse(m.generated);if(!finite(observed)||observed>now.getTime()+60000)throw Error("Invalid report generation time");
 const today=ist(now).day;
 const valid=m.stocks.filter(s=>s&&typeof s.symbol==="string"&&s.symbol.trim()&&date(s.date)&&s.date<=today);
 if(valid.length/m.stocks.length<.9)throw Error("Missing or invalid stock dates");
 const latest=valid.reduce((d,s)=>s.date>d?s.date:d,"");
 if(latest>expectedWeekday(now))throw Error("Session not confirmed complete");
 const counts=new Map();for(const s of valid)counts.set(s.symbol,(counts.get(s.symbol)||0)+1);
 const fresh=valid.filter(s=>s.date===latest&&counts.get(s.symbol)===1);
 if(fresh.length/m.stocks.length<.9)throw Error("Fewer than 90% of stocks have unique matching session dates");
 return {latest,expected:expectedWeekday(now),current:latest===expectedWeekday(now),coverage:fresh.length/m.requested,stocks:fresh,generated:m.generated,requested:m.requested,connected:m.stocks.length};
}
function model(stock,diag,h){
 const p=stock["prediction_"+h+"d"]||{},d=diag?.[String(h)]||{},e=d.evaluation||{};
 const ok=p.status==="Available"&&d.reliable===true&&finite(p.up_probability)&&p.up_probability>=0&&p.up_probability<=100&&finite(e.accuracy)&&finite(e.baseline_accuracy)&&e.accuracy>e.baseline_accuracy&&finite(e.balanced_accuracy)&&e.balanced_accuracy>51&&finite(e.brier_score)&&finite(e.baseline_brier)&&e.brier_score<e.baseline_brier;
 return {h,probability:ok?p.up_probability:null,accuracy:ok?e.accuracy:null,baseline:ok?e.baseline_accuracy:null,reason:ok?"Shared market model; not a stock-specific success rate":p.reason||"No approved model for this horizon"};
}
function eligible(s,kind){
 const c=configs[kind];
 return [s.price,s.score,s.rsi,s.sma20,s.sma50,s.sma200,s.atr,s.average_daily_turnover,s.relative_volume].every(finite)&&s.price>=20&&s.score>=65&&s.score<=100&&s.rsi>=45&&s.rsi<=70&&s.sma20>0&&s.sma50>0&&s.sma200>0&&s.atr>0&&s.atr/s.price*100<=c.atrMax&&s.average_daily_turnover>=c.minTurnover&&s.relative_volume>0&&s.price>s.sma50;
}
function candidate(s,kind,diag){
 const trend=clamp((s.price/s.sma50-1)*400+50);
 const alignment=(s.price>s.sma20?25:0)+(s.sma20>s.sma50?35:0)+(s.sma50>s.sma200?40:0);
 const volume=clamp(s.relative_volume*35);
 const liquidity=clamp(Math.log10(s.average_daily_turnover/10000000+1)*65);
 const risk=clamp(100-(s.atr/s.price*100)*15);
 const bt=[s.backtest_return,s.benchmark_return,s.backtest_trades,s.max_drawdown].every(finite)&&s.backtest_trades>=20;
 const backtest=bt?clamp(50+(s.backtest_return-s.benchmark_return)):null;
 const models=(kind==="intraday"?[1]:kind==="short"?[5,10,20]:[]).map(h=>model(s,diag,h));
 const weights=kind==="intraday"?{Technical:s.score,Trend:alignment,Volume:volume,Liquidity:liquidity,Risk:risk}:kind==="short"?{Technical:s.score,Trend:alignment,Momentum:trend,Risk:risk,Liquidity:liquidity}:{Technical:s.score,Trend:alignment,Risk:risk,Liquidity:liquidity};
 const w=kind==="intraday"?[.25,.15,.30,.20,.10]:kind==="short"?[.30,.25,.20,.15,.10]:[.25,.40,.20,.15];
 const parts=Object.entries(weights).map(([label,value],i)=>({label,value:round(value),weight:w[i]}));
 const score=round(parts.reduce((a,p)=>a+p.value*p.weight,0));
 const gap=kind==="intraday"?1:2;
 let setup=null;
 if(kind!=="long"){const entry=round(s.price),stop=round(s.price-gap*s.atr),target=round(s.price+2*gap*s.atr);if(stop>0&&stop<entry&&entry<target)setup={entry,stop,target,rewardRisk:round((target-entry)/(entry-stop)),label:"Illustrative prior-close ATR setup, not executable live prices"};}
 return {symbol:s.symbol,date:s.date,price:s.price,score,parts,technical:s.score,rsi:s.rsi,relativeVolume:s.relative_volume,turnover:s.average_daily_turnover,atrPct:round(s.atr/s.price*100),sma20:s.sma20,sma50:s.sma50,sma200:s.sma200,models,setup,backtest:bt?{return:s.backtest_return,benchmark:s.benchmark_return,trades:s.backtest_trades,drawdown:s.max_drawdown,winRate:finite(s.win_rate)?s.win_rate:null,method:s.backtest_strategy||"Legacy scanner rule",cost:finite(s.transaction_cost_pct)?s.transaction_cost_pct:null}:null,
 status:"RESEARCH ONLY",blockers:kind==="intraday"?["No current-session price, VWAP, spread or intraday candles","No validated intraday strategy","Fundamentals and news not integrated"]:kind==="short"?["Horizon-specific strategy not validated","Latest company news and financials not integrated"]:["No verified financial, valuation, debt or growth comparison","Technical screen alone cannot establish long-term value","No validated 1–3 year strategy"]};
}
function daily(m,now=new Date()){
 const report=validateMarket(m,now),groups={};
 for(const kind of Object.keys(configs)){
  const rows=report.stocks.filter(s=>eligible(s,kind)).map(s=>candidate(s,kind,m.ai_diagnostics)).sort((a,b)=>b.score-a.score||a.symbol.localeCompare(b.symbol));
  groups[kind]={...configs[kind],eligible:rows.length,verified:0,rows:rows.slice(0,5)};
 }
 return {...report,groups,stocks:undefined,method:"EOD technical screening v1; fixed heuristic weights, not trained confidence; no guarantee or verified BUY calls"};
}
return {daily,validateMarket,expectedWeekday,model,configs};
});
