import unittest
from auto_paper import advance,stamp
class TestPaper(unittest.TestCase):
    def test_flow(self):
        s={"open":{},"closed":[],"seen":[]}
        now=stamp("2026-11-27T05:05:00Z")
        advance(s,None,now)
        self.assertFalse(s["open"])
        e=dict(id="1",time="2026-11-27T05:00:00Z",signal_time="2026-11-27T04:59:00Z",verified=True,source="synthetic test",category="short",symbol="TEST",price=100,stop=95,target=110,action="BUY")
        f={"verified":True,"events":[e]}
        advance(s,f,now)
        advance(s,f,now)
        self.assertEqual(len(s["open"]),1)
        advance(s,{"verified":True,"events":[dict(e,id="2",time="2026-11-27T05:04:00Z",price=111,action="QUOTE")]},now)
        self.assertFalse(s["open"])
        self.assertEqual(s["closed"][0]["reason"],"target")
        self.assertGreater(s["closed"][0]["pnl"],0)
    def test_stale(self):
        s={"open":{},"closed":[],"seen":[]}
        advance(s,{"verified":True,"events":[{"time":"2026-11-27T04:00:00Z"}]},stamp("2026-11-27T05:00:00Z"))
        self.assertFalse(s["open"])
