#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m event_stream.pipeline
python3 -m pytest -q tests_stream
python3 -m event_stream.pipeline --verify-only
echo "EVENT_STREAM_ENGINEERING_STATUS=PASS"
