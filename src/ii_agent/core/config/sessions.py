"""Configuration for the session purge subsystem (§4.4).

Single source of truth for all timing budgets, retry budgets, allowlist
overrides, and feature flags driving the three-phase purge driver (§4.1)
and the storage reaper (§4.6).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class SessionsSettings(BaseSettings):
    """Tunables for the §4 runtime changes.

    All values are reload-safe: `get_settings()` returns a cached instance
    but operators can hot-tune by restarting the cleanup-loop worker.
    """

    # ---- Feature flags (default OFF until PR-A/PR-B migrations land) ----
    purge_enabled: bool = False
    """Master kill switch for the three-phase purge driver (§4.1).
    When False, the cleanup-loop stage is a no-op. Default False so the
    feature ships dark and can be enabled per-environment after migration."""

    storage_reaper_enabled: bool = False
    """Kill switch for §4.6 storage reaper. Independent of `purge_enabled`."""

    provider_cleanup_enabled: bool = True
    """Whether phase (b) actually invokes upstream DELETEs. False ⇒ phase (b)
    no-ops and phase (c) deletes the session row anyway (lab/test mode)."""

    # ---- Grace windows ----
    purge_grace_period_seconds: int = 30 * 24 * 3600
    """Standard grace before purge_after fires (30 days, GDPR-typical)."""

    ephemeral_purge_grace_period_seconds: int = 3600
    """Short grace for `custody='ephemeral'` (1 hour)."""

    # ---- Per-loop budgets ----
    purge_max_seconds_per_loop: int = 30
    """Wall-clock cap per cleanup-loop iteration. Caps replica-lag impact."""

    purge_max_attempts: int = 5
    """After this many failed phase-(b) attempts, dead-letter and stop."""

    # ---- Claim TTL & heartbeat ----
    purge_claim_timeout_seconds: int = 600
    """A claim older than this with no heartbeat is considered stale and
    reclaimable. Phase-(b) implementations MUST heartbeat at the cadence below."""

    heartbeat_interval_seconds: int = 120
    """How often phase (b) refreshes the claim. Must be < claim_timeout / 2."""

    # ---- Storage reaper (§4.6) ----
    storage_reaper_min_age_seconds: int = 3600
    """Asset must be older than this with no SessionAsset link before reaping —
    avoids racing two-step upload pipelines (UserAsset insert before
    SessionAsset link)."""

    storage_reaper_batch_size: int = 50
    """Max orphan rows per reaper invocation. Caps GCS DELETE QPS."""

    # ---- Per-session purge_now (PR-F follow-up) ----
    purge_now_lock_ttl_seconds: int = 60
    purge_now_rate_limit_per_minute: int = 5

    # ---- User-account purge (PR-G follow-up) ----
    user_purge_parallelism: int = 4
    user_purge_overall_timeout_seconds: int = 1800

    # ---- Dead-letter retention ----
    dead_letter_retention_seconds: int = 365 * 24 * 3600
    """TTL for RESOLVED dead-letter rows. Unresolved rows never expire (I10)."""

    class Config:
        env_prefix = "SESSIONS_"
        env_file = ".env"
        extra = "ignore"
