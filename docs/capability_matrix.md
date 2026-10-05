# Capability Matrix

| Capability | Public evidence |
|---|---|
| Python | input contracts, replay, as-of baseline, duration scoring, reporting, verification |
| SQL / SQLite | checkpoint QA plus independent arrival/version/state/clock/profile/score reconstruction |
| ETL | fabricated catalogs and delivery logs -> typed relational audit tables |
| Data modeling | physical delivery identity, logical event identity, revisions, tombstones and case projections |
| Data quality | conflicting identities fail; ambiguous/reversed/incomplete processes remain review cases |
| Process analytics | alternative clock starts, stage partitions, open-case exposure and historical duration deviation |
| Failure handling | malformed envelopes, cutoff leakage, stale revisions, corrupt outputs, locked/failed publication |
| Reporting | CSV queue and evidence, JSON/Markdown audit, searchable local HTML review view |
| Testing | analytical invariants, fabricated scenario assertions, integration and negative tests |
| CI | both demos/tests, public-boundary scan, Docker gates and public artifact upload |
| Containerization | Python + pytest Dockerfile; execution status requires a completed run |

This is offline synthetic engineering evidence. It does not establish a deployed broker service, distributed exactly-once processing, empirical replication, or externally calibrated detector performance.
