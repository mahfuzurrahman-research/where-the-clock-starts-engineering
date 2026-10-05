from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import random

from .contracts import CASE_FIELDS, EVENT_FIELDS, STAGES, load_policy, timestamp, utc
from .io import write_json, write_rows


def synthetic_tables(policy: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    """All records, clocks, groups, and scenario labels are fabricated in this function."""
    policy = policy or load_policy()
    rng = random.Random(policy["seed"])
    cases, events = [], []
    def case(key, start, group="FLOW_A"):
        cases.append(dict(case_id=key, service_group=group, registered_at=utc(start), synthetic_record="true"))
    def event(key, stage, when, recorded=None, revision=1, operation="UPSERT", suffix=""):
        row = dict(delivery_id=f"DEL{len(events):06d}", delivery_seq=0, event_id=f"{key}-{stage}{suffix}",
                   revision=revision, case_id=key, event_type=stage, operation=operation,
                   event_time=utc(when) if operation == "UPSERT" else "",
                   recorded_at=utc(recorded if recorded is not None else when), synthetic_record="true")
        events.append(row)
        return row
    for period, count, origin, divisor in (
        ("BASE", policy["generation"]["training_cases"], "2025-12-01T00:00:00Z", 2),
        ("MON", policy["generation"]["monitoring_cases"], "2026-01-16T00:00:00Z", 3),
    ):
        for i in range(count):
            key = f"{period}{i:04d}"
            group = "FLOW_A" if i % 2 == 0 else "FLOW_B"
            start = timestamp(origin) + (i // divisor) * 86400 + (i % divisor) * 3600
            case(key, start, group)
            when = start
            for j, stage in enumerate(STAGES):
                if j:
                    when += (rng.randint(3, 7) if j == 1 else rng.randint(10, 20)) * 3600
                    if group == "FLOW_B":
                        when += 3 * 3600
                event(key, stage, when, when + rng.randint(0, 2) * 3600)
    start = timestamp("2026-01-20T00:00:00Z")
    later = timestamp("2026-01-31T00:00:00Z")
    scenarios = {
        "SIM_LATE": ("COMPLETE", ["late_event_update"]),
        "SIM_ORDER": ("REVIEW", ["stage_reversal"]),
        "SIM_GAP": ("REVIEW", ["missing_predecessor"]),
        "SIM_REPEAT": ("REVIEW", ["ambiguous_stage"]),
        "SIM_OPEN": ("OPEN", ["aged_open_case"]),
        "SIM_LONG": ("COMPLETE", ["duration_upper_tail"]),
        "SIM_CORRECT": ("COMPLETE", ["revised_event_record"]),
        "SIM_RETRACT": ("OPEN", ["decision_withdrawn"]),
        "SIM_REV_ORDER": ("COMPLETE", ["revised_event_record"]),
        "SIM_EMPTY": ("EMPTY", ["no_observed_events"]),
        "SIM_DUP": ("COMPLETE", ["duplicate_delivery"]),
        "SIM_CLOCK": ("COMPLETE", []),
    }
    for key in scenarios:
        case(key, start)
        if key == "SIM_EMPTY":
            continue
        times = [start + j * 12 * 3600 for j in range(5)]
        if key == "SIM_LONG":
            times = [start + h * 3600 for h in (0, 24, 72, 96, 192)]
        if key == "SIM_CLOCK":
            times[1] = times[0]
        if key == "SIM_ORDER":
            times[3] = times[2] - 3600
        if key == "SIM_CORRECT":
            times[4] = times[2]
        for j, stage in enumerate(STAGES):
            if (key == "SIM_GAP" and stage == "REPORTED") or (key == "SIM_OPEN" and j > 2):
                continue
            if key == "SIM_REV_ORDER" and stage == "DECIDED":
                event(key, stage, start + 3 * 86400, revision=2)
                continue
            arrival = timestamp("2026-01-30T00:00:00Z") if key == "SIM_LATE" and stage == "VISITED" else times[j] + 2 * 3600
            row = event(key, stage, times[j], arrival)
            if key == "SIM_DUP" and stage == "ISSUED":
                events.append(deepcopy(row))
                event(key, stage, times[j], start + 3 * 86400)
        if key == "SIM_REPEAT":
            event(key, "VISITED", times[2] + 3600, suffix="-SECOND")
        if key == "SIM_CORRECT":
            event(key, "DECIDED", start + 3 * 86400, later, revision=2)
            event(key, "DECIDED", timestamp("2026-02-02T00:00:00Z"), timestamp("2026-02-03T00:00:00Z"), revision=3)
        if key == "SIM_RETRACT":
            event(key, "DECIDED", None, later, revision=2, operation="RETRACT")
            event(key, "DECIDED", times[4], later + 3600)
        if key == "SIM_REV_ORDER":
            event(key, "DECIDED", times[2], later, revision=1)
    events.sort(key=lambda row: (timestamp(row["recorded_at"]), row["delivery_id"]))
    sequence = {}
    for row in events:
        if row["delivery_id"] not in sequence:
            sequence[row["delivery_id"]] = len(sequence) + 1
        row["delivery_seq"] = sequence[row["delivery_id"]]
    truth = {"synthetic_only": True, "usage": "fabricated scenario assertions only; never fit the duration baseline",
             "scenarios": {key: dict(expected_state=state, expected_reasons=reasons) for key, (state, reasons) in scenarios.items()}}
    return cases, events, truth


def generate(directory: Path, policy: dict | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    cases, events, truth = synthetic_tables(policy)
    write_rows(directory / "cases.csv", CASE_FIELDS, cases)
    write_rows(directory / "events.csv", EVENT_FIELDS, events)
    write_json(directory / "scenario_truth.json", truth)
