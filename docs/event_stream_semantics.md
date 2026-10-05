# Event-Stream and Clock Semantics

## Identity and temporal order

The catalog supplies `case_id`, `service_group`, and the time a case became known to the stream. Every delivery supplies a physical `delivery_id` and positive `delivery_seq`, a logical `event_id` and positive `revision`, a case/stage identity, operation, event time and recorded arrival time. All rows require `synthetic_record=true`.

Timestamps have whole-second precision and an explicit UTC offset; accepted values are normalized to UTC. Naive, fractional, invalid, and future event timestamps are rejected. Event time describes the recorded process occurrence. `recorded_at` describes arrival. Replay order is the declared delivery sequence, which must agree with nondecreasing recorded time. Equal arrival timestamps use that explicit sequence rather than an invented event-ID chronology. Sequence numbers may have gaps; they do not prove transport completeness.

Exact physical redelivery is idempotent. Another delivery of an already-seen logical revision is also ignored. Reusing a delivery identity with a different payload, changing a logical event's case/stage identity, or changing a revision's semantic payload fails the source contract. Equivalent timezone representations are normalized before comparison.

## Revisions and retractions

The highest observed revision of a logical event determines its current projection. A higher revision may correct event time or retract the event. Lower revisions arriving later are ignored. Revision gaps and a retraction first seen without its original delivery are allowed; missing historical deliveries are not invented.

Retractions have a blank event time and leave a retained tombstone. Old redelivery cannot resurrect a retracted decision. A later higher UPSERT revision can reinstate it. Case projection revisions count accepted updates and exclude duplicates/stale revisions. Saved snapshots are reconstructed from the append-only raw log; a later snapshot does not mutate an earlier one.

## Late updates and the watermark

Before each accepted update, the heuristic watermark is the maximum previously accepted UPSERT event time minus the declared lateness allowance (24 hours by default). Updates strictly earlier than that watermark are tagged late. Equality is not late. Retraction lateness refers to the prior projected event time when available; without a prior timestamp it is unknown and not tagged late.

The maximum never moves backward after a backdated correction. Duplicates, stale revisions and retractions do not advance it. The policy is **retain and revise**: late updates remain in the audit and modify the current projection. The watermark is progress metadata, not proof that a source is complete; this demonstration does not implement broker partitions, window finalization or distributed watermark coordination.

Only deliveries recorded by the observation timestamp and cases registered by then enter that snapshot. Later arrivals are excluded even if they describe an earlier event time. Historical model fitting applies the same arrival cutoff.

## Toy path and alternative clocks

The declared path is `ISSUED → NOTIFIED → VISITED → REPORTED → DECIDED`, with nondecreasing event times. Equal stage timestamps are allowed. A valid full path is COMPLETE; a valid prefix is OPEN. Missing predecessors, repeated live stages, and reversed stage times produce REVIEW. No live events produces EMPTY. Multiple live events for one stage are not collapsed to an arbitrary earliest/latest value.

This single-pass path is a toy convention. Repeated visits or reports may be legitimate in an actual program, requiring a different process contract before interpretation.

Complete cases report issue-to-decision and notification-to-decision hours. Adjacent stage intervals partition the full clock; changing the start excludes the issue-to-notification interval. Open cases report issue/notification-to-observation ages, leave completed durations blank, and are not scored as completed durations. Review/empty cases retain available timestamp evidence but receive no duration/age calculations.

These are continuously elapsed UTC hours. They apply no business-day or holiday calendar and do not establish legal delay, organizational responsibility or administrative performance.

## References

- [Python aware/naive datetime documentation](https://docs.python.org/3.12/library/datetime.html#aware-and-naive-objects).
- [Apache Beam watermarks and late-data concepts](https://beam.apache.org/documentation/programming-guide/#watermarks-and-late-data). The local heuristic is explicitly defined above; the repository does not run Beam or assert Beam runner semantics.
- [SQLite window functions](https://www.sqlite.org/windowfunctions.html), used for independent as-of revision and audit reconstruction.
