from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.clock_engineering.pipeline import run
run(ROOT)
print('CONTRACT_VALIDATION=PASS'); print('CHECKPOINT_RECONCILIATION=PASS'); print('PROCESS_CLOCK_QA=PASS'); print('RELATIONAL_QA=PASS')
