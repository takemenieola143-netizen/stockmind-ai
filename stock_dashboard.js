/* Shared stock-dashboard validation; no data fetching or trading. */
(function(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.StockMindDashboard = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function() {
  "use strict";
  const finite = v => typeof v === "number" && Number.isFinite(v);
  const validDate = v => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) &&
    !Number.isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0,10) === v;
  function chartPath(symbol) {
    if (typeof symbol !== "string" || !symbol || symbol.length > 80) throw Error("Invalid symbol");
    return "charts/" + Array.from(new TextEncoder().encode(symbol),
      b => b.toString(16).padStart(2,"0")).join("") + ".json";
  }
  function filterStocks(stocks, query) {
    const q = String(query || "").trim().toUpperCase();
    return stocks.filter(s => s && typeof s.symbol === "string" && s.symbol &&
      [s.symbol,s.name,s.company_name,s.company].some(v =>
        typeof v === "string" && v.toUpperCase().includes(q)));
  }
  function validChart(c, symbol) {
    if (!c || c.symbol !== symbol || !validDate(c.price_date) || !finite(c.close) ||
        !Array.isArray(c.candles) || c.candles.length < 2 || c.candles.length > 90) return false;
    const ok = c.candles.every((v,i,a) => v && validDate(v.date) &&
      (!i || a[i-1].date < v.date) &&
      ["open","high","low","close","volume"].every(k => finite(v[k])) &&
      v.low > 0 && v.low <= Math.min(v.open,v.close) &&
      v.high >= Math.max(v.open,v.close) && v.volume >= 0);
    const last = c.candles[c.candles.length-1];
    return ok && last.date === c.price_date && Math.abs(last.close-c.close) <= 0.000001;
  }
  function matchesSnapshot(c, stock, market) {
    return validChart(c,stock.symbol) && c.freshness_verified === true &&
      market.completed_sessions_only === true && stock.date === c.price_date &&
      finite(stock.price) && Math.abs(stock.price-c.close) <= 0.05 &&
      !(market.stocks || []).some(s => s && validDate(s.date) && s.date > c.price_date);
  }
  function predictionLabel(p) {
    if (!p || p.status !== "Available" || !finite(p.up_probability) ||
        p.up_probability < 0 || p.up_probability > 100) return "No validated signal";
    return (typeof p.direction === "string" ? p.direction : "Unknown") +
      " | Up probability " + p.up_probability.toFixed(1) + "%";
  }
  function personalChart(payload,symbol,to) {
    if (!payload || payload.meta?.symbol !== symbol ||
        String(payload.meta?.exchange).toUpperCase() !== "NSE" ||
        !Array.isArray(payload.data) || !validDate(to)) throw Error("Wrong stock or exchange");
    const candles = payload.data.filter(c => c && (c.series === undefined || c.series === "EQ"))
      .map(c => ({date:c.date,open:c.open,high:c.high,low:c.low,close:c.close,volume:c.volume}))
      .sort((a,b)=>String(a.date).localeCompare(String(b.date)));
    if (candles.some(c=>!validDate(c.date)||c.date>to) || candles.length<2 ||
        new Set(candles.map(c=>c.date)).size!==candles.length) throw Error("Invalid candle dates");
    const last=candles[candles.length-1], prior=candles.slice(-21,-1);
    const c={symbol,price_date:last.date,close:last.close,candles:candles.slice(-90),
      source:"TejHQ personal EOD data",freshness_verified:false,reference_plan:null,
      decision:"WAIT",patterns:[],breakout:false};
    if (!validChart(c,symbol)) throw Error("Invalid prices");
    if(prior.length===20){
      c.support_20d=Math.min(...prior.map(x=>x.low));
      c.resistance_20d=Math.max(...prior.map(x=>x.high));
      c.trend="Not evaluated — unadjusted history";
    }
    return c;
  }
  function chartInsights(chart,symbol) {
    if(!validChart(chart,symbol))throw Error("Invalid chart");
    const c=chart.candles,last=c[c.length-1],prev=c[c.length-2],prior=c.slice(-21,-1);
    const mean=a=>a.reduce((x,y)=>x+y,0)/a.length;
    const avg=n=>c.length>=n?mean(c.slice(-n).map(x=>x.close)):null;
    const sma20=avg(20),sma50=avg(50);
    const trend=sma50===null?"Need 50 candles":last.close>sma20&&sma20>sma50?"Upward":last.close<sma20&&sma20<sma50?"Downward":"Mixed";
    const range=last.high-last.low,body=Math.abs(last.close-last.open);
    const lower=Math.min(last.open,last.close)-last.low,upper=last.high-Math.max(last.open,last.close);
    const patterns=[];
    if(range>0&&body/range<=.1)patterns.push("Doji");
    if(body>0&&lower>=2*body&&upper<=body)patterns.push("Hammer-shaped");
    if(body>0&&upper>=2*body&&lower<=body)patterns.push("Shooting-star-shaped");
    if(prev.close<prev.open&&last.close>last.open&&last.open<=prev.close&&last.close>=prev.open)patterns.push("Bullish engulfing");
    if(prev.close>prev.open&&last.close<last.open&&last.open>=prev.close&&last.close<=prev.open)patterns.push("Bearish engulfing");
    const support=prior.length===20?Math.min(...prior.map(x=>x.low)):null;
    const resistance=prior.length===20?Math.max(...prior.map(x=>x.high)):null;
    const v=prior.length===20?mean(prior.map(x=>x.volume)):0;
    const relative_volume=v>0?last.volume/v:null;
    const tr=c.slice(1).map((x,i)=>Math.max(x.high-x.low,Math.abs(x.high-c[i].close),Math.abs(x.low-c[i].close)));
    const atr=tr.length>=14?mean(tr.slice(-14)):null;
    const round=x=>Math.round(x*100)/100;
    let paper=null,reason="At least 21 candles and positive ATR required";
    if(resistance!==null&&atr!==null&&atr>0){
      const entry=round(Math.max(resistance,last.high)+.1*atr);
      const stop=round(Math.min(...c.slice(-5).map(x=>x.low))-.1*atr);
      const risk=entry-stop;
      reason="Hypothetical setup rejected: invalid stop or risk exceeds 8%";
      if(stop>0&&risk>0&&risk/entry<=.08){
        paper={entry_trigger:entry,stop_loss:stop,target:round(entry+2*risk),reward_risk:2,risk_pct:round(100*risk/entry)};
        reason="Historical rule example only; not a live signal or validated strategy";
      }
    }
    return {trend:trend+" (raw-price chart)",patterns,support_20d:support,resistance_20d:resistance,relative_volume,atr_14:atr,breakout:resistance!==null&&relative_volume!==null&&last.close>resistance&&relative_volume>=1.5,paper,reason};
  }
  function modelEvidence(stock,diagnostics,h) {
    const p=stock?.["prediction_"+h+"d"]||{},d=diagnostics?.[String(h)]||{},e=d.evaluation||{};
    const approved=p.status==="Available"&&d.reliable===true&&finite(p.up_probability)&&p.up_probability>=0&&p.up_probability<=100;
    return {approved,probability:approved?p.up_probability:null,reason:approved?"Shared market model passed its historical gate":p.reason||(d.reliable===false?"Shared model failed final holdout":Array.isArray(d.selected_models)&&!d.selected_models.length?"No model beat selection baseline":"Stock prediction unavailable or holdout incomplete"),evaluation:e,models:Array.isArray(d.selected_models)?d.selected_models:[]};
  }
  function scannerReport(market) {
    if(!market||!Array.isArray(market.stocks)||market.completed_sessions_only!==true)throw Error("Invalid published scanner report");
    return market.stocks.filter(s=>s&&typeof s.symbol==="string").map(s=>{
      const models=Object.fromEntries([1,5,10,20].map(h=>[h,modelEvidence(s,market.ai_diagnostics,h)]));
      return {symbol:s.symbol,date:s.date,price:s.price,technical_score:s.score,decision:"WAIT",
        fundamental:{status:"ON_DEMAND",reason:"Open company research to fetch authorized financial ratios"},news:{status:"ON_DEMAND",reason:"Open company research for news"},
        probabilities:Object.fromEntries(Object.entries(models).map(([h,m])=>[h,m.probability])),
        model_evidence:models,backtest:{status:"LEGACY_SCANNER",return_pct:s.backtest_return,benchmark_return_pct:s.benchmark_return,max_drawdown_pct:s.max_drawdown,trades:s.backtest_trades},
        blocks:["Published scanner snapshot only; price scenarios require historical candles","Financial and news evidence not part of automated model","Forward profitability not verified"]};
    });
  }
  function historicalScenarios(payload,symbol,to){
    const chart=personalChart(payload,symbol,to);
    const c=payload.data.filter(x=>x&&(x.series===undefined||x.series==="EQ")).sort((a,b)=>a.date.localeCompare(b.date));
    if(c.length>1250||c.some(x=>!finite(x.close)||x.close<=0||!finite(x.open)||!finite(x.high)||!finite(x.low)||x.low<=0||x.low>Math.min(x.open,x.close)||x.high<Math.max(x.open,x.close)))throw Error("Invalid historical prices");
    const prices=c.map(x=>x.close),n=prices.length;
    const q=(a,p)=>{const s=[...a].sort((x,y)=>x-y),i=(s.length-1)*p;return s[Math.floor(i)]+(s[Math.ceil(i)]-s[Math.floor(i)])*(i-Math.floor(i));};
    const out={};
    for(const h of [1,5,10,20]){
      const a=[];for(let i=n-1;i>=h;i-=h)a.push(prices[i]/prices[i-h]-1);
      if(a.length<20){out[h]={status:"INSUFFICIENT_HISTORY",samples:a.length};continue;}
      const p=prices[n-1];
      out[h]={status:"HISTORICAL_SCENARIO",samples:a.length,low:p*(1+q(a,.1)),median:p*(1+q(a,.5)),high:p*(1+q(a,.9)),anchor_date:chart.price_date};
    }
    return {symbol,date:chart.price_date,close:chart.close,ranges:out,samples:n};
  }
  function observation(storage,symbol,kind,now=Date.now()){
    try {
      const v=JSON.parse(storage.getItem("stockmind-observed:"+symbol+":"+kind)||"null");
      if(!v||v.symbol!==symbol||v.kind!==kind||!finite(v.at)||now-v.at<0||now-v.at>24*3600000||typeof v.label!=="string")return null;
      return v.label;
    }catch{return null;}
  }
  function recordObservation(storage,symbol,kind,label,now=Date.now()){
    if(!["financials","news"].includes(kind)||typeof symbol!=="string"||!symbol||typeof label!=="string")return;
    try{storage.setItem("stockmind-observed:"+symbol+":"+kind,JSON.stringify({symbol,kind,label:label.slice(0,200),at:now}));}catch{}
  }
  return {chartPath,filterStocks,validChart,matchesSnapshot,predictionLabel,personalChart,chartInsights,modelEvidence,scannerReport,historicalScenarios,observation,recordObservation};
});
