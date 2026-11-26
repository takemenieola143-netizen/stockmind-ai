import unittest
from datetime import date, timedelta
from research_engine_v8 import fundamentals, news_review, empirical_ranges, backtest, integrate

ASOF=date(2026,11,25)

def history(n=500):
    return [{"date":(ASOF-timedelta(days=n-1-i)).isoformat(),
             "open":100+i*.2,"close":100.1+i*.2,
             "high":101+i*.2,"low":99+i*.2} for i in range(n)]

def financial(i=1):
    return {"available_date":"2026-11-20","source_url":"https://example.com/fixture",
            "sector":"Industrial","financial_company":False,"roe_pct":i,
            "roce_pct":i,"revenue_growth_pct":i,"profit_growth_pct":i,
            "pe":30-i,"pb":10-i*.1,"debt_to_equity":2-i*.1}

class ResearchTests(unittest.TestCase):
    def test_missing_and_future_financials(self):
        self.assertIsNone(fundamentals(None,[],ASOF)["score"])
        r=financial();r["available_date"]="2026-11-26"
        self.assertIsNone(fundamentals(r,[financial(i) for i in range(10)],ASOF)["score"])
    def test_sector_comparison(self):
        peers=[financial(i) for i in range(12)]
        self.assertGreater(fundamentals(peers[-1],peers,ASOF)["score"],fundamentals(peers[0],peers,ASOF)["score"])
        self.assertIsNone(fundamentals(peers[-1],peers[:3],ASOF)["score"])
    def test_news_dates_and_flags(self):
        item={"available_date":"2026-11-25","source_url":"https://example.com/fixture","headline":"Test disclosure","category":"default"}
        self.assertEqual(news_review([],ASOF)["status"],"UNKNOWN")
        self.assertEqual(news_review([item,item,{**item,"available_date":"2026-11-26"}],ASOF)["risk_flags"],["default"])
        self.assertEqual(len(news_review([item,item],ASOF)["items"]),1)
    def test_ranges_and_backtest(self):
        c=history()
        r=empirical_ranges(c,ASOF)
        self.assertEqual(r["20"]["status"],"HISTORICAL_SCENARIO")
        self.assertLessEqual(r["20"]["low"],r["20"]["high"])
        self.assertEqual(empirical_ranges(history(90),ASOF)["20"]["status"],"UNKNOWN")
        b=backtest(c,ASOF)
        self.assertEqual(b["status"],"HISTORICAL_ONLY")
        self.assertGreater(b["trades"],0)
        self.assertEqual(b["cost_bps_round_trip"],20)
        future={**c[-1],"date":"2026-11-26"}
        self.assertEqual(backtest(c+[future],ASOF),b)
    def test_fail_closed(self):
        s={"symbol":"TCS","date":ASOF.isoformat(),"price":105,"score":80,
           "prediction_1d":{"status":"Available","up_probability":80}}
        market={"completed_sessions_only":True,"stocks":[s],"ai_diagnostics":{"1":{"reliable":True}}}
        r=integrate(market,{}, {},{},ASOF)["stocks"][0]
        self.assertEqual(r["decision"],"WAIT")
        self.assertIsNone(r["research_rank"])
        self.assertIsNone(r["probabilities"]["1"])
        self.assertIn("Fundamentals incomplete",r["blocks"])
    def test_fresh_models_but_no_trade_approval(self):
        c=history()
        price=c[-1]["close"]
        s={"symbol":"TCS","date":ASOF.isoformat(),"price":price,"score":80,
           "prediction_1d":{"status":"Available","up_probability":80}}
        m={"completed_sessions_only":True,"stocks":[s],"ai_diagnostics":{"1":{"reliable":True}}}
        chart={"symbol":"TCS","price_date":ASOF.isoformat(),"close":price,"freshness_verified":True,"candles":c}
        r=integrate(m,{"TCS":chart},{},{},ASOF)["stocks"][0]
        self.assertEqual(r["probabilities"]["1"],80)
        self.assertEqual(r["decision"],"WAIT")
        self.assertEqual(r["backtest"]["status"],"HISTORICAL_ONLY")

if __name__=="__main__":
    unittest.main()
