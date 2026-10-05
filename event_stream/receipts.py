from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import re

from .anomalies import QUEUE_FIELDS, SCORE_FIELDS, duration_scores, fit_baseline, review_queue
from .contracts import EVENT_FIELDS, ROOT, StreamError, load_policy, read_log, timestamp
from .io import file_hash, object_hash, write_json
from .replay import AUDIT_FIELDS, CLOCK_FIELDS, STAGE_FIELDS, replay

RECEIPT = "run_receipt.json"
ARTIFACTS = {"cases.csv", "events.csv", "scenario_truth.json", "stream_policy.json", "ingest_audit.csv",
             "effective_events.csv", "case_clocks.csv", "stage_durations.csv", "frozen_baseline.json",
             "duration_scores.csv", "review_queue.csv", "stream.sqlite", "stream_quality_checks.csv",
             "stream_sql_quality.json", "stream_summary.json", "stream_report.md", "stream_dashboard.html", "source_manifest.json"}


def software_inventory() -> dict:
    paths = [*sorted((ROOT / "event_stream").glob("*.py")), ROOT / "sql/event_stream_validation.sql",
             ROOT / "contracts/event_stream.contract.json"]
    return {str(path.relative_to(ROOT)): file_hash(path) for path in paths}


def seal(directory: Path, runtime: dict) -> None:
    files = {path.name: file_hash(path) for path in sorted(directory.iterdir()) if path.is_file() and path.name != RECEIPT}
    if set(files) != ARTIFACTS:
        raise StreamError("cannot seal an incomplete stream run")
    receipt = dict(protocol="synthetic-process-stream-v1", status="PASS", synthetic_only=True,
                   establishes_legal_breach=False, establishes_wrongdoing=False, runtime=runtime,
                   files=files, software=software_inventory(), hash_scope="unsigned consistency; no provenance authentication")
    write_json(directory / RECEIPT, receipt)


def _compare_csv(path: Path, fields: list[str], expected: list[dict]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(expected)
    if path.read_text(encoding="utf-8") != buffer.getvalue():
        raise StreamError(f"saved stream projection disagrees with raw replay: {path.name}")


def verify(directory: Path) -> dict:
    receipt = json.loads((directory / RECEIPT).read_text())
    required = {"protocol", "status", "synthetic_only", "establishes_legal_breach", "establishes_wrongdoing",
                "runtime", "files", "software", "hash_scope"}
    if set(receipt) != required or receipt["protocol"] != "synthetic-process-stream-v1" or receipt["status"] != "PASS":
        raise StreamError("invalid stream receipt")
    if (receipt["synthetic_only"] is not True or receipt["establishes_legal_breach"] is not False
            or receipt["establishes_wrongdoing"] is not False):
        raise StreamError("receipt claim boundary violated")
    if set(receipt["files"]) != ARTIFACTS or {path.name for path in directory.iterdir() if path.name != RECEIPT} != ARTIFACTS:
        raise StreamError("stream artifact inventory changed")
    if receipt["software"] != software_inventory():
        raise StreamError("stream source changed; rerun before verification")
    for name, digest in receipt["files"].items():
        path = directory / name
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or path.is_symlink() or not path.is_file() or file_hash(path) != digest:
            raise StreamError(f"stream artifact hash mismatch: {name}")
    policy = load_policy(directory / "stream_policy.json")
    log = read_log(directory, policy)
    snapshot = replay(log, timestamp(policy["observed_at"]), policy["allowed_lateness_hours"])
    baseline = fit_baseline(log, policy)
    if baseline != json.loads((directory / "frozen_baseline.json").read_text()):
        raise StreamError("frozen baseline disagrees with historical arrivals")
    scores = duration_scores(snapshot, baseline)
    queue = review_queue(snapshot, scores, policy)
    for filename, fields, rows in (
        ("ingest_audit.csv", AUDIT_FIELDS, snapshot.audit), ("effective_events.csv", EVENT_FIELDS, [event.row() for event in snapshot.effective]),
        ("case_clocks.csv", CLOCK_FIELDS, snapshot.clocks), ("stage_durations.csv", STAGE_FIELDS, snapshot.stage_durations),
        ("duration_scores.csv", SCORE_FIELDS, scores), ("review_queue.csv", QUEUE_FIELDS, queue),
    ):
        _compare_csv(directory / filename, fields, rows)
    manifest = json.loads((directory / "source_manifest.json").read_text())
    expected = dict(protocol=policy["protocol"], source_hash=log.source_hash(), policy_hash=object_hash(policy),
                    observed_source_hash=log.source_hash(snapshot.as_of), baseline_hash=object_hash(baseline))
    if manifest != expected:
        raise StreamError("stream source manifest changed")
    quality = json.loads((directory / "stream_sql_quality.json").read_text())
    if quality["status"] != "PASS" or quality["failed_checks"] != 0:
        raise StreamError("stream SQL quality is not passing")
    return dict(status="PASS", files_verified=len(ARTIFACTS), replay_verified=True, baseline_verified=True)
