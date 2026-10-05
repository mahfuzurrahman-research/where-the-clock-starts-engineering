from __future__ import annotations

import math
from pathlib import Path
import sqlite3

from .anomalies import QUEUE_FIELDS, SCORE_FIELDS
from .contracts import CASE_FIELDS, EVENT_FIELDS, ROOT, Log, StreamError, timestamp
from .io import object_hash, write_json, write_rows
from .replay import AUDIT_FIELDS, CLOCK_FIELDS, STAGE_FIELDS, Snapshot


def _table(con, name, fields, rows, integers=(), reals=()):
    schema = ','.join(f'{field} {"INTEGER" if field in integers else "REAL" if field in reals else "TEXT"}' for field in fields)
    con.execute(f'CREATE TABLE {name}({schema})')
    con.executemany(f'INSERT INTO {name} VALUES ({",".join("?" for _ in fields)})',
                    [tuple(None if row[field] == "" else row[field] for field in fields) for row in rows])


def validate_sql(directory: Path, log: Log, snapshot: Snapshot, baseline: dict,
                 scores: list[dict], queue: list[dict], policy: dict) -> dict:
    path = directory / "stream.sqlite"
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as con:
        con.create_function("log1p", 1, math.log1p, deterministic=True)
        _table(con, "case_catalog", CASE_FIELDS, [case.row() for case in log.cases.values()])
        _table(con, "raw_events", ["input_index", *EVENT_FIELDS],
               [dict(input_index=i, **event.row()) for i, event in enumerate(log.events, 1)],
               integers=("input_index", "delivery_seq", "revision"))
        _table(con, "snapshot_parameters", ["kind", "as_of", "lateness_seconds"],
               [dict(kind=kind, as_of=timestamp(policy[field]), lateness_seconds=int(policy["allowed_lateness_hours"]*3600))
                for kind, field in (("OBS", "observed_at"), ("BASE", "baseline_cutoff"))], integers=("as_of", "lateness_seconds"))
        param_fields = ["mad_scale_floor", "duration_score_threshold", "absolute_duration_hours", "open_age_hours", "notification_wait_hours", "baseline_hash"]
        _table(con, "policy_parameters", param_fields, [{**{field: policy[field] for field in param_fields[:-1]}, "baseline_hash": object_hash(baseline)}], reals=param_fields[:-1])
        _table(con, "ingest_audit", AUDIT_FIELDS, snapshot.audit,
               integers=("ingest_index", "delivery_seq", "revision", "late_update", "case_revision"))
        _table(con, "effective_events", EVENT_FIELDS, [event.row() for event in snapshot.effective], integers=("delivery_seq", "revision"))
        _table(con, "case_clocks", CLOCK_FIELDS, snapshot.clocks, integers=("projection_revision", "decision_retracted"),
               reals=("issue_to_decision_hours", "notification_to_decision_hours", "issue_age_hours", "notification_age_hours"))
        _table(con, "stage_durations", STAGE_FIELDS, snapshot.stage_durations, reals=("duration_hours",))
        members = [dict(case_id=key, service_group=group) for group, profile in baseline["profiles"].items() for key in profile["case_ids"]]
        _table(con, "baseline_members", ["case_id", "service_group"], members)
        _table(con, "baseline_profiles", ["service_group", "count", "log_median", "log_mad", "scale"],
               [dict(service_group=group, **{field: profile[field] for field in ("count", "log_median", "log_mad", "scale")})
                for group, profile in baseline["profiles"].items()], integers=("count",), reals=("log_median", "log_mad", "scale"))
        _table(con, "duration_scores", SCORE_FIELDS, scores, integers=("flagged",),
               reals=("duration_hours", "log_duration", "baseline_median", "baseline_scale", "upper_tail_score", "score_threshold", "absolute_floor_hours"))
        _table(con, "review_queue", QUEUE_FIELDS, queue)
        con.executescript((ROOT / "sql/event_stream_validation.sql").read_text())
        checks = [dict(check_name=name, failures=failures, status="PASS" if failures == 0 else "FAIL")
                  for name, failures in con.execute("SELECT * FROM stream_quality_results ORDER BY check_name")]
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise StreamError("stream SQLite integrity failed")
    failed = [row for row in checks if row["status"] != "PASS"]
    quality = dict(status="FAIL" if failed else "PASS", total_checks=len(checks), passed_checks=len(checks)-len(failed), failed_checks=len(failed))
    write_rows(directory / "stream_quality_checks.csv", ["check_name", "failures", "status"], checks)
    write_json(directory / "stream_sql_quality.json", quality)
    if failed:
        raise StreamError(f"independent stream SQL gates failed: {failed}")
    return quality
