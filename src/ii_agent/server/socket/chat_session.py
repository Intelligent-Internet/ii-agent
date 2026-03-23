from dataclasses import dataclass
import logging
from typing import Optional, TYPE_CHECKING


from ii_agent.controller.agent_controller import AgentController
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.event import AgentStatus, RealtimeEvent, EventType
from ii_agent.core.event_stream import AsyncEventStream, EventStream
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.server.models.messages import QueryCommandContent
from ii_agent.server.models.sessions import SessionInfo
from ii_agent.storage import BaseStorage
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.sandbox.ii_sandbox import IISandbox
from ii_agent.server.messages import UserMessageHook
from ii_agent.server.slides.content_hook import SlideContentHook
from ii_agent.server.slides.init_project_hook import InitProjectHook
from ii_agent.storage.factory import create_storage_client
from ii_tool.tools.base import ToolResult

if TYPE_CHECKING:
    from ii_agent.server.models.messages import QueryContentInternal


logger = logging.getLogger(__name__)


@dataclass
class ChatSessionContext:
    """Manages a single standalone chat session with its own agent, workspace, and message handling."""

    workspace_manager: WorkspaceManager
    file_store: BaseStorage
    config: IIAgentConfig
    session_info: SessionInfo
    llm_config: LLMConfig
    # Session state
    agent_controller: AgentController
    event_stream: EventStream
    first_message: bool = True
    sandbox: Optional[IISandbox] = None
    session_metadata: Optional[dict] = None
    vscode_url: Optional[str] = None

    def __post_init__(self):
        """Initialize runtime state after dataclass initialization."""
        self._register_user_message_hook()
        self._register_slide_hook_if_needed()
        self._register_project_init_hook()

    def get_sandbox(self) -> IISandbox:
        if not self.sandbox:
            raise ValueError("Sandbox not initialized")
        return self.sandbox

    def _register_slide_hook_if_needed(self) -> None:
        """Register slide content hook if custom domain is configured and sandbox is available."""
        if not self.sandbox:
            return

        if not self.config.custom_domain:
            return

        if hasattr(self, "_slide_hook_registered"):
            return

        try:
            # Use slide assets bucket if configured, otherwise fall back to file upload bucket
            project_id = (
                self.config.slide_assets_project_id
                or self.config.file_upload_project_id
            )
            bucket_name = (
                self.config.slide_assets_bucket_name
                or self.config.file_upload_bucket_name
            )

            slide_storage = create_storage_client(
                self.config.storage_provider,
                project_id,  # type: ignore
                bucket_name,  # type: ignore
                self.config.custom_domain,
            )
            slide_hook = SlideContentHook(slide_storage, self.sandbox)
            if self.event_stream:
                self.event_stream.register_hook(slide_hook)
            self._slide_hook_registered = True
            logger.info(
                f"Registered slide content hook for session {self.session_info.id}"
            )
        except Exception as e:
            logger.error(f"Failed to register slide content hook: {e}")

    def _register_user_message_hook(self) -> None:
        """Register message hook to upload attachments to object storage."""
        if not self.sandbox or not self.event_stream:
            return

        if hasattr(self, "_user_message_hook_registered"):
            return

        try:
            project_id = (
                self.config.slide_assets_project_id
                or self.config.file_upload_project_id
            )
            bucket_name = (
                self.config.slide_assets_bucket_name
                or self.config.file_upload_bucket_name
            )
            storage = create_storage_client(
                self.config.storage_provider,
                project_id,  # type: ignore
                bucket_name, # type: ignore
                self.config.custom_domain,
            )
            message_hook = UserMessageHook(storage, self.sandbox)
            self.event_stream.register_hook(message_hook)
            self._user_message_hook_registered = True
            logger.info(
                f"Registered user message hook for session {self.session_info.id}"
            )
        except Exception as e:
            logger.error(f"Failed to register user message hook: {e}")

    def _register_project_init_hook(self) -> None:
        """Register hook that persists project metadata for init tool."""
        if not self.event_stream:
            return

        if hasattr(self, "_project_init_hook_registered"):
            return

        init_project_hook = InitProjectHook()
        self.event_stream.register_hook(init_project_hook)
        self._project_init_hook_registered = True

    async def arun(self, query_content: "QueryContentInternal") -> ToolResult:
        """Run the agent asynchronously with the given query content."""
        try:
            # Add user message and run agent
            return await self.agent_controller.run_agent_async(
                instruction=query_content.text,
                files=query_content.file_upload_paths,
                resume=query_content.resume,
                images_data=query_content.images_data,
            )

        except Exception as e:
            error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
            logger.error(f"Error running agent: {error_msg}", exc_info=True)
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.ERROR,
                    session_id=self.session_info.id,
                    content={"message": f"Error running agent: {error_msg}"},
                )
            )
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.STATUS_UPDATE,
                    session_id=self.session_info.id,
                    content={"status": AgentStatus.READY},
                )
            )
            return ToolResult(llm_content=[], is_error=True)

        finally:
            self.agent_controller.state.save_to_session(
                str(self.session_info.id), self.file_store
            )

            logger.info(f"Saved session state for session {self.session_info.id}")

    async def cleanup(self):
        """Clean up resources associated with this session."""

        self.agent_controller.cancel()

        # Clean up event stream subscribers
        if self.event_stream:
            self.event_stream.clear_subscribers()
            self.event_stream.clear_hooks()

        self.agent_controller = None
