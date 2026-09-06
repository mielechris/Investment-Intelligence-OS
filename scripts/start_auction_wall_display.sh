#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime_root="${TMPDIR:-/tmp}/iios-auction-wall-display"
display_url="${1:-http://127.0.0.1:5173/?wall=1}"

case "$display_url" in
  http://127.0.0.1:*|https://*.vercel.app/*|https://*.vercel.app) ;;
  *) printf '%s\n' "Refusing unapproved display URL." >&2; exit 2 ;;
esac

mkdir -p "$runtime_root"
if [ "${display_url#http://127.0.0.1:}" != "$display_url" ]; then
  if [ -f "$runtime_root/server.pid" ] && kill -0 "$(sed -n '1p' "$runtime_root/server.pid")" 2>/dev/null; then
    printf '%s\n' "Auction wall server is already running."
  else
    (
      server_child=""
      stop_child() {
        if [ -n "$server_child" ] && kill -0 "$server_child" 2>/dev/null; then kill "$server_child"; fi
        exit 0
      }
      trap stop_child INT TERM
      while :; do
        npm --prefix "$repo_root/FRONT END" run dev -- --host 127.0.0.1 &
        server_child=$!
        health_attempt=0
        while [ "$health_attempt" -lt 30 ]; do
          if /usr/bin/curl --silent --fail --max-time 2 "${display_url%%\?*}" >/dev/null 2>&1; then break; fi
          health_attempt=$((health_attempt + 1))
          sleep 1
        done
        wait "$server_child" || true
        server_child=""
        sleep 2
      done
    ) >"$runtime_root/server.log" 2>&1 &
    printf '%s\n' "$!" >"$runtime_root/server.pid"
  fi
fi

open -a Safari "$display_url"
printf '%s\n' "Display opened in Wall Art Mode. Verify truth health, then enter browser full screen manually."
printf '%s\n' "Exit remains available through Reveal Controls and Exit Full Screen."
