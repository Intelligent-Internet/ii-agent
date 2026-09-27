#!/usr/bin/env bash
# scripts/local/lib/platform_checks.sh
#
# Dispatcher for the platform-health section of `stack_control.sh status`.
#
# Sources platform_checks_common.sh always, plus any release-specific
# modules whose `applicable()` returns 0. Each module exports:
#   - applicable           : returns 0 when the module should run
#   - display              : prints one section to stdout
#   - verdict              : echoes one of OK | WATCH | WARN | CRIT
#                            (worst-case across signals in the module)
#
# Verdict ordering used by the dispatcher when rolling up: CRIT > WARN > WATCH > OK.
#
# Design source of truth:
#   docs/design-docs/stack-control-platform-health.md
#
# Layout:
#   lib_dir = $(dirname $BASH_SOURCE)
#   lib_dir/platform_checks_common.sh   (any Linux)
#   lib_dir/platform_checks_wsl.sh      (loaded if WSL detected)
#   lib_dir/platform_checks_ubuntu.sh   (loaded if Ubuntu detected)
#   lib_dir/platform_checks_backend.sh  (Phase 6.c, requires backend)
#
# Usage from stack_control.sh:
#   source "${REPO_ROOT}/scripts/local/lib/platform_checks.sh"
#   platform_checks_run                  # prints all applicable sections
#
# Honour --no-platform by simply not calling platform_checks_run.

set -u  # unset-var safety; intentionally NOT -e so a single bad signal
        # does not blank the whole report.

_PLATFORM_CHECKS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Worst-case verdict aggregator. Mutates global _PLATFORM_VERDICT.
_PLATFORM_VERDICT="OK"
_platform_merge_verdict() {
  local incoming="${1:-OK}"
  case "$incoming" in
    CRIT) _PLATFORM_VERDICT="CRIT" ;;
    WARN)
      [[ "$_PLATFORM_VERDICT" == "CRIT" ]] || _PLATFORM_VERDICT="WARN"
      ;;
    WATCH)
      case "$_PLATFORM_VERDICT" in
        CRIT|WARN) ;;
        *) _PLATFORM_VERDICT="WATCH" ;;
      esac
      ;;
    OK|"") ;;
    *) ;;
  esac
}

# Run a single module file: source it inside a subshell-free block, call
# applicable, then display + verdict. Each module defines functions
# prefixed by an internal namespace so re-sourcing is safe.
_platform_run_module() {
  local module_name="$1"
  local module_path="${_PLATFORM_CHECKS_LIB_DIR}/platform_checks_${module_name}.sh"
  [[ -r "$module_path" ]] || return 0

  # Source in current shell so functions are reachable.
  # shellcheck disable=SC1090
  source "$module_path"

  # Each module exposes applicable_<name> / display_<name> / verdict_<name>
  # to avoid colliding when several modules are sourced.
  local apply_fn="applicable_${module_name}"
  local display_fn="display_${module_name}"
  local verdict_fn="verdict_${module_name}"

  if ! declare -F "$apply_fn" >/dev/null; then
    return 0
  fi
  "$apply_fn" || return 0

  "$display_fn"
  echo

  if declare -F "$verdict_fn" >/dev/null; then
    local v
    v="$("$verdict_fn" 2>/dev/null || echo OK)"
    _platform_merge_verdict "$v"
  fi
}

# Public entry point.
platform_checks_run() {
  if [[ ! -d /proc ]]; then
    echo "=== Platform Health ===                                 [unavailable: non-Linux host]"
    return 0
  fi

  # Save caller's errexit state and disable it while modules run — any
  # single grep/test returning non-zero inside a module must not kill
  # the whole sweep. `stack_control.sh` runs with `set -euo pipefail`,
  # so without this guard only the first module would be seen.
  local _prev_errexit="+e"
  case "$-" in *e*) _prev_errexit="-e" ;; esac
  set +e

  _PLATFORM_VERDICT="OK"

  # Always-loaded module name "common" => platform_checks_common.sh
  _platform_run_module common
  _platform_run_module wsl
  _platform_run_module ubuntu
  _platform_run_module backend
  _platform_run_module pool

  # Banner with rolled-up verdict — printed last because we don't know
  # the verdict until the modules have run. Mirror the layout the design
  # doc specified ("=== Platform Health === [verdict: WATCH]") by emitting
  # a final summary line.
  printf '=== Platform Health rollup ===   verdict: %s\n' "$_PLATFORM_VERDICT"

  # Restore the caller's errexit state.
  set "$_prev_errexit"
}

# JSON entry point (Phase 6.d). Emits a single-line JSON object:
#
#   {"verdict": "WARN",
#    "timestamp": "2026-04-23T19:45:12+00:00",
#    "modules": {"common": {...}, "wsl": {...}, "ubuntu": {...}, "backend": {...}}}
#
# Modules are included only when their applicable_<name> returns 0.
# The roll-up `verdict` is the worst module verdict, matching the
# semantics of the human-readable rollup line.
#
# This function is consumed by `stack_control.sh status --json` and is
# safe to call standalone (e.g. from heartbeat scripts) — it sets/restores
# errexit just like platform_checks_run.
platform_checks_json() {
  if [[ ! -d /proc ]]; then
    printf '{"verdict":"OK","timestamp":"%s","unavailable":"non-Linux host","modules":{}}' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    return 0
  fi

  local _prev_errexit="+e"
  case "$-" in *e*) _prev_errexit="-e" ;; esac
  set +e

  _PLATFORM_VERDICT="OK"

  local first=1
  local mods_payload=""

  _platform_emit_json() {
    local name="$1"
    local module_path="${_PLATFORM_CHECKS_LIB_DIR}/platform_checks_${name}.sh"
    [[ -r "$module_path" ]] || return 0
    # shellcheck disable=SC1090
    source "$module_path"

    local apply_fn="applicable_${name}"
    local json_fn="json_${name}"
    declare -F "$apply_fn" >/dev/null || return 0
    declare -F "$json_fn"  >/dev/null || return 0
    "$apply_fn" || return 0

    local body
    body=$("$json_fn" 2>/dev/null)
    [[ -n "$body" ]] || return 0

    if (( first )); then
      mods_payload="\"$name\":$body"
      first=0
    else
      mods_payload="$mods_payload,\"$name\":$body"
    fi

    # Each json_<name> embeds its own `"verdict":"X"` field. Pull it
    # back via cheap regex — `verdict_<name>` would not see the
    # mutation because command substitution above ran in a subshell.
    local v
    v=$(sed -n 's/.*"verdict":"\([A-Z]*\)".*/\1/p' <<<"$body" | head -1)
    [[ -n "$v" ]] && _platform_merge_verdict "$v"
  }

  _platform_emit_json common
  _platform_emit_json wsl
  _platform_emit_json ubuntu
  _platform_emit_json backend
  _platform_emit_json pool

  printf '{"verdict":"%s","timestamp":"%s","modules":{%s}}' \
    "$_PLATFORM_VERDICT" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$mods_payload"

  set "$_prev_errexit"
}

# Read-only accessor — `cmd_status --strict` calls this after
# platform_checks_run / _json to decide the exit code.
platform_checks_verdict() { echo "${_PLATFORM_VERDICT:-OK}"; }
