#!/usr/bin/env bash
# disk_cleanup_cron.sh — threshold-gated, stack-safe Docker disk cleanup for cron.
#
# Rationale, options chosen, and safety analysis are documented in
#   docs/runtime-docs/disk-cleanup-cron.md
#
# This wrapper exists so the cron schedule does NOT run an unconditional
# `docker system prune` every hour (which would needlessly churn images/cache).
# It only invokes the cleanup when the root filesystem crosses a usage
# threshold, never overlaps itself, and never runs during a stack rebuild.
set -uo pipefail

# Cron has a minimal PATH; /usr/sbin (fstrim) and /usr/bin (docker, flock) must
# both be present for stack_control.sh disk-cleanup to work.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO_DIR="/home/mdear/workspaces/git/ii-agent"
STACK_CTL="$REPO_DIR/scripts/stack_control.sh"
REBUILD_LOCK="/tmp/.ii-agent-rebuild-lock"      # honored by the systemd unit too
LOCK_FILE="/tmp/.ii-agent-disk-cleanup.lock"
LOG_FILE="$REPO_DIR/logs/disk-cleanup-cron.log"
THRESHOLD="${DISK_CLEANUP_THRESHOLD:-75}"        # percent of / used before acting
LOG_MAX_BYTES=1048576                            # 1 MiB cap — this job must never
                                                 # become a disk-flood source itself

mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S%z') $*" >>"$LOG_FILE"; }

# Self-cap our own log (irony guard: the cleanup log can never run away).
if [[ -f "$LOG_FILE" ]] && \
   [[ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]]; then
  tail -n 500 "$LOG_FILE" >"$LOG_FILE.tmp" 2>/dev/null && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

# Single-instance: never overlap with a previous (possibly long) prune run.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "SKIP another disk-cleanup instance is already running"
  exit 0
fi

# Never prune while a stack rebuild is staging images/containers.
if [[ -e "$REBUILD_LOCK" ]]; then
  log "SKIP rebuild in progress ($REBUILD_LOCK present)"
  exit 0
fi

USE_PCT="$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')"
if [[ -z "$USE_PCT" ]]; then
  log "ERROR could not read disk usage for /; aborting"
  exit 1
fi

if (( USE_PCT < THRESHOLD )); then
  log "OK disk ${USE_PCT}% < ${THRESHOLD}% threshold; no cleanup needed"
  exit 0
fi

log "TRIGGER disk ${USE_PCT}% >= ${THRESHOLD}% threshold; running stack-safe disk-cleanup"

# Default options only:
#   * docker system prune -af  — removes stopped containers, dangling/unused
#     images, unused networks, and build cache. Images referenced by RUNNING
#     containers are protected, including ii-agent-sandbox:latest (held by the
#     always-on a2a-adapter service).
#   * fstrim                    — returns freed blocks to the host VHDX.
# Deliberately NOT passing --prune-volumes: that could delete the postgres /
# redis / minio / filestore named volumes. Never automate volume deletion.
if "$STACK_CTL" disk-cleanup >>"$LOG_FILE" 2>&1; then
  AFTER="$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')"
  log "DONE disk-cleanup complete; disk now ${AFTER}% (was ${USE_PCT}%)"
else
  rc=$?
  log "ERROR disk-cleanup exited with status ${rc} (see lines above)"
  exit "$rc"
fi
