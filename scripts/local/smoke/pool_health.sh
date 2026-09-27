#!/usr/bin/env bash
# scripts/local/smoke/pool_health.sh
#
# Pool + host monitor smoke check. Replays the four manual checks
# documented in docs/exec-plans/sandbox-robustness-fix-a.md (Item 7
# smoke). Exits non-zero on regression so CI / cron can run it.
#
# Checks:
#   1. GET /health/sandbox-pool           — JSON has expected keys + available=true
#   2. ./scripts/stack_control.sh status  — human view shows "Sandbox Pool" section
#   3. status --json                       — modules.pool present with verdict OK/WATCH
#   4. status --strict                     — exit code in {0, 2}; 2 indicates a
#                                            non-pool warning (acceptable here)
#
# Exit codes:
#   0  all checks passed
#   1  one or more checks failed (see stderr for details)
#   2  prerequisites missing (curl/jq/python3, or stack down)
#
# Usage:
#   ./scripts/local/smoke/pool_health.sh
#   BACKEND_URL=http://localhost:8000 ./scripts/local/smoke/pool_health.sh

set -uo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
STACK_CTL="${REPO_ROOT}/scripts/stack_control.sh"

_failures=0
_red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
_green() { printf '\033[32m%s\033[0m\n' "$*"; }
_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || { _red "missing required command: $1"; exit 2; }
}

require curl
require python3

[[ -x "$STACK_CTL" ]] || { _red "missing $STACK_CTL"; exit 2; }

if ! curl -fsS --max-time 5 "${BACKEND_URL}/health" >/dev/null 2>&1; then
  _red "backend ${BACKEND_URL}/health is not reachable — start the stack first"
  exit 2
fi

# ─── Check 1: /health/sandbox-pool shape ─────────────────────────────────
_blue "[1/4] GET ${BACKEND_URL}/health/sandbox-pool"
pool_json="$(curl -fsS --max-time 10 "${BACKEND_URL}/health/sandbox-pool" 2>/dev/null || true)"
if [[ -z "$pool_json" ]]; then
  _red "  FAIL: empty response from /health/sandbox-pool"
  ((_failures++))
else
  pool_check="$(POOL_JSON="$pool_json" python3 <<'PY'
import json, os, sys

required = {
    "available", "enabled", "configured", "ready", "initializing",
    "initializing_age_max_seconds", "stuck_initializing", "claimed",
    "retiring", "stuck_threshold_seconds",
}
try:
    body = json.loads(os.environ["POOL_JSON"])
except Exception as exc:
    print(f"FAIL parse: {exc}")
    sys.exit(0)
missing = required - set(body.keys())
if missing:
    print(f"FAIL missing keys: {sorted(missing)}")
elif not body.get("available"):
    print(f"FAIL available=false reason={body.get('reason')!r}")
elif body.get("stuck_threshold_seconds") != 600:
    print(f"FAIL stuck_threshold_seconds={body.get('stuck_threshold_seconds')}")
else:
    print(
        "OK configured={c} ready={r} stuck_initializing={s} initializing={i}".format(
            c=body.get("configured"), r=body.get("ready"),
            s=body.get("stuck_initializing"), i=body.get("initializing"),
        )
    )
PY
)"
  if [[ "$pool_check" == OK* ]]; then
    _green "  PASS ${pool_check#OK }"
  else
    _red "  FAIL: $pool_check"
    ((_failures++))
  fi
fi

# ─── Check 2: human status shows Sandbox Pool section ────────────────────
_blue "[2/4] stack_control.sh status (human view)"
human_status="$("$STACK_CTL" status 2>/dev/null || true)"
if printf '%s' "$human_status" | grep -q "=== Sandbox Pool ==="; then
  pool_line="$(printf '%s' "$human_status" | grep -A 5 "=== Sandbox Pool ===" | grep -E '^[[:space:]]*status:' | head -1 | sed 's/^[[:space:]]*//')"
  _green "  PASS ${pool_line:-section present}"
else
  _red "  FAIL: '=== Sandbox Pool ===' section missing from status output"
  ((_failures++))
fi

# ─── Check 3: status --json modules.pool ─────────────────────────────────
_blue "[3/4] stack_control.sh status --json modules.pool"
json_status="$("$STACK_CTL" status --json 2>/dev/null || true)"
if [[ -z "$json_status" ]]; then
  _red "  FAIL: status --json produced no output"
  ((_failures++))
else
  json_check="$(STATUS_JSON="$json_status" python3 <<'PY'
import json, os, sys

try:
    payload = json.loads(os.environ["STATUS_JSON"])
except Exception as exc:
    print(f"FAIL parse: {exc}")
    sys.exit(0)
pool = (payload.get("modules") or {}).get("pool")
if pool is None:
    print("FAIL modules.pool missing")
elif not pool.get("reachable"):
    print(f"FAIL pool.reachable=false: {pool}")
elif pool.get("verdict") not in {"OK", "WATCH"}:
    print(f"FAIL pool.verdict={pool.get('verdict')!r}")
else:
    print("OK verdict={v} configured={c} ready={r}".format(
        v=pool["verdict"], c=pool.get("configured"), r=pool.get("ready"),
    ))
PY
)"
  if [[ "$json_check" == OK* ]]; then
    _green "  PASS ${json_check#OK }"
  else
    _red "  FAIL: $json_check"
    ((_failures++))
  fi
fi

# ─── Check 4: status --strict exit code ──────────────────────────────────
_blue "[4/4] stack_control.sh status --strict (exit code)"
"$STACK_CTL" status --strict >/dev/null 2>&1
strict_rc=$?
case "$strict_rc" in
  0) _green "  PASS exit=0 (all modules OK)" ;;
  2) _green "  PASS exit=2 (WARN/CRIT in non-pool module — acceptable)" ;;
  *)
    _red "  FAIL exit=${strict_rc} (expected 0 or 2)"
    ((_failures++))
    ;;
esac

echo
if (( _failures == 0 )); then
  _green "pool_health.sh: all 4 checks passed"
  exit 0
else
  _red "pool_health.sh: ${_failures} check(s) failed"
  exit 1
fi
