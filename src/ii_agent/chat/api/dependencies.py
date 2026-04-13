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

# Shared A2A resources — created once, reused across requests so the circuit
# breaker accumulates failures correctly and the HTTP client is reused.
# The client is automatically refreshed when the sandbox container changes.
_a2a_chat_client = None
_a2a_chat_circuit_breaker = None
_a2a_chat_client_url: str | None = None  # tracks URL the client was created with


def _discover_sandbox_adapter_url() -> str | None:
    """Auto-discover a running ii-sandbox A2A adapter for local development.

    When AGENT_A2A_AGENT_URL is not explicitly set, this finds any running
    sandbox container and returns its adapter endpoint via Docker networking
    (container_name:18100).  Uses the Docker socket API directly since Docker
    CLI may not be available inside the backend container.
    """

    try:
        # Use Unix socket via a custom opener
        import http.client
        import socket as _socket

        class _UnixHTTPConnection(http.client.HTTPConnection):
            def connect(self):
                self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
                self.sock.connect("/var/run/docker.sock")

        conn = _UnixHTTPConnection("localhost")
        conn.request(
            "GET",
            '/containers/json?filters={"name":["ii-sandbox"]}',
        )
        resp = conn.getresponse()
        if resp.status == 200:
            import json

            containers = json.loads(resp.read())
            for c in containers:
                names = c.get("Names", [])
                if names:
                    name = names[0].lstrip("/")
                    url = f"http://{name}:18100"
                    logger.info("Auto-discovered sandbox A2A adapter: %s", url)
                    return url
    except Exception as exc:
        logger.debug("Sandbox adapter auto-discovery failed: %s", exc)
    return None


def _get_shared_a2a_resources():
    """Lazily create the shared A2A client and circuit breaker singletons.

    If the sandbox container has changed (different URL from discovery), the
    stale client is replaced so council and chat don't route to a dead
    container.
    """
    global _a2a_chat_client, _a2a_chat_circuit_breaker, _a2a_chat_client_url

    from ii_agent.core.config.settings import get_settings
    from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
    from ii_agent.integrations.a2a.circuit_breaker import CircuitBreaker

    settings = get_settings()
    agent_settings = settings.agent

    if agent_settings.chat_inner_loop_mode != "a2a":
        return None, None

    client_url = agent_settings.a2a_agent_url
    if not client_url:
        client_url = _discover_sandbox_adapter_url()
    if not client_url:
        logger.warning(
            "chat_inner_loop_mode=a2a but AGENT_A2A_AGENT_URL is not set and "
            "no sandbox adapter found; falling back to direct LLM"
        )
        return None, None

    # If the discovered URL changed (sandbox recycled), recreate the client
    if _a2a_chat_client is not None and _a2a_chat_client_url != client_url:
        logger.info(
            "Sandbox adapter URL changed (%s -> %s), refreshing A2A client",
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

    settings = get_settings()
    agent_settings = settings.agent

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
