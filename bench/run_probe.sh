#!/bin/bash
# Run an authenticated bash /execute probe. Takes code on stdin.
# Usage:  cat payload.sh | bench/run_probe.sh [timeout]
# Requires admin creds in env (default: admin@supakiln.local / ChangeMe123).
TO="${1:-15}"
EMAIL="${SUPAKILN_ADMIN_EMAIL:-admin@supakiln.local}"
PASS="${SUPAKILN_ADMIN_PASSWORD:-ChangeMe123}"
DIR="$(dirname "$0")"
TOKEN=$(curl -sS -X POST http://localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python -c "import json,sys; print(json.load(sys.stdin)['session_token'])")
CODE=$(cat)
# Build JSON body safely.
python -c 'import json,sys; print(json.dumps({"code":sys.argv[1],"language":"bash","timeout":int(sys.argv[2])}))' "$CODE" "$TO" \
  | curl -sS -X POST http://localhost:8000/execute \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' --data-binary @- \
  | python "$DIR/_pretty.py"
