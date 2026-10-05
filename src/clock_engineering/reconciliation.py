import csv
from pathlib import Path

def reconcile(cases_csv,stages_csv):
    with Path(cases_csv).open(newline='',encoding='utf-8') as f: cases={r['case_id']:r for r in csv.DictReader(f)}
    with Path(stages_csv).open(newline='',encoding='utf-8') as f: stages={r['case_id']:r for r in csv.DictReader(f)}
    if set(cases)!=set(stages): raise ValueError('Checkpoint key sets disagree')
    for cid in sorted(cases):
        c,s=cases[cid],stages[cid]
        if c['primary_flag']!=s['primary_flag']: raise ValueError('Primary indicator mismatch')
        if s['stage_eligible']=='1' and c['process_flag']!='1': raise ValueError('Stage eligibility requires process eligibility')
    return {'cases':len(cases),'stages':len(stages),'keys_match':True,'primary_flags_match':True,'stage_requires_process':True}
