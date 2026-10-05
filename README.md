# Where the Clock Starts — Research Engineering Demonstration

**Public engineering companion for _Where the Clock Starts: Administrative Timeliness in a Multistage Public Program_.**

This repository demonstrates administrative-process data engineering with **fully synthetic records**. It does **not** contain the manuscript, private administrative data, real program identifiers, empirical estimates, bootstrap outputs, private provenance, or the complete scientific workflow.

## What this repository demonstrates

- Python input contracts and fail-fast validation
- multistage administrative-event modeling
- SQLite checkpoint construction and reconciliation
- relational keys and cross-table integrity checks
- process-clock construction and chronology validation
- nested sample/cohort accounting
- deterministic SQL audit views
- failure-mode tests for malformed clocks and broken linkage
- deterministic JSON and Markdown reporting
- public-safe static dashboard generation
- Docker-based reproducibility
- GitHub Actions continuous integration

## Engineering flow

```text
Synthetic administrative events
            │
            ▼
Machine-readable input contracts
            │
            ▼
Schema + key validation
            │
            ▼
SQLite checkpoint warehouse
            │
      ┌─────┴─────┐
      ▼           ▼
Event linkage   Cohort flags
      │           │
      └─────┬─────┘
            ▼
Process-clock construction
            │
            ▼
Chronology + partition QA
            │
            ▼
Checkpoint reconciliation
            │
            ▼
Deterministic audit report
            │
            ▼
Dashboard + CI + Docker
```

## Quick start

```bash
./run_public_demo.sh
```

Expected markers include:

```text
CONTRACT_VALIDATION=PASS
CHECKPOINT_RECONCILIATION=PASS
PROCESS_CLOCK_QA=PASS
RELATIONAL_QA=PASS
PUBLIC_ENGINEERING_DEMO=PASS
```

## Public-safe boundary

The synthetic schema is intentionally generic. It demonstrates engineering patterns without exposing the private study's exact administrative variables, identifiers, sample counts, empirical estimates, inference results, or manuscript logic.

## Scientific boundary

This repository demonstrates **engineering capability only**. It does not establish administrative wrongdoing, legal delay, negligence, causal effects, program performance, or empirical findings from the private paper.

## Author

**Mahfuzur Rahman**

Copyright © Mahfuzur Rahman. All rights reserved.
