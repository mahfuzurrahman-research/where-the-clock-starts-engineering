from dataclasses import replace

import pytest

from event_stream.anomalies import duration_scores, fit_baseline, review_queue
from event_stream.contracts import StreamError
from event_stream.warehouse import validate_sql


@pytest.mark.parametrize("problem", ["clock", "audit_action", "late_flag", "stale_projection", "claim",
                                      "missing_alert", "baseline_profile", "score", "null_score", "open_completed_clock"])
def test_sql_reconstructs_raw_log_and_rejects_corrupted_outputs(tmp_path, log, snapshot, policy, problem):
    baseline = fit_baseline(log, policy)
    scores = duration_scores(snapshot, baseline)
    queue = review_queue(snapshot, scores, policy)
    if problem == "clock":
        snapshot.clocks[0]["notification_to_decision_hours"] += 1
    elif problem == "audit_action":
        snapshot.audit[0]["action"] = "duplicate_delivery"
    elif problem == "late_flag":
        snapshot.audit[0]["late_update"] = 1
    elif problem == "stale_projection":
        index = next(i for i, event in enumerate(snapshot.effective) if event.event_id == "SIM_REV_ORDER-DECIDED")
        snapshot.effective[index] = replace(snapshot.effective[index], revision=1)
    elif problem == "claim":
        queue[0]["establishes_legal_breach"] = "true"
    elif problem == "missing_alert":
        queue.pop()
    elif problem == "baseline_profile":
        baseline["profiles"]["FLOW_A"]["log_median"] += 0.1
    elif problem == "score":
        scores[0]["upper_tail_score"] += 0.1
    elif problem == "null_score":
        scores[0]["log_duration"] = None
    else:
        row = next(row for row in snapshot.clocks if row["state"] == "OPEN")
        row["notification_to_decision_hours"] = 0
    with pytest.raises(StreamError, match="SQL gates failed"):
        validate_sql(tmp_path, log, snapshot, baseline, scores, queue, policy)


def test_all_independent_sql_gates_pass(tmp_path, log, snapshot, policy):
    baseline = fit_baseline(log, policy)
    scores = duration_scores(snapshot, baseline)
    queue = review_queue(snapshot, scores, policy)
    assert validate_sql(tmp_path, log, snapshot, baseline, scores, queue, policy) == dict(status="PASS", total_checks=26, passed_checks=26, failed_checks=0)
