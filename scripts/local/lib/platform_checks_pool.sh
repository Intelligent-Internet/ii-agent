#!/usr/bin/env bash
# scripts/local/lib/platform_checks_pool.sh
#
# Pre-warmed sandbox pool occupancy check.
#
# Calls `GET /health/sandbox-pool` on the local backend (added alongside
# Fix A — the AVAILABLE+INITIALIZING zombie reaper). Pretty-prints the
# pool's configured-vs-ready slot count, any in-flight initialisations,
# and any rows wedged past the reap threshold.
#
# Verdict mapping:
#   - pool disabled (configured=0)              -> OK   (intentional opt-out)
#   - ready==configured                         -> OK
#   - any stuck_initializing > 0                -> WARN (reap will fire on
#                                                  next bootstrap/ensure_full)
#   - ready<configured AND no stuck             -> WATCH (slots provisioning)
#   - ready==0 AND configured>0 AND no stuck    -> WATCH (post-restart warmup)
#
# Applicable only when:
#   - curl is installed,
#   - the backend responds 2xx to GET /health,
#   - GET /health/sandbox-pool returns a JSON body with available=true.

_POOL_VERDICT="OK"
_POOL_PAYLOAD=""
_POOL_URL_BASE="${II_AGENT_BACKEND_URL:-http://localhost:${BACKEND_PORT:-8000}}"

_pool_set_verdict() {
  case "$1" in
    CRIT) _POOL_VERDICT="CRIT" ;;
    WARN)
      [[ "$_POOL_VERDICT" == "CRIT" ]] || _POOL_VERDICT="WARN"
      ;;
    WATCH)
      case "$_POOL_VERDICT" in
        CRIT|WARN) ;;
        *) _POOL_VERDICT="WATCH" ;;
      esac
      ;;
  esac
}

# Tiny scalar extractor for top-level JSON keys (numbers, strings, bools, null).
_pool_json_get() {
  local key="$1"
  # shellcheck disable=SC2001
  echo "$_POOL_PAYLOAD" \
    | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\\{0,1\\}\\([^,\"}]*\\)\"\\{0,1\\}.*/\\1/p" \
    | head -1
}

applicable_pool() {
  command -v curl >/dev/null 2>&1 || return 1
  if ! curl -fsS --max-time 2 "${_POOL_URL_BASE}/health" >/dev/null 2>&1; then
    return 1
  fi
  _POOL_PAYLOAD=$(curl -fsS --max-time 2 "${_POOL_URL_BASE}/health/sandbox-pool" 2>/dev/null || true)
  [[ -n "$_POOL_PAYLOAD" ]] || return 1
  return 0
}

display_pool() {
  local available enabled configured ready initializing init_age stuck claimed retiring threshold reason
  available=$(_pool_json_get available)
  enabled=$(_pool_json_get enabled)
  configured=$(_pool_json_get configured)
  ready=$(_pool_json_get ready)
  initializing=$(_pool_json_get initializing)
  init_age=$(_pool_json_get initializing_age_max_seconds)
  stuck=$(_pool_json_get stuck_initializing)
  claimed=$(_pool_json_get claimed)
  retiring=$(_pool_json_get retiring)
  threshold=$(_pool_json_get stuck_threshold_seconds)
  reason=$(_pool_json_get reason)

  echo "=== Sandbox Pool ==="
  echo "  url:            ${_POOL_URL_BASE}/health/sandbox-pool"

  if [[ "$available" != "true" ]]; then
    echo "  status:         unavailable (${reason:-unknown})"
    _pool_set_verdict WATCH
    return 0
  fi

  if [[ "$enabled" != "true" || "${configured:-0}" == "0" ]]; then
    echo "  status:         disabled (configured=${configured:-0})"
    return 0
  fi

  echo "  configured:     ${configured}  ready: ${ready:-0}"
  echo "  in-flight:      initializing=${initializing:-0} claimed=${claimed:-0} retiring=${retiring:-0}"

  local age_label="-"
  if [[ -n "$init_age" && "$init_age" != "null" ]]; then
    age_label="${init_age}s"
  fi
  echo "  oldest INIT:    ${age_label}  reap threshold: ${threshold:-0}s"

  if [[ "${stuck:-0}" -gt 0 ]]; then
    echo "  stuck rows:     ${stuck} (will be reaped on next bootstrap/ensure_full)"
    _pool_set_verdict WARN
  elif [[ "${ready:-0}" -lt "${configured}" ]]; then
    echo "  status:         warming (${ready:-0}/${configured} ready)"
    _pool_set_verdict WATCH
  else
    echo "  status:         OK (${ready}/${configured} ready)"
  fi
}

verdict_pool() { echo "$_POOL_VERDICT"; }

# JSON emitter: pass-through wrapper around /health/sandbox-pool plus a
# top-level verdict synthesised from the body.
json_pool() {
  _POOL_VERDICT="OK"
  if [[ -z "$_POOL_PAYLOAD" ]]; then
    if ! applicable_pool; then
      printf '{"verdict":"OK","reachable":false}'
      return 0
    fi
  fi

  local available enabled configured ready stuck
  available=$(_pool_json_get available)
  enabled=$(_pool_json_get enabled)
  configured=$(_pool_json_get configured)
  ready=$(_pool_json_get ready)
  stuck=$(_pool_json_get stuck_initializing)

  if [[ "$available" != "true" ]]; then
    _pool_set_verdict WATCH
  elif [[ "$enabled" == "true" && "${configured:-0}" != "0" ]]; then
    if [[ "${stuck:-0}" -gt 0 ]]; then
      _pool_set_verdict WARN
    elif [[ "${ready:-0}" -lt "${configured}" ]]; then
      _pool_set_verdict WATCH
    fi
  fi

  local body="${_POOL_PAYLOAD#\{}"
  printf '{"verdict":"%s","reachable":true,%s' "$_POOL_VERDICT" "$body"
}
