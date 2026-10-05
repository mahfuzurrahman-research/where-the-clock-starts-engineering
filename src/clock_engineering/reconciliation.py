import csv
from pathlib import Path

def reconcile(cases_csv,stages_csv):
    def indexed(path):
        result={}
        with Path(path).open(newline='',encoding='utf-8') as f:
            for row in csv.DictReader(f):
                key=row.get('case_id')
                if not key or key in result: raise ValueError('Invalid/duplicate checkpoint key')
                result[key]=row
        if not result: raise ValueError('Empty checkpoint')
        return result
    cases=indexed(cases_csv); stages=indexed(stages_csv)
    if set(cases)!=set(stages): raise ValueError('Checkpoint key sets disagree')
    for cid in sorted(cases):
        c,s=cases[cid],stages[cid]
        if c['primary_flag']!=s['primary_flag']: raise ValueError('Primary indicator mismatch')
        if s['stage_eligible']=='1' and c['process_flag']!='1': raise ValueError('Stage eligibility requires process eligibility')
    return {'cases':len(cases),'stages':len(stages),'keys_match':True,'primary_flags_match':True,'stage_requires_process':True}
