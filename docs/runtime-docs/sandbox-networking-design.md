# Sandbox Networking Design

**Purpose:** Define the Docker network topology used by sandbox containers in local mode, distinguish it clearly from the E2B cloud networking model, and document what is and is not affected by the shared-bridge migration.

**Scope:** Docker bridge / veth / port mapping concerns for locally-hosted sandboxes. WSL kernel tuning is in [wsl2-host-configuration.md](wsl2-host-configuration.md). Runtime monitoring is in [host-resource-monitoring.md](host-resource-monitoring.md).

**Status:** Design agreed 2026-04-23. Implementation tracked in [../impl-docs/sandbox-robustness-impl-tracker.md](../impl-docs/sandbox-robustness-impl-tracker.md). Associated design doc: [../design-docs/sandbox-shared-bridge-network.md](../design-docs/sandbox-shared-bridge-network.md).

---

## Two deployment modes — keep them separate

The codebase supports two orthogonal sandbox backends. Each has its own networking model, and changes to one must not regress the other.

### Local mode (Docker on WSL2)

- Backend is a compose service; it mounts `/var/run/docker.sock` and spawns sandbox containers via docker-py.
- Sandboxes are siblings of the backend on a Docker bridge network.
- Backend reaches sandbox-exposed ports via:
  - **Host port mapping** for browser-facing URLs (VS Code, noVNC, web preview): `http://localhost:{host_port}`.
  - **Container IP** for backend-internal protocols (MCP, per-sandbox A2A adapter): `http://{container_ip}:{internal_port}`.
- Frontend reaches sandbox URLs via the same host port mappings (browser → host `localhost:{host_port}`).

### Cloud mode (E2B)

- Sandboxes run on E2B's managed infrastructure. The backend does not touch Docker at all.
- E2B exposes each port as a public HTTPS URL: `https://{sandbox_id}.{e2b_domain}`.
- There are no host ports, no bridges, no veth pairs. Networking is E2B's concern.
- Backend code path: `E2BSandbox.expose_port(port)` returns the HTTPS URL directly.

The two modes converge only at the `Sandbox` interface (`expose_port()`, `get_info()`). Below that interface they share no assumptions. **The shared-bridge work described below applies to Docker mode only; the E2B code path is untouched.**

## Current Docker topology (before migration)

```
compose project: ii-agent-local
├── ii-agent-local_default (bridge, auto-created by compose)
│   ├── postgres       (5432)
│   ├── redis          (6379)
│   ├── minio          (9000, 9001)
│   ├── a2a-adapter    (18100 — internal service DNS)
│   ├── backend        (8000 — published)
│   ├── frontend       (3000 — published)
│   └── sandbox-*      (ALL sandboxes — PROBLEM)
```

**Problem statement (corrected 2026-04-23).** Every sandbox joins `ii-agent-local_default`. That means:

1. The compose default network carries combined iptables NAT + filter chain state for **every** compose service (postgres, redis, minio, adapter, frontend, backend) **and** every sandbox. On each sandbox create/destroy, Docker updates chains that are many times larger than they would be on a sandbox-only bridge.
2. Under memory-fragmentation pressure, large chain updates take longer because the kernel does more work per rule batch. Slow chain work means dockerd holds the Docker-level per-network lock longer, which serialises subsequent create/destroy requests on the same bridge.
3. What we saw on 2026-04-23 was not a kernel-RTNL cross-network stall (RTNL is global and a separate bridge would not have protected us from that). It was: kernel `order:7` allocation failures under veth churn → one container's shutdown stuck inside the kernel → dockerd held its per-container lock waiting for that teardown → the backend's synchronous `docker.client` calls on the asyncio event loop queued behind that lock → the whole backend appeared hung.

The bridge migration addresses **load on the shared network's iptables chains and IPAM tables**, which is a real but secondary factor. The primary amplifier — synchronous Docker calls on the event loop — was already fixed in Phase 2 (bounded executor + 8 s timeouts + per-sandbox breaker). The migration is complementary defence-in-depth, not the keystone fix.

## Target Docker topology (after migration)

```
compose project: ii-agent-local
├── ii-agent-local_default (bridge, existing)
│   ├── postgres
│   ├── redis
│   ├── minio
│   ├── a2a-adapter
│   ├── backend  ← ALSO on ii-sandboxes below
│   └── frontend
│
└── ii-sandboxes (bridge, new, user-defined)
    ├── backend (second attachment)
    └── sandbox-*  ← all sandboxes move here
```

### Key design points

- **The backend is dual-homed.** It attaches to both networks. `default` for infra services (postgres, redis, minio, a2a-adapter). `ii-sandboxes` for sandbox IP access (MCP, per-sandbox A2A adapter).
- **Sandboxes are isolated to `ii-sandboxes`.** Verified 2026-04-23: the sandbox image receives only `SANDBOX_ID`, `WORKSPACE_DIR`, `AGENT_BROWSER_HEADED`, and A2A adapter tokens — no infra service DNS references are injected, and no sandbox-side code in the repo references `postgres:`, `redis:`, `minio:`, `backend:`, or `a2a-adapter:` hostnames. Single-network attach is safe. The `host.docker.internal` → `host-gateway` mapping survives on any bridge.
- **Infra chain state is isolated from sandbox churn.** iptables NAT/filter rules for sandbox ports live on `ii-sandboxes`; infra rules live on `default`. When dockerd rewrites the sandbox bridge's chains on create/destroy, the `default` bridge's chains are untouched. This reduces chain work per sandbox operation and avoids polluting the infra bridge with ephemeral rules.
- **Host port mapping is unchanged.** Published ports (VS Code, noVNC, web preview) map `{container_port} → host:{random_30000-39999}` regardless of which bridge. Browser URLs continue to work with no config change.
- **Network config is explicit.** `ii-sandboxes` gets a dedicated small subnet. Proposed: `10.88.0.0/24` — avoids the crowded Docker 172.17–172.31 range, does not overlap the WSL NAT (172.29.192.0/20), and 254 addresses is ample for the 16-container typical footprint. Larger `/16` is unnecessary.
- **ICC = false on `ii-sandboxes`.** Sandboxes cannot reach each other directly. Current behaviour anyway (no feature relies on sandbox-to-sandbox); enforcing it locks in the property.

### What does not change

- `SANDBOX_DOCKER_HOST` (defaults to `localhost`) — still the host the browser reaches.
- `PortPoolManager` range (30000–39999) — unchanged.
- `host.docker.internal` mapping — works across all networks.
- E2B code path — untouched, governed by `SANDBOX_PROVIDER != docker`.
- `expose_port(external=True)` semantics — returns host-port URL as before.
- `expose_port(external=False)` semantics — returns container IP. The IP now comes from the `ii-sandboxes` network, but the shape of the call is identical.

### What config changes

| Env / setting | Old | New |
|---|---|---|
| `SANDBOX_DOCKER_NETWORK` | `${COMPOSE_PROJECT_NAME}_default` | `${COMPOSE_PROJECT_NAME}_ii-sandboxes` |
| `docker-compose.local.yaml` → `networks:` | (implicit default only) | adds `ii-sandboxes` with `10.88.0.0/24` subnet and `enable_icc=false` |
| `docker-compose.local.yaml` → `backend.networks` | (implicit default) | `[default, ii-sandboxes]` |

### Code change required: `expose_port(external=False)` network disambiguation

Verified 2026-04-23: [src/ii_agent/agents/sandboxes/docker.py#L1145](src/ii_agent/agents/sandboxes/docker.py#L1145) (`expose_port`) and [#L1113](src/ii_agent/agents/sandboxes/docker.py#L1113) (`get_host`) iterate `NetworkSettings.Networks.values()` and return the **first** entry with a non-empty IP. This works when a container is on exactly one network, but is not deterministic for dual-homed containers.

`_wait_for_ready` at [#L1232](src/ii_agent/agents/sandboxes/docker.py#L1232) already gets this right — it tries `docker_network` first and falls back. We must port the same pattern to `get_host` and `expose_port(external=False)`:

```python
networks = self._container.attrs.get("NetworkSettings", {}).get("Networks", {})
preferred = self._config.sandbox.docker_network
if preferred in networks and networks[preferred].get("IPAddress"):
    return networks[preferred]["IPAddress"]
# Fall back to first available (existing behaviour)
for net_info in networks.values():
    if net_info.get("IPAddress"):
        return net_info["IPAddress"]
```

This is a prerequisite for Phase 3, tracked separately in the impl doc. It is also a latent correctness bug today even without migration, because pool operations may dual-home a container transiently during attach/reattach.

## Feature impact assessment

Based on the survey of all networking-dependent features (2026-04-23). For each feature: does the shared-bridge change break, degrade, or complicate it?

### Unaffected (no change needed)

| Feature | Why |
|---|---|
| **Storage proxy router** (`/storage/d/{path}`) | Backend ↔ MinIO via compose service DNS. No sandbox involvement. |
| **Slide assets router** (`/files/slides/assets/{hash}.{ext}`) | Static assets from object storage. No sandbox involvement. |
| **Sandbox file preview** (`/sandbox-files/...`) | Uses Docker API (socket), not network. |
| **MCP server** (port 6060) | `expose_port(external=False)` returns container IP on whichever bridge. Works transparently on `ii-sandboxes`. |
| **Per-sandbox A2A adapter** (port 18100) | Same as MCP — internal container IP, works on any bridge. |
| **A2A chat adapter sidecar** | Resolves by compose service DNS (`a2a-adapter`). Stays on `default`. Backend reaches it via `default`. |
| **TestFlight handler** (uses MCP) | Rides on MCP. Same as MCP above. |
| **Docker socket mount** | Unix socket, not network. |
| **`host.docker.internal`** | `extra_hosts` mapping works on user-defined bridges. |

### Affected but safe (returns the same external URLs)

| Feature | Why safe |
|---|---|
| **VS Code URL** (port 9000) | Host port mapping is independent of bridge. `http://localhost:{host_port}` still works. |
| **noVNC URL** (port 6080) | Same as VS Code. |
| **Web preview iframe** (ports 3000/5173/8080/custom) | Same as VS Code. Published to host ports regardless of bridge. |
| **Register Port agent tool** | Returns host-port URL, unchanged. |
| **Sandbox status WebSocket event** | Contains the above URLs. Unchanged. |

The critical insight: **host-port publication does not depend on which user-defined bridge a container joins.** Docker's port forwarder (userland-proxy or kernel iptables NAT) routes host traffic to the container by matching the container ID, not by matching the bridge. So all browser-facing URLs continue to work unchanged.

### Affected and requires verification

| Feature | Concern | Mitigation |
|---|---|---|
| **Project design preview proxy** (`/projects/design/preview?url=...`) | Backend proxies to a sandbox URL; if the URL is `http://{container_ip}:{port}`, backend must be able to reach that IP. | Backend is dual-homed; reaches `ii-sandboxes` bridge directly. If the URL instead uses `localhost:{host_port}`, works regardless. Verify both forms during migration. |
| **Orphan cleanup network validation** | `_cleanup_orphaned_volumes` + `_health_check_sandbox_rows` compare DB state to Docker state. | Queries use Docker API; must not filter by network name. Verify in code that we iterate all networks or the correct one (`ii-sandboxes`). |

### Explicitly not supported (unchanged by migration)

- Sandbox-to-sandbox direct networking. ICC=false on the bridge enforces this.
- External (internet-side) inbound to sandbox ports. Not supported today; not a goal.

## Risks and rollback

### Risk: dual-homed backend regresses service-to-service latency

Docker containers attached to multiple networks resolve other services by name from the network on which the other service is present. Measured experimentally: sub-millisecond overhead. Accepted.

### Risk: existing sandboxes on old network at deploy time

Rollout procedure:

1. Deploy compose change with `ii-sandboxes` network and dual-homed backend.
2. `docker compose up` will recreate backend (brief downtime, expected).
3. Existing running sandboxes remain on `default` — the new backend can still reach them (still on `default`) but any NEW sandbox will use `ii-sandboxes`.
4. Existing sandboxes drain naturally (timeout / retire / user end-of-session). Within 24 h all active sandboxes are on `ii-sandboxes`.
5. If needed, manual migration: the user can restart any long-lived session to recycle the sandbox.

No code migration is required for existing sandboxes because the backend's network resolution is dynamic — it reads the current network via docker-py each time.

### Rollback

If the migration misbehaves:

1. Revert compose change (`git revert <commit>`).
2. Set `SANDBOX_DOCKER_NETWORK=${COMPOSE_PROJECT_NAME}_default`.
3. `stack_control.sh rebuild backend`.
4. New sandboxes go back on `default`; old sandboxes on `ii-sandboxes` will be orphaned and reaped on the next cleanup sweep (the orphan cleanup is network-agnostic).

No data migration needed either direction.

## Expected benefits (honest)

Ranked by strength of evidence:

- **Reduced iptables chain work per sandbox operation.** The default compose network currently holds combined NAT + filter rules for all infra services plus every sandbox. Dedicating a bridge to sandboxes shrinks the per-operation rule set Docker rewrites. Real but modest win; measurable at scale (> 10 concurrent sandbox lifecycles).
- **Cleaner operational separation.** `tcpdump -i br-ii-sandboxes` shows only sandbox traffic. Network inspection, iptables audits, and IPAM reasoning become easier.
- **Scoped ICC policy.** `enable_icc=false` enforces no sandbox-to-sandbox without affecting infra traffic. Current behaviour is no-sandbox-to-sandbox by convention; this change makes it structural.
- **Cheaper bulk reap.** Flushing `ii-sandboxes` rules on catastrophic recovery is one operation that does not touch infra.

## What we are NOT claiming

- **Not RTNL lock isolation.** The kernel's RTNL lock is a single global lock across all network namespaces. A veth teardown stuck inside the kernel (the 2026-04-23 failure mode) holds RTNL globally; a separate bridge does not protect against this. The mitigation for that class of failure is Phase 2's memory monitor + Phase 0's bounded Docker executor + breaker, not this migration.
- **Not a fix for `order:7` allocation failures themselves.** Those are driven by kernel memory fragmentation (see [host-resource-monitoring.md](host-resource-monitoring.md)). Shared bridge reduces *how often* we touch the fragmented zone slightly, not fragmentation itself.
- **Not a substitute for sandbox concurrent-create limit.** Still want a semaphore to cap veth create bursts.
- **Not a performance improvement for healthy operation.** Under normal load this is neutral. Value is in reduced shared-state churn.

## Implementation ordering

Sequence agreed 2026-04-23 (see impl tracker for full dependency graph):

1. Land concurrent-create semaphore first (small, backend-only, independent).
2. Land integrated host monitor (infrastructure for observing the fix working).
3. Land shared-bridge migration (larger change, needs clean baseline).
4. Tune WSL config last (host-side, done in user's own environment).

Each step is independently valuable and independently revertible.

## References

- Feature survey from 2026-04-23 — reported via Explore subagent (not persisted; see impl doc for extraction if needed).
- Docker network drivers reference: https://docs.docker.com/network/drivers/bridge/
- Kernel RTNL lock background: https://lwn.net/Articles/767949/
