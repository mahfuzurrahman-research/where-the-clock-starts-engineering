# Reproducibility

```bash
python3 -m pip install -r requirements.txt
./run_all_demos.sh
```

Python 3.12 and SQLite with window, `unixepoch` and JSON functions are required. The processing runtime uses the standard library; tests use pinned pytest. The local validation used Python 3.12.14, SQLite 3.53.1 and pytest 9.1.1 on a POSIX environment. Publication locks use `fcntl`.

The original runner is `./run_public_demo.sh`; the new runner is `./run_stream_demo.sh`. The combined runner executes both once and scans the public boundary after completion. Outputs are ignored by Git except `.gitkeep`.

## Stream commands

```bash
python3 -m event_stream.pipeline
python3 -m event_stream.pipeline --verify-only
python3 -m event_stream.pipeline --as-of 2026-01-25T00:00:00Z --output /tmp/earlier-process-snapshot
python3 -m pytest -q tests tests_stream
```

The default destination is `outputs/stream/`. A custom destination must be new or contain a recognized stream receipt. Unrelated directories are protected. The policy fixes the seed, historical cutoff, observation timestamp, stage path and thresholds; the wall clock does not determine analysis membership.

The pipeline validates raw inputs, replays both temporal snapshots, calculates the historical reference and later candidates, executes SQL reconstruction, writes reports, and verifies a receipt before replacing the destination. Gate failures preserve the previous completed run. A process lock rejects competing publishers. An ordinary failure of the final rename restores the prior directory. This staged replacement has a brief swap interval and is not crash-durable transactional storage.

The receipt inventories 18 files and fingerprints the stream source, SQL, and original policy. Verification checks hashes, reconstructs the raw replay, refits the historical reference, and checks saved clocks/scores/queue against those computations. It does not rerun SQL. Source changes require a new run. Unsigned hashes cannot prevent a coherent rewrite of raw data, outputs and receipt together.

CSV and analysis JSON are deterministic for the tested runtime. Database bytes and receipt checksums are not promised to match across platforms or SQLite versions. The scenario expectations describe the default snapshot; another `--as-of` value may produce different states and alerts.

## Docker and hosted CI

```bash
docker build -t where-the-clock-starts-engineering .
docker run --rm where-the-clock-starts-engineering
```

Docker was unavailable in the local validation environment, so the local record does not claim a container pass. The GitHub workflow runs both demos/tests, Docker build/run, public-boundary checks, and artifact upload. Assess hosted execution from the [Actions page](https://github.com/mahfuzurrahman-research/where-the-clock-starts-engineering/actions/workflows/public-validation.yml); configuration alone is not evidence of a successful run.
