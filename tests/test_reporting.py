import tempfile,unittest
from pathlib import Path
from src.clock_engineering.reporting import write_reports
class T(unittest.TestCase):
 def test_reports(self):
  o={'checkpoint':{'parent_rows':1,'primary_rows':1,'process_rows':1,'payment_rows':0},'quality':{'checks':1,'failures':0,'status':'PASS'},'clock':{'eligible_rows':1,'clock_flagged':0,'clock_restricted':1,'chronology_failures':0},'reconciliation':{'cases':1,'stages':1,'keys_match':True}}
  with tempfile.TemporaryDirectory() as td:
   out=Path(td); write_reports(o,out); self.assertTrue((out/'audit_summary.json').is_file()); self.assertTrue((out/'audit_report.md').is_file())
if __name__=='__main__': unittest.main()
