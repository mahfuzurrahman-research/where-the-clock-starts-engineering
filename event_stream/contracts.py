from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from .io import object_hash, read_rows

ROOT = Path(__file__).resolve().parents[1]
STAGES = ["ISSUED", "NOTIFIED", "VISITED", "REPORTED", "DECIDED"]
CASE_FIELDS = ["case_id", "service_group", "registered_at", "synthetic_record"]
EVENT_FIELDS = ["delivery_id", "delivery_seq", "event_id", "revision", "case_id", "event_type",
                "operation", "event_time", "recorded_at", "synthetic_record"]
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})")


class StreamError(ValueError):
    """The declared synthetic stream or an execution artifact is inconsistent."""


def timestamp(value: object) -> int:
    # Explicit second precision: never silently truncate fractional or naive timestamps.
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise StreamError("timestamp needs whole seconds and an explicit timezone")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise StreamError("invalid timezone offset")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("naive timestamp")
        return int(dt.astimezone(timezone.utc).timestamp())
    except (ValueError, OverflowError, OSError) as exc:
        raise StreamError("invalid timestamp") from exc


def utc(epoch: int | None) -> str:
    return "" if epoch is None else datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise StreamError(f"invalid {field}")
    return value


def positive_int(value: object, field: str) -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        result = int(value)
    else:
        raise StreamError(f"{field} must be a positive integer")
    if result <= 0:
        raise StreamError(f"nonpositive {field}")
    return result


def validate_policy(policy: dict) -> dict:
    fields = {"protocol", "seed", "synthetic_only", "establishes_legal_breach", "establishes_wrongdoing",
              "stages", "service_groups", "late_policy", "allowed_lateness_hours", "baseline_cutoff",
              "observed_at", "minimum_baseline_cases", "mad_scale_floor", "duration_score_threshold",
              "absolute_duration_hours", "open_age_hours", "notification_wait_hours", "generation"}
    if not isinstance(policy, dict) or set(policy) != fields:
        raise StreamError("stream policy schema mismatch")
    if (policy["protocol"] != "synthetic-process-stream-v1" or policy["stages"] != STAGES
            or policy["service_groups"] != ["FLOW_A", "FLOW_B"] or policy["late_policy"] != "retain_and_revise"):
        raise StreamError("unsupported stream protocol")
    if (policy["synthetic_only"] is not True or policy["establishes_legal_breach"] is not False
            or policy["establishes_wrongdoing"] is not False):
        raise StreamError("synthetic review-only claim boundary violated")
    if timestamp(policy["observed_at"]) <= timestamp(policy["baseline_cutoff"]):
        raise StreamError("observation time must follow the baseline cutoff")
    for field in ("allowed_lateness_hours", "mad_scale_floor", "duration_score_threshold",
                  "absolute_duration_hours", "open_age_hours", "notification_wait_hours"):
        value = policy[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise StreamError(f"invalid threshold: {field}")
    if not float(policy["allowed_lateness_hours"] * 3600).is_integer():
        raise StreamError("lateness allowance must use whole seconds")
    if type(policy["seed"]) is not int or policy["seed"] < 0:
        raise StreamError("invalid generator seed")
    if type(policy["minimum_baseline_cases"]) is not int or policy["minimum_baseline_cases"] < 3:
        raise StreamError("baseline needs at least three cases per group")
    generation = policy["generation"]
    if (not isinstance(generation, dict) or set(generation) != {"training_cases", "monitoring_cases"}
            or any(type(value) is not int or value < 1 for value in generation.values())):
        raise StreamError("invalid generation settings")
    return policy


def load_policy(path: Path | None = None) -> dict:
    return validate_policy(json.loads((path or ROOT / "contracts/event_stream.contract.json").read_text()))


@dataclass(frozen=True)
class Case:
    case_id: str
    service_group: str
    registered_at: int

    def row(self) -> dict:
        return dict(case_id=self.case_id, service_group=self.service_group,
                    registered_at=utc(self.registered_at), synthetic_record="true")


@dataclass(frozen=True)
class Event:
    delivery_id: str
    delivery_seq: int
    event_id: str
    revision: int
    case_id: str
    event_type: str
    operation: str
    event_time: int | None
    recorded_at: int

    def semantic(self) -> tuple:
        return self.case_id, self.event_type, self.operation, self.event_time

    def row(self) -> dict:
        return dict(delivery_id=self.delivery_id, delivery_seq=self.delivery_seq, event_id=self.event_id,
                    revision=self.revision, case_id=self.case_id, event_type=self.event_type,
                    operation=self.operation, event_time=utc(self.event_time),
                    recorded_at=utc(self.recorded_at), synthetic_record="true")


@dataclass
class Log:
    cases: dict[str, Case]
    events: list[Event]

    def source_hash(self, as_of: int | None = None) -> str:
        return object_hash({"cases": [case.row() for case in self.cases.values()
                                      if as_of is None or case.registered_at <= as_of],
                            "events": [event.row() for event in self.events
                                       if as_of is None or event.recorded_at <= as_of]})


def _schema(rows: list[dict], fields: list[str]) -> None:
    if not rows:
        raise StreamError("empty stream input table")
    for row in rows:
        if set(row) != set(fields):
            raise StreamError("stream row schema mismatch")
        if row["synthetic_record"] != "true":
            raise StreamError("explicit synthetic marker required")


def validate_inputs(cases: list[dict], events: list[dict], policy: dict | None = None) -> Log:
    policy = validate_policy(policy) if policy is not None else load_policy()
    _schema(cases, CASE_FIELDS)
    _schema(events, EVENT_FIELDS)
    catalog = {}
    for row in cases:
        key = identifier(row["case_id"], "case_id")
        if key in catalog:
            raise StreamError("duplicate case_id")
        if row["service_group"] not in policy["service_groups"]:
            raise StreamError("unknown service group")
        catalog[key] = Case(key, row["service_group"], timestamp(row["registered_at"]))
    parsed, deliveries, sequences, versions, identities = [], {}, {}, {}, {}
    for row in events:
        key = identifier(row["case_id"], "case_id")
        if key not in catalog:
            raise StreamError("unknown event case_id")
        operation = row["operation"]
        if operation not in ("UPSERT", "RETRACT") or row["event_type"] not in STAGES:
            raise StreamError("unknown operation or event type")
        event_time = timestamp(row["event_time"]) if operation == "UPSERT" else None
        if operation == "RETRACT" and row["event_time"] != "":
            raise StreamError("retractions require a blank event_time")
        recorded = timestamp(row["recorded_at"])
        if recorded < catalog[key].registered_at or (event_time is not None and event_time > recorded):
            raise StreamError("future event time or delivery before case registration")
        event = Event(identifier(row["delivery_id"], "delivery_id"), positive_int(row["delivery_seq"], "delivery_seq"),
                      identifier(row["event_id"], "event_id"), positive_int(row["revision"], "revision"),
                      key, row["event_type"], operation, event_time, recorded)
        if event.delivery_id in deliveries and deliveries[event.delivery_id] != event:
            raise StreamError("conflicting delivery identity")
        if event.delivery_seq in sequences and sequences[event.delivery_seq] != event.delivery_id:
            raise StreamError("delivery_seq must identify one delivery")
        version_key = event.event_id, event.revision
        if version_key in versions and versions[version_key] != event.semantic():
            raise StreamError("conflicting event revision payload")
        if event.event_id in identities and identities[event.event_id] != (key, event.event_type):
            raise StreamError("logical event identity changed case or stage")
        deliveries[event.delivery_id] = event
        sequences[event.delivery_seq] = event.delivery_id
        versions[version_key] = event.semantic()
        identities[event.event_id] = key, event.event_type
        parsed.append(event)
    parsed.sort(key=lambda event: event.delivery_seq)
    if any(left.recorded_at > right.recorded_at for left, right in zip(parsed, parsed[1:])):
        raise StreamError("delivery sequence contradicts recorded_at chronology")
    return Log(dict(sorted(catalog.items())), parsed)


def read_log(directory: Path, policy: dict | None = None) -> Log:
    return validate_inputs(read_rows(directory / "cases.csv"), read_rows(directory / "events.csv"), policy)
