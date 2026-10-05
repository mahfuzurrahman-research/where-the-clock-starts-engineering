# Architecture

Synthetic case + stage checkpoints -> contract validation -> key reconciliation -> SQLite warehouse -> process-clock construction -> chronology/partition checks -> SQL marts -> QA -> deterministic reporting/dashboard -> tests/CI/Docker.

The event-stream module is separate from that original checkpoint audit. `event_stream/contracts.py` validates a case catalog and delivery log. `replay.py` reconstructs logical event versions, arrival decisions, watermark metadata, and a case projection at an explicit observation time. `anomalies.py` fits a historical reference at an earlier arrival cutoff and produces later duration scores and review candidates.

`sql/event_stream_validation.sql` independently reconstructs both snapshots directly from the raw log using window functions. It calculates stage clocks, historical membership, group medians/MADs, scores, and review-rule coverage. Intermediate tables are materialized to avoid repeating expensive window/correlated calculations for every QA gate. Only the scalar `math.log1p` callback is shared with Python; SQL does not read Python's replay decisions to resolve versions or clocks.

The pipeline builds all stream artifacts in a temporary sibling directory, runs the SQL gates, seals an unsigned receipt, and verifies the saved replay before publishing. A process lock prevents competing publishers. Reports include CSV, JSON, Markdown and a local HTML review view. See [semantics](event_stream_semantics.md) and [reproducibility](reproducibility.md) for the operational limits.
