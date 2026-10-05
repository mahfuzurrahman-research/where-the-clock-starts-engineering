import tempfile,unittest
from pathlib import Path
from src.clock_engineering.warehouse import build,quality_summary,checkpoint_summary
ROOT=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_warehouse(self):
  with tempfile.TemporaryDirectory() as td:
   con=build(ROOT/'data/synthetic/cases.csv',ROOT/'data/synthetic/stages.csv',Path(td)/'x.sqlite')
   try: self.assertEqual(quality_summary(con)['status'],'PASS'); self.assertGreater(checkpoint_summary(con)['parent_rows'],0)
   finally: con.close()
if __name__=='__main__': unittest.main()
