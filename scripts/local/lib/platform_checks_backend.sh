#!/usr/bin/env bash
# scripts/local/lib/platform_checks_backend.sh
#
# Phase 6.c — Backend host-monitor cross-check.
#
# Calls `GET /health/host` on the local backend (serviced by the Phase 2
# host_monitor). Pretty-prints the backend's current verdict, baseline
# warmth, and a reconciliation line comparing the backend's snapshot to
# the shell-side /proc read done by platform_checks_common.sh.
#
# The reconciliation is best-effort: a disagreement between "local
# shell view" and "backend ring-buffer view" is itself a useful
# operator signal (e.g. stale ring buffer, transient local spike,
# backend worker wedged on the monitor loop).
#
# This module is applicable only when:
#   - curl is installed,
#   - the backend responds to GET /health with 2xx,
#   - the backend returns a JSON body for GET /health/host.
#
# Contract with dispatcher: expose applicable_backend / display_backend
# / verdict_backend (see platform_checks.sh).

_BACKEND_VERDICT="OK"
_BACKEND_PAYLOAD=""
_BACKEND_STATE=""
_BACKEND_URL_BASE="${II_AGENT_BACKEND_URL:-http://localhost:${BACKEND_PORT:-8000}}"

_backend_set_verdict() {
  case "$1" in
    CRIT) _BACKEND_VERDICT="CRIT" ;;
    WARN)
      [[ "$_BACKEND_VERDICT" == "CRIT" ]] || _BACKEND_VERDICT="WARN"
      ;;
    WATCH)
      case "$_BACKEND_VERDICT" in
        CRIT|WARN) ;;
        *) _BACKEND_VERDICT="WATCH" ;;
      esac
      ;;
  esac
}

# Tiny POSIX-ish extractor: `_backend_json_get <key>` on _BACKEND_PAYLOAD.
# Handles top-level scalar string/number values only (state, p99_docker_call_ms,
# baseline_warm, baseline_window_samples, baseline_window_capacity,
# captured_at). Never invoked for nested objects — callers parse those
# with sed/awk directly.
_backend_json_get() {
  local key="$1"
  # shellcheck disable=SC2001
  echo "$_BACKEND_PAYLOAD" \
    | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\\{0,1\\}\\([^,\"}]*\\)\"\\{0,1\\}.*/\\1/p" \
    | head -1
}

applicable_backend() {
  command -v curl >/dev/null 2>&1 || return 1
  # Fast liveness probe; 2s cap so a wedged backend can never block
  # status output.
  if ! curl -fsS --max-time 2 "${_BACKEND_URL_BASE}/health" >/dev/null 2>&1; then
    return 1
  fi
  _BACKEND_PAYLOAD=$(curl -fsS --max-time 2 "${_BACKEND_URL_BASE}/health/host" 2>/dev/null || true)
  [[ -n "$_BACKEND_PAYLOAD" ]] || return 1
  return 0
}

display_backend() {
  local state p99_ms warm samples capacity captured
  state=$(_backend_json_get state)
  p99_ms=$(_backend_json_get p99_docker_call_ms)
  warm=$(_backend_json_get baseline_warm)
  samples=$(_backend_json_get baseline_window_samples)
  capacity=$(_backend_json_get baseline_window_capacity)
  captured=$(_backend_json_get captured_at)

  _BACKEND_STATE="${state:-UNKNOWN}"

  # Map backend state -> module verdict. BOOTSTRAP is not a degradation;
  # it simply means the ring buffer hasn't warmed yet. Treat it as OK.
  case "$_BACKEND_STATE" in
    CRIT) _backend_set_verdict CRIT ;;
    WARN) _backend_set_verdict WARN ;;
    WATCH) _backend_set_verdict WATCH ;;
    OK|BOOTSTRAP|UNKNOWN) ;;
  esac

  local warm_label="no"
  [[ "$warm" == "true" ]] && warm_label="yes"

  local samples_line="${samples:-0}/${capacity:-0} samples"
  if [[ -n "$captured" && "$captured" != "null" ]]; then
    samples_line="${samples_line}  last_sample=${captured}"
  fi

  # Reconciliation with the shell-side common module. _COMMON_VERDICT is
  # set by platform_checks_common.sh which ran before us in the
  # dispatcher. If it's unset (e.g. --no-platform gating) the reconcile
  # line degrades gracefully.
  local local_view="${_COMMON_VERDICT:-unknown}"
  local reconcile
  if [[ "$local_view" == "$_BACKEND_STATE" ]]; then
    reconcile="local+backend snapshots agree (${local_view})"
  elif [[ "$_BACKEND_STATE" == "BOOTSTRAP" ]]; then
    reconcile="backend baseline warming; local view=${local_view}"
  else
    reconcile="disagreement: local=${local_view} backend=${_BACKEND_STATE}"
    # A disagreement where the backend reports worse than local is a
    # soft WATCH signal for the module roll-up.
    case "$_BACKEND_STATE" in
      WATCH|WARN|CRIT) _backend_set_verdict WATCH ;;
    esac
  fi

  cat <<EOF
=== Backend Host Monitor ===
  url:            ${_BACKEND_URL_BASE}/health/host
  state:          ${_BACKEND_STATE}
  baseline:       warm=${warm_label}  ${samples_line}
  p99 docker_call: ${p99_ms:-?} ms
  reconcile:      ${reconcile}
EOF
}

verdict_backend() { echo "$_BACKEND_VERDICT"; }

# JSON emitter (Phase 6.d). Pass-through wrapper around the backend's
# /health/host JSON, with a top-level verdict field synthesised from
# the backend's reported state.
json_backend() {
  _BACKEND_VERDICT="OK"
  if [[ -z "$_BACKEND_PAYLOAD" ]]; then
    # applicable_backend hasn't run yet (or failed). Probe now to be
    # self-sufficient.
    if ! applicable_backend; then
      printf '{"verdict":"OK","reachable":false}'
      return 0
    fi
  fi

  local state
  state=$(_backend_json_get state)
  case "$state" in
    CRIT) _backend_set_verdict CRIT ;;
    WARN) _backend_set_verdict WARN ;;
    WATCH) _backend_set_verdict WATCH ;;
  esac

  # Embed the raw backend payload as a sub-object. We strip the leading
  # `{` so we can splice in our own verdict + reachable flag without
  # re-parsing the body.
  local body="${_BACKEND_PAYLOAD#\{}"
  printf '{"verdict":"%s","reachable":true,%s' "$_BACKEND_VERDICT" "$body"
}
