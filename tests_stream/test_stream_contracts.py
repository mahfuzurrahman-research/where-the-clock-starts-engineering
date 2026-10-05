import copy
import random

import pytest

from event_stream.contracts import ROOT, StreamError, timestamp, utc, validate_inputs, validate_policy
from event_stream.io import read_rows
from src.clock_engineering.contracts import validate_cases
from src.clock_engineering.reconciliation import reconcile


@pytest.mark.parametrize("value", ["2026-01-01", "2026-01-01T00:00:00", "2026-01-01T00:00:00.5Z",
                                    "2026-02-30T00:00:00Z", "2026-01-01T00:00:00+06:99"])
def test_rejects_ambiguous_invalid_or_unsupported_timestamp_precision(value):
    with pytest.raises(StreamError):
        timestamp(value)


def test_offsets_normalize_to_the_same_utc_instant():
    assert timestamp("2026-01-01T06:00:00+06:00") == timestamp("2026-01-01T00:00:00Z")
    assert utc(timestamp("2026-01-01T06:00:00+06:00")) == "2026-01-01T00:00:00Z"


def test_accepted_four_digit_year_round_trips_without_losing_padding():
    value = "0001-01-01T00:00:00Z"
    assert utc(timestamp(value)) == value


@pytest.mark.parametrize("field,value", [("revision", 0), ("revision", True), ("delivery_seq", "1.5"),
                                         ("operation", "DELETE"), ("event_type", "UNKNOWN"),
                                         ("case_id", "UNKNOWN"), ("synthetic_record", "false")])
def test_event_envelope_domains(tables, field, value):
    tables[1][0][field] = value
    with pytest.raises(StreamError):
        validate_inputs(tables[0], tables[1])


def test_future_event_timestamp_cannot_poison_watermark(tables):
    tables[1][0]["event_time"] = "2027-01-01T00:00:00Z"
    with pytest.raises(StreamError, match="future event"):
        validate_inputs(tables[0], tables[1])


@pytest.mark.parametrize("problem", ["extra_column", "duplicate_case", "unknown_group", "empty_events"])
def test_exact_schemas_and_case_catalog(tables, problem):
    if problem == "extra_column":
        tables[1][-1]["undeclared_field"] = 1
    elif problem == "duplicate_case":
        tables[0].append(copy.deepcopy(tables[0][0]))
    elif problem == "unknown_group":
        tables[0][0]["service_group"] = "OTHER"
    else:
        tables[1].clear()
    with pytest.raises(StreamError):
        validate_inputs(tables[0], tables[1])


@pytest.mark.parametrize("problem", ["delivery_identity", "delivery_sequence", "event_version", "event_identity"])
def test_conflicts_fail_instead_of_selecting_an_arbitrary_record(tables, problem):
    row = copy.deepcopy(tables[1][0])
    if problem == "delivery_identity":
        row["event_time"] = utc(timestamp(row["event_time"]) - 1)
    else:
        row["delivery_id"] = "CONFLICT"
        if problem != "delivery_sequence":
            row["delivery_seq"] = max(event["delivery_seq"] for event in tables[1]) + 1
            row["recorded_at"] = "2026-02-04T00:00:00Z"
        if problem == "event_version":
            row["event_time"] = utc(timestamp(row["event_time"]) - 1)
        if problem == "event_identity":
            row["revision"] = 2
            row["event_type"] = "NOTIFIED"
    tables[1].append(row)
    with pytest.raises(StreamError, match="conflict|identity|delivery_seq"):
        validate_inputs(tables[0], tables[1])


def test_transport_sequence_must_agree_with_recorded_time(tables):
    first, last = tables[1][0], tables[1][-1]
    first["delivery_seq"], last["delivery_seq"] = last["delivery_seq"], first["delivery_seq"]
    with pytest.raises(StreamError, match="sequence contradicts"):
        validate_inputs(tables[0], tables[1])


def test_file_row_permutation_preserves_canonical_source_identity(tables):
    before = validate_inputs(tables[0], tables[1])
    random.Random(19).shuffle(tables[0])
    random.Random(23).shuffle(tables[1])
    after = validate_inputs(tables[0], tables[1])
    assert before.source_hash() == after.source_hash()
    assert before.events == after.events


@pytest.mark.parametrize("field,value", [("establishes_legal_breach", True), ("late_policy", "drop"),
                                         ("duration_score_threshold", float("nan")), ("open_age_hours", True),
                                         ("observed_at", "2026-01-01T00:00:00Z")])
def test_policy_and_claim_boundaries(policy, field, value):
    policy[field] = value
    with pytest.raises(StreamError):
        validate_policy(policy)


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "empty", "ragged"])
def test_original_checkpoint_rejects_nonfinite_and_malformed_inputs(tmp_path, bad):
    source = ROOT / "data/synthetic/cases.csv"
    text = source.read_text()
    if bad == "empty":
        text = text.splitlines()[0] + "\n"
    elif bad == "ragged":
        text += "BROKEN,ROW\n"
    else:
        rows = read_rows(source)
        rows[-1]["reported_delay_days"] = bad
        from event_stream.io import write_rows
        target = tmp_path / "cases.csv"
        write_rows(target, list(rows[0]), rows)
        with pytest.raises(ValueError):
            validate_cases(target, ROOT / "contracts/cases.contract.json")
        return
    target = tmp_path / "cases.csv"
    target.write_text(text)
    with pytest.raises(ValueError):
        validate_cases(target, ROOT / "contracts/cases.contract.json")


def test_original_reconciliation_cannot_hide_duplicate_keys(tmp_path):
    source = ROOT / "data/synthetic/cases.csv"
    target = tmp_path / "cases.csv"
    target.write_text(source.read_text() + source.read_text().splitlines()[1] + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        reconcile(target, ROOT / "data/synthetic/stages.csv")
