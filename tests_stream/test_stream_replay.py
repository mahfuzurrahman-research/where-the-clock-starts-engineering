from event_stream.contracts import STAGES, timestamp, utc, validate_inputs
from event_stream.replay import replay


def small_log(offsets):
    start = timestamp("2026-01-01T00:00:00Z")
    cases = [dict(case_id="TEST", service_group="FLOW_A", registered_at=utc(start), synthetic_record="true")]
    events = [dict(delivery_id=f"D{i}", delivery_seq=i+1, event_id=f"E{i}", revision=1, case_id="TEST",
                   event_type=STAGES[i], operation="UPSERT", event_time=utc(start+offset),
                   recorded_at="2026-01-05T00:00:00Z", synthetic_record="true") for i, offset in enumerate(offsets)]
    return cases, events


def test_clock_start_changes_exposure_and_stage_partition():
    log = validate_inputs(*small_log([0, 6*3600, 12*3600, 18*3600, 24*3600]))
    snapshot = replay(log, timestamp("2026-01-06T00:00:00Z"), 24)
    row = snapshot.clocks[0]
    assert row["issue_to_decision_hours"] == 24
    assert row["notification_to_decision_hours"] == 18
    assert sum(gap["duration_hours"] for gap in snapshot.stage_durations) == 24
    assert row["issue_age_hours"] == row["notification_age_hours"] == ""


def test_open_case_uses_observation_age_and_has_no_completed_duration():
    log = validate_inputs(*small_log([0, 6*3600, 12*3600]))
    row = replay(log, timestamp("2026-01-06T00:00:00Z"), 24).clocks[0]
    assert row["state"] == "OPEN"
    assert row["issue_age_hours"] == 120
    assert row["notification_age_hours"] == 114
    assert row["issue_to_decision_hours"] == row["notification_to_decision_hours"] == ""


def test_equal_stage_timestamps_are_valid_without_inventing_elapsed_time():
    row = replay(validate_inputs(*small_log([0, 0, 3600, 7200, 10800])), timestamp("2026-01-06T00:00:00Z"), 24).clocks[0]
    assert row["state"] == "COMPLETE"
    assert row["issue_to_decision_hours"] == row["notification_to_decision_hours"] == 3


def test_strict_watermark_boundary_and_monotonic_progress():
    cases, events = small_log([0, 3*3600, 2*3600, 2*3600-1])
    snapshot = replay(validate_inputs(cases, events), timestamp("2026-01-06T00:00:00Z"), 1)
    assert snapshot.audit[2]["late_update"] == 0  # equal to the prior watermark
    assert snapshot.audit[3]["late_update"] == 1  # one second earlier
    progress = [timestamp(row["watermark_after"]) for row in snapshot.audit]
    assert progress == sorted(progress)


def test_correction_revises_clock_without_mutating_prior_snapshot(log, policy):
    before = replay(log, timestamp("2026-01-25T00:00:00Z"), 24)
    after = replay(log, timestamp(policy["observed_at"]), 24)
    old = next(row for row in before.clocks if row["case_id"] == "SIM_CORRECT")
    new = next(row for row in after.clocks if row["case_id"] == "SIM_CORRECT")
    assert old["state"] == "REVIEW"
    assert new["state"] == "COMPLETE"
    assert new["notification_to_decision_hours"] == 60
    assert new["projection_revision"] > old["projection_revision"]
    assert old["state"] == "REVIEW"


def test_retraction_and_old_redelivery_do_not_resurrect_decision(log, policy):
    before = replay(log, timestamp("2026-01-25T00:00:00Z"), 24)
    after = replay(log, timestamp(policy["observed_at"]), 24)
    assert next(row for row in before.clocks if row["case_id"] == "SIM_RETRACT")["state"] == "COMPLETE"
    row = next(row for row in after.clocks if row["case_id"] == "SIM_RETRACT")
    assert row["state"] == "OPEN" and row["decision_retracted"] == 1
    assert row["notification_to_decision_hours"] == ""
    decision = next(event for event in after.effective if event.event_id == "SIM_RETRACT-DECIDED")
    assert decision.revision == 2 and decision.operation == "RETRACT"


def test_lower_revision_arriving_later_is_ignored(snapshot):
    decision = next(event for event in snapshot.effective if event.event_id == "SIM_REV_ORDER-DECIDED")
    assert decision.revision == 2
    assert any(row["case_id"] == "SIM_REV_ORDER" and row["action"] == "stale_revision" for row in snapshot.audit)


def test_late_visit_repairs_gap_instead_of_being_dropped(log, policy):
    early = replay(log, timestamp("2026-01-25T00:00:00Z"), 24)
    final = replay(log, timestamp(policy["observed_at"]), 24)
    assert next(row for row in early.clocks if row["case_id"] == "SIM_LATE")["state"] == "REVIEW"
    assert next(row for row in final.clocks if row["case_id"] == "SIM_LATE")["state"] == "COMPLETE"
    assert any(row["case_id"] == "SIM_LATE" and row["late_update"] for row in final.audit)


def test_ambiguous_and_reversed_stages_are_not_sorted_into_valid_clocks(snapshot):
    for key in ("SIM_REPEAT", "SIM_ORDER", "SIM_GAP"):
        row = next(row for row in snapshot.clocks if row["case_id"] == key)
        assert row["state"] == "REVIEW"
        assert row["notification_to_decision_hours"] == ""
        assert not any(gap["case_id"] == key for gap in snapshot.stage_durations)


def test_duplicate_deliveries_are_idempotent(tables, policy):
    before = replay(validate_inputs(tables[0], tables[1]), timestamp(policy["observed_at"]), 24)
    tables[1].append(dict(tables[1][0]))
    after = replay(validate_inputs(tables[0], tables[1]), timestamp(policy["observed_at"]), 24)
    assert before.clocks == after.clocks
    assert before.effective == after.effective
    assert after.metadata["action_counts"]["duplicate_delivery"] == before.metadata["action_counts"]["duplicate_delivery"] + 1


def test_future_delivery_is_excluded_until_its_arrival(log, policy):
    before = replay(log, timestamp(policy["observed_at"]), 24)
    after = replay(log, timestamp("2026-02-04T00:00:00Z"), 24)
    first = next(event for event in before.effective if event.event_id == "SIM_CORRECT-DECIDED")
    second = next(event for event in after.effective if event.event_id == "SIM_CORRECT-DECIDED")
    assert (first.revision, second.revision) == (2, 3)
    assert before.metadata["excluded_future_deliveries"] == 1
    assert after.metadata["excluded_future_deliveries"] == 0
