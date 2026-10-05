# CV Evidence: Event-Stream and Process Analytics Engineering

Suggested project bullet supported by the public code and local validation:

> Engineered synthetic event-log replay with event/arrival-time separation, idempotent delivery handling, corrections and retractions, explicit completed/open clocks, and frozen-reference duration anomaly detection; validated 89 tests and 38 SQL quality checks.

Optional technical detail for a longer project description:

> Added a process review queue with timestamp and revision evidence, a filtered HTML view, independent SQL reconstruction of historical/current projections, and source/artifact receipts with raw-replay verification.

| Claim | Reviewable implementation |
|---|---|
| Event-stream chronology | `event_stream/contracts.py`, `event_stream/replay.py`, `docs/event_stream_semantics.md` |
| Process anomaly detection | `event_stream/anomalies.py`, `contracts/event_stream.contract.json` |
| Cutoff integrity | Historical arrival snapshot, baseline membership/hash, late backdated-correction test |
| SQL validation | `sql/event_stream_validation.sql` and original checkpoint QA |
| Review/reporting | Queue CSV, structured evidence and `event_stream/reporting.py` |
| Reproducibility/integrity | Staged runner, process lock, verification CLI, receipts and failure-mode tests |
| CI/container engineering | GitHub workflow and Dockerfile; execution status is separate |

Use “synthetic,” “offline replay,” and “review candidates” when describing this project. The code does not establish a deployed Kafka/Beam service, distributed exactly-once guarantees, calibrated external detector accuracy, real administrative lateness, wrongdoing or private-study replication.

Counts record [the tested upgrade](event_stream_validation_record.md) and should be revised after implementation changes. This upgrade does not modify an actual CV document.
