#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
entrypoint_file="$repo_root/config/iios_browser_entrypoint.json"
display_url="http://127.0.0.1:5176/"
expected_identity="THE AUCTION EDITION · MUSEUM MASTER 1.2"
open_browser=false

case "${1:-}" in
  "") ;;
  --open) open_browser=true ;;
  *) printf '%s\n' "CANONICAL_ENTRYPOINT_ARGUMENT_REJECTED" >&2; exit 2 ;;
esac

if [ ! -f "$entrypoint_file" ] || ! /usr/bin/python3 -c 'import json,sys; value=json.load(open(sys.argv[1],encoding="utf-8")); raise SystemExit(0 if value=={"schema_version":"iios-canonical-browser-entrypoint-v1","canonical_url":"http://127.0.0.1:5176/","expected_identity":"THE AUCTION EDITION · MUSEUM MASTER 1.2","user_facing_frontend_count":1,"internal_diagnostics":{"5177":"INTERNAL_DIAGNOSTIC_ONLY","5185":"INTERNAL_DIAGNOSTIC_ONLY"},"development_frontends":{"5184":"DEVELOPMENT_ONLY","5186":"DEVELOPMENT_ONLY"}} else 1)' "$entrypoint_file"; then
  printf '%s\n' "CANONICAL_ENTRYPOINT_CONTRACT_INVALID" >&2
  exit 3
fi

for health_url in \
  http://127.0.0.1:8002/system/status \
  http://127.0.0.1:5176/health \
  http://127.0.0.1:5177/health \
  http://127.0.0.1:5185/; do
  if ! /usr/bin/curl --silent --fail --max-time 3 --output /dev/null "$health_url"; then
    printf '%s\n' "PROTECTED_SERVICE_HEALTH_UNAVAILABLE" >&2
    exit 4
  fi
done

page=$(/usr/bin/curl --silent --fail --max-time 3 "$display_url") || { printf '%s\n' "CANONICAL_MUSEUM_UNAVAILABLE" >&2; exit 5; }
asset=$(printf '%s' "$page" | /usr/bin/sed -n 's/.*src="\([^\"]*\.js\)".*/\1/p' | /usr/bin/head -n 1)
case "$asset" in /assets/*.js) ;; *) printf '%s\n' "CANONICAL_MUSEUM_IDENTITY_UNAVAILABLE" >&2; exit 6 ;; esac
bundle=$(/usr/bin/curl --silent --fail --max-time 5 "http://127.0.0.1:5176$asset") || { printf '%s\n' "CANONICAL_MUSEUM_IDENTITY_UNAVAILABLE" >&2; exit 6; }
for marker in "$expected_identity" Gallery Story Replay Command Cases "Expansion Wing" "Factory Watch"; do
  printf '%s' "$bundle" | /usr/bin/grep -F -q "$marker" || { printf '%s\n' "CANONICAL_MUSEUM_IDENTITY_MISMATCH" >&2; exit 7; }
done

printf '%s\n' "CANONICAL_MUSEUM_READY http://127.0.0.1:5176/"
if [ "$open_browser" = true ]; then
  /usr/bin/open -a Safari "$display_url"
  printf '%s\n' "CANONICAL_MUSEUM_OPEN_REQUESTED"
else
  printf '%s\n' "BROWSER_OPEN_NOT_REQUESTED"
fi
