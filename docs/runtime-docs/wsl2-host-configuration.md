# WSL2 Host Configuration for ii-agent

**Purpose:** Document the `.wslconfig` settings and host-kernel tuning used on the development machine, why each setting is there, and how to recover if the host becomes unresponsive.

**Scope:** WSL2 guest-side and Windows-host-side configuration only. Docker network topology is covered in [sandbox-networking-design.md](sandbox-networking-design.md). Runtime monitoring is in [host-resource-monitoring.md](host-resource-monitoring.md).

**Last reviewed:** 2026-04-23 (memory bump to 45 GB; see Change log).

---

## Host profile

| Property | Value |
|---|---|
| Host OS | Windows 11 (WSL2 via Hyper-V) |
| Host CPU | 16 logical processors |
| Host RAM | **64 GB** |
| System SSD (C:) | **NOT** where WSL lives. Moved after a prior crash. |
| WSL storage (ext4.vhdx) | Drive G: — non-backed-up HDD, 100% utilisation under load |
| WSL swap | Drive G: — same HDD |
| WSL distro | Ubuntu 22.04, kernel 6.6.87.2-microsoft-standard-WSL2 |

Operational constraint: **drive G: I/O is the floor.** When the HDD is saturated (which it always is during heavy stack activity), swap performance is catastrophic. This makes *preventing swap* more important than it would be on an SSD host. Settings below reflect that.

## Current `.wslconfig`

Located at `C:\Users\Myles Dear\.wslconfig`. Take effect after `wsl --shutdown` and a subsequent WSL launch. Always back up before editing.

**Live contents on disk (2026-04-23):**

```ini
[wsl2]
# Store swap on G: drive, not C:
swap=16GB
swapFile=G:\\WSL\\swap.vhdx
# Memory limit raised 2026-04-23: 64 GB host, leave ~19 GB for Windows.
# Helps Docker --no-cache builds avoid swap thrashing.
memory=45GB
```

The richer config block below (kernel command line, memory reclaim, sparse VHDX,
explicit `processors=`) is the **target** state and is recommended on this host.
Keys not present in the live file fall back to WSL2 defaults.

**Recommended full config (target state):**

```ini
[wsl2]
# --- Resource allocation ---
# Host has 64 GB. Leave ~19 GB for Windows + page cache + Hyper-V overhead.
# WSL at 32 GB on a 64 GB host left Docker --no-cache builds thrashing into
# swap; 45 GB eliminated that without starving the Windows side.
memory=45GB
# Reserve 4 vCPUs for Windows. 4 is the minimum for a responsive desktop
# with AV + Explorer + browser + Teams during a Docker storm.
processors=12

# --- Swap ---
# 16 GB on G: HDD. Slow but exists. Goal is to never actually swap
# (see vm.swappiness tuning below).
swap=16GB
swapFile=G:\\WSL\\swap.vhdx

# --- Kernel command line ---
# transparent_hugepage=madvise: stops the kernel from handing out 2 MB
#   hugepages opportunistically. Under Docker workloads, THP-always caused
#   more fragmentation than it saved in TLB pressure. `madvise` means only
#   apps that ask (via madvise(MADV_HUGEPAGE)) get them.
# cgroup_enable=memory: required for Docker memory limits to be honoured.
kernelCommandLine=transparent_hugepage=madvise cgroup_enable=memory

# --- Memory reclaim ---
# gradual: the guest returns freed memory to the host slowly. Alternatives
#   are `dropcache` (aggressive, hits page cache hard and causes re-read
#   storms on the slow G: drive) and `disabled` (VHDX grows unboundedly).
autoMemoryReclaim=gradual

# --- Sparse VHDX ---
# Allows the ext4.vhdx to shrink when files are deleted. Without this the
# VHDX only grows and G: eventually fills. Essential given G: is tight.
sparseVhd=true
```

### Why these numbers

| Setting | Old | New | Rationale |
|---|---|---|---|
| `memory` | 32 GB (half of 64 GB host) | **45 GB** (2026-04-23) | At 32 GB, `--no-cache` backend rebuilds thrashed into swap and ran 45+ min. 45 GB leaves ~19 GB for Windows + Hyper-V overhead, which is sufficient on this user's workload (no heavy concurrent Windows apps). |
| `processors` | unset (= 16) | **12** | Reserve 4 vCPUs for Windows. 4 is the minimum for a responsive desktop with AV + Explorer + browser + Teams during a Docker storm. 2 is too few (verified by prior experience). |
| `kernelCommandLine` | (default) | `transparent_hugepage=madvise cgroup_enable=memory` | Reduces fragmentation pressure; ensures cgroup v1 memory accounting still works for older Docker paths. |
| `autoMemoryReclaim` | (unset, = disabled) | **gradual** | VHDX was growing without bound; reclaim keeps it in check without the page-cache-evict storm that `dropcache` causes on slow disk. |
| `sparseVhd` | (unset) | **true** | Needed because G: is the bottleneck; we want freed space to actually return. |

### Change log

| Date | Change | Reason |
|---|---|---|
| 2026-04-23 | `memory` 32 GB → **45 GB** | Host has 64 GB; previous 32 GB cap caused `docker compose build --no-cache backend` to swap-thrash for 45+ minutes. New cap leaves ~19 GB for Windows. Requires `wsl --shutdown` from PowerShell to take effect. |

## Host-kernel tuning inside the WSL guest

Applied via `/etc/sysctl.d/99-ii-agent.conf` on the Ubuntu side. Take effect after `sudo sysctl --system`.

```conf
# --- Memory headroom ---
# Default was 45 MB on a 32 GB guest — lethal for Docker veth/bridge
# allocations which need contiguous high-order pages. 256 MB is the
# standard recommendation for servers running container workloads.
vm.min_free_kbytes = 262144

# --- Compaction ---
# Allow kernel to compact even unevictable pages when high-order
# allocations are under pressure. Prevents the "no 2 MB block available
# anywhere" kernel errors we saw on 2026-04-23.
vm.compact_unevictable_allowed = 1

# Raise proactive (background) compaction intensity.  Kernel default is
# 20; setting 50 makes the kernel compact more aggressively during idle
# moments so high-order allocations (veth, bridge, docker) are more
# likely to succeed without stalling.  Host-side only: the backend
# container cannot write compact_memory itself (procfs mounted ro), and
# we explicitly chose kernel-managed compaction over user-space
# triggering.  Range 0–100; above ~80 wastes CPU on healthy systems.
vm.compaction_proactiveness = 50

# --- Swappiness ---
# G: is a non-backed-up HDD that runs at 100% util during stack activity.
# Actually swapping = catastrophe. Set low to strongly prefer dropping
# page cache over swapping anonymous pages.
vm.swappiness = 10

# --- Dirty page flushing ---
# Smaller dirty ratio reduces the size of fsync stalls when they happen
# on slow disk. Stack processes that write (minio, postgres) will feel
# more consistent latency.
vm.dirty_background_ratio = 5
vm.dirty_ratio = 15
```

Verification:

```bash
sudo sysctl -p /etc/sysctl.d/99-ii-agent.conf
cat /proc/sys/vm/min_free_kbytes      # expect 262144
cat /proc/sys/vm/swappiness           # expect 10
```

## Applying the changes

1. Back up existing `.wslconfig`: `copy "%UserProfile%\.wslconfig" "%UserProfile%\.wslconfig.backup.<date>"`.
2. Edit `.wslconfig` to match the block above.
3. From PowerShell: `wsl --shutdown`.
4. Start WSL again (open a terminal, or `wsl -d Ubuntu-22.04`).
5. Install the sysctl file: `sudo cp /home/mdear/workspaces/git/ii-agent/scripts/99-ii-agent.conf /etc/sysctl.d/99-ii-agent.conf && sudo sysctl --system`.
6. Validate with the verification commands above.
7. Bring the stack back up: `./scripts/stack_control.sh --local up`.

## Rollback

If anything misbehaves:

1. Restore the backup `.wslconfig`.
2. `sudo rm /etc/sysctl.d/99-ii-agent.conf && sudo sysctl --system`.
3. `wsl --shutdown` from PowerShell.
4. Next WSL start will use defaults.

## Disaster recovery for WSL

Use these procedures **only** when the host is already unresponsive or has been force-rebooted.

### Stack is sluggish, but host is still responsive

1. Check `/proc/buddyinfo` Normal zone — if orders 6–8 are all near zero, kernel is fragmented.
2. Proactive compaction (cheap, safe): `sudo bash -c 'echo 1 > /proc/sys/vm/compact_memory'`. Takes ~100–500 ms.
3. Monitor `/proc/vmstat | grep -E "compact_|allocstall"` — if `compact_fail` keeps rising after compaction, move to step 4.
4. Evaluate `docker ps -q | wc -l`. If > 15 sandboxes exist, trigger orphan cleanup via backend API or wait 60 s for the cron sweep.

### Drop page cache (emergency only, **not automatic**)

**Do NOT run this during normal operation.** It causes the kernel to evict clean page cache, forcing all subsequent reads (including Docker image layers, Postgres data pages, application binaries) back from disk. On G: drive this is minutes of latency spike. Only use when:

- `/proc/buddyinfo` shows order ≥ 7 is zero.
- `compact_memory` has been tried and failed.
- Docker API calls are already timing out.
- You would otherwise have to reboot.

```bash
# Synchronise dirty pages first so we don't lose writes
sync
# Then drop caches (3 = pagecache + dentries + inodes)
sudo bash -c 'echo 3 > /proc/sys/vm/drop_caches'
```

Expect 30–90 s of sluggishness after this as hot paths re-populate cache. The backend should survive it because Docker calls are now bounded by the 8 s `docker_call` timeout.

### Host is unresponsive (no terminal input)

If even `sudo` won't execute, WSL2 has lost scheduling. From a Windows PowerShell:

1. `wsl --list --running` — see which distros are alive.
2. `wsl --shutdown` — shuts down all WSL instances. Often returns immediately even when the guest is wedged.
3. Wait 10 s. If PowerShell is also sluggish, open Task Manager and look for `vmmem` / `vmmemWSL` — it should drop to zero RAM within 20 s of shutdown.
4. If `vmmem` doesn't drop: `Stop-Service LxssManager -Force` from elevated PowerShell.
5. Once clear, restart WSL: `wsl -d Ubuntu-22.04`.
6. `docker ps` to verify the daemon restarted cleanly. If not, see [docker-wsl2-recovery.md](docker-wsl2-recovery.md).

### After an unplanned reboot

1. Check `sudo journalctl -b -1 --since "-2 hours" | grep -iE "oom|allocation failure|hung|blocked"` — understand why.
2. Run stack cleanup: `./scripts/stack_control.sh --local status` → observe orphaned sandboxes.
3. The new startup reconciliation (phase 10a in `app/lifespan.py`) should handle stale DB rows automatically; verify with `docker logs ii-agent-local-backend-1 | grep "Startup sandbox reconciliation"`.
4. File an entry in [post-reboot-followups.md](post-reboot-followups.md) with timeline so we build a corpus of real incidents.

## Observed baselines (for comparison during future incidents)

**Healthy state (2026-04-23, 23:01, post `wsl --shutdown`, post sysctl install, post-reboot fresh stack):**

```
MemTotal:        46 GB  (cap = 45 GB; +overhead)
MemAvailable:    31 GB
Swap used:        0 GB
/proc/buddyinfo Normal:  order-7 = 1, order-8 = 2, order-10 = 6098
vm.min_free_kbytes        = 262144
vm.compaction_proactiveness = 50
vm.compact_unevictable_allowed = 1
vm.swappiness             = 10
vm.dirty_background_ratio = 5
vm.dirty_ratio            = 15
```

**Pressure state (2026-04-23, 22:23, stack up + `--no-cache` backend rebuild in flight, before memory bump and before sysctl install):**

```
MemTotal:        32 GB  (old cap)
MemAvailable:    16 GB
Swap used:        5.4 GB (growing)
Build elapsed:   55 min and counting (would normally be ~10 min)
```

This is what triggered the bump from 32 GB to 45 GB and the sysctl install.

**Earlier "healthy" reading (2026-04-23, 18:14, stack up, 2 warm sandboxes, 32 GB cap, no sysctls):**

```
MemAvailable:   18 GB
Swap used:      4.4 GB (residual, not growing)
/proc/buddyinfo Normal:  order-7 = 6 blocks, order-8 = 0, order-9 = 71
```

Note even that earlier "healthy" baseline had order-8 at zero. The new baseline above shows the difference the tuning makes -- plenty of high-order pages available.

## References

- [post-reboot-followups.md](post-reboot-followups.md) — incident ledger.
- [sandbox-networking-design.md](sandbox-networking-design.md) — Docker bridge topology (separate concern).
- [host-resource-monitoring.md](host-resource-monitoring.md) — runtime monitoring design.
- [docker-wsl2-recovery.md](docker-wsl2-recovery.md) — Docker-socket-specific recovery.
- Microsoft .wslconfig reference: https://learn.microsoft.com/en-us/windows/wsl/wsl-config
