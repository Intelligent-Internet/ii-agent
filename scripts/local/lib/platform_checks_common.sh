#!/usr/bin/env bash
# scripts/local/lib/platform_checks_common.sh
#
# Any-Linux signals: load avg, memory, /proc/buddyinfo high-order
# fragmentation, compaction failures, swap, root disk + inodes.
# Backend-independent: only reads /proc + /etc + invokes df / awk.
#
# Conservative hardcoded floors. The backend's percentile-baseline
# evaluator (Phase 2) is strictly tighter on a per-host basis.
#
# Override `/proc` root via PLATFORM_CHECKS_PROC (used by tests).

PROC_ROOT_COMMON="${PLATFORM_CHECKS_PROC:-/proc}"
_COMMON_VERDICT="OK"

_common_set_verdict() {
  local v="$1"
  case "$v" in
    CRIT) _COMMON_VERDICT="CRIT" ;;
    WARN)
      [[ "$_COMMON_VERDICT" == "CRIT" ]] || _COMMON_VERDICT="WARN"
      ;;
    WATCH)
      case "$_COMMON_VERDICT" in
        CRIT|WARN) ;;
        *) _COMMON_VERDICT="WATCH" ;;
      esac
      ;;
  esac
}

applicable_common() { [[ -d "$PROC_ROOT_COMMON" ]]; }

# --- meminfo helper ----------------------------------------------------------
_common_meminfo_kb() {
  awk -v key="$1:" '$1==key {print $2}' "${PROC_ROOT_COMMON}/meminfo"
}

# --- buddyinfo helper -------------------------------------------------------
# Returns three numbers: total_blocks_at_orders_4_plus, ratio_vs_order0_int,
# raw "order7=N order8=N order9=N order10=N" string for display.
_common_buddyinfo_normal() {
  local bf="${PROC_ROOT_COMMON}/buddyinfo"
  [[ -r "$bf" ]] || { echo "0 0 unavailable"; return 0; }
  awk '
    $4 == "Normal" {
      # fields 5..end are free-block counts at orders 0..N
      total = 0; high = 0; o0 = $5
      for (i = 5; i <= NF; i++) {
        ord = i - 5
        total += $i
        if (ord >= 4) high += $i
      }
      o7 = ($12 == "" ? 0 : $12)
      o8 = ($13 == "" ? 0 : $13)
      o9 = ($14 == "" ? 0 : $14)
      o10 = ($15 == "" ? 0 : $15)
      ratio_int = (o0 > 0 ? int(1000 * high / o0) / 1000 : 0)
      printf "%d %.3f order-7=%d order-8=%d order-9=%d order-10=%d\n", \
        high, ratio_int, o7, o8, o9, o10
      exit
    }
  ' "$bf"
}

# --- vmstat rate helper -----------------------------------------------------
# Reads two integer keys from /proc/vmstat and returns "compact_fail allocstall"
_common_vmstat() {
  local vf="${PROC_ROOT_COMMON}/vmstat"
  [[ -r "$vf" ]] || { echo "0 0"; return 0; }
  local cf as
  cf=$(awk '$1=="compact_fail" {print $2}' "$vf")
  as=$(awk '$1=="allocstall_normal" {print $2}' "$vf")
  echo "${cf:-0} ${as:-0}"
}

display_common() {
  local mem_total mem_avail swap_total swap_free
  mem_total=$(_common_meminfo_kb MemTotal)
  mem_avail=$(_common_meminfo_kb MemAvailable)
  swap_total=$(_common_meminfo_kb SwapTotal)
  swap_free=$(_common_meminfo_kb SwapFree)

  local mem_total_gb mem_avail_gb mem_pct
  mem_total_gb=$(awk -v k="$mem_total" 'BEGIN{printf "%.1f", k/1024/1024}')
  mem_avail_gb=$(awk -v k="$mem_avail" 'BEGIN{printf "%.1f", k/1024/1024}')
  mem_pct=$(awk -v a="$mem_avail" -v t="$mem_total" 'BEGIN{ if(t==0){print 0}else{printf "%d", 100*a/t} }')

  local mem_state="OK"
  if   (( mem_pct < 5  )); then mem_state="CRIT"
  elif (( mem_pct < 10 )); then mem_state="WARN"
  elif (( mem_pct < 20 )); then mem_state="WATCH"
  fi
  _common_set_verdict "$mem_state"

  local swap_used_gb swap_total_gb swap_pct swap_state="OK"
  swap_used_gb=$(awk -v t="$swap_total" -v f="$swap_free" 'BEGIN{printf "%.1f",(t-f)/1024/1024}')
  swap_total_gb=$(awk -v t="$swap_total" 'BEGIN{printf "%.1f", t/1024/1024}')
  swap_pct=$(awk -v t="$swap_total" -v f="$swap_free" 'BEGIN{ if(t==0){print 0}else{printf "%d", 100*(t-f)/t} }')
  if   (( swap_pct > 50 )); then swap_state="WARN"
  elif (( swap_pct > 25 )); then swap_state="WATCH"
  fi
  _common_set_verdict "$swap_state"

  # Load
  local load la1 la5 la15 ncpu load_factor load_state="OK"
  read -r la1 la5 la15 _ < "${PROC_ROOT_COMMON}/loadavg" 2>/dev/null
  ncpu=$(grep -c '^processor' "${PROC_ROOT_COMMON}/cpuinfo" 2>/dev/null || echo 1)
  load_factor=$(awk -v l="$la15" -v c="$ncpu" 'BEGIN{ if(c==0){print 0}else{printf "%.2f", l/c} }')
  if awk -v lf="$load_factor" 'BEGIN{exit !(lf>=2.0)}'; then load_state="WARN"
  elif awk -v lf="$load_factor" 'BEGIN{exit !(lf>=1.5)}'; then load_state="WATCH"
  fi
  _common_set_verdict "$load_state"

  # Buddyinfo
  local bi high_blocks ratio bi_summary frag_state="OK"
  bi=$(_common_buddyinfo_normal)
  high_blocks=$(awk '{print $1}' <<<"$bi")
  ratio=$(awk '{print $2}' <<<"$bi")
  bi_summary=$(awk '{$1=$2=""; sub(/^  +/,""); print}' <<<"$bi")
  if [[ "$bi_summary" == "unavailable" ]]; then
    frag_state="OK"
  else
    # Order-7 floor: 0 == CRIT, 1-2 == WARN, 3-5 == WATCH
    local o7
    o7=$(awk -F= '/order-7/ {print $2; exit}' <<<"$(echo "$bi_summary" | tr ' ' '\n')")
    o7="${o7:-0}"
    if   (( o7 == 0 )); then frag_state="CRIT"
    elif (( o7 <= 2 )); then frag_state="WARN"
    elif (( o7 <= 5 )); then frag_state="WATCH"
    fi
  fi
  _common_set_verdict "$frag_state"

  # vmstat rates (instantaneous values for now; rate-of-change would need
  # a small state file in $TMPDIR — deferred until 6.d)
  local vmstats compact_fail allocstall
  vmstats=$(_common_vmstat)
  compact_fail=$(awk '{print $1}' <<<"$vmstats")
  allocstall=$(awk '{print $2}' <<<"$vmstats")

  # Disk + inodes
  local disk_used disk_state="OK" inode_used inode_state="OK"
  disk_used=$(df --output=pcent / 2>/dev/null | tail -1 | tr -d ' %')
  inode_used=$(df --output=ipcent / 2>/dev/null | tail -1 | tr -d ' %')
  disk_used="${disk_used:-0}"
  inode_used="${inode_used:-0}"
  if   (( disk_used > 95 )); then disk_state="CRIT"
  elif (( disk_used > 85 )); then disk_state="WARN"
  fi
  if   (( inode_used > 85 )); then inode_state="WARN"; fi
  _common_set_verdict "$disk_state"
  _common_set_verdict "$inode_state"

  cat <<EOF
=== Platform Health ===
  uptime:        $(awk '{printf "%dd %dh %dm", $1/86400, ($1%86400)/3600, ($1%3600)/60}' "${PROC_ROOT_COMMON}/uptime" 2>/dev/null) load 1/5/15: ${la1:-?} / ${la5:-?} / ${la15:-?}
  cpu:           ${ncpu} vCPU  load_factor_15m: ${load_factor} (${load_state})
  memory:        ${mem_avail_gb}G available / ${mem_total_gb}G total  (${mem_pct}% free, ${mem_state})
                 swap ${swap_used_gb}G / ${swap_total_gb}G  (${swap_pct}% used, ${swap_state})
  fragmentation: order-4+ free: ${high_blocks} blocks  (${frag_state})
                 ${bi_summary}
                 compact_fail: ${compact_fail}  allocstall_normal: ${allocstall}
  disk:          root ${disk_used}% used (${disk_state})  inodes ${inode_used}% used (${inode_state})
EOF
}

verdict_common() { echo "$_COMMON_VERDICT"; }

# JSON emitter (Phase 6.d). Re-reads /proc so it can be called
# independently of display_common; cheap because /proc reads are
# in-kernel. Emits one JSON object with no surrounding whitespace.
# Side effect: updates _COMMON_VERDICT so the dispatcher sees the
# right verdict even when only json_* runs.
json_common() {
  # Reset and recompute. display_common may have already populated
  # _COMMON_VERDICT in mixed mode; that's fine since we'll just
  # recompute the same value.
  _COMMON_VERDICT="OK"

  local mem_total mem_avail swap_total swap_free
  mem_total=$(_common_meminfo_kb MemTotal)
  mem_avail=$(_common_meminfo_kb MemAvailable)
  swap_total=$(_common_meminfo_kb SwapTotal)
  swap_free=$(_common_meminfo_kb SwapFree)
  local mem_pct
  mem_pct=$(awk -v a="$mem_avail" -v t="$mem_total" 'BEGIN{ if(t==0){print 0}else{printf "%d", 100*a/t} }')
  local mem_state="OK"
  if   (( mem_pct < 5  )); then mem_state="CRIT"
  elif (( mem_pct < 10 )); then mem_state="WARN"
  elif (( mem_pct < 20 )); then mem_state="WATCH"
  fi
  _common_set_verdict "$mem_state"

  local swap_pct=0
  if (( swap_total > 0 )); then
    swap_pct=$(awk -v t="$swap_total" -v f="$swap_free" 'BEGIN{printf "%d", 100*(t-f)/t}')
  fi

  local la1 la5 la15 ncpu load_factor
  read -r la1 la5 la15 _ < "${PROC_ROOT_COMMON}/loadavg" 2>/dev/null
  ncpu=$(grep -c '^processor' "${PROC_ROOT_COMMON}/cpuinfo" 2>/dev/null || echo 1)
  load_factor=$(awk -v l="$la15" -v c="$ncpu" 'BEGIN{ if(c==0){print 0}else{printf "%.2f", l/c} }')
  if awk -v lf="$load_factor" 'BEGIN{exit !(lf>=2.0)}'; then _common_set_verdict "WARN"
  elif awk -v lf="$load_factor" 'BEGIN{exit !(lf>=1.5)}'; then _common_set_verdict "WATCH"
  fi

  local bi high_blocks o7=0 o8=0 o9=0 o10=0
  bi=$(_common_buddyinfo_normal)
  high_blocks=$(awk '{print $1}' <<<"$bi")
  if [[ "$bi" != "0 0 unavailable" ]]; then
    o7=$(awk -F= '/order-7/ {print $2}' <<<"$(echo "$bi" | tr ' ' '\n')")
    o8=$(awk -F= '/order-8/ {print $2}' <<<"$(echo "$bi" | tr ' ' '\n')")
    o9=$(awk -F= '/order-9/ {print $2}' <<<"$(echo "$bi" | tr ' ' '\n')")
    o10=$(awk -F= '/order-10/ {print $2}' <<<"$(echo "$bi" | tr ' ' '\n')")
    o7="${o7:-0}"; o8="${o8:-0}"; o9="${o9:-0}"; o10="${o10:-0}"
    if   (( o7 == 0 )); then _common_set_verdict "CRIT"
    elif (( o7 <= 2 )); then _common_set_verdict "WARN"
    elif (( o7 <= 5 )); then _common_set_verdict "WATCH"
    fi
  fi

  local vmstats compact_fail allocstall
  vmstats=$(_common_vmstat)
  compact_fail=$(awk '{print $1}' <<<"$vmstats")
  allocstall=$(awk '{print $2}' <<<"$vmstats")

  local disk_used inode_used
  disk_used=$(df --output=pcent / 2>/dev/null | tail -1 | tr -d ' %')
  inode_used=$(df --output=ipcent / 2>/dev/null | tail -1 | tr -d ' %')
  disk_used="${disk_used:-0}"
  inode_used="${inode_used:-0}"
  if   (( disk_used > 95 )); then _common_set_verdict "CRIT"
  elif (( disk_used > 85 )); then _common_set_verdict "WARN"
  fi
  if   (( inode_used > 85 )); then _common_set_verdict "WARN"; fi

  printf '{"verdict":"%s","load_1m":%s,"load_5m":%s,"load_15m":%s,"ncpu":%s,"load_factor_15m":%s,"mem_available_kb":%s,"mem_total_kb":%s,"mem_available_pct":%s,"swap_used_pct":%s,"buddy_normal_high_blocks":%s,"order7_free":%s,"order8_free":%s,"order9_free":%s,"order10_free":%s,"compact_fail_total":%s,"allocstall_normal_total":%s,"disk_root_pct":%s,"inodes_root_pct":%s}' \
    "$_COMMON_VERDICT" "${la1:-0}" "${la5:-0}" "${la15:-0}" "${ncpu:-1}" "${load_factor:-0}" \
    "${mem_avail:-0}" "${mem_total:-0}" "${mem_pct:-0}" "${swap_pct:-0}" \
    "${high_blocks:-0}" "${o7:-0}" "${o8:-0}" "${o9:-0}" "${o10:-0}" \
    "${compact_fail:-0}" "${allocstall:-0}" \
    "${disk_used:-0}" "${inode_used:-0}"
}
