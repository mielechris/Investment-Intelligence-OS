#!/bin/sh
set -eu

runtime_root="${TMPDIR:-/tmp}/iios-auction-wall-display"
pid_file="$runtime_root/server.pid"

if [ -f "$pid_file" ]; then
  server_pid=$(sed -n '1p' "$pid_file")
  case "$server_pid" in *[!0-9]*|'') printf '%s\n' "Invalid runtime PID; no process stopped." >&2; exit 2 ;; esac
  if kill -0 "$server_pid" 2>/dev/null; then kill "$server_pid"; fi
  rm -f "$pid_file"
fi

printf '%s\n' "Auction wall server stopped. Safari and macOS settings were not changed."
