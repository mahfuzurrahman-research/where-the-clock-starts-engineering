# Data Quality

Checks cover key coverage, orphan records, indicator agreement, nested eligibility logic, clock completeness, chronology ordering, and clock-partition reconciliation. Any required nonzero failure blocks the pipeline.

The original checkpoint contracts now reject empty or ragged inputs, duplicate/extra headers, whitespace-altered identifiers, and nonfinite reported numeric values. Standalone reconciliation rejects duplicate keys rather than overwriting them in a dictionary.

The stream contract checks every row's exact schema, explicit synthetic markers, valid whole-second timezone-aware timestamps, positive integer revisions/sequences, case linkage, supported stages/operations, and immutable logical identity. Delivery conflicts, revision-payload conflicts, future event timestamps, and a sequence inconsistent with recorded arrival order stop the run.

Valid envelopes may still describe an ambiguous process. Missing predecessors, reversed stage times, repeated live stages, and absent observed events remain visible in the case projection and review queue. Completed duration calculations and duration scoring exclude those cases. Open cases retain observation ages rather than fabricated completion times.

The 26 stream SQL gates reconstruct ingestion actions, watermarks, effective revisions/tombstones, state membership, clock anchors, duration partitions, open ages, frozen training membership, robust profiles, duration scores, review-rule coverage and claim boundaries. They also test queue evidence JSON and unique alert keys. The original warehouse retains its 12 checks.
