from __future__ import annotations
import csv,json,math
from datetime import date
from pathlib import Path

def _bit(value,field):
    if value not in {'0','1'}: raise ValueError(f'{field} must be 0 or 1')
    return int(value)

def validate_cases(csv_path,contract_path):
    c=json.loads(Path(contract_path).read_text(encoding='utf-8'))
    with Path(csv_path).open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); expected=set(c['required_columns'])
        if set(r.fieldnames or [])!=expected or len(r.fieldnames or [])!=len(expected): raise ValueError('Case schema mismatch')
        seen=set(); rows=0
        for n,row in enumerate(r,start=2):
            if set(row)!=expected or any(v is None for v in row.values()): raise ValueError(f'Row {n}: malformed case row')
            rows+=1; cid=(row['case_id'] or '').strip()
            if not cid or cid!=row['case_id'] or cid in seen: raise ValueError(f'Row {n}: invalid/duplicate case_id')
            seen.add(cid); primary=_bit(row['primary_flag'],'primary_flag'); process=_bit(row['process_flag'],'process_flag'); payment=_bit(row['payment_flag'],'payment_flag')
            inspections=int(row['inspection_count'])
            if inspections<0: raise ValueError(f'Row {n}: negative inspection_count')
            if process and not primary: raise ValueError(f'Row {n}: process requires primary')
            if payment and not process: raise ValueError(f'Row {n}: payment requires process')
            if row['reported_delay_days']!='' and not math.isfinite(float(row['reported_delay_days'])): raise ValueError(f'Row {n}: nonfinite reported delay')
        if not rows: raise ValueError('Empty case checkpoint')
    return {'rows_checked':rows,'contract_name':c['contract_name']}

def validate_stages(csv_path,contract_path):
    c=json.loads(Path(contract_path).read_text(encoding='utf-8')); ordered=['issue_date','notification_date','visit_date','report_date','decision_date']
    with Path(csv_path).open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); expected=set(c['required_columns'])
        if set(r.fieldnames or [])!=expected or len(r.fieldnames or [])!=len(expected): raise ValueError('Stage schema mismatch')
        seen=set(); rows=0
        for n,row in enumerate(r,start=2):
            if set(row)!=expected or any(v is None for v in row.values()): raise ValueError(f'Row {n}: malformed stage row')
            rows+=1; cid=(row['case_id'] or '').strip()
            if not cid or cid!=row['case_id'] or cid in seen: raise ValueError(f'Row {n}: invalid/duplicate case_id')
            seen.add(cid); primary=_bit(row['primary_flag'],'primary_flag'); eligible=_bit(row['stage_eligible'],'stage_eligible')
            if eligible and not primary: raise ValueError(f'Row {n}: stage requires primary')
            clock=(row.get('clock_flag') or '').strip()
            if eligible and clock not in {'0','1'}: raise ValueError(f'Row {n}: eligible stage needs clock_flag')
            if not eligible and clock!='': raise ValueError(f'Row {n}: nonstage clock_flag must be blank')
            vals=[date.fromisoformat(row[x]) if (row.get(x) or '').strip() else None for x in ordered]
            if eligible:
                if any(v is None for v in vals): raise ValueError(f'Row {n}: incomplete eligible process clock')
                if vals!=sorted(vals): raise ValueError(f'Row {n}: process clock chronology violation')
        if not rows: raise ValueError('Empty stage checkpoint')
    return {'rows_checked':rows,'contract_name':c['contract_name']}
