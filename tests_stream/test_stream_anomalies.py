import pytest

from event_stream.anomalies import duration_scores, fit_baseline, review_queue
from event_stream.contracts import STAGES, StreamError, timestamp, utc, validate_inputs


def resequence(events):
    events.sort(key=lambda row: (timestamp(row["recorded_at"]), row["delivery_id"]))
    sequence = {}
    for row in events:
        if row["delivery_id"] not in sequence:
            sequence[row["delivery_id"]] = len(sequence) + 1
        row["delivery_seq"] = sequence[row["delivery_id"]]


def test_baseline_uses_only_completed_cases_known_at_cutoff(log, policy):
    baseline = fit_baseline(log, policy)
    assert len(baseline["training_case_ids"]) == 60
    assert all(key.startswith("BASE") for key in baseline["training_case_ids"])
    assert {group: profile["count"] for group, profile in baseline["profiles"].items()} == {"FLOW_A": 30, "FLOW_B": 30}
    assert baseline["snapshot_source_hash"] == log.source_hash(timestamp(policy["baseline_cutoff"]))


def test_backdated_correction_arriving_after_cutoff_cannot_leak_into_fit(tables, policy):
    before = fit_baseline(validate_inputs(tables[0], tables[1]), policy)
    original = next(row for row in tables[1] if row["event_id"] == "BASE0000-DECIDED")
    correction = dict(original, delivery_id="LATE_BASELINE_CORRECTION", revision=2,
                      event_time=utc(timestamp(original["event_time"])+86400), recorded_at="2026-01-31T00:00:00Z")
    tables[1].append(correction)
    resequence(tables[1])
    after = fit_baseline(validate_inputs(tables[0], tables[1]), policy)
    assert before == after


def test_zero_mad_uses_declared_floor_without_division_by_zero(tables, policy):
    starts = {case["case_id"]: timestamp(case["registered_at"]) for case in tables[0]}
    for row in tables[1]:
        if row["case_id"].startswith("BASE"):
            row["event_time"] = utc(starts[row["case_id"]] + STAGES.index(row["event_type"])*3600)
    baseline = fit_baseline(validate_inputs(tables[0], tables[1]), policy)
    for profile in baseline["profiles"].values():
        assert profile["log_mad"] == 0
        assert profile["scale"] == policy["mad_scale_floor"]


def test_insufficient_historical_support_fails_without_fallback(log, policy):
    policy["minimum_baseline_cases"] = 100
    with pytest.raises(StreamError, match="insufficient completed historical"):
        fit_baseline(log, policy)


def test_open_and_review_cases_are_excluded_from_completed_duration_scoring(log, snapshot, policy):
    baseline = fit_baseline(log, policy)
    scores = duration_scores(snapshot, baseline)
    assert len(scores) == 42
    assert not set(row["case_id"] for row in scores) & set(baseline["training_case_ids"])
    assert not set(row["case_id"] for row in scores) & {"SIM_OPEN", "SIM_RETRACT", "SIM_ORDER", "SIM_REPEAT", "SIM_GAP", "SIM_EMPTY"}
    assert [row["case_id"] for row in scores if row["flagged"]] == ["SIM_LONG"]


@pytest.mark.parametrize("boundary", ["score", "absolute_floor"])
def test_duration_threshold_equality_does_not_trigger(log, snapshot, policy, boundary):
    baseline = fit_baseline(log, policy)
    score = next(row for row in duration_scores(snapshot, baseline) if row["case_id"] == "SIM_LONG")
    if boundary == "score":
        baseline["duration_score_threshold"] = score["upper_tail_score"]
    else:
        baseline["absolute_duration_hours"] = score["duration_hours"]
    result = next(row for row in duration_scores(snapshot, baseline) if row["case_id"] == "SIM_LONG")
    assert result["flagged"] == 0


def test_all_fabricated_scenarios_match_state_and_review_rules(tables, log, snapshot, policy):
    scores = duration_scores(snapshot, fit_baseline(log, policy))
    queue = review_queue(snapshot, scores, policy)
    for key, expected in tables[2]["scenarios"].items():
        assert next(row for row in snapshot.clocks if row["case_id"] == key)["state"] == expected["expected_state"]
        reasons = {row["reason"] for row in queue if row["case_id"] == key}
        assert set(expected["expected_reasons"]) <= reasons
    assert all(row["status"] == "review_required" and row["establishes_legal_breach"] == row["establishes_wrongdoing"] == "false" for row in queue)


def test_duration_baseline_must_precede_snapshot(log, snapshot, policy):
    baseline = fit_baseline(log, policy)
    baseline["baseline_cutoff"] = policy["observed_at"]
    with pytest.raises(StreamError, match="must precede"):
        duration_scores(snapshot, baseline)
