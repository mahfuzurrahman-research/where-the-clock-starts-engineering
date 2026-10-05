import unittest
from pathlib import Path
from src.clock_engineering.pipeline import run
ROOT=Path(__file__).resolve().parents[1]
class T(unittest.TestCase):
 def test_end_to_end(self):
  o=run(ROOT); self.assertEqual(o['quality']['status'],'PASS'); self.assertEqual(o['clock']['chronology_failures'],0); self.assertTrue(o['reconciliation']['keys_match'])
if __name__=='__main__': unittest.main()
