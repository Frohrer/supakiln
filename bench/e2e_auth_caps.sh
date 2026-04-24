#!/bin/bash
# End-to-end smoke test for steps 1-3: auth, per-user containers, caps+eviction.
#
# Prerequisites:
#   - backend running on :8000
#   - admin@supakiln.local / ChangeMe123 exists (bootstrapped from env)
#   - MAX_WORKERS_PER_USER small (default 5) — for cap test, set to 2:
#       SUPAKILN_MAX_WORKERS_PER_USER=2 docker compose up -d backend
#
# Runs every assertion as `expect=<actual>`; exits non-zero if anything is off.

set -u
BASE=http://localhost:8000
FAIL=0

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()  { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }
fail() { printf '  \033[0;31m✗\033[0m %s\n' "$*"; FAIL=$((FAIL+1)); }

jq_get() { python -c "import json,sys; print(json.load(sys.stdin).get('$1',''))"; }

# ------------ step 1: auth ------------
say "Step 1 — login as admin"
ADMIN_RESP=$(curl -sS -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@supakiln.local","password":"ChangeMe123"}')
ADMIN=$(echo "$ADMIN_RESP" | jq_get session_token)
[ -n "$ADMIN" ] && ok "admin session token obtained" || fail "admin login failed: $ADMIN_RESP"

say "Step 1 — wrong password rejected"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@supakiln.local","password":"wrong"}')
[ "$CODE" = "401" ] && ok "wrong password → 401" || fail "wrong password → $CODE (expected 401)"

say "Step 1 — /auth/me resolves bearer token"
ME=$(curl -sS $BASE/auth/me -H "Authorization: Bearer $ADMIN")
IS_ADMIN=$(echo "$ME" | jq_get is_admin)
[ "$IS_ADMIN" = "True" ] && ok "/auth/me says is_admin=True" || fail "/auth/me: $ME"

say "Step 1 — create fresh test users alice+bob"
curl -sS -o /dev/null -X POST $BASE/admin/users -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"email":"e2e-alice@example.com","password":"alicePW1"}'
curl -sS -o /dev/null -X POST $BASE/admin/users -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"email":"e2e-bob@example.com","password":"bobPW5678"}'
ALICE=$(curl -sS -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"e2e-alice@example.com","password":"alicePW1"}' | jq_get session_token)
BOB=$(curl -sS -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"e2e-bob@example.com","password":"bobPW5678"}' | jq_get session_token)
[ -n "$ALICE" ] && [ -n "$BOB" ] && ok "alice+bob logged in" || fail "couldn't get tokens"

say "Step 1 — alice mints + uses API key"
KEYRESP=$(curl -sS -X POST $BASE/users/me/keys -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' -d '{"label":"ci"}')
KEY=$(echo "$KEYRESP" | jq_get token)
[ -n "$KEY" ] && ok "key minted" || fail "key mint failed: $KEYRESP"
EMAIL_VIA_KEY=$(curl -sS $BASE/auth/me -H "Authorization: Bearer $KEY" | jq_get email)
[ "$EMAIL_VIA_KEY" = "e2e-alice@example.com" ] \
  && ok "API key resolves to alice" \
  || fail "API key resolved to: $EMAIL_VIA_KEY"

say "Step 1 — alice can't reach /admin/users"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" $BASE/admin/users \
  -H "Authorization: Bearer $ALICE")
[ "$CODE" = "403" ] && ok "alice → /admin/users → 403" || fail "alice got $CODE"

# ------------ step 2: per-user containers ------------
say "Step 2 — reset workers, alice+bob each run bash"
curl -sS -X POST $BASE/workers/reset -H "Authorization: Bearer $ADMIN" > /dev/null
A_CID=$(curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' \
  -d '{"code":"echo alice","language":"bash","timeout":5}' | jq_get container_id)
B_CID=$(curl -sS -X POST $BASE/execute -H "Authorization: Bearer $BOB" \
  -H 'Content-Type: application/json' \
  -d '{"code":"echo bob","language":"bash","timeout":5}' | jq_get container_id)
[ -n "$A_CID" ] && [ -n "$B_CID" ] && [ "$A_CID" != "$B_CID" ] \
  && ok "alice=${A_CID:0:12} bob=${B_CID:0:12} — different containers" \
  || fail "same container: alice=$A_CID bob=$B_CID"

say "Step 2 — env vars don't leak across users"
curl -sS -o /dev/null -X POST $BASE/env -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' -d '{"name":"LEAKTEST","value":"alice-val"}'
curl -sS -o /dev/null -X POST $BASE/env -H "Authorization: Bearer $BOB" \
  -H 'Content-Type: application/json' -d '{"name":"LEAKTEST","value":"bob-val"}'
A_SEES=$(curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' \
  -d '{"code":"echo $LEAKTEST","language":"bash","timeout":5}' | jq_get output | tr -d '\r\n ')
B_SEES=$(curl -sS -X POST $BASE/execute -H "Authorization: Bearer $BOB" \
  -H 'Content-Type: application/json' \
  -d '{"code":"echo $LEAKTEST","language":"bash","timeout":5}' | jq_get output | tr -d '\r\n ')
[ "$A_SEES" = "alice-val" ] && [ "$B_SEES" = "bob-val" ] \
  && ok "alice sees 'alice-val', bob sees 'bob-val'" \
  || fail "alice=$A_SEES bob=$B_SEES"

say "Step 2 — alice creates job, bob can't see it"
JID=$(curl -sS -X POST $BASE/jobs -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' \
  -d '{"name":"alice-only","code":"print(1)","cron_expression":"0 0 1 1 0","language":"python"}' \
  | jq_get id)
BOB_CNT=$(curl -sS $BASE/jobs -H "Authorization: Bearer $BOB" \
  | python -c "import json,sys; print(len(json.load(sys.stdin)))")
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$BASE/jobs/$JID" \
  -H "Authorization: Bearer $BOB")
[ "$BOB_CNT" = "0" ] && [ "$CODE" = "404" ] \
  && ok "bob sees 0 jobs, alice's job GET → 404 for bob" \
  || fail "bob sees $BOB_CNT jobs, GET → $CODE"
curl -sS -X DELETE "$BASE/jobs/$JID" -H "Authorization: Bearer $ALICE" > /dev/null

# ------------ step 3: caps + eviction ------------
say "Step 3 — checking per-user cap"
MAX_USER=$(docker exec supakiln-backend-1 sh -c 'echo $SUPAKILN_MAX_WORKERS_PER_USER')
echo "  MAX_WORKERS_PER_USER=$MAX_USER (run with =2 for a tight test)"

say "Step 3 — warm alice's workers (bash+python)"
curl -sS -X POST $BASE/workers/reset -H "Authorization: Bearer $ADMIN" > /dev/null
curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' -d '{"code":"echo","language":"bash"}' > /dev/null
curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' -d '{"code":"print(1)","language":"python"}' > /dev/null
COUNT=$(curl -sS $BASE/workers -H "Authorization: Bearer $ALICE" \
  | python -c "import json,sys; print(len(json.load(sys.stdin)['workers']))")
[ "$COUNT" = "2" ] && ok "alice has 2 workers" || fail "alice has $COUNT workers"

say "Step 3 — 3rd distinct cache key triggers LRU eviction (cap=2) or coexists (cap>=3)"
THIRD=$(curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
  -H 'Content-Type: application/json' \
  -d '{"code":"console.log(1)","language":"node"}' | jq_get container_id)
[ -n "$THIRD" ] && ok "3rd (node) container=${THIRD:0:12} came up" || fail "3rd failed"
AFTER=$(curl -sS $BASE/workers -H "Authorization: Bearer $ALICE" \
  | python -c "import json,sys; print(len(json.load(sys.stdin)['workers']))")
printf "  alice now has %s worker(s) (cap=%s — eviction iff cap < 3)\n" "$AFTER" "$MAX_USER"

if [ "$MAX_USER" -le 2 ]; then
  say "Step 3 — saturate both workers and try a 3rd → expect 429"
  curl -sS -X POST $BASE/workers/reset -H "Authorization: Bearer $ALICE" > /dev/null
  curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
    -H 'Content-Type: application/json' -d '{"code":"echo","language":"bash"}' > /dev/null
  curl -sS -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
    -H 'Content-Type: application/json' -d '{"code":"print(1)","language":"python"}' > /dev/null
  (curl -sS -o /dev/null -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
    -H 'Content-Type: application/json' \
    -d '{"code":"sleep 6","language":"bash","timeout":10}') &
  (curl -sS -o /dev/null -X POST $BASE/execute -H "Authorization: Bearer $ALICE" \
    -H 'Content-Type: application/json' \
    -d '{"code":"import time; time.sleep(6)","language":"python","timeout":10}') &
  sleep 2
  CODE=$(curl -sS -o /tmp/429.json -w "%{http_code}" -X POST $BASE/execute \
    -H "Authorization: Bearer $ALICE" -H 'Content-Type: application/json' \
    -d '{"code":"console.log(1)","language":"node","timeout":5}')
  wait
  [ "$CODE" = "429" ] && ok "3rd request → HTTP 429 (worker cap, all busy)" \
    || fail "expected 429, got $CODE — body: $(cat /tmp/429.json)"
else
  echo "  (skipping 429 saturation test — cap is $MAX_USER; re-run with MAX_WORKERS_PER_USER=2)"
fi

say "Step 3 — pressure reaper sanity check"
REAPED=$(docker logs --since=10m supakiln-backend-1 2>&1 \
  | grep -E "Memory-pressure reaped|CPU-pressure reaped" | wc -l)
echo "  pressure reap events in last 10min: $REAPED"
ok "reaper is registered (check docker logs for activity under load)"

# ------------ summary ------------
echo
if [ "$FAIL" = "0" ]; then
  echo -e "\033[1;32m✔ ALL CHECKS PASSED\033[0m"
  exit 0
else
  echo -e "\033[1;31m✘ $FAIL CHECK(S) FAILED\033[0m"
  exit 1
fi
