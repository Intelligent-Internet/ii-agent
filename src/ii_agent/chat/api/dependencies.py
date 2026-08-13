"""FastAPI dependencies for chat domain."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep, PubSubDep
from ii_agent.chat.messages.repository import ChatMessageRepository
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.messages.history_service import ChatMessageHistoryService

from ii_agent.settings.llm.dependencies import ModelSettingServiceDep
from ii_agent.credits.dependencies import CreditServiceDep
from ii_agent.files.dependencies import FileRepositoryDep
from ii_agent.integrations.connectors.dependencies import ConnectorRepositoryDep
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.sessions.dependencies import SessionTitleServiceDep

logger = logging.getLogger(__name__)


# ==================== Repository Dependencies ====================


def get_chat_message_repository() -> ChatMessageRepository:
    return ChatMessageRepository()


ChatMessageRepositoryDep = Annotated[ChatMessageRepository, Depends(get_chat_message_repository)]


# ==================== Services in container ====================


def _get_message_service(container: ContainerDep) -> MessageService:
    return container.message_service


MessageServiceDep = Annotated[MessageService, Depends(_get_message_service)]


# ==================== Factory-wired sub-services ====================


def get_chat_file_processor(container: ContainerDep) -> ChatFileProcessor:
    return ChatFileProcessor(config=container.config)


ChatFileProcessorDep = Annotated[ChatFileProcessor, Depends(get_chat_file_processor)]


def get_chat_tool_service(
    connector_repo: ConnectorRepositoryDep,
    container: ContainerDep,
) -> ChatToolService:
    return ChatToolService(
        connector_repo=connector_repo,
        container=container,
    )


ChatToolServiceDep = Annotated[ChatToolService, Depends(get_chat_tool_service)]


def get_chat_message_history(
    chat_repo: ChatMessageRepositoryDep,
    file_repo: FileRepositoryDep,
) -> ChatMessageHistoryService:
    return ChatMessageHistoryService(chat_repo=chat_repo, file_repo=file_repo)


ChatMessageHistoryServiceDep = Annotated[
    ChatMessageHistoryService, Depends(get_chat_message_history)
]


# ==================== ChatService ====================

# ============================================================================
# A2A chat loop singleton — URL resolution
#
# Chat sessions do **not** own sandboxes.  The chat-mode A2A inner loop
# is a stateless protocol bridge to a single A2A adapter HTTP endpoint
# configured by the operator.
#
# Design intent: chat A2A must work **regardless of sandbox presence**.
# Native fallback is reserved for genuine A2A failures only — circuit
# breaker open, rate limits, transport errors at request time — never
# for "no adapter URL configured" or "no sandbox running".  Silent
# fallback in those misconfiguration cases routes traffic to the
# expensive native LLM (10×+ Copilot subscription cost) and produces
# surprise upstream API charges.  See:
#   - docs/design-docs/a2a-inner-loop-url-resolution.md
#   - docs/design-docs/chat-a2a-adapter-sidecar.md
#
# Deployment expectation:
#   * Local Docker stack: docker-compose.local.yaml ships an
#     ``a2a-adapter`` sidecar service.  Backend defaults
#     ``AGENT_A2A_AGENT_URL=http://a2a-adapter:18100``.
#   * Cloud / E2B: operator deploys an adapter service and sets
#     ``AGENT_A2A_AGENT_URL`` explicitly.
#
# Misconfiguration handling (this module):
#   * URL missing at startup with chat_inner_loop_mode=a2a → loud
#     ERROR log; if AGENT_A2A_CHAT_STRICT=true the lifespan crashes
#     the process (preferred).
#   * URL missing at request time → A2AAdapterUnavailableError raised
#     to the caller (HTTP 503) when strict=true; loud ERROR + native
#     fallback when strict=false (back-compat default).
#
# Agent-mode A2A is independent: it resolves the adapter URL per-session
# via ``sandbox.expose_port(ADAPTER_CONTAINER_PORT)`` (see
# ``AgentFactory._build_inner_loop_strategy``).  Agents may also use the
# shared sidecar by setting ``AGENT_A2A_AGENT_URL``.
# ============================================================================

_a2a_chat_client = None
_a2a_chat_circuit_breaker = None
_a2a_chat_client_url: str | None = None  # tracks URL the client was created with


def _resolve_chat_a2a_url() -> str | None:
    """Resolve the chat-mode A2A adapter URL.

    Returns the configured ``AGENT_A2A_AGENT_URL`` when chat A2A is
    enabled, else ``None``.  No discovery, no probing — chat A2A is
    sandbox-independent by design and operators are responsible for
    pointing it at a reachable adapter (see module docstring).
    """
    from ii_agent.core.config.settings import get_settings

    settings = get_settings()
    if settings.agent.chat_inner_loop_mode != "a2a":
        return None

    return settings.agent.a2a_agent_url or None


def _get_shared_a2a_resources():
    """Lazily create the shared A2A client and circuit breaker singletons.

    If the resolved URL changes between calls (sandbox container recycled
    in dev), the stale client is replaced so chat doesn't keep talking to
    a dead endpoint.
    """
    global _a2a_chat_client, _a2a_chat_circuit_breaker, _a2a_chat_client_url

    from ii_agent.core.config.settings import get_settings
    from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
    from ii_agent.integrations.a2a.circuit_breaker import CircuitBreaker

    agent_settings = get_settings().agent

    if agent_settings.chat_inner_loop_mode != "a2a":
        return None, None

    client_url = _resolve_chat_a2a_url()
    if not client_url:
        # Loud, actionable error — silent fallback to direct LLM has
        # caused unexpected upstream API charges in the past.
        logger.error(
            "chat_inner_loop_mode=a2a but NO A2A adapter URL is "
            "available (AGENT_A2A_AGENT_URL not set, and no local "
            "sandbox adapter discoverable). Falling back to native LLM "
            "for this request — this WILL incur direct provider "
            "charges. Set AGENT_A2A_AGENT_URL or start a sandbox; set "
            "AGENT_A2A_CHAT_STRICT=true to crash instead of falling "
            "back. See docs/design-docs/a2a-inner-loop-url-resolution.md."
        )
        if agent_settings.a2a_chat_strict:
            from ii_agent.integrations.a2a.exceptions import A2AAdapterUnavailableError

            raise A2AAdapterUnavailableError(
                "A2A chat adapter unavailable and AGENT_A2A_CHAT_STRICT=true; "
                "refusing to silently fall back to native LLM."
            )
        return None, None

    # Refresh the client if the resolved URL changed (e.g. a dev
    # restarted the sandbox and got a new container name).
    if _a2a_chat_client is not None and _a2a_chat_client_url != client_url:
        logger.info(
            "A2A adapter URL changed (%s -> %s); refreshing chat client",
            _a2a_chat_client_url,
            client_url,
        )
        _a2a_chat_client = None

    if _a2a_chat_client is None:
        _a2a_chat_client = IIAgentA2AClient(
            agent_url=client_url,
            timeout=agent_settings.a2a_timeout_seconds,
        )
        _a2a_chat_client_url = client_url
    if _a2a_chat_circuit_breaker is None:
        _a2a_chat_circuit_breaker = CircuitBreaker(name="a2a-chat")

    return _a2a_chat_client, _a2a_chat_circuit_breaker


def _build_a2a_chat_loop(
    *,
    message_service: MessageService,
    pubsub,
    fallback_loop: LLMTurnLoopService,
):
    """Build A2AChatTurnLoop if config says a2a, else return None."""
    from ii_agent.core.config.settings import get_settings
    from ii_agent.chat.application.a2a_turn_loop_service import A2AChatTurnLoop

    client, circuit_breaker = _get_shared_a2a_resources()
    if client is None or circuit_breaker is None:
        return None

    agent_settings = get_settings().agent
    return A2AChatTurnLoop(
        client=client,
        circuit_breaker=circuit_breaker,
        fallback_loop=fallback_loop,
        fallback_to_native=agent_settings.a2a_fallback_to_native,
        context_reuse=agent_settings.a2a_context_reuse,
        a2a_backend=agent_settings.a2a_backend,
        message_service=message_service,
        pubsub=pubsub,
    )


def get_chat_service(
    model_setting_service: ModelSettingServiceDep,
    credit_service: CreditServiceDep,
    file_processor: ChatFileProcessorDep,
    tool_service: ChatToolServiceDep,
    message_history: ChatMessageHistoryServiceDep,
    message_service: MessageServiceDep,
    session_repo: SessionRepositoryDep,
    container: ContainerDep,
    title_service: SessionTitleServiceDep,
    pubsub: PubSubDep,
) -> ChatService:
    llm_loop = LLMTurnLoopService(message_service=message_service, pubsub=pubsub)
    a2a_loop = _build_a2a_chat_loop(
        message_service=message_service,
        pubsub=pubsub,
        fallback_loop=llm_loop,
    )
    return ChatService(
        file_processor=file_processor,
        tool_service=tool_service,
        llm_loop=llm_loop,
        message_history=message_history,
        message_service=message_service,
        session_repo=session_repo,
        model_setting_service=model_setting_service,
        credit_service=credit_service,
        container=container,
        title_service=title_service,
        a2a_loop=a2a_loop,
        pubsub=pubsub,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
