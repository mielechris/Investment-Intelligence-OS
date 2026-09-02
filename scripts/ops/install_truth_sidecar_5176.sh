#!/bin/zsh
# Install and bootstrap the read-only IIOS-9L-V7-LIVING truth sidecar (port 5176)
# as a persistent per-user launchd service.
#
# Safety: this script never touches backend 8002, workers 9A/9B/9E, or any
# other com.iios.* label. It only manages com.iios.v7living-truth-sidecar.
set -euo pipefail

REPO_ROOT="/Users/crm/Documents/GitHub/IIOS-9L-V7-LIVING"
LABEL="com.iios.v7living-truth-sidecar"
PLIST_SRC="$REPO_ROOT/ops/launchd/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/IIOS"
UID_NUM="$(id -u)"

if [[ ! -f "$PLIST_SRC" ]]; then
  echo "ERROR: template plist not found: $PLIST_SRC" >&2
  exit 1
fi

echo "== Validating plist =="
plutil -lint "$PLIST_SRC"

echo "== Ensuring log directory exists: $LOG_DIR =="
mkdir -p "$LOG_DIR"

echo "== Ensuring built frontend exists =="
if [[ ! -f "$REPO_ROOT/FRONT END/dist/index.html" ]]; then
  echo "ERROR: $REPO_ROOT/FRONT END/dist/index.html missing. Run 'npm run build' in 'FRONT END' first." >&2
  exit 1
fi

echo "== Installing plist to $PLIST_DST =="
cp "$PLIST_SRC" "$PLIST_DST"
plutil -lint "$PLIST_DST"

echo "== Bootstrapping (removing any prior instance of this label only) =="
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST"
launchctl enable "gui/$UID_NUM/$LABEL"
launchctl kickstart -k "gui/$UID_NUM/$LABEL"

echo "== Installed and started: $LABEL =="
echo "Inspect with: launchctl print gui/$UID_NUM/$LABEL"
echo "Verify with: $REPO_ROOT/scripts/ops/verify_truth_sidecar_5176.sh"
