from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path

from .replay import Snapshot
from .io import write_json


def reports(directory: Path, snapshot: Snapshot, baseline: dict, scores: list[dict], queue: list[dict], quality: dict) -> None:
    summary = dict(protocol=baseline["protocol"], synthetic_only=True, establishes_legal_breach=False,
                   establishes_wrongdoing=False, replay=snapshot.metadata,
                   frozen_baseline=dict(cutoff=baseline["baseline_cutoff"], training_cases=len(baseline["training_case_ids"]),
                                        groups={group: profile["count"] for group, profile in baseline["profiles"].items()}),
                   duration_monitoring=dict(scored_completed_cases=len(scores), flagged_cases=sum(row["flagged"] for row in scores)),
                   review_queue=dict(candidates=len(queue), by_reason=dict(sorted(Counter(row["reason"] for row in queue).items()))),
                   sql_quality=quality)
    write_json(directory / "stream_summary.json", summary)
    text = ("# Synthetic event-stream audit\n\n"
            f"Observation snapshot: {snapshot.metadata['observed_at']}. "
            f"Consumed deliveries: {len(snapshot.audit)}; future arrivals excluded: {snapshot.metadata['excluded_future_deliveries']}.\n\n"
            f"States: {json.dumps(snapshot.metadata['state_counts'], sort_keys=True)}. "
            f"Late updates retained: {snapshot.metadata['late_updates']}.\n\n"
            f"Historical baseline: {len(baseline['training_case_ids'])} completed cases known at {baseline['baseline_cutoff']}. "
            f"Scored later completed cases: {len(scores)}; upper-tail duration candidates: {sum(row['flagged'] for row in scores)}.\n\n"
            f"Review queue: {len(queue)} rule-level candidates. SQL: {quality['passed_checks']}/{quality['total_checks']} gates passed.\n\n"
            "Completed durations use event time. Open ages stop at the observation timestamp and are not completed durations. "
            "Late data and corrections can revise the projection. The watermark is a declared heuristic, not a completeness guarantee.\n\n"
            "All records and thresholds are fabricated for this demonstration. A review flag does not establish legal delay, "
            "negligence, wrongdoing, causality, or a finding from the private study. The duration detector has no externally "
            "validated sensitivity, specificity, or false-positive rate.\n")
    (directory / "stream_report.md").write_text(text, encoding="utf-8")
    clocks = {row["case_id"]: row for row in snapshot.clocks}
    table = []
    for alert in queue:
        clock = clocks[alert["case_id"]]
        fields = [alert["priority"], alert["case_id"], alert["reason"], clock["state"],
                  clock["issue_to_decision_hours"], clock["notification_to_decision_hours"], clock["notification_age_hours"]]
        cells = ''.join(f'<td>{escape(str(value)) if value != "" else "—"}</td>' for value in fields)
        cells += f'<td><details><summary>Evidence</summary><pre>{escape(alert["evidence_json"])}</pre></details></td>'
        table.append(f'<tr>{cells}</tr>')
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Synthetic process review</title><style>
body{{font:16px system-ui,sans-serif;background:#f6f7fa;color:#1d2939;max-width:1300px;margin:32px auto;padding:0 20px}}
h1{{font-size:28px}}table{{border-collapse:collapse;background:white;width:100%;font-size:14px}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #d8deea;vertical-align:top}}
th{{background:#e8edf5}}pre{{white-space:pre-wrap;max-width:380px}}input{{padding:10px;margin:12px 0;width:300px}}.scroll{{overflow:auto}}.note{{padding:16px;background:#e8edf5;border-radius:8px}}
</style><h1>Synthetic process review</h1><p>{len(queue)} review candidates · {len(snapshot.clocks)} cases · snapshot {escape(snapshot.metadata['observed_at'])}</p>
<p class="note">All records and thresholds are fabricated. Alerts require review and do not establish legal breach or wrongdoing. Open ages are observed exposure, not completed duration.</p>
<label>Filter candidates <input id="filter" type="search" placeholder="Case, reason or state"></label><div class="scroll"><table>
<thead><tr><th>Priority</th><th>Case</th><th>Reason</th><th>State</th><th>Issue → decision (h)</th><th>Notification → decision (h)</th><th>Open notification age (h)</th><th>Evidence</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></div><p>Historical duration reference: {escape(baseline['baseline_cutoff'])}. SQL gates: {quality['passed_checks']}/{quality['total_checks']}.</p>
<script>document.getElementById('filter').addEventListener('input',function(){{const q=this.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));}});</script></html>'''
    (directory / "stream_dashboard.html").write_text(html, encoding="utf-8")
