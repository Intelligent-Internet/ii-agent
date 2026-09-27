# Sandbox Shared Bridge Network — Design Decision

**Status:** Approved 2026-04-23. Implementation tracked in [../impl-docs/sandbox-robustness-impl-tracker.md](../impl-docs/sandbox-robustness-impl-tracker.md).

**Detailed operational design:** [../runtime-docs/sandbox-networking-design.md](../runtime-docs/sandbox-networking-design.md).

**Related runtime docs:**
- [../runtime-docs/wsl2-host-configuration.md](../runtime-docs/wsl2-host-configuration.md) — host / WSL tuning (separate concern).
- [../runtime-docs/host-resource-monitoring.md](../runtime-docs/host-resource-monitoring.md) — integrated monitor design.
- [../runtime-docs/post-reboot-followups.md](../runtime-docs/post-reboot-followups.md) — incident ledger that drove this work.

---

## Decision

In local Docker mode, all sandbox containers will attach to a dedicated user-defined bridge network `ii-sandboxes`, separate from the compose default network which hosts the backend / postgres / redis / minio / a2a-adapter.

The backend will be dual-homed on both networks.

E2B cloud mode is unchanged.

## Why (corrected rationale)

On 2026-04-23 the WSL2 guest had to be force-rebooted after a sandbox container's network-namespace teardown got stuck in the kernel. The proximate amplifier was that the backend made **synchronous** Docker API calls on the asyncio event loop, so when dockerd's per-container lock was held waiting for the stuck teardown, all user traffic queued behind it. That class of failure is now addressed by Phase 2 fixes (bounded executor, 8 s `docker_call` timeouts, per-sandbox circuit breaker).

However the shared compose default network also contributes to the amplification pathway in a different way: every sandbox create/destroy updates iptables NAT + filter chains that currently carry rules for **all** infra services combined with all sandboxes. Larger chains mean longer per-operation work inside Docker; longer work means longer lock-hold windows. Dedicating a bridge to sandboxes shrinks that per-operation work surface and avoids polluting the infra-service chains with sandbox churn.

**Correction of earlier framing (important):** An initial draft claimed the shared bridge caused "kernel RTNL lock contention across the default network". That was wrong. The kernel's RTNL lock is a single global lock across all network namespaces — a separate bridge does *not* give you RTNL isolation. What a separate bridge gives you is:

1. **Smaller iptables chain work per sandbox lifecycle event.**
2. **Separation of the IPAM / ARP / chain state for infra services from sandbox churn.** Makes `iptables-save`, `tcpdump`, and network troubleshooting tractable.
3. **Scoped ICC policy** (`enable_icc=false`) without affecting infra traffic.
4. **Cheaper catastrophic recovery** (flush the sandbox bridge's chains without touching infra).

The durable wedge-isolation story is Phase 2 (backend guardrails already live) + Phase 1 (concurrent-create semaphore) + Phase 2 monitor (memory pressure detection). The shared-bridge migration is **secondary defence-in-depth**, not the keystone fix.

## Rejected alternatives

1. **Sandbox in its own container network per-sandbox (`network_mode=none` + manual veth).** Higher engineering cost, same fragmentation footprint per sandbox, harder operational model.
2. **Host networking (`network_mode=host`).** Collapses the isolation we built for sandboxes. Security regression. Rejected on principle.
3. **Shared internal network with direct IP tables manipulation.** Fragile and hard to reason about; we would lose Docker-managed iptables chain idempotency.
4. **Do nothing, rely only on backend-side fixes (circuit breaker, timeouts).** Already landed in Phase 2. These are the *primary* defence for the amplification pathway. Shared-bridge migration is complementary and corrects a genuine but smaller problem (chain-state co-mingling + operational inspection clarity). Not sufficient to replace the Phase 2 work; not made redundant by it either.

## Key insight that reduces migration risk

**Host port publishing is independent of which user-defined bridge a container joins.** The browser-facing URLs that frontends and users rely on (VS Code, noVNC, web preview, tool `register_port`) all resolve to `http://localhost:{host_port}` and continue to work unchanged regardless of migration. See the feature-impact table in the runtime design doc for the full list.

## What makes this a design-level decision

Three things:

1. It changes the stack's network topology, not just a service.
2. It requires the backend to be aware of two networks (dual-home).
3. It introduces a new persistent compose resource (`ii-sandboxes`) that must be provisioned on fresh deploys.

For those reasons the decision is recorded here rather than in a runtime doc alone. Operational detail (subnets, ICC flag, iptables, rollback) lives in the runtime doc.

## Constraints honoured

- **Cloud mode not degraded.** E2B code path is gated by `SANDBOX_PROVIDER`; no shared assumption with Docker networking.
- **No feature regression.** All 16 networking-adjacent features surveyed (2026-04-23) survive without code change, except for the `SANDBOX_DOCKER_NETWORK` env var being pointed at the new network.
- **Rollback is one env var + one compose revert.** Documented in the runtime doc.

## Verified preconditions (2026-04-23)

- **Sandbox has no infra-service dependency.** The sandbox environment only receives `SANDBOX_ID`, `WORKSPACE_DIR`, `AGENT_BROWSER_HEADED`, plus A2A adapter tokens. No code in `docker/sandbox/`, `src/ii_agent_tools/`, or `src/ii_sandbox_server/` references `postgres:`, `redis:`, `minio:`, `backend:`, or `a2a-adapter:` hostnames. Single-network attach is safe.
- **Subnet choice.** Existing Docker subnets are `172.17.0.0/16` (bridge), `172.18.0.0/16`, `172.19.0.0/16` (ii-agent-local_default). WSL NAT occupies `172.29.192.0/20`. Proposed `10.88.0.0/24` is outside both ranges and well-sized (254 addresses) for the typical 16-sandbox footprint. (An earlier draft suggested `172.30.0.0/16`; both are safe, but `10.88.0.0/24` is tidier and avoids the crowded 172.x docker range.)
- **Latent bug in `expose_port(external=False)` and `get_host`.** Verified by code inspection 2026-04-23: both iterate `NetworkSettings.Networks.values()` and return the first non-empty IP. `_wait_for_ready` already does the correct prefer-configured-network pattern. Porting that pattern to the other two call sites is a prerequisite for this migration and is tracked in the impl doc. It is also a latent bug today that the migration would expose if left unfixed.

## Verification plan

Before declaring the migration complete we will verify:

1. A fresh sandbox starts on `ii-sandboxes` and its VS Code/noVNC/web-preview URLs are reachable from the host browser.
2. Agent MCP calls succeed (backend → `ii-sandboxes` IP : 6060).
3. Per-sandbox A2A adapter is reachable from backend (A2A agent mode).
4. Backend reaches postgres / redis / minio (via `default`).
5. Chat A2A adapter sidecar is reachable from backend (via `default`).
6. Orphan cleanup correctly reaps a sandbox on `ii-sandboxes` after manual `docker rm`.
7. Killing a sandbox container's docker-proxy process does not stall backend API calls (blast-radius test).

## Revisit triggers

Revisit this decision if:

- We see a second cross-network stall incident (meaning even the dual-home-backed separation wasn't enough).
- Docker releases first-class support for per-container network namespaces without a bridge (currently not on roadmap).
- We add a feature that requires sandbox-to-sandbox reachability (would need to re-enable ICC).
