import csv,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def _sql(con,rel): con.executescript((ROOT/rel).read_text(encoding='utf-8'))
def build(cases_csv,stages_csv,db_path):
    db_path=Path(db_path); db_path.parent.mkdir(parents=True,exist_ok=True)
    if db_path.exists(): db_path.unlink()
    con=sqlite3.connect(db_path); con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); _sql(con,'sql/schema.sql')
    with Path(cases_csv).open(newline='',encoding='utf-8') as f: cases=list(csv.DictReader(f))
    with Path(stages_csv).open(newline='',encoding='utf-8') as f: stages=list(csv.DictReader(f))
    with con:
        con.executemany('INSERT INTO cases VALUES (?,?,?,?,?,?,?)',[(r['case_id'],r['decision_period'],int(r['primary_flag']),int(r['process_flag']),int(r['payment_flag']),int(r['inspection_count']),None if r['reported_delay_days']=='' else float(r['reported_delay_days'])) for r in cases])
        con.executemany('INSERT INTO stages VALUES (?,?,?,?,?,?,?,?,?,?)',[(r['case_id'],int(r['primary_flag']),int(r['stage_eligible']),r['second_stage_indicator'],None if r['clock_flag']=='' else int(r['clock_flag']),r['issue_date'] or None,r['notification_date'] or None,r['visit_date'] or None,r['report_date'] or None,r['decision_date'] or None) for r in stages])
    _sql(con,'sql/marts.sql'); _sql(con,'sql/quality_checks.sql')
    if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or con.execute('PRAGMA foreign_key_check').fetchall(): raise RuntimeError('SQLite integrity verification failed')
    return con
def quality_summary(con):
    rows=con.execute('SELECT check_name,violations FROM quality_results ORDER BY check_name').fetchall(); failures=sum(int(r['violations']) for r in rows)
    return {'checks':len(rows),'failures':failures,'status':'PASS' if failures==0 else 'FAIL'}
def checkpoint_summary(con): return dict(con.execute('SELECT * FROM mart_checkpoint_summary').fetchone())
def clock_summary(con): return [dict(r) for r in con.execute('SELECT * FROM mart_process_clock_summary ORDER BY decision_period')]
