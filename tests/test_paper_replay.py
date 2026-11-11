import csv, tempfile, unittest
from pathlib import Path
from decimal import Decimal
from research.paper_replay import PaperReplay, load_bars

class PaperReplayTests(unittest.TestCase):
    def make_csv(self,root):
        path=Path(root)/"bars.csv"
        prices=[10,9,8,7,8,9,10,11,12,13,14,13,12,11,10,9]
        with path.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["timestamp","symbol","open","high","low","close","volume"])
            for i,p in enumerate(prices): w.writerow([f"2026-01-{i+1:02d}T12:00:00Z","TEST",p,p+1,p-1,p,100])
        return path
    def test_durable_idempotent_hash_chained_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=self.make_csv(tmp); bars,digest=load_bars(src); db=Path(tmp)/"state.sqlite3"
            engine=PaperReplay(db,fast=2,slow=3,starting_cash=Decimal("1000"))
            first=engine.replay(bars,digest); self.assertTrue(first["event_chain_valid"]); self.assertGreater(first["entries"],0)
            count=first["event_count"]; second=engine.replay(bars,digest); self.assertEqual(second["event_count"],count); engine.close()
            reopened=PaperReplay(db,fast=2,slow=3); self.assertEqual(reopened.report()["event_count"],count)
            self.assertTrue(reopened.verify_chain()); reopened.close()
    def test_incremental_import_uses_persisted_sma_warmup(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.make_csv(tmp); bars,digest=load_bars(source)
            engine=PaperReplay(Path(tmp)/"incremental.sqlite3",fast=2,slow=3)
            engine.replay(bars[:5],digest)
            result=engine.replay(bars[5:],digest)
            self.assertGreater(result["entries"],0)
            self.assertTrue(result["event_chain_valid"])
            engine.close()
    def test_rejects_timezone_naive_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bad.csv"; p.write_text("timestamp,symbol,open,high,low,close,volume\n2026-01-01,TEST,1,2,0.5,1,10\n")
            with self.assertRaises(ValueError): load_bars(p)
    def test_rejects_invalid_sma_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): PaperReplay(Path(tmp)/"state.db",fast=5,slow=5)
if __name__=="__main__": unittest.main()
