#!/bin/zsh
# Verify the persistent IIOS-9L-V7-LIVING truth sidecar (port 5176) is healthy,
# read-only, bound to localhost only, and reporting the correct checkout/ledger
# identity. Exits non-zero on any failed check.
set -uo pipefail

LABEL="com.iios.v7living-truth-sidecar"
UID_NUM="$(id -u)"
PORT=5176
FAIL=0

echo "== launchctl service state =="
if ! launchctl print "gui/$UID_NUM/$LABEL" >/tmp/v7living-truth-sidecar-print.txt 2>&1; then
  echo "FAIL: service $LABEL is not loaded" >&2
  FAIL=1
else
  grep -E "pid|state|last exit" /tmp/v7living-truth-sidecar-print.txt || true
fi

echo "== Port binding (must be 127.0.0.1 only) =="
BIND_LINES="$(lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null)"
echo "$BIND_LINES"
LISTEN_ROWS="$(echo "$BIND_LINES" | tail -n +2)"
if [[ -z "$LISTEN_ROWS" ]]; then
  echo "FAIL: nothing listening on $PORT" >&2
  FAIL=1
elif echo "$LISTEN_ROWS" | grep -qv "127.0.0.1:$PORT"; then
  echo "FAIL: $PORT is bound to something other than 127.0.0.1" >&2
  FAIL=1
fi

echo "== /health =="
HEALTH_JSON="$(curl -s --max-time 8 "http://127.0.0.1:$PORT/health")"
echo "$HEALTH_JSON"
echo "$HEALTH_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d.get('status') == 'BATCH9L_BROWSER_PREVIEW_HEALTHY', d
assert d.get('live_execution') is False, d
assert d.get('backend_write_permission') is False, d
print('health: OK')
" || FAIL=1

echo "== /living/overview (reachability only) =="
curl -s --max-time 8 -o /dev/null -w "http status: %{http_code}\n" "http://127.0.0.1:$PORT/living/overview" || FAIL=1

echo "== /truth/factory identity + invariants =="
TRUTH_JSON="$(curl -s --max-time 8 "http://127.0.0.1:$PORT/truth/factory")"
echo "$TRUTH_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['sidecar']['checkout'] == '/Users/crm/Documents/GitHub/IIOS-9L-V7-LIVING', d['sidecar']
assert d['sidecar']['ledger_path'] == '/Users/crm/Documents/GitHub/IIOS-9L-V7-LIVING/BACK END/backend/iios_ledger.db', d['sidecar']
assert d['source']['mode'] == 'FACTORY_TELEMETRY_V2_SQLITE_READ_ONLY', d['source']
inv = d['live_authority_invariants']
assert inv['verified'] is True, inv
assert inv['live_execution'] is False, inv
assert inv['broker_connected'] is False, inv
assert inv['trade_execution_permission'] is False, inv
pa = d['paper_account']
assert pa['starting_cash'] == 10000.0, pa
assert pa['position_count'] == 0, pa
print('truth/factory pid:', d['sidecar']['pid'])
print('truth/factory ledger_fingerprint:', d['source']['ledger_fingerprint'])
print('truth/factory: OK')
" || FAIL=1

if [[ "$FAIL" -ne 0 ]]; then
  echo "VERIFY: FAILED" >&2
  exit 1
fi
echo "VERIFY: PASSED"
