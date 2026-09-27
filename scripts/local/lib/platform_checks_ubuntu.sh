#!/usr/bin/env bash
# scripts/local/lib/platform_checks_ubuntu.sh
#
# Ubuntu-specific module. Detects via /etc/os-release ID=ubuntu.

_UBUNTU_VERDICT="OK"

_ubuntu_set_verdict() {
  case "$1" in
    CRIT) _UBUNTU_VERDICT="CRIT" ;;
    WARN)
      [[ "$_UBUNTU_VERDICT" == "CRIT" ]] || _UBUNTU_VERDICT="WARN"
      ;;
    WATCH)
      case "$_UBUNTU_VERDICT" in
        CRIT|WARN) ;;
        *) _UBUNTU_VERDICT="WATCH" ;;
      esac
      ;;
  esac
}

applicable_ubuntu() {
  [[ -r /etc/os-release ]] && grep -q '^ID=ubuntu' /etc/os-release
}

display_ubuntu() {
  local pretty version_id
  pretty=$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d'=' -f2- | tr -d '"')
  version_id=$(grep -E '^VERSION_ID=' /etc/os-release | cut -d'=' -f2- | tr -d '"')

  local journal_size="(unknown)"
  if command -v journalctl >/dev/null 2>&1; then
    journal_size=$(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9.]+[KMGT]?' | head -1)
    journal_size="${journal_size:-(empty)}"
  fi

  local sysctl_drop="missing"
  local sysctl_state="WATCH"
  if [[ -r /etc/sysctl.d/99-ii-agent.conf ]]; then
    sysctl_drop="present"
    sysctl_state="OK"
  fi
  _ubuntu_set_verdict "$sysctl_state"

  local reboot_required="no"
  if [[ -f /var/run/reboot-required ]]; then
    reboot_required="YES — kernel update pending"
    _ubuntu_set_verdict "WATCH"
  fi

  cat <<EOF
=== Ubuntu Release ===
  release:        ${pretty:-unknown} (VERSION_ID=${version_id:-?})
  journald usage: ${journal_size}
  sysctl drop-in: /etc/sysctl.d/99-ii-agent.conf  (${sysctl_drop}, ${sysctl_state})
  reboot needed:  ${reboot_required}
EOF
}

verdict_ubuntu() { echo "$_UBUNTU_VERDICT"; }

# JSON emitter (Phase 6.d). See platform_checks_common.sh::json_common
# for the contract.
json_ubuntu() {
  _UBUNTU_VERDICT="OK"
  local pretty version_id
  pretty=$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d'=' -f2- | tr -d '"')
  version_id=$(grep -E '^VERSION_ID=' /etc/os-release | cut -d'=' -f2- | tr -d '"')

  local journal_bytes="null"
  if command -v journalctl >/dev/null 2>&1; then
    # journalctl --disk-usage prints e.g. "Archived and active journals take up 80.0M in the file system."
    local raw
    raw=$(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9.]+[KMGT]?' | head -1)
    if [[ -n "$raw" ]]; then
      journal_bytes=$(awk -v v="$raw" 'BEGIN{
        n=v; u="B";
        if (match(v,/[KMGT]/)){u=substr(v,RSTART,1); n=substr(v,1,RSTART-1)}
        mult = (u=="K"?1024 : u=="M"?1048576 : u=="G"?1073741824 : u=="T"?1099511627776 : 1)
        printf "%d", n*mult
      }')
    fi
  fi

  local sysctl_present=false sysctl_state="WATCH"
  if [[ -r /etc/sysctl.d/99-ii-agent.conf ]]; then
    sysctl_present=true; sysctl_state="OK"
  fi
  _ubuntu_set_verdict "$sysctl_state"

  local reboot_required=false
  if [[ -f /var/run/reboot-required ]]; then
    reboot_required=true
    _ubuntu_set_verdict "WATCH"
  fi

  printf '{"verdict":"%s","release":"%s","version_id":"%s","journald_bytes":%s,"sysctl_drop_in_present":%s,"reboot_required":%s}' \
    "$_UBUNTU_VERDICT" "${pretty:-unknown}" "${version_id:-?}" "$journal_bytes" "$sysctl_present" "$reboot_required"
}
