from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import sqlite3
import tempfile

from .anomalies import QUEUE_FIELDS, SCORE_FIELDS, duration_scores, fit_baseline, review_queue
from .contracts import EVENT_FIELDS, ROOT, load_policy, read_log, timestamp, validate_policy
from .generator import generate
from .io import object_hash, write_json, write_rows
from .receipts import seal, verify
from .replay import AUDIT_FIELDS, CLOCK_FIELDS, STAGE_FIELDS, replay
from .reporting import reports
from .warehouse import validate_sql


def _stage(directory: Path, policy: dict) -> None:
    write_json(directory / "stream_policy.json", policy)
    generate(directory, policy)
    log = read_log(directory, policy)
    snapshot = replay(log, timestamp(policy["observed_at"]), policy["allowed_lateness_hours"])
    baseline = fit_baseline(log, policy)
    scores = duration_scores(snapshot, baseline)
    queue = review_queue(snapshot, scores, policy)
    write_json(directory / "frozen_baseline.json", baseline)
    write_json(directory / "source_manifest.json", dict(protocol=policy["protocol"], source_hash=log.source_hash(),
               observed_source_hash=log.source_hash(snapshot.as_of), policy_hash=object_hash(policy), baseline_hash=object_hash(baseline)))
    for filename, fields, rows in (
        ("ingest_audit.csv", AUDIT_FIELDS, snapshot.audit), ("effective_events.csv", EVENT_FIELDS, [event.row() for event in snapshot.effective]),
        ("case_clocks.csv", CLOCK_FIELDS, snapshot.clocks), ("stage_durations.csv", STAGE_FIELDS, snapshot.stage_durations),
        ("duration_scores.csv", SCORE_FIELDS, scores), ("review_queue.csv", QUEUE_FIELDS, queue),
    ):
        write_rows(directory / filename, fields, rows)
    quality = validate_sql(directory, log, snapshot, baseline, scores, queue, policy)
    reports(directory, snapshot, baseline, scores, queue, quality)
    seal(directory, dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version))
    verify(directory)


def run(output: Path | None = None, policy: dict | None = None) -> dict:
    policy = validate_policy(policy) if policy is not None else load_policy()
    output = (output or ROOT / "outputs/stream").absolute()
    if output.is_symlink() or output == ROOT or output in ROOT.parents:
        raise RuntimeError("unsafe stream output destination")
    if output.exists():
        try:
            previous = json.loads((output / "run_receipt.json").read_text())
        except (OSError, ValueError) as exc:
            raise RuntimeError("refusing to replace a directory without a stream receipt") from exc
        if previous.get("protocol") != policy["protocol"]:
            raise RuntimeError("refusing to replace an unrelated output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with (output.parent / f".{output.name}.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another stream run is publishing to this destination") from exc
        with tempfile.TemporaryDirectory(prefix=f".{output.name}-stage-", dir=output.parent) as temporary:
            staged = Path(temporary) / "stream"
            staged.mkdir()
            _stage(staged, policy)
            backup = Path(temporary) / "previous"
            existed = output.exists()
            if existed:
                os.replace(output, backup)
            try:
                os.replace(staged, output)
            except BaseException:
                if existed:
                    os.replace(backup, output)
                raise
        return verify(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay and monitor a fabricated process event stream")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/stream")
    parser.add_argument("--as-of", help="explicit observation timestamp with timezone; baseline stays frozen")
    parser.add_argument("--verify-only", action="store_true", help="verify saved replay and baseline without rebuilding SQL")
    args = parser.parse_args()
    if args.verify_only and args.as_of:
        parser.error("--verify-only uses the saved snapshot, so --as-of cannot be supplied")
    policy = load_policy()
    if args.as_of:
        policy["observed_at"] = args.as_of
    status = verify(args.output) if args.verify_only else run(args.output, policy)
    print(json.dumps(status, sort_keys=True))


if __name__ == "__main__":
    main()
