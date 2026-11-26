/* StockMind 8.0 on-demand research; no credential storage or automatic trading. */
(function(root,factory){
 const api=factory();if(typeof module==="object"&&module.exports)module.exports=api;else root.CompanyResearch=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
 "use strict";
 const finite=v=>typeof v==="number"&&Number.isFinite(v);
 function parseRatio(v){
   if(finite(v))return v;
   if(typeof v!=="string")return null;
   const s=v.trim().replace(/[,₹%]/g,"").trim();
   if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(s))return null;
   const n=Number(s);return finite(n)?n:null;
 }
 function validSymbol(s){return typeof s==="string"&&/^[A-Z0-9&_.-]{1,40}$/.test(s);}
 function normalizeFinancial(payload,symbol,now=new Date()){
   if(!validSymbol(symbol)||!payload||payload.trading_symbol!==symbol||
       ![true,"true"].includes(payload.success)||!payload.data||typeof payload.data!=="object")
     throw Error("Provider response does not match selected stock.");
   const d=payload.data, r=d.top_ratios;
   if(!r||typeof r!=="object")throw Error("Financial ratios unavailable.");
   const stamp=d.last_updated_at;
   // Provider example has a timezone-free timestamp: use calendar date, not assumed time.
   const day=typeof stamp==="string"?stamp.slice(0,10):"";
   if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!Number.isFinite(Date.parse(day))||
       new Date(day).toISOString().slice(0,10)!==day)throw Error("Provider update date unavailable.");
   const today=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(now);
   const p=Object.fromEntries(today.map(x=>[x.type,x.value]));
   const observed=p.year+"-"+p.month+"-"+p.day;
   if(day>observed)throw Error("Provider update date is in the future.");
   const age=(Date.parse(observed)-Date.parse(day))/86400000;
   const pe=parseRatio(r["Stock P/E"]), price=parseRatio(r["Current Price"]), book=parseRatio(r["Book Value"]);
   const values=[["P/E",pe!==null&&pe>0?pe:null,"x"],["P/B (provider price / book)",price!==null&&price>0&&book!==null&&book>0?price/book:null,"x"],
     ["ROE",parseRatio(r.ROE),"%"],["ROCE",parseRatio(r.ROCE),"%"],["Dividend yield",parseRatio(r["Dividend Yield"]),"%"],
     ["Provider price",price,"₹"],["Book value per share",book,"₹"]];
   if(!values.some(v=>v[1]!==null))throw Error("No supported financial ratios returned.");
   return {symbol,company:typeof payload.company==="string"?payload.company:symbol,day,observed,age,statement:d.statement_type||"Unspecified",values,
     status:age>180?"STALE":"PROVIDER_DATA",note:"Provider-reported ratios; not independently audited. No peer score without comparable sector records."};
 }
 function companyPhrase(s){
   if(typeof s!=="string")return "";
   return s.normalize("NFKC").replace(/\b(?:limited|ltd|inc|plc|corporation)\.?$/i,"").replace(/["\\]/g,"").trim().replace(/\s+/g," ");
 }
 function newsURL(name){
   const phrase=companyPhrase(name);
   if(phrase.length<5||phrase.length>100||!/[\p{L}]/u.test(phrase))throw Error("Enter the full company name (at least 5 characters).");
   const u=new URL("https://api.gdeltproject.org/api/v2/doc/doc");
   u.search=new URLSearchParams({query:'"'+phrase+'"',mode:"ArtList",format:"json",maxrecords:"20",timespan:"14d",sort:"DateDesc"}).toString();
   return u.href;
 }
 function normalizeNews(payload,name){
   const phrase=companyPhrase(name).toLowerCase();
   if(!payload||!Array.isArray(payload.articles))throw Error("News service returned an unexpected response.");
   const results=[],seen=new Set();
   for(const a of payload.articles){
     if(!a||typeof a.title!=="string"||!a.title.toLowerCase().includes(phrase))continue;
     try{
       const u=new URL(a.url);if(u.protocol!=="https:"&&u.protocol!=="http:")continue;
       if(seen.has(u.href))continue;seen.add(u.href);
       const date=typeof a.seendate==="string"&&/^\d{8}T\d{6}Z$/.test(a.seendate)?a.seendate.slice(0,4)+"-"+a.seendate.slice(4,6)+"-"+a.seendate.slice(6,8):"Unknown";
       // This is a topic cue, not a claim that an event occurred.
       const risk=/\b(fraud|default|probe|penalty|investigation|lawsuit|resignation|downgrade)\b/i.test(a.title);
       results.push({title:a.title.slice(0,300),url:u.href,domain:u.hostname,seen:date,topic:risk?"Risk-related words — read source":"Read source"});
     }catch{}
   }
   return results;
 }
 function normalizeProviderNews(payload,symbol,now=new Date()){
   if(!validSymbol(symbol)||!payload||payload.trading_symbol!==symbol||!Array.isArray(payload.data))throw Error("Provider news does not match selected stock.");
   const results=[],seen=new Set();
   for(const a of payload.data){
     if(!a||typeof a.heading!=="string"||!finite(a.published_time))continue;
     const age=now.getTime()-a.published_time;
     if(age<0||age>14*86400000)continue;
     try{
       const u=new URL(a.article_link);if(u.protocol!=="https:"&&u.protocol!=="http:")continue;
       if(seen.has(u.href))continue;seen.add(u.href);
       const risk=/\b(fraud|default|probe|penalty|investigation|lawsuit|resignation|downgrade)\b/i.test(a.heading);
       results.push({title:a.heading.slice(0,300),url:u.href,domain:u.hostname,seen:new Date(a.published_time).toISOString().slice(0,10),topic:risk?"Risk-related words — read source":"Read source"});
     }catch{}
   }
   return results;
 }
 return {parseRatio,validSymbol,normalizeFinancial,companyPhrase,newsURL,normalizeNews,normalizeProviderNews};
});
