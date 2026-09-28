#!/usr/bin/env bash
#
# The only command the GitHub deploy key may run (forced command in
# ~/.ssh/authorized_keys). Accepts exactly:
#
#   deploy v<version>    rollback    status
#
# and hands it to csc_release_deploy.sh, logging to ~/csc/shared/logs/deploy.log.

# supervisorctl and python3.13 need the login environment; load it before
# strict mode, which would abort on any unset variable inside the profile
[ -f "$HOME/.bash_profile" ] && source "$HOME/.bash_profile" >/dev/null 2>&1

set -euo pipefail

CSC_HOME="${CSC_HOME:-$HOME/csc}"
LOG="$CSC_HOME/shared/logs/deploy.log"
mkdir -p "$(dirname "$LOG")"

request="${SSH_ORIGINAL_COMMAND:-}"
case "$request" in
  "status")   args=(--status) ;;
  "rollback") args=(--rollback) ;;
  deploy\ v*)
    tag="${request#deploy }"
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] \
      || { echo "refused: bad tag '$tag'" >&2; exit 2; }
    args=("$tag") ;;
  *)
    echo "refused: '$request' (allowed: deploy v<version> | rollback | status)" >&2
    exit 2 ;;
esac

{
  client="${SSH_CLIENT:-local}"
  echo "=== $(date -Iseconds) $request (from ${client%% *})"
  "$CSC_HOME/bin/csc_release_deploy.sh" "${args[@]}"
} 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
