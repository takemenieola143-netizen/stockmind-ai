const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const api=require("../company_research.js");
test("financial identity, ratio normalization and dates",()=>{
 const p={success:"true",trading_symbol:"TCS",company:"Tata Consultancy Services",data:{statement_type:"consolidated",last_updated_at:"2026-11-25T09:00:00",top_ratios:{"Stock P/E":"24.3","Current Price":"₹3,000","Book Value":"₹500",ROE:"32.5%",ROCE:"45%","Dividend Yield":"2.0%"}}};
 const now=new Date("2026-11-26T08:00:00Z");
 const f=api.normalizeFinancial(p,"TCS",now);
 assert.equal(f.values[1][1],6);
 assert.equal(f.values[2][1],32.5);
 assert.throws(()=>api.normalizeFinancial(p,"INFY",now));
 assert.equal(api.normalizeFinancial({...p,data:{...p.data,last_updated_at:"2025-11-25"}},"TCS",now).status,"STALE");
 assert.throws(()=>api.normalizeFinancial({...p,data:{...p.data,last_updated_at:"2026-11-27"}},"TCS",now));
 assert.equal(api.parseRatio("N/A"),null);
});
test("news relevance and safe links",()=>{
 const name="Tata Consultancy Services Limited";
 const a={title:"Tata Consultancy Services announces results",url:"https://example.com/tcs",seendate:"20261126T080000Z"};
 const rows=api.normalizeNews({articles:[a,a,{...a,url:"javascript:alert(1)"},{...a,title:"Unrelated bank news"}]},name);
 assert.equal(rows.length,1);assert.equal(rows[0].seen,"2026-11-26");
 assert.equal(new URL(api.newsURL(name)).searchParams.get("query"),'"Tata Consultancy Services"');
 assert.throws(()=>api.newsURL("TCS"));
});
test("company research scripts parse and key is not persisted",()=>{
 const html=fs.readFileSync("company_research.html","utf8");
 for(const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)){if(m[1].trim())new vm.Script(m[1]);}
 assert.match(html,/type="password"/);
 assert.doesNotMatch(html,/localStorage|sessionStorage|document\.cookie/);
});

test("ticker news fallback verifies symbol, dates and links",()=>{
 const now=new Date("2026-11-26T08:00:00Z");
 const item={heading:"Company update",article_link:"https://example.com/news",published_time:now.getTime()-3600000};
 const p={trading_symbol:"TCS",data:[item,item,{...item,article_link:"javascript:alert(1)"},{...item,published_time:now.getTime()+1000}]};
 assert.equal(api.normalizeProviderNews(p,"TCS",now).length,1);
 assert.throws(()=>api.normalizeProviderNews(p,"INFY",now));
});
