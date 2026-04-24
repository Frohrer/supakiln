#!/bin/bash
# Helper: POST a bash payload, pretty-print output/error.
# Usage: ./secprobe.sh "bash one-liner" [timeout_seconds]
code="$1"
to="${2:-15}"
dir="$(dirname "$0")"
payload=$(python "$dir/_mkpayload.py" "$code" "$to")
curl -sS -X POST http://localhost:8000/execute \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  | python "$dir/_pretty.py"
