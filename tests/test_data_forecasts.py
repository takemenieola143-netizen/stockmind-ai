import unittest
from datetime import date, timedelta
from personal_data_adapter import financial_record, news_records
from research_engine_v8 import validate_ranges, integrate

ASOF=date(2026,11,25)

class DataForecastTests(unittest.TestCase):
    def test_normalization_and_identity(self):
        info={"symbol":"TCS.NS","quoteType":"EQUITY","sector":"Technology",
              "trailingPE":25,"returnOnEquity":.35,"revenueGrowth":.05,
              "earningsGrowth":.07,"debtToEquity":12,"marketCap":1000,
              "freeCashflow":40,"currency":"INR","financialCurrency":"INR"}
        r=financial_record(info,"TCS",ASOF)
        self.assertEqual(r["roe_pct"],35)
        self.assertEqual(r["debt_to_equity"],.12)
        self.assertEqual(r["free_cash_flow_yield_pct"],4)
        self.assertEqual(r["source_kind"],"provider_snapshot")
        self.assertIsNone(financial_record(info,"INFY",ASOF))
        self.assertNotIn("free_cash_flow_yield_pct",financial_record({**info,"financialCurrency":"USD"},"TCS",ASOF))
    def test_news_ticker_and_date(self):
        c={"title":"Fixture headline","pubDate":"2026-11-25T09:00:00Z",
           "canonicalUrl":{"url":"https://example.com/story"},
           "finance":{"stockTickers":[{"symbol":"TCS.NS"}]}}
        self.assertEqual(len(news_records([{"content":c}],"TCS",ASOF)),1)
        self.assertFalse(news_records([{"content":c}],"INFY",ASOF))
        self.assertFalse(news_records([{"content":{**c,"pubDate":"2026-11-26T09:00:00Z"}}],"TCS",ASOF))
        self.assertFalse(news_records([{"content":{**c,"canonicalUrl":{"url":"javascript:alert(1)"}}}],"TCS",ASOF))
    def test_walk_forward_no_future(self):
        candles=[]
        for i in range(1250):
            p=100+i*.1+(i%7)*.4
            candles.append({"date":(ASOF-timedelta(days=1249-i)).isoformat(),"open":p,"high":p+1,"low":p-1,"close":p})
        r=validate_ranges(candles,ASOF)
        self.assertEqual(r["1"]["status"],"HISTORICAL_DIAGNOSTIC")
        self.assertEqual(r["20"]["status"],"HISTORICAL_DIAGNOSTIC")
        self.assertTrue(0<=r["1"]["coverage_pct"]<=100)
        future={**candles[-1],"date":"2026-11-26","open":999,"close":999,"low":998,"high":1000}
        self.assertEqual(validate_ranges(candles+[future],ASOF),r)
        self.assertEqual(validate_ranges(candles[-90:],ASOF)["20"]["status"],"INSUFFICIENT_HOLDOUT")
    def test_information_cutoff(self):
        m={"completed_sessions_only":True,"stocks":[]}
        with self.assertRaises(ValueError): integrate(m,{}, {},{},ASOF,information_asof=ASOF-timedelta(days=1))

if __name__=="__main__": unittest.main()
