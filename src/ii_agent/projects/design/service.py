"""Service layer for project design domain - business logic only."""

from __future__ import annotations

import json
import re
import shlex
import time
import uuid
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.llm.factory import get_client
from ii_agent.chat.llm.utils import make_message, run_tool_loop
from ii_agent.chat.types import (
    Message,
    MessageRole,
    TextContent,
    ToolResult,
)
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.projects.design.tools import (
    DesignModeAIChangeTool,
    DesignModeIframeAIGetIconSvgTool,
    DesignModeIframeAIGetNodeTool,
    DesignModeIframeAIListIconsTool,
    DesignModeIframeAIPlanTool,
    DesignModeIframeAISearchTool,
    tool_to_provider_definition,
)
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.settings import Settings
from ii_agent.core.logger import logger
from ii_agent.projects.design.utils.constants import (
    DESIGN_MODE_GOOGLE_FONTS,
    DESIGN_MODE_RUNTIME_SCRIPT,
)
from ii_agent.projects.design.exceptions import (
    DesignProxyFetchError,
    DesignProxyHostNotAllowedError,
    DesignSandboxUnavailableError,
    DesignSessionNotFoundError,
    DesignSessionAccessDeniedError,
    DesignValidationError,
)
from ii_agent.projects.design.repository import ProjectDesignRepository
from ii_agent.projects.design.schemas import (
    AIChangeRequest,
    AIChangeResponse,
    DesignStateRequest,
    DesignStateResponse,
    ElementInfoRequest,
    IframeAIPlanRequest,
    IframeAIPlanResponse,
    IframeDocumentSnapshotNode,
    StyleChange,
    SyncRequest,
    SyncResponse,
    SyncStateRequest,
    SyncStateResponse,
)
from ii_agent.projects.design.source_mapping_sync import apply_changes_with_source_mapping
from ii_agent.projects.design.prompts import (
    build_design_mode_iframe_plan_prompt,
    build_design_mode_style_change_prompt,
)
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.service import SandboxService
from ii_agent.realtime.events.app_events import AgentResponseEvent, AgentStatusUpdateEvent
from ii_agent.settings.llm.service import ModelSettingService

if TYPE_CHECKING:
    from ii_agent.realtime.events.repository import EventRepository as EventService

ProgressCallback = Callable[..., Awaitable[None]]
SummaryCallback = Callable[[str], Awaitable[str | None]]

_E2B_ALLOWED_HOST_SUFFIXES = (".e2b.app", ".e2b.dev")
_IFRAME_MAX_TOOL_LOOPS = 10


class ProjectDesignService:
    """Domain service for project design mode website workflows."""

    def __init__(
        self,
        *,
        repo: ProjectDesignRepository,
        sandbox_service: SandboxService,
        event_service: EventService | None = None,
        model_setting_service: ModelSettingService,
        config: Settings,
    ) -> None:
        self._repo = repo
        self._sandbox_service = sandbox_service
        self._event_service = event_service
        self._model_setting_service = model_setting_service
        self._config = config

    async def _get_session_for_request(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_id: str,
    ) -> Any:
        session = await self._repo.get_session(db, session_id=session_id)
        if not session:
            raise DesignSessionNotFoundError("Session not found")
        if str(getattr(session, "user_id", "")) != str(user_id):
            raise DesignSessionAccessDeniedError("Access denied")
        return session

    async def get_proxy_html(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_id: str,
        url: str,
    ) -> str:
        """Fetch sandbox HTML for website design mode and inject runtime script."""
        session = await self._get_session_for_request(
            db,
            session_id=session_id,
            user_id=user_id,
        )

        parsed = self._validate_proxy_url(url)
        requested_hostname = (parsed.hostname or "").lower()

        sandbox_record: AgentSandbox | None = None
        try:
            sandbox_record = await self._sandbox_service.get_by_session_id(
                db, session_id=session_id
            )
        except Exception:
            sandbox_record = None

        # Support forked sessions that share parent's sandbox.
        if not sandbox_record and session.parent_session_id:
            try:
                sandbox_record = await self._sandbox_service.get_by_session_id(
                    db,
                    session_id=session.parent_session_id,
                )
            except Exception:
                sandbox_record = None

        allowed = self._build_proxy_hostname_allow_check(
            session_public_url=getattr(session, "public_url", None),
            requested_hostname=requested_hostname,
            sandbox_record=sandbox_record,
        )
        if not allowed(requested_hostname):
            raise DesignProxyHostNotAllowedError("Proxy URL host not allowed")

        html, final_url = await self._fetch_proxy_html(
            url=parsed.geturl(),
            is_hostname_allowed=allowed,
        )
        return self._inject_runtime_script_with_base(html=html, base_url=final_url)

    async def ai_design_change(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: AIChangeRequest,
    ) -> AIChangeResponse:
        """Generate structured style/text change suggestions for one selected element."""
        session = await self._get_session_for_request(
            db,
            session_id=request.session_id,
            user_id=user_id,
        )

        llm_config = await self._resolve_llm_config_for_session(
            db, session_id=request.session_id, user_id=user_id, session=session
        )
        llm_config.temperature = 0.2
        client = get_client(llm_config)

        prompt = build_design_mode_style_change_prompt(
            tag_name=request.element_info.tagName,
            class_name=request.element_info.className or "",
            computed_styles=request.element_info.computedStyles or {},
            text_content=request.element_info.textContent or "",
            user_request=request.user_request,
        )
        messages = self._build_llm_messages(
            session_id=request.session_id,
            user_prompt=prompt,
        )
        design_mode_ai_change_tool = DesignModeAIChangeTool()
        try:
            result = await run_tool_loop(
                client=client,
                session_id=request.session_id,
                messages=messages,
                tools=[tool_to_provider_definition(design_mode_ai_change_tool)],
                final_tool_name=design_mode_ai_change_tool.name,
                tool_registry={
                    design_mode_ai_change_tool.name: design_mode_ai_change_tool,
                },
                max_loops=2,
            )
            payload = result.final_payload
        except Exception as exc:
            logger.warning("[DesignMode AI Change] LLM call failed: {}", exc)
            fallback_changes, fallback_explanation = self._parse_design_request(
                request.user_request,
                request.element_info.computedStyles or {},
            )
            return AIChangeResponse(
                changes=fallback_changes,
                explanation=fallback_explanation,
            )

        changes_raw = payload.get("changes")
        explanation = payload.get("explanation")
        if not isinstance(changes_raw, list):
            changes_raw = []
        changes: list[dict[str, str]] = []
        for item in changes_raw:
            if not isinstance(item, dict):
                continue
            prop = item.get("property")
            value = item.get("value")
            if isinstance(prop, str) and isinstance(value, str):
                changes.append({"property": prop, "value": value})
        if not changes:
            fallback_changes, fallback_explanation = self._parse_design_request(
                request.user_request,
                request.element_info.computedStyles or {},
            )
            return AIChangeResponse(
                changes=fallback_changes,
                explanation=fallback_explanation,
            )
        if not isinstance(explanation, str) or not explanation.strip():
            explanation = "Applied the requested changes."
        return AIChangeResponse(changes=changes, explanation=explanation)

    async def ai_iframe_plan(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: IframeAIPlanRequest,
    ) -> IframeAIPlanResponse:
        """Create an ordered iframe edit plan using tool-assisted LLM reasoning."""
        session = await self._get_session_for_request(
            db,
            session_id=request.session_id,
            user_id=user_id,
        )

        llm_config = await self._resolve_llm_config_for_session(
            db, session_id=request.session_id, user_id=user_id, session=session
        )
        llm_config.temperature = 0.0
        if hasattr(llm_config, "thinking_tokens"):
            llm_config.thinking_tokens = 0
        client = get_client(llm_config)

        snapshot_nodes = request.document_snapshot.nodes or []
        snapshot_desc = self._build_snapshot_desc(snapshot_nodes)
        selected_desc = self._build_selected_desc(request.selected_element)
        selected_subtree_hint = self._build_selected_subtree_hint(
            snapshot_nodes=snapshot_nodes,
            selected_design_id=(
                request.selected_element.designId if request.selected_element else None
            ),
        )

        prompt = build_design_mode_iframe_plan_prompt(
            snapshot_desc=snapshot_desc,
            user_request=request.user_request,
            selected_desc=selected_desc,
            selected_subtree_hint=selected_subtree_hint,
        )
        messages = self._build_llm_messages(
            session_id=request.session_id,
            user_prompt=prompt,
        )

        iframe_search_tool = DesignModeIframeAISearchTool(snapshot_nodes)
        iframe_get_node_tool = DesignModeIframeAIGetNodeTool(snapshot_nodes)
        iframe_list_icons_tool = DesignModeIframeAIListIconsTool(max_icon_searches=3)
        iframe_get_icon_svg_tool = DesignModeIframeAIGetIconSvgTool()
        design_mode_iframe_ai_plan_tool = DesignModeIframeAIPlanTool()
        tool_registry = {
            iframe_search_tool.name: iframe_search_tool,
            iframe_get_node_tool.name: iframe_get_node_tool,
            iframe_list_icons_tool.name: iframe_list_icons_tool,
            iframe_get_icon_svg_tool.name: iframe_get_icon_svg_tool,
            design_mode_iframe_ai_plan_tool.name: design_mode_iframe_ai_plan_tool,
        }

        try:
            result = await run_tool_loop(
                client=client,
                session_id=request.session_id,
                messages=messages,
                tools=[
                    tool_to_provider_definition(iframe_search_tool),
                    tool_to_provider_definition(iframe_get_node_tool),
                    tool_to_provider_definition(iframe_list_icons_tool),
                    tool_to_provider_definition(iframe_get_icon_svg_tool),
                    tool_to_provider_definition(design_mode_iframe_ai_plan_tool),
                ],
                final_tool_name=design_mode_iframe_ai_plan_tool.name,
                tool_registry=tool_registry,
                max_loops=_IFRAME_MAX_TOOL_LOOPS,
            )
            payload = result.final_payload
        except Exception as exc:
            logger.warning("[DesignMode AI Iframe] LLM call failed: {}", exc)
            return IframeAIPlanResponse(
                operations=[],
                explanation="I couldn't generate an edit plan due to an error.",
            )
        if payload and isinstance(payload, dict):
            operations = payload.get("operations")
            explanation = payload.get("explanation")
            normalized_operations = await self._normalize_iframe_plan_operations(
                operations=operations,
                snapshot_nodes=snapshot_nodes,
                icon_svg_tool=iframe_get_icon_svg_tool,
            )
            if not isinstance(explanation, str) or not explanation.strip():
                explanation = "Applied the requested changes."
            return IframeAIPlanResponse(
                operations=normalized_operations,
                explanation=explanation,
            )

        return IframeAIPlanResponse(
            operations=[],
            explanation=(
                "I couldn't generate a structured edit plan. "
                "Try re-selecting the element (or a smaller child element) and re-run the request."
            ),
        )

    async def sync_design_changes(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: SyncRequest,
        on_progress: ProgressCallback | None = None,
    ) -> SyncResponse:
        response, _failed_indexes = await self._sync_design_changes_internal(
            db=db,
            user_id=user_id,
            request=request,
            on_progress=on_progress,
        )
        return response

    async def sync_persisted_design_changes(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: SyncStateRequest,
        on_progress: ProgressCallback | None = None,
        on_summary: SummaryCallback | None = None,
    ) -> SyncStateResponse:
        session_uuid = request.session_id
        if not isinstance(session_uuid, uuid.UUID):
            raise DesignValidationError("Invalid session_id")

        session = await self._get_session_for_request(
            db,
            session_id=request.session_id,
            user_id=user_id,
        )

        raw_changes, raw_redo, _updated_at = self._repo.get_design_state(session)
        changes = self._parse_persisted_design_changes(raw_changes)
        total = len(changes)
        if total == 0:
            return SyncStateResponse(
                success=False,
                applied=0,
                total=0,
                remaining=0,
                errors=[],
                summary="No pending Design Mode changes found for this session.",
                remaining_changes=[],
                event_id=None,
            )

        sync_request = SyncRequest(
            session_id=request.session_id,
            changes=changes,
            project_info=None,
        )
        sync_response, failed_indexes = await self._sync_design_changes_internal(
            db=db,
            user_id=user_id,
            request=sync_request,
            on_progress=on_progress,
        )

        remaining_changes = [change for idx, change in enumerate(changes) if idx in failed_indexes]
        updated_at = int(time.time() * 1000)
        await self._repo.update_design_state(
            db,
            session=session,
            changes=[change.model_dump() for change in remaining_changes],
            redo_changes=[c for c in raw_redo if isinstance(c, dict)],
            updated_at=updated_at,
        )

        all_applied = len(remaining_changes) == 0 and not sync_response.errors
        if all_applied:
            summary = (
                f"Synced {sync_response.applied} design change"
                f"{'' if sync_response.applied == 1 else 's'} to source files."
            )
        elif sync_response.applied > 0:
            summary = (
                f"Partially synced Design Mode changes: applied {sync_response.applied}/{total}. "
                "Review pending changes and retry Save."
            )
        else:
            summary = (
                "I could not apply the saved Design Mode changes. "
                "Review pending changes and retry Save."
            )

        event_id = None
        if on_summary:
            try:
                event_id = await on_summary(summary)
            except Exception as exc:
                logger.warning("[DesignMode Sync] Failed to emit summary event: {}", exc)
        elif self._event_service:
            try:
                event_id = await self._emit_sync_summary(
                    db,
                    session_id=session_uuid,
                    summary=summary,
                )
            except Exception as exc:
                logger.warning("[DesignMode Sync] Failed to emit summary event: {}", exc)

        return SyncStateResponse(
            success=all_applied,
            applied=sync_response.applied,
            total=total,
            remaining=len(remaining_changes),
            errors=sync_response.errors,
            summary=summary,
            remaining_changes=remaining_changes,
            event_id=event_id,
        )

    async def get_design_state(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_id: str,
    ) -> DesignStateResponse:
        session = await self._get_session_for_request(
            db,
            session_id=session_id,
            user_id=user_id,
        )

        raw_changes, raw_redo, updated_at = self._repo.get_design_state(session)
        changes = self._parse_persisted_design_changes(raw_changes)
        redo_changes = self._parse_persisted_design_changes(raw_redo)

        return DesignStateResponse(
            session_id=session_id,
            changes=changes,
            redo_changes=redo_changes,
            updated_at=updated_at if isinstance(updated_at, int) else None,
        )

    async def save_design_state(
        self,
        db: AsyncSession,
        *,
        request: DesignStateRequest,
        user_id: str,
    ) -> DesignStateResponse:
        session = await self._get_session_for_request(
            db,
            session_id=request.session_id,
            user_id=user_id,
        )

        _, existing_redo, _ = self._repo.get_design_state(session)
        redo_changes = request.redo_changes
        if redo_changes is None:
            redo_changes = self._parse_persisted_design_changes(existing_redo)
        updated_at = int(time.time() * 1000)

        await self._repo.update_design_state(
            db,
            session=session,
            changes=[change.model_dump() for change in request.changes],
            redo_changes=[change.model_dump() for change in redo_changes],
            updated_at=updated_at,
        )

        return DesignStateResponse(
            session_id=request.session_id,
            changes=request.changes,
            redo_changes=redo_changes,
            updated_at=updated_at,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _resolve_llm_config_for_session(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_id: str,
        session: Any,
    ) -> LLMConfig:
        setting_id = getattr(session, "model_setting_id", None)
        if isinstance(setting_id, str) and setting_id.strip():
            model_id = setting_id.strip()
            try:
                resolved = await self._model_setting_service.get_user_llm_config(
                    db,
                    setting_id=model_id,
                    user_id=user_id,
                )
                return resolved.model_copy(deep=True)
            except Exception:
                try:
                    resolved = await self._model_setting_service.resolve_system_config(
                        db, model_id=model_id
                    )
                    return resolved.model_copy(deep=True)
                except Exception:
                    logger.warning(
                        "[DesignMode] Failed loading session model {} for session {}",
                        model_id,
                        session_id,
                    )

        # Fallback: use "default" system config from DB
        try:
            resolved = await self._model_setting_service.resolve_system_config(
                db, model_id="default"
            )
            return resolved.model_copy(deep=True)
        except ValueError:
            return LLMConfig()

    @staticmethod
    def _build_llm_messages(*, session_id: uuid.UUID, user_prompt: str) -> list[Message]:
        return [
            make_message(
                role=MessageRole.USER,
                session_id=session_id,
                parts=[TextContent(text=user_prompt)],
            )
        ]

    @staticmethod
    def _tool_result_value(tool_result: ToolResult) -> Any:
        output = getattr(tool_result, "output", None)
        if output is None:
            return None
        value = getattr(output, "value", None)
        if value is not None:
            return value
        if hasattr(output, "model_dump"):
            try:
                return output.model_dump()
            except Exception:
                return None
        return None

    @staticmethod
    def _is_e2b_hostname(hostname: str) -> bool:
        value = (hostname or "").strip().lower().rstrip(".")
        if not value:
            return False
        return value.endswith(_E2B_ALLOWED_HOST_SUFFIXES)

    @classmethod
    def _extract_e2b_port_from_hostname(cls, hostname: str) -> Optional[int]:
        hn = (hostname or "").strip().lower().rstrip(".")
        if not hn or not cls._is_e2b_hostname(hn):
            return None
        label = hn.split(".", 1)[0]
        first = label.split("-", 1)[0]
        if not first.isdigit():
            return None
        port = int(first)
        if port < 1 or port > 65535:
            return None
        return port

    @classmethod
    def _hostname_matches_sandbox_id(cls, hostname: str, sandbox_id: str) -> bool:
        hn = (hostname or "").strip().lower().rstrip(".")
        sid = (sandbox_id or "").strip().lower()
        if not hn or not sid or not cls._is_e2b_hostname(hn):
            return False
        label = hn.split(".", 1)[0]
        if label == sid:
            return True
        if label.endswith(f"-{sid}") or label.startswith(f"{sid}-") or f"-{sid}-" in label:
            return True
        return sid in [part for part in label.split("-") if part]

    def _validate_proxy_url(self, url: str) -> Any:
        if not isinstance(url, str):
            raise DesignValidationError("Invalid URL")
        normalized = url.strip()
        if not normalized:
            raise DesignValidationError("Invalid URL")
        try:
            parsed = urlparse(normalized)
        except Exception as exc:
            raise DesignValidationError("Invalid URL") from exc
        if parsed.scheme not in {"http", "https"}:
            raise DesignValidationError("Invalid URL scheme")
        if not parsed.netloc or not parsed.hostname:
            raise DesignValidationError("Invalid URL")
        if parsed.username or parsed.password:
            raise DesignValidationError("Invalid URL")
        return parsed

    def _build_proxy_hostname_allow_check(
        self,
        *,
        session_public_url: Optional[str],
        requested_hostname: str,
        sandbox_record: Optional[AgentSandbox],
    ) -> Callable[[str], bool]:
        allowed_public_hostname = ""
        if isinstance(session_public_url, str) and session_public_url.strip():
            try:
                allowed_public_hostname = (
                    urlparse(session_public_url.strip()).hostname or ""
                ).lower()
            except Exception:
                allowed_public_hostname = ""

        provider_sandbox_id = ""
        if sandbox_record and isinstance(sandbox_record.provider_sandbox_id, str):
            provider_sandbox_id = sandbox_record.provider_sandbox_id.strip().lower()

        requested_port = self._extract_e2b_port_from_hostname(requested_hostname)
        expected_hostnames: set[str] = set()
        if requested_port and provider_sandbox_id:
            expected_hostnames.add(f"{requested_port}-{provider_sandbox_id}.e2b.app")
            expected_hostnames.add(f"{requested_port}-{provider_sandbox_id}.e2b.dev")

        def is_allowed(hostname: str) -> bool:
            hn = (hostname or "").strip().lower().rstrip(".")
            if not hn:
                return False
            if hn in expected_hostnames:
                return True
            if provider_sandbox_id and self._hostname_matches_sandbox_id(hn, provider_sandbox_id):
                return True
            return bool(allowed_public_hostname and hn == allowed_public_hostname)

        return is_allowed

    async def _fetch_proxy_html(
        self,
        *,
        url: str,
        is_hostname_allowed: Callable[[str], bool],
    ) -> tuple[str, str]:
        max_redirects = 5
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                current_url = url
                for _ in range(max_redirects + 1):
                    response = await client.get(
                        current_url,
                        headers={"Accept": "text/html,application/xhtml+xml"},
                    )
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise DesignProxyFetchError(
                                "Failed to fetch sandbox content (invalid redirect)"
                            )
                        next_url = urljoin(current_url, location)
                        parsed_next = urlparse(next_url)
                        if (
                            parsed_next.scheme not in {"http", "https"}
                            or not parsed_next.netloc
                            or not parsed_next.hostname
                        ):
                            raise DesignProxyFetchError(
                                "Failed to fetch sandbox content (invalid redirect)"
                            )
                        if not is_hostname_allowed((parsed_next.hostname or "").lower()):
                            raise DesignProxyFetchError(
                                "Failed to fetch sandbox content (redirect not allowed)"
                            )
                        current_url = next_url
                        continue

                    response.raise_for_status()
                    content_type = (response.headers.get("content-type") or "").lower()
                    if (
                        "text/html" not in content_type
                        and "application/xhtml+xml" not in content_type
                    ):
                        raise DesignProxyFetchError(
                            "Failed to fetch sandbox content (expected HTML)"
                        )
                    return response.text, current_url

                raise DesignProxyFetchError("Failed to fetch sandbox content (too many redirects)")
        except httpx.HTTPStatusError as exc:
            logger.error("Failed to fetch sandbox URL: {}", exc)
            raise DesignProxyFetchError(
                f"Failed to fetch sandbox content: {exc.response.status_code}"
            ) from exc
        except DesignProxyFetchError:
            raise
        except Exception as exc:
            logger.error("Error fetching sandbox URL: {}", exc)
            raise DesignProxyFetchError("Failed to fetch sandbox content") from exc

    def _inject_runtime_script_with_base(self, *, html: str, base_url: str) -> str:
        rewritten = self._rewrite_urls(html=html, base_url=base_url)
        injection = f"{DESIGN_MODE_GOOGLE_FONTS}\n{DESIGN_MODE_RUNTIME_SCRIPT}"
        if "<head>" in rewritten:
            return rewritten.replace("<head>", f"<head>\n{injection}\n", 1)
        if "<head " in rewritten:
            return re.sub(
                r"(<head[^>]*>)",
                lambda m: f"{m.group(1)}\n{injection}\n",
                rewritten,
                count=1,
            )
        if "<html>" in rewritten or "<html " in rewritten:
            return re.sub(
                r"(<html[^>]*>)",
                lambda m: f"{m.group(1)}\n<head>\n{injection}\n</head>\n",
                rewritten,
                count=1,
            )
        return f"{injection}\n{rewritten}"

    def _rewrite_urls(self, *, html: str, base_url: str) -> str:
        parsed_base = urlparse(base_url)
        origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
        base_href = urljoin(base_url, ".")
        if base_href and not base_href.endswith("/"):
            base_href += "/"

        html = re.sub(
            r'(src=["\'])(/[^"\']*)',
            lambda m: f"{m.group(1)}{urljoin(origin, m.group(2))}",
            html,
        )
        html = re.sub(
            r'(href=["\'])(/[^"\'#][^"\']*)',
            lambda m: f"{m.group(1)}{urljoin(origin, m.group(2))}",
            html,
        )

        def rewrite_srcset(value: str) -> str:
            rewritten: list[str] = []
            for part in (value or "").split(","):
                item = part.strip()
                if not item:
                    continue
                pieces = item.split()
                if not pieces:
                    continue
                url_part = pieces[0]
                if url_part.startswith("/"):
                    url_part = urljoin(origin, url_part)
                rewritten.append(" ".join([url_part, *pieces[1:]]).strip())
            return ", ".join(rewritten)

        html = re.sub(
            r'(srcset=["\'])([^"\']*)(["\'])',
            lambda m: f"{m.group(1)}{rewrite_srcset(m.group(2))}{m.group(3)}",
            html,
        )

        if "<base" not in html.lower():
            if "<head>" in html:
                html = html.replace("<head>", f'<head>\n<base href="{base_href}">\n', 1)
            elif "<head " in html:
                html = re.sub(
                    r"(<head[^>]*>)",
                    rf'\1\n<base href="{base_href}">\n',
                    html,
                    count=1,
                )
        return html

    @staticmethod
    def _snapshot_nodes_by_id(
        snapshot_nodes: list[IframeDocumentSnapshotNode],
    ) -> dict[str, dict[str, Any]]:
        nodes_by_id: dict[str, dict[str, Any]] = {}
        for node in snapshot_nodes:
            design_id = (getattr(node, "designId", "") or "").strip()
            if not design_id:
                continue
            nodes_by_id[design_id] = {
                "designId": design_id,
                "tagName": (getattr(node, "tagName", "") or "").strip().lower(),
                "className": (getattr(node, "className", "") or "").strip(),
                "id": (getattr(node, "id", "") or "").strip(),
                "textContent": (getattr(node, "textContent", "") or "").strip(),
                "attributes": getattr(node, "attributes", {}) or {},
                "parentDesignId": (getattr(node, "parentDesignId", "") or "").strip() or None,
                "childDesignIds": [
                    child
                    for child in (getattr(node, "childDesignIds", None) or [])
                    if isinstance(child, str) and child
                ],
                "html": getattr(node, "html", "") or "",
            }
        return nodes_by_id

    def _build_snapshot_desc(self, snapshot_nodes: list[IframeDocumentSnapshotNode]) -> str:
        lines = [f"- nodes: {len(snapshot_nodes)}"]
        for node in snapshot_nodes[:12]:
            design_id = (getattr(node, "designId", "") or "")[:80]
            tag = (getattr(node, "tagName", "") or "")[:40]
            class_name = (getattr(node, "className", "") or "")[:100]
            text = (getattr(node, "textContent", "") or "")[:140]
            lines.append(f"- {design_id}: <{tag}> class='{class_name}' text='{text}'")
        return "\n".join(lines)

    @staticmethod
    def _build_selected_desc(selected: Optional[ElementInfoRequest]) -> str:
        if not selected:
            return "(none)"
        computed_summary = ""
        computed = selected.computedStyles if isinstance(selected.computedStyles, dict) else {}
        if computed:
            picked = {}
            for key in (
                "backgroundColor",
                "color",
                "fontSize",
                "fontWeight",
                "padding",
                "margin",
            ):
                value = computed.get(key)
                if isinstance(value, str) and value.strip():
                    picked[key] = value.strip()
            if picked:
                computed_summary = json.dumps(picked, ensure_ascii=False)[:400]
        lines = [
            f"- designId: {selected.designId}",
            f"- tag: {selected.tagName}",
            f"- class: {(selected.className or '')[:200]}",
            f"- text: {(selected.textContent or '')[:200]}",
        ]
        if computed_summary:
            lines.append(f"- computedStyles: {computed_summary}")
        return "\n".join(lines)

    def _build_selected_subtree_hint(
        self,
        *,
        snapshot_nodes: list[IframeDocumentSnapshotNode],
        selected_design_id: Optional[str],
        max_nodes: int = 28,
    ) -> str:
        root_id = (selected_design_id or "").strip()
        if not root_id:
            return ""
        nodes_by_id = self._snapshot_nodes_by_id(snapshot_nodes)
        if root_id not in nodes_by_id:
            return ""

        queue = [root_id]
        visited: set[str] = set()
        collected: list[dict[str, Any]] = []
        while queue and len(collected) < max_nodes:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            node = nodes_by_id.get(current)
            if not node:
                continue
            collected.append(node)
            for child in node.get("childDesignIds") or []:
                if isinstance(child, str) and child and child not in visited:
                    queue.append(child)

        lines: list[str] = []
        for node in collected:
            design_id = node.get("designId") or ""
            tag = node.get("tagName") or ""
            class_name = (node.get("className") or "")[:140]
            text = (node.get("textContent") or "")[:140]
            html = (node.get("html") or "").lower()
            has_svg = "<svg" in html or tag == "svg"
            lines.append(
                f"- {design_id}: <{tag}> class='{class_name}' text='{text}' has_svg={has_svg}"
            )
        return "\n".join(lines)

    async def _normalize_iframe_plan_operations(
        self,
        *,
        operations: Any,
        snapshot_nodes: list[IframeDocumentSnapshotNode],
        icon_svg_tool: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(operations, list):
            return []
        nodes_by_id = self._snapshot_nodes_by_id(snapshot_nodes)
        normalized: list[dict[str, Any]] = []

        for raw in operations:
            if not isinstance(raw, dict):
                continue
            op_type = raw.get("op")
            design_id = raw.get("design_id") or raw.get("designId") or raw.get("designID")
            if not isinstance(op_type, str) or not isinstance(design_id, str):
                continue
            op_type = op_type.strip()
            design_id = design_id.strip()
            if not op_type or not design_id or design_id not in nodes_by_id:
                continue

            item: dict[str, Any] = {"op": op_type, "design_id": design_id}
            if op_type == "set_style":
                prop = raw.get("property")
                if not isinstance(prop, str) or not prop.strip():
                    continue
                item["property"] = prop.strip()
                item["value"] = raw.get("value") if isinstance(raw.get("value"), str) else ""
                normalized.append(item)
                continue
            if op_type == "set_text":
                item["text"] = raw.get("text") if isinstance(raw.get("text"), str) else ""
                normalized.append(item)
                continue
            if op_type == "set_icon":
                icon_name = raw.get("icon_name") or raw.get("iconName") or raw.get("name")
                if not isinstance(icon_name, str) or not icon_name.strip():
                    continue
                svg_inner = raw.get("svg_inner") or raw.get("svgInner")
                if isinstance(svg_inner, str) and svg_inner.strip():
                    svg_inner = svg_inner.replace('\\"', '"').replace("\\'", "'")
                else:
                    icon_svg_result = await ChatToolService.execute_tool(
                        tool_call_id=f"design-mode-{uuid.uuid4().hex}",
                        tool_name=icon_svg_tool.name,
                        tool_input=json.dumps(
                            {"name": icon_name},
                            ensure_ascii=False,
                            default=str,
                        ),
                        tool_registry={icon_svg_tool.name: icon_svg_tool},
                    )
                    icon_svg_payload = self._tool_result_value(icon_svg_result)
                    svg_inner = (
                        icon_svg_payload.get("svg_inner")
                        if isinstance(icon_svg_payload, dict)
                        else None
                    )
                if not isinstance(svg_inner, str) or not svg_inner.strip():
                    continue
                if len(svg_inner) > 20000:
                    continue
                item["icon_name"] = icon_name.strip()
                item["svg_inner"] = svg_inner
                normalized.append(item)
                continue
            if op_type == "move":
                anchor = raw.get("anchor")
                if not isinstance(anchor, str) or not anchor.strip():
                    continue
                anchor = anchor.strip()
                if anchor.startswith("before:") or anchor.startswith("after:"):
                    target_id = anchor.split(":", 1)[1].strip()
                    if not target_id or target_id not in nodes_by_id:
                        continue
                item["anchor"] = anchor
                normalized.append(item)
                continue
            if op_type == "swap":
                target = raw.get("target_design_id") or raw.get("targetDesignId")
                if not isinstance(target, str) or not target.strip() or target not in nodes_by_id:
                    continue
                item["target_design_id"] = target.strip()
                normalized.append(item)
                continue

        return normalized

    async def _sync_design_changes_internal(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: SyncRequest,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[SyncResponse, set[int]]:
        await self._get_session_for_request(
            db,
            session_id=request.session_id,
            user_id=user_id,
        )

        total = len(request.changes)
        if total == 0:
            return SyncResponse(success=True, applied=0, errors=[]), set()

        session_uuid = request.session_id
        if not isinstance(session_uuid, uuid.UUID):
            raise DesignValidationError("Invalid session_id")

        sandbox = await self._sandbox_service.get_sandbox_by_session_id(db, session_id=session_uuid)
        if not sandbox:
            try:
                sandbox = await self._sandbox_service.get_sandbox_by_session(
                    db,
                    session_id=session_uuid,
                    user_id=user_id,
                )
            except Exception as exc:
                raise DesignSandboxUnavailableError(
                    f"No active sandbox found for session {request.session_id}"
                ) from exc

        try:
            _effective_progress = on_progress or (
                (lambda **payload: self._emit_sync_progress(db, **payload))
                if self._event_service
                else None
            )
            applied, errors, remaining_changes = await apply_changes_with_source_mapping(
                sandbox=sandbox,
                changes=request.changes,
                session_id=session_uuid,
                emit_progress=_effective_progress,
            )
        except Exception as exc:
            errors = [f"Deterministic source mapping sync failed: {exc}"]
            failed_indexes = set(range(total))
            _error_progress = _effective_progress
            if _error_progress:
                await _error_progress(
                    session_id=session_uuid,
                    processed=total,
                    total=total,
                    applied=0,
                    errors=len(errors),
                    current=None,
                    done=True,
                )
            return SyncResponse(success=False, applied=0, errors=errors), failed_indexes

        failed_indexes = self._resolve_failed_sync_indexes(
            changes=request.changes,
            remaining_changes=remaining_changes if isinstance(remaining_changes, list) else [],
        )
        if not isinstance(applied, int):
            applied = max(0, total - len(failed_indexes))
        if not isinstance(errors, list):
            errors = [str(errors)]

        return (
            SyncResponse(success=(applied == total and not errors), applied=applied, errors=errors),
            failed_indexes,
        )

    def _resolve_failed_sync_indexes(
        self,
        *,
        changes: list[StyleChange],
        remaining_changes: list[Any],
    ) -> set[int]:
        if not remaining_changes:
            return set()

        failed_indexes: set[int] = set()
        remaining_id_counts: dict[int, int] = defaultdict(int)
        for change in remaining_changes:
            remaining_id_counts[id(change)] += 1
        for idx, change in enumerate(changes):
            change_id = id(change)
            if remaining_id_counts.get(change_id, 0) > 0:
                failed_indexes.add(idx)
                remaining_id_counts[change_id] -= 1

        if len(failed_indexes) == len(remaining_changes):
            return failed_indexes

        failed_indexes.clear()
        remaining_fingerprint_counts: dict[str, int] = defaultdict(int)
        for change in remaining_changes:
            remaining_fingerprint_counts[self._sync_change_fingerprint(change)] += 1
        for idx, change in enumerate(changes):
            fingerprint = self._sync_change_fingerprint(change)
            if remaining_fingerprint_counts.get(fingerprint, 0) > 0:
                failed_indexes.add(idx)
                remaining_fingerprint_counts[fingerprint] -= 1
        return failed_indexes

    @staticmethod
    def _sync_change_fingerprint(change: Any) -> str:
        try:
            if hasattr(change, "model_dump"):
                payload = change.model_dump()
            elif hasattr(change, "dict"):
                payload = change.dict()
            elif isinstance(change, dict):
                payload = change
            else:
                payload = {
                    "designId": getattr(change, "designId", None),
                    "type": getattr(change, "type", None),
                    "property": getattr(change, "property", None),
                    "value": getattr(change, "value", None),
                }
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return repr(change)

    async def _build_sync_workspace_roots_text(self, sandbox: Any) -> str:
        try:
            output = await sandbox.run_command("ls -1 /workspace 2>/dev/null || true")
        except Exception:
            output = ""
        roots = []
        for line in (output or "").splitlines():
            entry = line.strip()
            if entry:
                roots.append(entry)
        if roots:
            formatted = "\n".join(f"- {name}" for name in roots[:30])
        else:
            formatted = "- (unable to list /workspace)"
        return f"Top-level directories under `/workspace`:\n{formatted}"

    async def _build_source_hints_for_changes(
        self,
        sandbox: Any,
        changes: list[StyleChange],
    ) -> dict[int, str]:
        hints: dict[int, str] = {}
        for index, change in enumerate(changes, start=1):
            queries = self._extract_source_search_queries(change)
            best_match: Optional[tuple[str, int]] = None
            for query in queries[:4]:
                matches = await self._search_workspace_query(sandbox, query=query)
                if matches:
                    best_match = matches[0]
                    break
            if not best_match:
                continue
            candidate_file, line_no = best_match
            snippet = await self._read_source_snippet(
                sandbox,
                file_path=candidate_file,
                line_no=line_no,
            )
            hint_lines = [f"- candidate_file: {candidate_file}"]
            if line_no > 0:
                hint_lines.append(f"- match_line: {line_no}")
            if snippet:
                compact = re.sub(r"\s+", " ", snippet).strip()[:900]
                hint_lines.append(f"- snippet: {compact}")
            hints[index] = "\n".join(hint_lines)
        return hints

    @staticmethod
    def _extract_source_search_queries(change: StyleChange) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            if not isinstance(value, str):
                return
            text = value.strip()
            if not text or text.lower() == "n/a":
                return
            if text in seen:
                return
            seen.add(text)
            queries.append(text)

        add(change.designId)
        ctx = change.elementContext
        if ctx:
            add(ctx.designId)
            add(ctx.id)
            add(ctx.textContent)
            add(ctx.contextText)
            add(ctx.prevSiblingText)
            add(ctx.nextSiblingText)
            add(ctx.className)
            attrs = ctx.attributes or {}
            if isinstance(attrs, dict):
                for key in (
                    "aria-label",
                    "aria-labelledby",
                    "title",
                    "placeholder",
                    "alt",
                    "name",
                    "value",
                    "href",
                ):
                    add(attrs.get(key))

        if isinstance(change.value, dict):
            add(change.value.get("to"))
            add(change.value.get("from"))
        return queries

    async def _search_workspace_query(
        self,
        sandbox: Any,
        *,
        query: str,
    ) -> list[tuple[str, int]]:
        quoted = shlex.quote(query)
        cmd = (
            "if command -v rg >/dev/null 2>&1; then "
            "rg --no-heading -n -F --hidden "
            "--glob '!**/node_modules/**' "
            "--glob '!**/.git/**' "
            "--glob '!**/dist/**' "
            "--glob '!**/build/**' "
            "--glob '!**/.next/**' "
            f"{quoted} /workspace | head -n 20 || true; "
            "else "
            "grep -R -n -F "
            "--exclude-dir=node_modules "
            "--exclude-dir=.git "
            "--exclude-dir=dist "
            "--exclude-dir=build "
            "--exclude-dir=.next "
            f"-e {quoted} /workspace | head -n 20 || true; "
            "fi"
        )
        try:
            output = await sandbox.run_command(cmd)
        except Exception:
            return []
        return self._parse_search_lines(output or "")

    @staticmethod
    def _parse_search_lines(output: str) -> list[tuple[str, int]]:
        matches: list[tuple[str, int]] = []
        for line in (output or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            found = re.match(r"^(?P<path>/[^:]+):(?P<line>\d+):", stripped)
            if not found:
                continue
            try:
                line_no = int(found.group("line"))
            except Exception:
                continue
            matches.append((found.group("path"), line_no))
        matches.sort(key=lambda item: (len(item[0]), item[0]))
        return matches

    async def _read_source_snippet(
        self,
        sandbox: Any,
        *,
        file_path: str,
        line_no: int,
    ) -> Optional[str]:
        try:
            content = await sandbox.read_file(file_path)
        except Exception:
            return None
        if not isinstance(content, str) or not content:
            return None
        lines = content.splitlines()
        if not lines:
            return None
        idx = max(0, min(len(lines) - 1, line_no - 1))
        start = max(0, idx - 2)
        end = min(len(lines), idx + 3)
        snippet = "\n".join(lines[start:end]).strip()
        return snippet or None

    def _build_sync_changes_text(
        self,
        changes: list[StyleChange],
        *,
        source_hints: dict[int, str],
    ) -> str:
        blocks: list[str] = []
        for index, change in enumerate(changes, start=1):
            ctx = change.elementContext
            to_value = ""
            from_value = ""
            if isinstance(change.value, dict):
                maybe_to = change.value.get("to")
                maybe_from = change.value.get("from")
                if isinstance(maybe_to, str):
                    to_value = maybe_to
                if isinstance(maybe_from, str):
                    from_value = maybe_from

            lines = [
                f"Change {index}:",
                f"- change_index: {index}",
                f"- design_id: {change.designId}",
                f"- type: {change.type}",
                f"- property: {change.property}",
                f"- from: {from_value[:300]}",
                f"- to: {to_value[:300]}",
            ]
            if ctx:
                lines.extend(
                    [
                        f"- element_tag: {ctx.tagName}",
                        f"- element_id: {(ctx.id or '')[:120]}",
                        f"- class_name: {(ctx.className or '')[:200]}",
                        f"- text_content: {(ctx.textContent or '')[:220]}",
                        f"- xpath: {(ctx.xpath or '')[:220]}",
                    ]
                )
            source_hint = source_hints.get(index)
            if source_hint:
                lines.append("- source_hint:")
                lines.append(source_hint)
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    async def _apply_sync_plan(
        self,
        *,
        sandbox: Any,
        changes: list[StyleChange],
        plan_entries: list[Any],
    ) -> tuple[int, list[str], set[int]]:
        by_index: dict[int, dict[str, Any]] = {}
        for entry in plan_entries:
            if not isinstance(entry, dict):
                continue
            raw_index = entry.get("change_index")
            if not isinstance(raw_index, int):
                continue
            by_index[raw_index] = entry

        applied = 0
        errors: list[str] = []
        failed_indexes: set[int] = set()

        for index, _change in enumerate(changes, start=1):
            entry = by_index.get(index)
            if not entry:
                errors.append(f"Change {index}: Missing plan entry from AI.")
                failed_indexes.add(index - 1)
                continue

            file_path = entry.get("file_path")
            modifications = entry.get("modifications")
            if (
                not isinstance(file_path, str)
                or not file_path.strip()
                or not file_path.strip().startswith("/workspace/")
            ):
                errors.append(f"Change {index}: Invalid file_path in plan.")
                failed_indexes.add(index - 1)
                continue
            if not isinstance(modifications, list) or not modifications:
                errors.append(f"Change {index}: Empty modifications in plan.")
                failed_indexes.add(index - 1)
                continue

            ok, reason = await self._apply_replace_modifications(
                sandbox=sandbox,
                file_path=file_path.strip(),
                modifications=modifications,
            )
            if ok:
                applied += 1
                continue
            errors.append(f"Change {index}: {reason}")
            failed_indexes.add(index - 1)

        return applied, errors, failed_indexes

    async def _apply_replace_modifications(
        self,
        *,
        sandbox: Any,
        file_path: str,
        modifications: list[Any],
    ) -> tuple[bool, str]:
        try:
            content = await sandbox.read_file(file_path)
        except Exception as exc:
            return False, f"Failed to read {file_path}: {exc}"
        if not isinstance(content, str):
            return False, f"File is not text: {file_path}"

        updated = content
        for modification in modifications:
            if not isinstance(modification, dict):
                return False, "Modification entry must be an object."
            mod_type = modification.get("type")
            old = modification.get("old")
            new = modification.get("new")
            if mod_type != "replace":
                return False, "Only replace modifications are supported."
            if not isinstance(old, str) or not isinstance(new, str):
                return False, "replace modifications require string old/new."
            if not old:
                return False, "replace old cannot be empty."
            if old not in updated:
                return False, f"Target substring not found in {file_path}."
            updated = updated.replace(old, new, 1)

        if updated == content:
            return False, "No effective file change generated."

        try:
            await sandbox.write_file(file_path, updated)
        except Exception as exc:
            return False, f"Failed to write {file_path}: {exc}"
        return True, ""

    async def _emit_sync_summary(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        summary: str,
    ) -> str:
        sync_event = AgentResponseEvent(
            session_id=session_id,
            content={"text": summary},
        )
        saved = await self._event_service.save_event(
            db,
            session_id=session_id,
            event=sync_event,
        )
        return str(saved.id)

    async def _emit_sync_progress(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        processed: int,
        total: int,
        applied: int,
        errors: int,
        current: Optional[int],
        done: bool,
    ) -> None:
        progress_payload = {
            "processed": processed,
            "total": total,
            "applied": applied,
            "errors": errors,
            "current": current,
            "done": done,
        }
        content = {
            "operation": "design_mode_sync",
            # Keep legacy payload shape expected by the frontend listener.
            "progress": progress_payload,
            # Keep flat fields for compatibility with newer consumers.
            **progress_payload,
        }
        progress_event = AgentStatusUpdateEvent(
            session_id=session_id,
            content=content,
        )
        await self._event_service.save_event(
            db,
            session_id=session_id,
            event=progress_event,
        )
        await self._event_service.emit_event(progress_event)

    @staticmethod
    def _parse_persisted_design_changes(raw_changes: Any) -> list[StyleChange]:
        if not isinstance(raw_changes, list):
            return []
        parsed: list[StyleChange] = []
        for item in raw_changes:
            if not isinstance(item, dict):
                continue
            try:
                parsed.append(StyleChange.model_validate(item))
            except Exception:
                continue
        parsed.sort(key=lambda change: int(getattr(change, "timestamp", 0) or 0))
        return parsed

    @staticmethod
    def _parse_design_request(
        user_request: str,
        current_styles: dict[str, Any],
    ) -> tuple[list[dict[str, str]], str]:
        request_lower = (user_request or "").lower()
        changes: list[dict[str, str]] = []
        explanation = ""

        color_keywords = {
            "red": "#ef4444",
            "blue": "#3b82f6",
            "green": "#22c55e",
            "yellow": "#eab308",
            "purple": "#a855f7",
            "pink": "#ec4899",
            "orange": "#f97316",
            "white": "#ffffff",
            "black": "#000000",
            "gray": "#6b7280",
            "grey": "#6b7280",
        }

        for color_name, color_value in color_keywords.items():
            if color_name in request_lower:
                if any(word in request_lower for word in ("background", "bg")):
                    changes.append({"property": "background-color", "value": color_value})
                    explanation = f"Changed background color to {color_name}"
                elif (
                    any(word in request_lower for word in ("text", "font", "color"))
                    or "make" in request_lower
                ):
                    changes.append({"property": "color", "value": color_value})
                    explanation = f"Changed text color to {color_name}"
                else:
                    changes.append({"property": "background-color", "value": color_value})
                    explanation = f"Changed background color to {color_name}"
                break

        if any(word in request_lower for word in ("bigger", "larger", "increase size")):
            current_size = str((current_styles or {}).get("fontSize", "16px"))
            try:
                size_val = int(current_size.replace("px", ""))
                new_size = min(size_val + 4, 72)
                changes.append({"property": "font-size", "value": f"{new_size}px"})
                explanation = f"Increased font size to {new_size}px"
            except Exception:
                changes.append({"property": "font-size", "value": "20px"})
                explanation = "Increased font size"

        if any(word in request_lower for word in ("smaller", "decrease size", "reduce")):
            current_size = str((current_styles or {}).get("fontSize", "16px"))
            try:
                size_val = int(current_size.replace("px", ""))
                new_size = max(size_val - 4, 8)
                changes.append({"property": "font-size", "value": f"{new_size}px"})
                explanation = f"Decreased font size to {new_size}px"
            except Exception:
                changes.append({"property": "font-size", "value": "12px"})
                explanation = "Decreased font size"

        if any(word in request_lower for word in ("bold", "bolder")):
            changes.append({"property": "font-weight", "value": "700"})
            explanation = "Made text bold"

        if "padding" in request_lower:
            if any(word in request_lower for word in ("more", "increase", "add")):
                changes.append({"property": "padding", "value": "16px"})
                explanation = "Increased padding"
            elif any(word in request_lower for word in ("less", "decrease", "remove")):
                changes.append({"property": "padding", "value": "4px"})
                explanation = "Decreased padding"

        if any(word in request_lower for word in ("round", "rounded", "radius")):
            changes.append({"property": "border-radius", "value": "8px"})
            explanation = "Added rounded corners"

        if "center" in request_lower:
            changes.append({"property": "text-align", "value": "center"})
            explanation = "Centered the text"

        if not changes:
            explanation = (
                f"I understood your request: '{user_request}'. "
                "Try being more specific like 'make it red' or 'increase font size'."
            )

        return changes, explanation
