from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from statistics import median

from .contracts import Log, StreamError, timestamp
from .io import object_hash
from .replay import Snapshot, replay

SCORE_FIELDS = ["case_id", "service_group", "duration_hours", "log_duration", "baseline_median",
                "baseline_scale", "upper_tail_score", "score_threshold", "absolute_floor_hours",
                "flagged", "baseline_cutoff", "baseline_hash", "synthetic_record"]
QUEUE_FIELDS = ["alert_id", "case_id", "service_group", "priority", "category", "reason", "evidence_json",
                "status", "establishes_legal_breach", "establishes_wrongdoing", "synthetic_record"]


def fit_baseline(log: Log, policy: dict) -> dict:
    cutoff = timestamp(policy["baseline_cutoff"])
    snapshot = replay(log, cutoff, policy["allowed_lateness_hours"])
    profiles = {}
    training = []
    for group in policy["service_groups"]:
        rows = [row for row in snapshot.clocks if row["service_group"] == group and row["state"] == "COMPLETE"]
        if len(rows) < policy["minimum_baseline_cases"]:
            raise StreamError(f"insufficient completed historical cases: {group}")
        values = [math.log1p(row["notification_to_decision_hours"]) for row in rows]
        center = median(values)
        mad = median(abs(value - center) for value in values)
        ids = sorted(row["case_id"] for row in rows)
        profiles[group] = dict(count=len(rows), case_ids=ids, log_median=center, log_mad=mad,
                               scale=max(1.4826 * mad, policy["mad_scale_floor"]))
        training.extend(ids)
    return {"protocol": policy["protocol"], "baseline_cutoff": policy["baseline_cutoff"],
            "clock": "notification_to_decision_hours", "snapshot_source_hash": log.source_hash(cutoff),
            "training_case_ids": sorted(training), "profiles": profiles,
            "score_formula": "(log1p(hours) - median) / max(1.4826 * MAD, declared floor)",
            "duration_score_threshold": policy["duration_score_threshold"],
            "absolute_duration_hours": policy["absolute_duration_hours"], "synthetic_only": True}


def duration_scores(snapshot: Snapshot, baseline: dict) -> list[dict]:
    if timestamp(baseline["baseline_cutoff"]) >= snapshot.as_of:
        raise StreamError("duration baseline must precede the observation snapshot")
    training = set(baseline["training_case_ids"])
    rows = []
    digest = object_hash(baseline)
    for clock in snapshot.clocks:
        if clock["state"] != "COMPLETE" or clock["case_id"] in training:
            continue
        group = clock["service_group"]
        if group not in baseline["profiles"]:
            raise StreamError("no frozen baseline for service group")
        profile = baseline["profiles"][group]
        duration = clock["notification_to_decision_hours"]
        transformed = math.log1p(duration)
        score = (transformed - profile["log_median"]) / profile["scale"]
        if not math.isfinite(score):
            raise StreamError("nonfinite duration score")
        flagged = (score > baseline["duration_score_threshold"] and duration > baseline["absolute_duration_hours"])
        rows.append(dict(case_id=clock["case_id"], service_group=group, duration_hours=duration,
                         log_duration=transformed, baseline_median=profile["log_median"], baseline_scale=profile["scale"],
                         upper_tail_score=score, score_threshold=baseline["duration_score_threshold"],
                         absolute_floor_hours=baseline["absolute_duration_hours"], flagged=int(flagged),
                         baseline_cutoff=baseline["baseline_cutoff"], baseline_hash=digest, synthetic_record="true"))
    return rows


def review_queue(snapshot: Snapshot, scores: list[dict], policy: dict) -> list[dict]:
    by_case = defaultdict(list)
    for row in snapshot.audit:
        by_case[row["case_id"]].append(row)
    rows = []
    def add(clock, priority, category, reason, evidence):
        rows.append(dict(alert_id="ALERT-" + object_hash([clock["case_id"], reason])[:20],
                         case_id=clock["case_id"], service_group=clock["service_group"], priority=priority,
                         category=category, reason=reason,
                         evidence_json=json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False),
                         status="review_required", establishes_legal_breach="false", establishes_wrongdoing="false",
                         synthetic_record="true"))
    clocks = {row["case_id"]: row for row in snapshot.clocks}
    for clock in snapshot.clocks:
        for issue in json.loads(clock["issues_json"]):
            add(clock, "P1", "data_quality", issue,
                dict(state=clock["state"], issue_time=clock["issue_time"], notification_time=clock["notification_time"],
                     decision_time=clock["decision_time"], observed_at=policy["observed_at"]))
        if clock["state"] == "OPEN":
            if clock["decision_retracted"]:
                add(clock, "P2", "process_pattern", "decision_withdrawn", dict(state="OPEN", decision_retracted=True))
            if clock["notification_age_hours"] != "" and clock["notification_age_hours"] > policy["open_age_hours"]:
                add(clock, "P2", "process_pattern", "aged_open_case",
                    dict(clock="notification_to_observation", age_hours=clock["notification_age_hours"],
                         threshold_hours=policy["open_age_hours"], completed_duration_known=False))
            elif not clock["notification_time"] and clock["issue_age_hours"] > policy["notification_wait_hours"]:
                add(clock, "P2", "process_pattern", "awaiting_notification",
                    dict(clock="issue_to_observation", age_hours=clock["issue_age_hours"],
                         threshold_hours=policy["notification_wait_hours"], completed_duration_known=False))
        history = by_case[clock["case_id"]]
        actions = Counter(row["action"] for row in history)
        for action in ("duplicate_delivery", "duplicate_version", "stale_revision"):
            if actions[action]:
                add(clock, "P3", "delivery_quality", action, dict(deliveries=actions[action], projection_state=clock["state"]))
        late = [row["delivery_id"] for row in history if row["late_update"]]
        if late:
            add(clock, "P3", "delivery_quality", "late_event_update", dict(delivery_ids=late, policy="retained_and_revised"))
        revisions = [row["delivery_id"] for row in history if row["action"] == "accepted" and row["revision"] > 1]
        if revisions:
            add(clock, "P3", "delivery_quality", "revised_event_record", dict(delivery_ids=revisions, projection_revision=clock["projection_revision"]))
    for score in scores:
        if score["flagged"]:
            add(clocks[score["case_id"]], "P2", "duration_candidate", "duration_upper_tail",
                {key: score[key] for key in ("duration_hours", "upper_tail_score", "score_threshold",
                                             "absolute_floor_hours", "baseline_cutoff", "baseline_hash")})
    return sorted(rows, key=lambda row: (row["priority"], row["case_id"], row["reason"]))
