#!/usr/bin/env sh
# Usage: pane-wait.sh SESSION TEXT [TIMEOUT_SECONDS]
set -eu
session=$1
text=$2
timeout=${3:-10}
deadline=$(( $(date +%s) + timeout ))
pane=""
while :; do
  pane=$(tmux capture-pane -pt "$session" 2>/dev/null || true)
  case $pane in
    *"$text"*) printf '%s\n' "$pane"; exit 0 ;;
  esac
  if [ "$(date +%s)" -ge "$deadline" ]; then
    printf '%s\n' "$pane"
    echo "pane-wait: timed out after ${timeout}s waiting for: $text" >&2
    exit 1
  fi
  sleep 0.1
done
