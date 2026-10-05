from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math

from .contracts import Case, Event, Log, STAGES, StreamError, utc

AUDIT_FIELDS = ["ingest_index", "delivery_id", "delivery_seq", "event_id", "revision", "case_id",
                "operation", "action", "late_update", "lateness_event_time", "watermark_before",
                "watermark_after", "case_revision", "synthetic_record"]
CLOCK_FIELDS = ["case_id", "service_group", "state", "projection_revision", "issue_time", "notification_time",
                "decision_time", "issue_to_decision_hours", "notification_to_decision_hours",
                "issue_age_hours", "notification_age_hours", "issues_json", "decision_retracted", "synthetic_record"]
STAGE_FIELDS = ["case_id", "from_stage", "to_stage", "duration_hours", "synthetic_record"]


@dataclass
class Snapshot:
    as_of: int
    audit: list[dict]
    effective: list[Event]
    clocks: list[dict]
    stage_durations: list[dict]
    metadata: dict


def _project(case: Case, effective: list[Event], revision: int, as_of: int) -> tuple[dict, list[dict]]:
    import json
    by_stage = defaultdict(list)
    for event in effective:
        if event.operation == "UPSERT":
            by_stage[event.event_type].append(event.event_time)
    issues = []
    if not by_stage:
        issues.append("no_observed_events")
    if any(len(values) > 1 for values in by_stage.values()):
        issues.append("ambiguous_stage")
    present = [stage for stage in STAGES if stage in by_stage]
    if present and present != STAGES[:len(present)]:
        issues.append("missing_predecessor")
    unique = {stage: values[0] for stage, values in by_stage.items() if len(values) == 1}
    ordered = [unique[stage] for stage in STAGES if stage in unique]
    if ordered != sorted(ordered):
        issues.append("stage_reversal")
    if not by_stage:
        state = "EMPTY"
    elif issues:
        state = "REVIEW"
    else:
        state = "COMPLETE" if present == STAGES else "OPEN"
    complete = state == "COMPLETE"
    open_case = state == "OPEN"
    issue, notification, decision = (unique.get(stage) for stage in ("ISSUED", "NOTIFIED", "DECIDED"))
    hours = lambda end, start: (end - start) / 3600 if end is not None and start is not None else ""
    row = dict(case_id=case.case_id, service_group=case.service_group, state=state, projection_revision=revision,
               issue_time=utc(issue), notification_time=utc(notification), decision_time=utc(decision),
               issue_to_decision_hours=hours(decision, issue) if complete else "",
               notification_to_decision_hours=hours(decision, notification) if complete else "",
               issue_age_hours=hours(as_of, issue) if open_case else "",
               notification_age_hours=hours(as_of, notification) if open_case else "",
               issues_json=json.dumps(sorted(issues), separators=(",", ":")),
               decision_retracted=int(any(event.event_type == "DECIDED" and event.operation == "RETRACT"
                                          for event in effective)), synthetic_record="true")
    gaps = []
    if state in ("COMPLETE", "OPEN"):
        for left, right in zip(present, present[1:]):
            gaps.append(dict(case_id=case.case_id, from_stage=left, to_stage=right,
                             duration_hours=hours(unique[right], unique[left]), synthetic_record="true"))
    return row, gaps


def replay(log: Log, as_of: int, allowed_lateness_hours: float) -> Snapshot:
    if (type(allowed_lateness_hours) not in (int, float) or not math.isfinite(allowed_lateness_hours)
            or allowed_lateness_hours <= 0 or not float(allowed_lateness_hours * 3600).is_integer()):
        raise StreamError("lateness allowance must be positive")
    latest, seen_deliveries, seen_versions = {}, set(), set()
    case_revisions = Counter()
    audit = []
    maximum = None
    allowance = allowed_lateness_hours * 3600
    for event in log.events:
        if event.recorded_at > as_of:
            continue
        previous = latest.get(event.event_id)
        before = None if maximum is None else int(maximum - allowance)
        key = event.event_id, event.revision
        if event.delivery_id in seen_deliveries:
            action = "duplicate_delivery"
        elif key in seen_versions:
            action = "duplicate_version"
        elif previous is not None and event.revision < previous.revision:
            action = "stale_revision"
        else:
            action = "accepted"
        seen_deliveries.add(event.delivery_id)
        seen_versions.add(key)
        probe = event.event_time if event.operation == "UPSERT" else (previous.event_time if previous else None)
        late = action == "accepted" and probe is not None and before is not None and probe < before
        if action == "accepted":
            latest[event.event_id] = event
            case_revisions[event.case_id] += 1
            if event.operation == "UPSERT":
                maximum = event.event_time if maximum is None else max(maximum, event.event_time)
        after = None if maximum is None else int(maximum - allowance)
        audit.append(dict(ingest_index=len(audit) + 1, delivery_id=event.delivery_id, delivery_seq=event.delivery_seq,
                          event_id=event.event_id, revision=event.revision, case_id=event.case_id, operation=event.operation,
                          action=action, late_update=int(late), lateness_event_time=utc(probe), watermark_before=utc(before),
                          watermark_after=utc(after), case_revision=case_revisions[event.case_id], synthetic_record="true"))
    effective = [latest[key] for key in sorted(latest)]
    by_case = defaultdict(list)
    for event in effective:
        by_case[event.case_id].append(event)
    clocks, gaps = [], []
    for case in log.cases.values():
        if case.registered_at <= as_of:
            row, stages = _project(case, by_case[case.case_id], case_revisions[case.case_id], as_of)
            clocks.append(row)
            gaps.extend(stages)
    metadata = dict(observed_at=utc(as_of), consumed_deliveries=len(audit),
                    excluded_future_deliveries=len(log.events) - len(audit), effective_event_versions=len(effective),
                    active_events=sum(event.operation == "UPSERT" for event in effective),
                    action_counts=dict(sorted(Counter(row["action"] for row in audit).items())),
                    late_updates=sum(row["late_update"] for row in audit), final_watermark=utc(None if maximum is None else int(maximum - allowance)),
                    state_counts=dict(sorted(Counter(row["state"] for row in clocks).items())))
    return Snapshot(as_of, audit, effective, clocks, gaps, metadata)
