import tempfile,unittest,csv
from pathlib import Path
from src.clock_engineering.warehouse import build
from src.clock_engineering.clocks import validate_process_clocks
from src.clock_engineering.contracts import validate_stages
ROOT=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_clock_pass(self):
  with tempfile.TemporaryDirectory() as td:
   con=build(ROOT/'data/synthetic/cases.csv',ROOT/'data/synthetic/stages.csv',Path(td)/'x.sqlite')
   try: self.assertEqual(validate_process_clocks(con)['chronology_failures'],0)
   finally: con.close()
 def test_bad_chronology_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'s.csv'
   with p.open('w',newline='',encoding='utf-8') as f:
    x=csv.writer(f); x.writerow(['case_id','primary_flag','stage_eligible','second_stage_indicator','clock_flag','issue_date','notification_date','visit_date','report_date','decision_date']); x.writerow(['X','1','1','0','1','2025-01-05','2025-01-04','2025-01-06','2025-01-07','2025-01-08'])
   with self.assertRaises(ValueError): validate_stages(p,ROOT/'contracts/stages.contract.json')
if __name__=='__main__': unittest.main()
