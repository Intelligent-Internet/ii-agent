"""Registry for command handlers."""

from __future__ import annotations

from typing import Dict

from ii_agent.core.container import ApplicationContainer
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.handlers.query import UserQueryHandler
from ii_agent.realtime.handlers.plan import PlanHandler
from ii_agent.realtime.handlers.publish import PublishProjectHandler
from ii_agent.realtime.handlers.cloud_run_publish import CloudRunPublishHandler
from ii_agent.realtime.handlers.sandbox_status import SandboxStatusHandler
from ii_agent.realtime.handlers.awake_sandbox import AwakeSandboxHandler
from ii_agent.realtime.handlers.workspace_info import WorkspaceInfoHandler
from ii_agent.realtime.handlers.ping import PingHandler
from ii_agent.realtime.handlers.cancel import CancelHandler
from ii_agent.realtime.handlers.continue_run import ContinueRunHandler
from ii_agent.realtime.handlers.enhance_prompt import EnhancePromptHandler
from ii_agent.realtime.handlers.save_env import SaveEnvHandler
from ii_agent.realtime.handlers.start_fork import StartForkHandler
from ii_agent.realtime.handlers.submit_testflight import SubmitTestflightHandler
from ii_agent.realtime.handlers.apple_auth import (
    AppleAuthLoginHandler,
    AppleAuth2FAHandler,
    AppleAuthSelectTeamHandler,
    AppleCheckAuthHandler,
    SaveExpoTokenHandler,
)
from ii_agent.realtime.handlers.apple_app_setup import (
    AppleAppSetupHandler,
    AppleListAppsHandler,
)
from ii_agent.realtime.handlers.file_tree_handler import FileTreeHandler
from ii_agent.realtime.handlers.file_content_handler import FileContentHandler
from ii_agent.realtime.handlers.design_get_state import DesignGetStateHandler
from ii_agent.realtime.handlers.design_save_state import DesignSaveStateHandler
from ii_agent.realtime.handlers.design_sync_state import DesignSyncStateHandler
from ii_agent.realtime.handlers.slide_deck_sync_state import SlideDeckSyncStateHandler
from ii_agent.realtime.handlers.cowork_query import CoworkQueryHandler
from ii_agent.realtime.handlers.cowork_continue_run import CoworkContinueRunHandler


class CommandHandlerFactory:
    """Registry for managing command handlers."""

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        self._pubsub = pubsub
        self._container = container
        self._handlers: Dict[CommandType, BaseCommandHandler] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if not self._initialized:
            self._initialize_handlers()
            self._initialized = True

    def _initialize_handlers(self) -> None:
        ps = self._pubsub
        ct = self._container

        query_handler = UserQueryHandler(pubsub=ps, container=ct)

        self._handlers = {
            CommandType.QUERY: query_handler,
            CommandType.COWORK_QUERY: CoworkQueryHandler(pubsub=ps, container=ct),
            CommandType.PLAN: PlanHandler(pubsub=ps, container=ct),
            CommandType.SANDBOX_STATUS: SandboxStatusHandler(pubsub=ps, container=ct),
            CommandType.AWAKE_SANDBOX: AwakeSandboxHandler(pubsub=ps, container=ct),
            CommandType.WORKSPACE_INFO: WorkspaceInfoHandler(pubsub=ps),
            CommandType.PING: PingHandler(pubsub=ps, container=ct),
            CommandType.CANCEL: CancelHandler(pubsub=ps, container=ct),
            CommandType.CONTINUE_RUN: ContinueRunHandler(pubsub=ps, container=ct),
            CommandType.COWORK_CONTINUE_RUN: CoworkContinueRunHandler(pubsub=ps, container=ct),
            CommandType.ENHANCE_PROMPT: EnhancePromptHandler(pubsub=ps, container=ct),
            CommandType.PUBLISH_PROJECT: PublishProjectHandler(pubsub=ps, container=ct),
            CommandType.PUBLISH_CLOUD_RUN: CloudRunPublishHandler(pubsub=ps, container=ct),
            CommandType.SAVE_ENV: SaveEnvHandler(pubsub=ps, container=ct),
            CommandType.START_FORK: StartForkHandler(
                pubsub=ps,
                query_handler=query_handler,
                container=ct,
            ),
            CommandType.SUBMIT_TESTFLIGHT: SubmitTestflightHandler(pubsub=ps, container=ct),
            CommandType.APPLE_AUTH_LOGIN: AppleAuthLoginHandler(pubsub=ps, container=ct),
            CommandType.APPLE_AUTH_2FA: AppleAuth2FAHandler(pubsub=ps, container=ct),
            CommandType.APPLE_AUTH_SELECT_TEAM: AppleAuthSelectTeamHandler(pubsub=ps, container=ct),
            CommandType.APPLE_APP_SETUP: AppleAppSetupHandler(pubsub=ps, container=ct),
            CommandType.APPLE_LIST_APPS: AppleListAppsHandler(pubsub=ps, container=ct),
            CommandType.APPLE_CHECK_AUTH: AppleCheckAuthHandler(pubsub=ps, container=ct),
            CommandType.SAVE_EXPO_TOKEN: SaveExpoTokenHandler(pubsub=ps, container=ct),
            CommandType.FILE_TREE: FileTreeHandler(pubsub=ps, container=ct),
            CommandType.FILE_CONTENT: FileContentHandler(pubsub=ps, container=ct),
            CommandType.DESIGN_GET_STATE: DesignGetStateHandler(pubsub=ps, container=ct),
            CommandType.DESIGN_SAVE_STATE: DesignSaveStateHandler(pubsub=ps, container=ct),
            CommandType.DESIGN_SYNC_STATE: DesignSyncStateHandler(pubsub=ps, container=ct),
            CommandType.SLIDE_DECK_SYNC_STATE: SlideDeckSyncStateHandler(pubsub=ps, container=ct),
        }

    def get_handler(self, command_type: CommandType) -> BaseCommandHandler | None:
        return self._handlers.get(command_type)

    def get_handler_by_string(self, command_type_str: str) -> BaseCommandHandler | None:
        try:
            return self.get_handler(CommandType(command_type_str))
        except ValueError:
            return None
