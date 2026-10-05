import fcntl
import json
import os
import shutil

import pytest

from event_stream import pipeline
from event_stream.contracts import StreamError
from event_stream.io import file_hash, read_rows, write_json, write_rows
from event_stream.receipts import verify


def clone(completed_run, tmp_path):
    destination = tmp_path / "stream"
    shutil.copytree(completed_run, destination)
    return destination


def test_completed_run_has_replay_baseline_and_review_evidence(completed_run):
    assert verify(completed_run)["files_verified"] == 18
    summary = json.loads((completed_run / "stream_summary.json").read_text())
    assert summary["replay"]["consumed_deliveries"] == 539
    assert summary["replay"]["excluded_future_deliveries"] == 1
    assert summary["frozen_baseline"]["training_cases"] == 60
    assert summary["review_queue"]["candidates"] == 18
    assert summary["sql_quality"]["passed_checks"] == 26


@pytest.mark.parametrize("stage", ["validate_sql", "reports"])
def test_failed_stage_preserves_previous_completed_run(monkeypatch, completed_run, tmp_path, stage):
    destination = clone(completed_run, tmp_path)
    before = file_hash(destination / "run_receipt.json")
    def fail(*args):
        raise RuntimeError("deliberate gate failure")
    monkeypatch.setattr(pipeline, stage, fail)
    with pytest.raises(RuntimeError, match="deliberate gate failure"):
        pipeline.run(destination)
    assert file_hash(destination / "run_receipt.json") == before
    assert verify(destination)["status"] == "PASS"
    assert not list(tmp_path.glob(".stream-stage-*"))


def test_publish_rename_failure_rolls_back(monkeypatch, completed_run, tmp_path):
    destination = clone(completed_run, tmp_path)
    before = file_hash(destination / "run_receipt.json")
    original_replace = os.replace
    failed = False
    def fail_once(source, target):
        nonlocal failed
        if target == destination and source.name == "stream" and not failed:
            failed = True
            raise OSError("deliberate rename failure")
        return original_replace(source, target)
    monkeypatch.setattr(pipeline.os, "replace", fail_once)
    with pytest.raises(OSError, match="rename failure"):
        pipeline.run(destination)
    assert failed
    assert file_hash(destination / "run_receipt.json") == before
    assert verify(destination)["status"] == "PASS"


def test_process_lock_rejects_competing_publishers(completed_run, tmp_path):
    destination = clone(completed_run, tmp_path)
    with (tmp_path / ".stream.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="another stream run"):
            pipeline.run(destination)


def test_destination_guard_preserves_unrelated_files(tmp_path):
    destination = tmp_path / "personal"
    destination.mkdir()
    note = destination / "note.txt"
    note.write_text("keep")
    with pytest.raises(RuntimeError, match="without a stream receipt"):
        pipeline.run(destination)
    assert note.read_text() == "keep"


@pytest.mark.parametrize("problem", ["file_hash", "missing_file_and_hash", "claim_boundary", "extra_file"])
def test_receipt_detects_tampering_and_incomplete_inventory(completed_run, tmp_path, problem):
    destination = clone(completed_run, tmp_path)
    path = destination / "run_receipt.json"
    receipt = json.loads(path.read_text())
    if problem == "file_hash":
        (destination / "events.csv").write_text("corrupt")
    elif problem == "missing_file_and_hash":
        (destination / "stream_report.md").unlink()
        receipt["files"].pop("stream_report.md")
        write_json(path, receipt)
    elif problem == "claim_boundary":
        receipt["establishes_wrongdoing"] = True
        write_json(path, receipt)
    else:
        (destination / "extra.csv").write_text("unexpected")
    with pytest.raises(StreamError):
        verify(destination)


def test_updated_checksum_cannot_hide_projection_disagreement_with_raw_log(completed_run, tmp_path):
    destination = clone(completed_run, tmp_path)
    artifact = destination / "case_clocks.csv"
    rows = read_rows(artifact)
    rows[0]["notification_to_decision_hours"] = "999"
    write_rows(artifact, list(rows[0]), rows)
    receipt_path = destination / "run_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["files"][artifact.name] = file_hash(artifact)
    write_json(receipt_path, receipt)
    with pytest.raises(StreamError, match="raw replay"):
        verify(destination)


def test_repeated_run_preserves_deterministic_csv_and_analysis_json(completed_run, tmp_path):
    second = tmp_path / "second"
    pipeline.run(second)
    for original in completed_run.iterdir():
        if original.suffix == ".csv" or (original.suffix == ".json" and original.name != "run_receipt.json"):
            assert original.read_bytes() == (second / original.name).read_bytes(), original.name


def test_earlier_snapshot_with_no_review_candidates_is_valid(tmp_path, policy):
    policy["observed_at"] = "2026-01-15T01:00:00Z"
    destination = tmp_path / "earlier"
    assert pipeline.run(destination, policy)["status"] == "PASS"
    summary = json.loads((destination / "stream_summary.json").read_text())
    assert summary["review_queue"]["candidates"] == 0
    assert summary["duration_monitoring"]["scored_completed_cases"] == 0
