# Local Event-Stream Validation Record

Executed on **6 October 2026, Asia/Dhaka**. Analysis timestamps below belong to the fabricated fixture, not the execution date or the private paper.

| Validation | Observed result |
|---|---|
| Original checkpoint demonstration | PASS; nine original tests and 12 SQL checks |
| New stream/integrity suite | 80 tests passed; none skipped |
| Combined test command | 89 tests passed; none skipped |
| Stream SQL reconstruction | 26/26 checks passed; 38 total including the original warehouse |
| Fabricated inputs | 108 cases; 540 delivery rows |
| Observation snapshot | `2026-02-01T00:00:00Z`; 539 consumed, one future arrival excluded |
| Ingestion actions | 535 accepted, one duplicate delivery, two duplicate versions, one stale revision |
| Effective projection | 533 logical event versions, including one tombstone; 532 live events |
| Late updates | Three retained and applied |
| Case states | 102 COMPLETE, two OPEN, three REVIEW, one EMPTY |
| Historical cutoff | `2026-01-15T00:00:00Z`; 60 eligible cases, 30 per group |
| Later completed-case scoring | 42 scored; one synthetic upper-tail duration candidate |
| Review queue | 18 rule-level rows across 11 cases |
| Saved-run verification | PASS; 18 artifact hashes, source fingerprints, raw replay, baseline and queue reconstruction |
| Runtime | Python 3.12.14; SQLite 3.53.1; pytest 9.1.1 |
| Docker | Unavailable locally; not executed as part of this local record |

Validation commands were `./run_all_demos.sh` and `python3 -m pytest -q tests tests_stream`. SQL duration/profile/score reconciliation uses absolute tolerance `1e-10`; keys, revisions, state labels, claim flags and cutoff membership match exactly.

Tests cover UTC/offset normalization, unsupported precision, invalid timestamps, conflicting identities, future-time rejection, declared transport ordering, duplicate idempotence, late repair, strict watermark boundary, revisions/retractions, stale-version suppression, alternative start clocks, stage partitions, open-case exposure, frozen-reference leakage, zero-MAD behavior, strict thresholds, corrupted SQL outputs, receipt tampering, staged failure/rename rollback, process locks and unrelated-directory protection. An earlier snapshot with no scored cases or alerts also passes.

The GitHub workflow includes Docker build/run and artifact upload. Assess that execution separately on the [Actions page](https://github.com/mahfuzurrahman-research/where-the-clock-starts-engineering/actions/workflows/public-validation.yml). No successful hosted run is inferred from local tests or workflow configuration.

All results describe a synthetic engineering protocol. They do not establish real-world detector performance, a legal breach, causal identification or empirical replication.
