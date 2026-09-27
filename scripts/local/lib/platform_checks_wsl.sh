#!/usr/bin/env bash
# scripts/local/lib/platform_checks_wsl.sh
#
# WSL2-specific module. Detects via /proc/version containing "microsoft"
# or the presence of /proc/sys/fs/binfmt_misc/WSLInterop. Both cheap.

PROC_ROOT_WSL="${PLATFORM_CHECKS_PROC:-/proc}"
_WSL_VERDICT="OK"

_wsl_set_verdict() {
  case "$1" in
    CRIT) _WSL_VERDICT="CRIT" ;;
    WARN)
      [[ "$_WSL_VERDICT" == "CRIT" ]] || _WSL_VERDICT="WARN"
      ;;
    WATCH)
      case "$_WSL_VERDICT" in
        CRIT|WARN) ;;
        *) _WSL_VERDICT="WATCH" ;;
      esac
      ;;
  esac
}

applicable_wsl() {
  if [[ -r "${PROC_ROOT_WSL}/version" ]] && grep -qi "microsoft" "${PROC_ROOT_WSL}/version"; then
    return 0
  fi
  [[ -e "${PROC_ROOT_WSL}/sys/fs/binfmt_misc/WSLInterop" ]]
}

_wsl_sysctl() {
  local key="$1"
  local path="${PROC_ROOT_WSL}/sys/$(echo "$key" | tr . /)"
  [[ -r "$path" ]] && cat "$path" || echo "?"
}

# Resolve the Windows-side %USERPROFILE%\.wslconfig path. Cached in
# _WSL_HOST_CONFIG_RESOLVED to keep cmd.exe spawns to one per run.
# Falls back gracefully when interop is disabled, cmd.exe is missing,
# or the resolved path isn't mounted into WSL.
#
# Honours an override env var WSL_HOST_CONFIG_PATH so CI / tests can
# point at a fixture file without invoking cmd.exe.
_WSL_HOST_CONFIG_RESOLVED=""
_WSL_HOST_CONFIG_DONE=""
_wsl_host_config_path() {
  if [[ -n "$_WSL_HOST_CONFIG_DONE" ]]; then
    echo "$_WSL_HOST_CONFIG_RESOLVED"
    return 0
  fi
  _WSL_HOST_CONFIG_DONE=1

  if [[ -n "${WSL_HOST_CONFIG_PATH:-}" ]]; then
    _WSL_HOST_CONFIG_RESOLVED="$WSL_HOST_CONFIG_PATH"
    echo "$_WSL_HOST_CONFIG_RESOLVED"
    return 0
  fi

  command -v cmd.exe >/dev/null 2>&1 || { echo ""; return 0; }

  local userprofile
  # cd /tmp avoids the noisy "UNC paths are not supported" warning when
  # cmd.exe is invoked from a /mnt/* working directory.
  userprofile=$(cd /tmp 2>/dev/null && cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r\n')
  [[ -n "$userprofile" ]] || { echo ""; return 0; }

  # Translate "C:\Users\Foo Bar" -> "/mnt/c/Users/Foo Bar/.wslconfig".
  # Drive letter lowercased, backslashes flipped, no shell-quoting needed
  # because we never pass it to a subshell as code.
  local drive rest
  drive=$(printf '%s' "$userprofile" | cut -c1 | tr 'A-Z' 'a-z')
  rest=$(printf '%s' "$userprofile" | cut -c3- | tr '\\' '/')
  _WSL_HOST_CONFIG_RESOLVED="/mnt/${drive}${rest}/.wslconfig"
  echo "$_WSL_HOST_CONFIG_RESOLVED"
}

# Read a single key from the Windows-side .wslconfig. Trims surrounding
# whitespace; returns empty string when the key is absent or the file is
# unreadable.
_wsl_host_config_get() {
  local key="$1" path="$2"
  [[ -r "$path" ]] || { echo ""; return 0; }
  awk -F= -v k="$key" '
    /^[[:space:]]*[#;]/ { next }
    {
      sub(/^[[:space:]]+/, "", $1); sub(/[[:space:]]+$/, "", $1)
      if ($1 == k) {
        sub(/^[^=]*=/, "")
        sub(/^[[:space:]]+/, ""); sub(/[[:space:]]+$/, "")
        print
        exit
      }
    }
  ' "$path"
}

display_wsl() {
  local kernel
  kernel=$(awk '{print $3}' "${PROC_ROOT_WSL}/version" 2>/dev/null)

  local cp mfk swp swp_state="OK" cp_state="OK" mfk_state="OK"
  cp=$(_wsl_sysctl vm.compaction_proactiveness)
  mfk=$(_wsl_sysctl vm.min_free_kbytes)
  swp=$(_wsl_sysctl vm.swappiness)

  # Phase 4 targets
  if [[ "$cp" =~ ^[0-9]+$ ]] && (( cp < 30 )); then cp_state="WATCH"; fi
  if [[ "$mfk" =~ ^[0-9]+$ ]] && (( mfk < 262144 )); then mfk_state="WATCH"; fi
  if [[ "$swp" =~ ^[0-9]+$ ]] && (( swp > 30 )); then swp_state="WATCH"; fi
  _wsl_set_verdict "$cp_state"
  _wsl_set_verdict "$mfk_state"
  _wsl_set_verdict "$swp_state"

  # Optional /etc/wsl.conf snippet — purely informational.
  # NOTE: /etc/wsl.conf is the *distro-side* config (automount, boot,
  # user). The Windows-host VM tuning ([wsl2] keys: memory, swap,
  # processors, …) lives in %USERPROFILE%\.wslconfig and is surfaced
  # separately below.
  local wslconf_excerpt="(none)"
  if [[ -r /etc/wsl.conf ]]; then
    wslconf_excerpt=$(grep -E '^\s*(automount|boot|user|network|interop)' /etc/wsl.conf 2>/dev/null | tr '\n' ' ')
    [[ -z "$wslconf_excerpt" ]] && wslconf_excerpt="(no distro-side keys set)"
  fi

  # Windows-host .wslconfig — the file that actually controls VM-level
  # memory, swap, processor count, and disk-backing. Best-effort:
  # absence is informational, not a degradation.
  local hostconf_path hostconf_line="(unresolved)"
  hostconf_path=$(_wsl_host_config_path)
  if [[ -n "$hostconf_path" ]]; then
    if [[ -r "$hostconf_path" ]]; then
      local hc_mem hc_swap hc_swapfile hc_proc hc_amr hc_sparse hc_net
      hc_mem=$(_wsl_host_config_get memory "$hostconf_path")
      hc_swap=$(_wsl_host_config_get swap "$hostconf_path")
      hc_swapfile=$(_wsl_host_config_get swapFile "$hostconf_path")
      hc_proc=$(_wsl_host_config_get processors "$hostconf_path")
      hc_amr=$(_wsl_host_config_get autoMemoryReclaim "$hostconf_path")
      hc_sparse=$(_wsl_host_config_get sparseVhd "$hostconf_path")
      hc_net=$(_wsl_host_config_get networkingMode "$hostconf_path")
      local parts=()
      [[ -n "$hc_mem"      ]] && parts+=("memory=${hc_mem}")
      [[ -n "$hc_proc"     ]] && parts+=("processors=${hc_proc}")
      [[ -n "$hc_swap"     ]] && parts+=("swap=${hc_swap}")
      [[ -n "$hc_swapfile" ]] && parts+=("swapFile=${hc_swapfile}")
      [[ -n "$hc_amr"      ]] && parts+=("autoMemoryReclaim=${hc_amr}")
      [[ -n "$hc_sparse"   ]] && parts+=("sparseVhd=${hc_sparse}")
      [[ -n "$hc_net"      ]] && parts+=("networkingMode=${hc_net}")
      if (( ${#parts[@]} == 0 )); then
        hostconf_line="${hostconf_path} (present, no [wsl2] keys)"
      else
        hostconf_line="${hostconf_path}  ${parts[*]}"
      fi
      # WATCH if memory unset on this host — the VM would default to
      # 50% of host RAM which has historically thrashed the buddy
      # allocator on bigger machines. Pure heuristic; never escalates
      # past WATCH.
      if [[ -z "$hc_mem" ]]; then _wsl_set_verdict "WATCH"; fi
    else
      hostconf_line="${hostconf_path} (not readable)"
    fi
  fi

  cat <<EOF
=== WSL2 Host ===
  kernel:        ${kernel:-unknown}
  vm tuning:     compaction_proactiveness=${cp} (${cp_state})  min_free_kbytes=${mfk} (${mfk_state})  swappiness=${swp} (${swp_state})
  /etc/wsl.conf: ${wslconf_excerpt}
  host .wslconfig: ${hostconf_line}
EOF
}

verdict_wsl() { echo "$_WSL_VERDICT"; }

# JSON emitter (Phase 6.d). See platform_checks_common.sh::json_common
# for the contract.
json_wsl() {
  _WSL_VERDICT="OK"
  local kernel cp mfk swp
  kernel=$(awk '{print $3}' "${PROC_ROOT_WSL}/version" 2>/dev/null)
  cp=$(_wsl_sysctl vm.compaction_proactiveness)
  mfk=$(_wsl_sysctl vm.min_free_kbytes)
  swp=$(_wsl_sysctl vm.swappiness)
  if [[ "$cp" =~ ^[0-9]+$ ]] && (( cp < 30 )); then _wsl_set_verdict "WATCH"; fi
  if [[ "$mfk" =~ ^[0-9]+$ ]] && (( mfk < 262144 )); then _wsl_set_verdict "WATCH"; fi
  if [[ "$swp" =~ ^[0-9]+$ ]] && (( swp > 30 )); then _wsl_set_verdict "WATCH"; fi

  # Numeric-or-null normaliser for sysctl fields that may read "?".
  local cp_j="${cp}" mfk_j="${mfk}" swp_j="${swp}"
  [[ "$cp_j"  =~ ^[0-9]+$ ]] || cp_j="null"
  [[ "$mfk_j" =~ ^[0-9]+$ ]] || mfk_j="null"
  [[ "$swp_j" =~ ^[0-9]+$ ]] || swp_j="null"

  # Windows-host .wslconfig surface. Always emitted as a sub-object so
  # downstream consumers can detect "interop unavailable" (path:null) vs
  # "file missing" (present:false) vs "file present but no [wsl2] keys"
  # (memory:null & swap:null).
  local hc_path hc_present="false"
  hc_path=$(_wsl_host_config_path)
  local hc_mem="" hc_swap="" hc_swapfile="" hc_proc="" hc_amr="" hc_sparse="" hc_net=""
  if [[ -n "$hc_path" && -r "$hc_path" ]]; then
    hc_present="true"
    hc_mem=$(_wsl_host_config_get memory "$hc_path")
    hc_swap=$(_wsl_host_config_get swap "$hc_path")
    hc_swapfile=$(_wsl_host_config_get swapFile "$hc_path")
    hc_proc=$(_wsl_host_config_get processors "$hc_path")
    hc_amr=$(_wsl_host_config_get autoMemoryReclaim "$hc_path")
    hc_sparse=$(_wsl_host_config_get sparseVhd "$hc_path")
    hc_net=$(_wsl_host_config_get networkingMode "$hc_path")
    [[ -z "$hc_mem" ]] && _wsl_set_verdict "WATCH"
  fi

  # Helpers: emit JSON string-or-null. Backslashes in swapFile values
  # need escaping so the JSON parses cleanly.
  _json_str_or_null() {
    if [[ -z "$1" ]]; then printf 'null'
    else printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    fi
  }

  local path_j present_j
  path_j=$(_json_str_or_null "$hc_path")
  present_j="$hc_present"

  printf '{"verdict":"%s","kernel":"%s","compaction_proactiveness":%s,"min_free_kbytes":%s,"swappiness":%s,"host_config":{"path":%s,"present":%s,"memory":%s,"processors":%s,"swap":%s,"swap_file":%s,"auto_memory_reclaim":%s,"sparse_vhd":%s,"networking_mode":%s}}' \
    "$_WSL_VERDICT" "${kernel:-unknown}" "$cp_j" "$mfk_j" "$swp_j" \
    "$path_j" "$present_j" \
    "$(_json_str_or_null "$hc_mem")" \
    "$(_json_str_or_null "$hc_proc")" \
    "$(_json_str_or_null "$hc_swap")" \
    "$(_json_str_or_null "$hc_swapfile")" \
    "$(_json_str_or_null "$hc_amr")" \
    "$(_json_str_or_null "$hc_sparse")" \
    "$(_json_str_or_null "$hc_net")"
}
