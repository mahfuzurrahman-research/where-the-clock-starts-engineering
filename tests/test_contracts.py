import tempfile,unittest,csv
from pathlib import Path
from src.clock_engineering.contracts import validate_cases,validate_stages
ROOT=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_valid(self):
  self.assertGreater(validate_cases(ROOT/'data/synthetic/cases.csv',ROOT/'contracts/cases.contract.json')['rows_checked'],0); self.assertGreater(validate_stages(ROOT/'data/synthetic/stages.csv',ROOT/'contracts/stages.contract.json')['rows_checked'],0)
 def test_bad_nested_flag(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'x.csv'
   with p.open('w',newline='',encoding='utf-8') as f:
    x=csv.writer(f); x.writerow(['case_id','decision_period','primary_flag','process_flag','payment_flag','inspection_count','reported_delay_days']); x.writerow(['X','2025-Q1','0','1','0','1','0'])
   with self.assertRaises(ValueError): validate_cases(p,ROOT/'contracts/cases.contract.json')
if __name__=='__main__': unittest.main()
