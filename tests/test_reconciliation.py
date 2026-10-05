import tempfile,unittest
from pathlib import Path
from src.clock_engineering.reconciliation import reconcile
ROOT=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_reconcile(self): self.assertTrue(reconcile(ROOT/'data/synthetic/cases.csv',ROOT/'data/synthetic/stages.csv')['keys_match'])
 def test_missing_key_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   c=Path(td)/'c.csv'; s=Path(td)/'s.csv'; c.write_text('case_id,primary_flag,process_flag\nA,1,1\n'); s.write_text('case_id,primary_flag,stage_eligible\nB,1,1\n')
   with self.assertRaises(ValueError): reconcile(c,s)
if __name__=='__main__': unittest.main()
