#!/bin/zsh
set -euo pipefail

label="com.iios.expansion-wing-preview"
plist="$HOME/Library/LaunchAgents/$label.plist"
state_dir="$HOME/Library/Application Support/IIOS/ExpansionWingPreview"
/bin/launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
[[ ! -e "$plist" ]] || /bin/rm "$plist"
if [[ -d "$state_dir" && "$state_dir" == "$HOME/Library/Application Support/IIOS/ExpansionWingPreview" ]]; then
  /bin/rm -rf "$state_dir"
fi
print "Removed $label; log retained for audit."
