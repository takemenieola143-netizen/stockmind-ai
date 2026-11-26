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
  },fetch:fakeFetch,AbortController,console});
  const tick=()=>new Promise(r=>setImmediate(r));
  await tick();await tick();
  assert.ok(resolveDixon);
  el("c7-stock").value="TCS";
  await el("c7-stock").events.change();
  assert.match(el("c7-symbol").textContent,/^TCS/);
  assert.match(el("c7-status").textContent,/Candle date/);
  assert.ok(el("c7-chart").children.length>0);
  assert.equal(el("c7-levels").disabled,true);
  resolveDixon(response(chart("DIXON")));
  await tick();
  assert.match(el("c7-symbol").textContent,/^TCS/);
  el("c7-stock").value="RELIANCE";
  await el("c7-stock").events.change();
  assert.match(el("c7-status").textContent,/not yet published for RELIANCE/);
  assert.equal(el("c7-chart").children.length,0);
  assert.equal(el("c7-plan").children.length,0);
});
