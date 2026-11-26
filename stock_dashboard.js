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
  return {chartPath,filterStocks,validChart,matchesSnapshot,predictionLabel,personalChart};
});
