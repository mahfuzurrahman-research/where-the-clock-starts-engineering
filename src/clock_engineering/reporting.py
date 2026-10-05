import json
from pathlib import Path
def write_reports(payload,out):
    out=Path(out); out.mkdir(parents=True,exist_ok=True); (out/'audit_summary.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    c=payload['checkpoint']; q=payload['quality']; clk=payload['clock']; rec=payload['reconciliation']
    md=f'''# Public Engineering Audit

## Checkpoint reconciliation
- Cases: {rec['cases']}
- Stage records: {rec['stages']}
- Keys match: **{str(rec['keys_match']).lower()}**

## Sample accounting
- Parent rows: {c['parent_rows']}
- Primary rows: {c['primary_rows']}
- Process rows: {c['process_rows']}
- Payment rows: {c['payment_rows']}

## Process-clock QA
- Eligible rows: {clk['eligible_rows']}
- Flagged rows: {clk['clock_flagged']}
- Restricted rows: {clk['clock_restricted']}
- Chronology failures: {clk['chronology_failures']}

## Relational QA
- Checks: {q['checks']}
- Failures: {q['failures']}
- Status: **{q['status']}**

## Boundary
All records are synthetic. No private study result is included.
'''
    (out/'audit_report.md').write_text(md,encoding='utf-8')
