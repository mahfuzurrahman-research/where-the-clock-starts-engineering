#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
./run_public_demo.sh
./run_stream_demo.sh
python3 scripts/verify_public_boundary.py
echo "ALL_PUBLIC_DEMOS_STATUS=PASS"
