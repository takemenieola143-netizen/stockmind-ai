const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const h = require("../stock_dashboard.js");

function chart(symbol="TCS") {
  return {symbol,price_date:"2026-11-25",close:105,freshness_verified:true,
    candles:[
      {date:"2026-11-23",open:100,high:105,low:98,close:102,volume:1000},
      {date:"2026-11-25",open:102,high:106,low:100,close:105,volume:1200}
    ]};
}
test("symbol and company search, case-insensitive", () => {
  const stocks=[{symbol:"TCS",name:"Tata Consultancy Services"},{symbol:"DIXON"},null];
  assert.deepEqual(h.filterStocks(stocks,"tata").map(s=>s.symbol),["TCS"]);
  assert.deepEqual(h.filterStocks(stocks," dix ").map(s=>s.symbol),["DIXON"]);
  assert.equal(h.filterStocks(stocks,"").length,2);
});
test("safe stock-specific paths", () => {
  assert.equal(h.chartPath("TCS"),"charts/544353.json");
  assert.match(h.chartPath("../M&M"),/^charts\/[a-f0-9]+\.json$/);
  assert.notEqual(h.chartPath("M&M"),h.chartPath("MM"));
  assert.throws(()=>h.chartPath(""));
});
test("wrong stock, duplicate dates, invalid prices, close mismatch rejected", () => {
  assert.equal(h.validChart(chart(),"TCS"),true);
  assert.equal(h.validChart(chart(),"DIXON"),false);
  let c=chart();c.candles[1].date=c.candles[0].date;
  assert.equal(h.validChart(c,"TCS"),false);
  c=chart();c.candles[1].high=101;
  assert.equal(h.validChart(c,"TCS"),false);
  c=chart();c.close=106;
  assert.equal(h.validChart(c,"TCS"),false);
  c=chart();c.candles[0].date="2026-02-30";
  assert.equal(h.validChart(c,"TCS"),false);
});
test("snapshot match requires date, price, backend verification and completed sessions",()=>{
  const stock={symbol:"TCS",date:"2026-11-25",price:105};
  const market={completed_sessions_only:true,stocks:[stock]};
  assert.equal(h.matchesSnapshot(chart(),stock,market),true);
  assert.equal(h.matchesSnapshot(chart(),{...stock,price:106},market),false);
  assert.equal(h.matchesSnapshot({...chart(),freshness_verified:false},stock,market),false);
  assert.equal(h.matchesSnapshot(chart(),stock,{...market,completed_sessions_only:false}),false);
  assert.equal(h.matchesSnapshot(chart(),stock,{...market,stocks:[stock,{date:"2026-11-26"}]}),false);
});
test("only approved probability values displayed",()=>{
  assert.equal(h.predictionLabel({status:"Available",up_probability:60,direction:"Bullish"}),"Bullish | Up probability 60.0%");
  assert.equal(h.predictionLabel({status:"No signal",up_probability:80}),"No validated signal");
  assert.equal(h.predictionLabel({status:"Available",up_probability:101}),"No validated signal");
});
test("all inline scripts parse and dashboard IDs are unique",()=>{
  const html=fs.readFileSync("index.html","utf8");
  for(const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)) {
    if(m[1].trim()) new vm.Script(m[1]);
  }
  const ids=[...html.matchAll(/\bid="(c7-[^"]+)"/g)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length);
  assert.ok(ids.includes("c7-stock") && ids.includes("c7-search"));
  assert.match(html,/<script src="stock_dashboard.js"><\/script>/);
});
test("stock changes cannot show an earlier asynchronous chart", async()=>{
  const html=fs.readFileSync("index.html","utf8");
  const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
  const code=scripts.find(m=>m[1].includes("async function renderSelected()"))[1];
  class Elem {
    constructor(){this.children=[];this.events={};this.value="";this.textContent="";this.style={};this.disabled=false;}
    replaceChildren(){this.children=[];this.value="";}
    appendChild(n){this.children.push(n);if(!this.value&&n.value)this.value=n.value;return n;}
    append(...nodes){nodes.forEach(n=>this.appendChild(n));}
    prepend(n){this.children.unshift(n);}
    addEventListener(k,f){this.events[k]=f;}
    setAttribute(){}
  }
  const elements=new Map();
  const el=id=>{if(!elements.has(id))elements.set(id,new Elem());return elements.get(id);};
  el("c7-range").value="30";
  const market={completed_sessions_only:true,stocks:[
    {symbol:"DIXON",date:"2026-11-25",price:105},
    {symbol:"TCS",date:"2026-11-25",price:105},
    {symbol:"RELIANCE",date:"2026-11-25",price:105}
  ]};
  let resolveDixon;
  const response=(value)=>({ok:true,json:async()=>value});
  const fakeFetch=async path=>{
    if(path==="market_data.json")return response(market);
    if(path==="chart_data.json")return response(chart("DIXON"));
    if(path===h.chartPath("DIXON"))return new Promise(r=>{resolveDixon=r;});
    if(path===h.chartPath("TCS"))return response(chart("TCS"));
    return {ok:false};
  };
  vm.runInNewContext(code,{StockMindDashboard:h,document:{
    getElementById:el,createElement:()=>new Elem(),createElementNS:()=>new Elem(),body:new Elem()
  },fetch:fakeFetch,AbortController,URLSearchParams,console});
  const tick=()=>new Promise(r=>setImmediate(r));
  await tick();await tick();
  assert.ok(resolveDixon);
  assert.equal(el("c7-stock").children.length,3);
  el("c7-stock").value="TCS";
  await el("c7-stock").events.change();
  assert.match(el("c7-symbol").textContent,/^TCS/);
  assert.match(el("c7-status").textContent,/Chart close/);
  assert.ok(el("c7-chart").children.length>0);
  assert.equal(el("c7-levels").disabled,false);
  resolveDixon(response(chart("DIXON")));
  await tick();
  assert.match(el("c7-symbol").textContent,/^TCS/);
  el("c7-stock").value="RELIANCE";
  await el("c7-stock").events.change();
  assert.match(el("c7-status").textContent,/not yet published for RELIANCE/);
  assert.equal(el("c7-chart").children.length,0);
  assert.equal(el("c7-plan").children.length,0);
  el("c7-search").value="TCS";el("c7-search").events.input();
  await tick();assert.equal(el("c7-stock").children.length,1);
  el("c7-reset").events.click();await tick();
  assert.equal(el("c7-stock").children.length,3);
});

test("personal chart validates provider identity and never enables trade levels",()=>{
  const p={meta:{symbol:"TCS",exchange:"NSE"},data:chart().candles};
  const r=h.personalChart(p,"TCS","2026-11-25");
  assert.equal(r.close,105);assert.equal(r.freshness_verified,false);assert.equal(r.reference_plan,null);
  assert.throws(()=>h.personalChart(p,"DIXON","2026-11-25"));
  assert.throws(()=>h.personalChart(p,"TCS","2026-11-23"));
  assert.throws(()=>h.personalChart({...p,data:[...p.data,p.data[1]]},"TCS","2026-11-25"));
});

test("raw chart indicators, hypothetical risk gate, and unvalidated model reason",()=>{
  const candles=Array.from({length:60},(_,i)=>({date:new Date(Date.parse("2026-11-25")-(59-i)*86400000).toISOString().slice(0,10),open:100+i*.1,high:101+i*.1,low:99+i*.1,close:100.5+i*.1,volume:i===59?2000:1000}));
  const report={symbol:"TCS",price_date:candles.at(-1).date,close:candles.at(-1).close,candles};
  const a=h.chartInsights(report,"TCS");
  assert.match(a.trend,/Upward/);assert.equal(a.relative_volume,2);assert.equal(a.paper.reward_risk,2);
  assert.ok(a.paper.stop_loss<a.paper.entry_trigger&&a.paper.entry_trigger<a.paper.target);
  assert.throws(()=>h.chartInsights(report,"INFY"));
  const extreme={...report,candles:candles.map((c,i)=>i===58?{...c,low:1}:c)};
  assert.equal(h.chartInsights(extreme,"TCS").paper,null);
  const m=h.modelEvidence({prediction_5d:{status:"No signal",reason:"No model beat validation baseline"}},{"5":{selected_models:[]}},5);
  assert.equal(m.probability,null);assert.match(m.reason,/baseline/);
  const unapproved=h.modelEvidence({prediction_1d:{status:"Available",up_probability:80}},{"1":{reliable:false}},1);
  assert.equal(unapproved.probability,null);
});
test("published scanner automatically yields reports without inventing financials",()=>{
  const report=h.scannerReport({completed_sessions_only:true,stocks:[{symbol:"TCS",price:100,date:"2026-11-25",score:80,backtest_return:5,backtest_trades:12}],ai_diagnostics:{}});
  assert.equal(report.length,1);assert.equal(report[0].backtest.return_pct,5);
  assert.equal(report[0].fundamental.status,"ON_DEMAND");assert.equal(report[0].decision,"WAIT");
  assert.equal(report[0].probabilities["10"],null);
});
test("long-history scenarios and private observation expiry",()=>{
  const candles=Array.from({length:420},(_,i)=>({date:new Date(Date.parse("2026-11-25")-(419-i)*86400000).toISOString().slice(0,10),open:100+i*.01,high:101+i*.01,low:99+i*.01,close:100.5+i*.01,volume:1000}));
  const result=h.historicalScenarios({meta:{symbol:"TCS",exchange:"NSE"},data:candles},"TCS","2026-11-25");
  assert.equal(result.ranges["20"].status,"HISTORICAL_SCENARIO");
  assert.ok(result.ranges["20"].low<=result.ranges["20"].high);
  const map=new Map(),storage={setItem:(k,v)=>map.set(k,v),getItem:k=>map.get(k)};
  h.recordObservation(storage,"TCS","financials","retrieved",1000);
  assert.equal(h.observation(storage,"TCS","financials",2000),"retrieved");
  assert.equal(h.observation(storage,"INFY","financials",2000),null);
  assert.equal(h.observation(storage,"TCS","financials",1000+86400001),null);
});
