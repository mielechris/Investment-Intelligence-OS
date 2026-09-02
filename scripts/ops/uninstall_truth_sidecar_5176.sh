#!/bin/zsh
# Uninstall the persistent IIOS-9L-V7-LIVING truth sidecar (port 5176) service.
# Only touches com.iios.v7living-truth-sidecar; never backend 8002 or 9A/9B/9E.
set -euo pipefail

LABEL="com.iios.v7living-truth-sidecar"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

echo "== Booting out $LABEL (if loaded) =="
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || echo "(was not loaded)"

if [[ -f "$PLIST_DST" ]]; then
  echo "== Removing installed plist: $PLIST_DST =="
  rm -f "$PLIST_DST"
else
  echo "(no installed plist found at $PLIST_DST)"
fi

echo "== Done. Port 5176 will no longer be persistently managed. =="
echo "To recover manually, run scripts/ops/install_truth_sidecar_5176.sh again,"
echo "or start manually per DOCS/RUNBOOK_TRUTH_SIDECAR_5176.md."
