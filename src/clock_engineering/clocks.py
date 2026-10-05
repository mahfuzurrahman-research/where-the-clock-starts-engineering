from datetime import date
FIELDS=['issue_date','notification_date','visit_date','report_date','decision_date']
def validate_process_clocks(con):
    eligible=con.execute('SELECT * FROM stages WHERE stage_eligible=1').fetchall(); cf=0; inc=0
    for row in eligible:
        vals=[date.fromisoformat(row[f]) if row[f] else None for f in FIELDS]
        if any(v is None for v in vals): inc+=1; continue
        if vals!=sorted(vals): cf+=1
    if cf or inc: raise ValueError({'chronology_failures':cf,'incomplete':inc})
    flagged=con.execute('SELECT COUNT(*) FROM stages WHERE stage_eligible=1 AND clock_flag=1').fetchone()[0]; restricted=con.execute('SELECT COUNT(*) FROM stages WHERE stage_eligible=1 AND clock_flag=0').fetchone()[0]
    return {'eligible_rows':len(eligible),'clock_flagged':flagged,'clock_restricted':restricted,'chronology_failures':0,'incomplete_clocks':0}
