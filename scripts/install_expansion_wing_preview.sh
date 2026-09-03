#!/bin/zsh
set -euo pipefail

label="com.iios.expansion-wing-preview"
port="${IIOS_EXPANSION_PORT:-5177}"
worktree="${1:-$(git rev-parse --show-toplevel)}"
worktree="$(cd "$worktree" && pwd -P)"
state_dir="$HOME/Library/Application Support/IIOS/ExpansionWingPreview"
log_dir="$HOME/Library/Logs/IIOS"
plist="$HOME/Library/LaunchAgents/$label.plist"
template="$worktree/config/$label.plist.template"
python_bin="$(command -v python3)"

[[ "$(git -C "$worktree" branch --show-current)" == "feature/iios-expansion-wing-dual-book-machinery" ]] || { print -u2 BRANCH_MISMATCH; exit 2; }
[[ -z "$(git -C "$worktree" status --porcelain)" ]] || { print -u2 WORKTREE_NOT_CLEAN; exit 2; }
[[ -f "$template" && -x "$python_bin" ]] || { print -u2 INSTALL_INPUT_MISSING; exit 2; }
! /usr/sbin/lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || { print -u2 PORT_IN_USE; exit 2; }
[[ ! -e "$plist" ]] || { print -u2 LABEL_COLLISION; exit 2; }

umask 077
mkdir -p "$state_dir" "$log_dir" "${plist:h}"
chmod 700 "$state_dir"
(cd "$worktree/FRONT END" && VITE_EXPANSION_WING_APP=1 VITE_EXPANSION_WING_LIVE_READONLY=1 VITE_BACKEND_RECOVERY_GREEN=1 VITE_EXPANSION_WING_READONLY_ENDPOINT=/snapshot npx vite build --outDir "$state_dir/www" --emptyOutDir)
/usr/bin/sed -e "s|__PYTHON__|$python_bin|g" -e "s|__PORT__|$port|g" -e "s|__STATE_DIR__|$state_dir|g" \
  -e "s|__HOME__|$HOME|g" -e "s|__WORKTREE__|$worktree|g" -e "s|__LOG__|$log_dir/expansion-wing-preview.log|g" "$template" > "$plist"
chmod 600 "$plist"
/usr/bin/plutil -lint "$plist" >/dev/null
/bin/launchctl bootstrap "gui/$(id -u)" "$plist"
print "Installed $label at http://127.0.0.1:$port/"
