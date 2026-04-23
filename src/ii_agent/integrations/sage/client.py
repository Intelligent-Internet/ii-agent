"""Async SAGE client wrapper with lazy initialisation and graceful degradation.

The wrapper serves three purposes:

1. Guard the optional ``sage-agent-sdk`` import so the framework keeps
   working when the extra is not installed.
2. Provide a lightweight ``is_available()`` health probe that the hook
   layer can call on every turn without paying a full SDK round-trip on
   failure paths.
3. Cache the :class:`AgentIdentity` and the underlying
   :class:`AsyncSageClient` so we don't regenerate keys or leak HTTP
   connections across turns.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ii_agent.core.config.sage_config import SageConfig
from ii_agent.core.logger import logger

# Lazy-resolved references to optional SDK symbols. Populated on first use.
_AsyncSageClientCls: Any | None = None
_AgentIdentityCls: Any | None = None
_MemoryTypeEnum: Any | None = None
_SDK_AVAILABLE: bool | None = None


def _ensure_sdk() -> bool:
    """Resolve the optional ``sage-agent-sdk`` symbols on first use.

    Returns ``True`` iff the SDK is importable. Subsequent calls are O(1).
    """
    global _AsyncSageClientCls, _AgentIdentityCls, _MemoryTypeEnum, _SDK_AVAILABLE
    if _SDK_AVAILABLE is not None:
        return _SDK_AVAILABLE
    try:
        from sage_sdk.async_client import AsyncSageClient as _AsyncSdk
        from sage_sdk.auth import AgentIdentity as _Identity
        from sage_sdk.models import MemoryType as _MemType

        _AsyncSageClientCls = _AsyncSdk
        _AgentIdentityCls = _Identity
        _MemoryTypeEnum = _MemType
        _SDK_AVAILABLE = True
    except ImportError:
        logger.debug("sage-agent-sdk not installed — SAGE integration disabled")
        _SDK_AVAILABLE = False
    return _SDK_AVAILABLE


class SageClient:
    """Async SAGE facade with a stable API for the hook layer.

    The underlying :class:`AsyncSageClient` is created lazily on the first
    call that actually needs it. Health probes use an independent
    short-lived client via ``httpx`` so a misconfigured node never
    poisons the cached client.
    """

    def __init__(self, config: SageConfig | None = None) -> None:
        self._config = config or SageConfig()
        self._sdk_client: Any | None = None
        self._identity: Any | None = None
        self._available: bool | None = None

    # ------------------------------------------------------------------
    # Config / identity
    # ------------------------------------------------------------------

    @property
    def config(self) -> SageConfig:
        return self._config

    @property
    def agent_identity(self) -> Any | None:
        """Return the cached :class:`AgentIdentity`, creating it if needed.

        Returns ``None`` when the SDK is unavailable or the integration is
        disabled — callers must guard accordingly.
        """
        if not self._config.enabled or not _ensure_sdk():
            return None
        if self._identity is None:
            assert _AgentIdentityCls is not None
            key_path = self._config.agent_key
            if key_path and Path(key_path).exists():
                self._identity = _AgentIdentityCls.from_file(key_path)
            else:
                self._identity = _AgentIdentityCls.default()
        return self._identity

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Return True iff SAGE is enabled, SDK installed, and node healthy.

        Uses a short-lived ``httpx`` request so the probe never stashes a
        broken cached client on the instance.
        """
        if not self._config.enabled:
            return False
        if not _ensure_sdk():
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self._config.pre_hook_timeout_s) as http:
                resp = await http.get(f"{self._config.node_url.rstrip('/')}/health")
            ok = resp.status_code == 200
            self._available = ok
            return ok
        except Exception as exc:  # noqa: BLE001 — health probe must never throw
            logger.debug(f"SAGE health check failed: {exc}")
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Lazy SDK client
    # ------------------------------------------------------------------

    async def _sdk(self) -> Any | None:
        """Return the cached :class:`AsyncSageClient`, building it on demand."""
        if not self._config.enabled or not _ensure_sdk():
            return None
        if self._sdk_client is None:
            identity = self.agent_identity
            if identity is None:
                return None
            assert _AsyncSageClientCls is not None
            self._sdk_client = _AsyncSageClientCls(
                base_url=self._config.node_url,
                identity=identity,
                timeout=max(self._config.pre_hook_timeout_s * 2, 5.0),
            )
        return self._sdk_client

    async def aclose(self) -> None:
        """Close the underlying HTTP client, if any."""
        if self._sdk_client is not None:
            try:
                await self._sdk_client.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"SAGE client close failed: {exc}")
            finally:
                self._sdk_client = None

    # ------------------------------------------------------------------
    # Memory operations
    # ------------------------------------------------------------------

    async def recall(
        self,
        text: str,
        *,
        domain: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Recall semantically similar committed memories.

        Returns a list of ``{content, confidence, domain}`` dicts. Returns
        an empty list on any error so callers can treat it as a pure
        fallback to the agent's existing context.
        """
        client = await self._sdk()
        if client is None:
            return []
        try:
            embedding = await client.embed(text)
            response = await client.query(
                embedding=embedding,
                domain_tag=domain or self._config.default_domain,
                top_k=top_k or self._config.recall_top_k,
            )
            results = getattr(response, "results", []) or []
            return [
                {
                    "content": getattr(r, "content", ""),
                    "confidence": getattr(r, "confidence_score", 0.0),
                    "domain": getattr(r, "domain_tag", ""),
                }
                for r in results
            ]
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — recall must never raise
            logger.debug(f"SAGE recall failed: {exc}")
            return []

    async def propose(
        self,
        content: str,
        *,
        memory_type: str = "observation",
        domain: str | None = None,
        confidence: float = 0.80,
    ) -> bool:
        """Propose a memory to the SAGE network.

        Returns ``True`` on a clean submission, ``False`` otherwise. This
        intentionally swallows exceptions so the post-hook background task
        does not surface failures back into the agent run.
        """
        client = await self._sdk()
        if client is None or not content:
            return False
        try:
            embedding = await client.embed(content)
            assert _MemoryTypeEnum is not None
            mt = getattr(_MemoryTypeEnum, memory_type, _MemoryTypeEnum.observation)
            await client.propose(
                content=content,
                memory_type=mt,
                domain_tag=domain or self._config.default_domain,
                confidence=confidence,
                embedding=embedding,
            )
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — propose must never raise
            logger.debug(f"SAGE propose failed: {exc}")
            return False
