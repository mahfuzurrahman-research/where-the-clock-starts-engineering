from pathlib import Path
from .contracts import validate_cases,validate_stages
from .reconciliation import reconcile
from .warehouse import build,quality_summary,checkpoint_summary,clock_summary
from .clocks import validate_process_clocks
from .reporting import write_reports
def run(root):
    root=Path(root); cases=root/'data/synthetic/cases.csv'; stages=root/'data/synthetic/stages.csv'
    vc=validate_cases(cases,root/'contracts/cases.contract.json'); vs=validate_stages(stages,root/'contracts/stages.contract.json'); rec=reconcile(cases,stages)
    con=build(cases,stages,root/'outputs/public_demo.sqlite')
    try:
        qa=quality_summary(con)
        if qa['status']!='PASS': raise RuntimeError('Relational QA failed')
        cp=checkpoint_summary(con); clk=validate_process_clocks(con); byp=clock_summary(con)
    finally: con.close()
    obj={'contracts':{'cases':vc,'stages':vs},'reconciliation':rec,'quality':qa,'checkpoint':cp,'clock':clk,'clock_by_period':byp}; write_reports(obj,root/'outputs'); return obj
