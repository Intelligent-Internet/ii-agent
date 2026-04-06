"""Centralized service container — single source of truth for service wiring.

Created once in ``ii_agent.app.lifespan`` after secrets are loaded and stored
on ``app.state.container``.  All consumers — FastAPI ``Depends()``, socket
handlers, subscribers, cron tasks — ultimately read services from here.

**Container-primary pattern:**

* ``ServiceContainer.create()`` instantiates all repositories and services
  directly (no factory-function imports from ``dependencies.py``).
* Domain ``dependencies.py`` files are *thin accessors* that pull from the
  container via ``ContainerDep``, so wiring logic lives in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import SecretStr

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.settings.llm import Provider
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.redis.client import get_redis_client
from ii_agent.core.redis.cache import TypedEntityCache, get_entity_cache

# ── Repository classes ────────────────────────────────────────────────────
from ii_agent.users.repository import APIKeyRepository, UserRepository
from ii_agent.users.waitlist_repository import WaitlistRepository
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.pin.repository import PinRepository
from ii_agent.sessions.wishlist.repository import WishlistRepository
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.files.repository import FileRepository
from ii_agent.tasks.repository import RunTaskRepository, TaskLogRepository
from ii_agent.settings.llm.repository import ModelSettingRepository
from ii_agent.settings.mcp.repository import MCPSettingRepository
from ii_agent.settings.skills.repository import SkillRepository
from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.deployments.repository import DeploymentsRepository
from ii_agent.projects.design.repository import ProjectDesignRepository
from ii_agent.projects.subdomains.repository import SubdomainRepository
from ii_agent.integrations.connectors.repository import ConnectorRepository
from ii_agent.integrations.connectors.composio.repository import ComposioProfileRepository
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.slides.repository import SlideContentRepository
from ii_agent.content.slides.templates.repository import SlideTemplateRepository
from ii_agent.content.slides.nano_banana.repository import NanoBananaRepository
from ii_agent.content.slides.design.repository import SlideDesignRepository
from ii_agent.credits.repository import CreditBalanceRepository, CreditTransactionRepository
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.memory.repository import MemoryRepository
from ii_agent.memory.cache_service import MemoryCacheService
from ii_agent.memory.service import MemoryService

# ── Schema classes (for TypedEntityCache) ────────────────────────────────
from ii_agent.tasks.schemas import RunTaskResponse
from ii_agent.users.schemas import UserResponse

# ── Service classes ───────────────────────────────────────────────────────
from ii_agent.users.service import UserService
from ii_agent.billing.service import BillingService
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.fork_service import SessionForkService
from ii_agent.sessions.pin.service import SessionPinService
from ii_agent.sessions.wishlist.service import SessionWishlistService
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.core.config.session_title import SessionTitleConfig
from ii_agent.files.service import FileService
from ii_agent.tasks.service import RunTaskService
from ii_agent.settings.llm.service import ModelSettingService
from ii_agent.settings.mcp.service import MCPSettingService
from ii_agent.settings.skills.service import SkillService
from ii_agent.projects.service import ProjectService
from ii_agent.projects.deployments.service import DeploymentsService
from ii_agent.projects.subdomains.service import SubdomainService
from ii_agent.projects.deployment_orchestration_service import DeploymentOrchestrationService
from ii_agent.integrations.connectors.service import ConnectorService
from ii_agent.integrations.connectors.composio.service import ComposioService
from ii_agent.integrations.connectors.composio.toolkit_service import ToolkitService
from ii_agent.integrations.connectors.composio.auth_config_service import AuthConfigService
from ii_agent.integrations.connectors.composio.connected_account_service import (
    ConnectedAccountService,
)
from ii_agent.integrations.connectors.composio.mcp_server_service import MCPServerService
from ii_agent.integrations.connectors.composio.cache_service import ComposioCacheService
from ii_agent.content.media.service import MediaTemplateService
from ii_agent.content.storybook.service import StorybookService
from ii_agent.content.storybook.edit_service import StorybookEditService
from ii_agent.content.storybook.export_service import StorybookExportService
from ii_agent.content.storybook.version_service import StorybookVersionService
from ii_agent.content.storybook.voice_service import StorybookVoiceService
from ii_agent.content.storybook.ai_edit_service import StorybookAIEditService
from ii_agent.content.slides.service import SlideService
from ii_agent.content.slides.templates.service import SlideTemplateService
from ii_agent.content.slides.nano_banana.service import NanoBananaService
from ii_agent.content.slides.design.service import SlideDesignService
from ii_agent.projects.design.service import ProjectDesignService
from ii_agent.chat.messages.service import MessageService
from ii_agent.credits.service import CreditService
from ii_agent.agents.sandboxes.live_terminal_service import LiveTerminalService
from ii_agent.agents.sandboxes.service import SandboxService
from ii_agent.agents.sandboxes.explorer import WorkspaceExplorer
from ii_agent.agents.plans.service import PlanService
from ii_agent.realtime.events.service import EventService

# ── Storage ───────────────────────────────────────────────────────────────
from ii_agent.core.storage.client import get_storage
from ii_agent.core.storage.service import StorageService
from ii_agent.core.storage.path_resolver import path_resolver


@dataclass
class ApplicationContainer:
    """Application-scoped service container.

    Every service is created once in :meth:`create` and made available as
    a read-only attribute.  Domain ``dependencies.py`` files access the
    container via ``ContainerDep`` and expose individual services as
    ``Annotated[SomeService, Depends(get_some_service)]``.
    """

    # ── Infrastructure ────────────────────────────────────────────────────
    config: Settings
    storage_service: StorageService

    # ── Domain services ───────────────────────────────────────────────────
    user_service: UserService
    billing_service: BillingService
    session_service: SessionService
    session_fork_service: SessionForkService
    session_title_service: SessionTitleService
    session_pin_service: SessionPinService
    session_wishlist_service: SessionWishlistService
    file_service: FileService
    run_task_service: RunTaskService
    model_setting_service: ModelSettingService
    mcp_setting_service: MCPSettingService
    skill_service: SkillService
    project_service: ProjectService
    deployments_service: DeploymentsService
    deployment_orchestration_service: DeploymentOrchestrationService
    subdomain_service: SubdomainService
    connector_service: ConnectorService
    composio_service: ComposioService
    media_template_service: MediaTemplateService
    storybook_service: StorybookService
    storybook_edit_service: StorybookEditService
    storybook_export_service: StorybookExportService
    storybook_version_service: StorybookVersionService
    storybook_voice_service: StorybookVoiceService
    storybook_ai_edit_service: StorybookAIEditService
    slide_service: SlideService
    slide_template_service: SlideTemplateService
    nano_banana_service: NanoBananaService
    slide_design_service: SlideDesignService
    project_design_service: ProjectDesignService
    message_service: MessageService
    credit_service: CreditService
    sandbox_service: SandboxService
    live_terminal_service: LiveTerminalService
    plan_service: PlanService
    event_service: EventService
    workspace_explorer_service: WorkspaceExplorer
    memory_service: MemoryService

    # ── Repositories (exposed for consumers that need direct repo access) ─
    event_repo: EventRepository = field(default_factory=EventRepository)

    @classmethod
    def init(cls) -> ApplicationContainer:
        """Wire all services with shared config.

        Call once, after GCP secrets have been applied to settings.
        """

        cfg = get_settings()
        storage_provider = get_storage()
        storage_svc = StorageService(provider=storage_provider, paths=path_resolver)

        # Caches (raw EntityCache for untyped, TypedEntityCache for single-model domains)
        redis_client = get_redis_client(redis_settings=cfg.redis)
        tasks_cache = TypedEntityCache(
            get_entity_cache(redis_client=redis_client, namespace="tasks", ttl=3600),
            RunTaskResponse,
        )
        users_cache = TypedEntityCache(
            get_entity_cache(redis_client=redis_client, namespace="users", ttl=3600),
            UserResponse,
        )
        sessions_cache = get_entity_cache(redis_client=redis_client, namespace="sessions", ttl=1800)
        composio_cache = get_entity_cache(
            redis_client=redis_client, namespace="composio", ttl=604800
        )
        media_cache = get_entity_cache(redis_client=redis_client, namespace="media", ttl=600)
        memory_cache_backend = get_entity_cache(
            redis_client=redis_client, namespace="memory", ttl=600
        )

        # Repositories
        user_repo = UserRepository()
        api_key_repo = APIKeyRepository()
        waitlist_repo = WaitlistRepository()
        session_repo = SessionRepository()
        event_repo = EventRepository()
        file_repo = FileRepository()
        run_task_repo = RunTaskRepository()
        task_log_repo = TaskLogRepository()
        model_setting_repo = ModelSettingRepository()
        mcp_setting_repo = MCPSettingRepository()
        skill_repo = SkillRepository()
        project_repo = ProjectRepository()
        deployments_repo = DeploymentsRepository()
        project_design_repo = ProjectDesignRepository(session_repo=session_repo)
        connector_repo = ConnectorRepository()
        composio_repo = ComposioProfileRepository()
        media_template_repo = MediaTemplateRepository()
        storybook_repo = StorybookRepository()
        slide_repo = SlideContentRepository()
        slide_design_repo = SlideDesignRepository(session_repo=session_repo, slide_repo=slide_repo)
        credit_balance_repo = CreditBalanceRepository()
        credit_tx_repo = CreditTransactionRepository()
        sandbox_repo = SandboxRepository()
        pin_repo = PinRepository()
        wishlist_repo = WishlistRepository()
        subdomain_repo = SubdomainRepository()
        slide_template_repo = SlideTemplateRepository()
        memory_repo = MemoryRepository()

        # services
        run_task_svc = RunTaskService(
            task_repo=run_task_repo, log_repo=task_log_repo, cache=tasks_cache, config=cfg
        )
        mcp_setting_svc = MCPSettingService(repo=mcp_setting_repo, config=cfg)
        skill_svc = SkillService(skill_repo=skill_repo, config=cfg)
        storybook_svc = StorybookService(repo=storybook_repo, config=cfg)
        storybook_version_svc = StorybookVersionService(
            repo=storybook_repo,
            storybook_service=storybook_svc,
            config=cfg,
        )
        connector_svc = ConnectorService(connector_repo=connector_repo, config=cfg)
        billing_svc = BillingService(settings=cfg)
        deployment_orch_svc = DeploymentOrchestrationService(config=cfg)
        message_svc = MessageService()
        memory_cache_svc = MemoryCacheService(cache=memory_cache_backend)
        memory_svc = MemoryService(memory_repo=memory_repo, cache=memory_cache_svc)
        credit_svc = CreditService(
            balance_repo=credit_balance_repo,
            transaction_repo=credit_tx_repo,
            config=cfg,
        )

        # ── Services with cross-service deps ──────────────────────────────
        user_svc = UserService(
            user_repo=user_repo,
            api_key_repo=api_key_repo,
            waitlist_repo=waitlist_repo,
            credit_service=credit_svc,
            cache=users_cache,
            config=cfg,
        )

        sandbox_svc = SandboxService(
            sandbox_repo=sandbox_repo,
            session_repo=session_repo,
            config=cfg,
        )

        file_svc = FileService(
            file_repo=file_repo,
            session_repo=session_repo,
            storage=storage_svc,
            config=cfg,
        )

        session_svc = SessionService(
            session_repo=session_repo,
            event_repo=event_repo,
            run_task_service=run_task_svc,
            file_store=storage_provider,
            file_service=file_svc,
            sandbox_repo=sandbox_repo,
            cache=sessions_cache,
            config=cfg,
        )

        live_terminal_svc = LiveTerminalService(
            sandbox_service=sandbox_svc,
        )

        workspace_explorer_svc = WorkspaceExplorer(
            sandbox_service=sandbox_svc,
        )

        event_svc = EventService(
            event_repo=event_repo,
            session_service=session_svc,
        )

        plan_svc = PlanService(
            session_service=session_svc,
            event_service=event_svc,
        )

        session_fork_svc = SessionForkService(
            session_repo=session_repo,
            sandbox_repo=sandbox_repo,
            config=cfg,
        )

        session_title_svc = SessionTitleService(
            config=SessionTitleConfig(),
        )

        session_pin_svc = SessionPinService(
            pin_repo=pin_repo,
            session_repo=session_repo,
            config=cfg,
        )

        session_wishlist_svc = SessionWishlistService(
            wishlist_repo=wishlist_repo,
            session_repo=session_repo,
            config=cfg,
        )

        model_setting_svc = ModelSettingService(
            repo=model_setting_repo,
            session_repo=session_repo,
        )

        composio_cache_svc = ComposioCacheService(cache=composio_cache)
        composio_svc = ComposioService(
            repo=composio_repo,
            config=cfg,
            mcp_setting_service=mcp_setting_svc,
            toolkit_service=ToolkitService(cache_service=composio_cache_svc),
            auth_config_service=AuthConfigService(),
            connected_account_service=ConnectedAccountService(),
            mcp_server_service=MCPServerService(),
            cache_service=composio_cache_svc,
        )

        project_svc = ProjectService(
            project_repo=project_repo,
            session_repo=session_repo,
            config=cfg,
        )

        deployments_svc = DeploymentsService(
            project_repo=project_repo,
            deployments_repo=deployments_repo,
            config=cfg,
        )

        media_template_svc = MediaTemplateService(
            repo=media_template_repo,
            media_storage=storage_provider,
            config=cfg,
            cache=media_cache,
        )

        # ── Storybook sub-services ───────────────────────────────────────
        storybook_export_svc = StorybookExportService(storybook_service=storybook_svc)
        storybook_edit_svc = StorybookEditService(
            repo=storybook_repo,
            version_service=storybook_version_svc,
            credit_service=credit_svc,
        )
        storybook_voice_svc = StorybookVoiceService(
            repo=storybook_repo,
            storybook_service=storybook_svc,
            config=cfg,
            credit_service=credit_svc,
        )
        storybook_ai_edit_svc = StorybookAIEditService(
            session_service=session_svc,
            user_service=user_svc,
            model_setting_service=model_setting_svc,
            credit_service=credit_svc,
            config=cfg,
        )

        # ── Subdomain service ────────────────────────────────────────────
        subdomain_svc = SubdomainService(
            subdomain_repo=subdomain_repo,
            project_repo=project_repo,
            deployments_repo=deployments_repo,
            config=cfg,
        )

        # ── Slide services ──────────────────────────────────────────────
        slide_svc = SlideService(
            slide_repo=slide_repo,
            session_repo=session_repo,
            config=cfg,
        )

        slide_template_svc = SlideTemplateService(
            template_repo=slide_template_repo,
            config=cfg,
        )

        nano_banana_repo = NanoBananaRepository(
            session_repo=session_repo,
            slide_repo=slide_repo,
        )
        nb_config = cfg.nano_banana
        nano_banana_llm_config = LLMConfig(
            model=nb_config.model,
            api_key=SecretStr(nb_config.api_key) if nb_config.api_key else None,
            provider=Provider(nb_config.provider),
            temperature=nb_config.temperature,
            base_url=nb_config.base_url,
            vertex_project_id=nb_config.vertex_project_id,
            vertex_region=nb_config.vertex_region,
            thinking_tokens=nb_config.thinking_tokens,
            config_type="system",
        )
        nano_banana_svc = NanoBananaService(
            repo=nano_banana_repo,
            llm_config=nano_banana_llm_config,
        )

        # ── Design services ──────────────────────────────────────────────
        slide_design_svc = SlideDesignService(
            repo=slide_design_repo,
            sandbox_service=sandbox_svc,
            config=cfg,
        )

        project_design_svc = ProjectDesignService(
            repo=project_design_repo,
            sandbox_service=sandbox_svc,
            model_setting_service=model_setting_svc,
            config=cfg,
        )

        return cls(
            config=cfg,
            storage_service=storage_svc,
            user_service=user_svc,
            billing_service=billing_svc,
            session_service=session_svc,
            session_fork_service=session_fork_svc,
            session_title_service=session_title_svc,
            session_pin_service=session_pin_svc,
            session_wishlist_service=session_wishlist_svc,
            file_service=file_svc,
            run_task_service=run_task_svc,
            model_setting_service=model_setting_svc,
            mcp_setting_service=mcp_setting_svc,
            skill_service=skill_svc,
            project_service=project_svc,
            deployments_service=deployments_svc,
            deployment_orchestration_service=deployment_orch_svc,
            subdomain_service=subdomain_svc,
            connector_service=connector_svc,
            composio_service=composio_svc,
            media_template_service=media_template_svc,
            storybook_service=storybook_svc,
            storybook_edit_service=storybook_edit_svc,
            storybook_export_service=storybook_export_svc,
            storybook_version_service=storybook_version_svc,
            storybook_voice_service=storybook_voice_svc,
            storybook_ai_edit_service=storybook_ai_edit_svc,
            slide_service=slide_svc,
            slide_template_service=slide_template_svc,
            nano_banana_service=nano_banana_svc,
            slide_design_service=slide_design_svc,
            project_design_service=project_design_svc,
            message_service=message_svc,
            credit_service=credit_svc,
            sandbox_service=sandbox_svc,
            live_terminal_service=live_terminal_svc,
            plan_service=plan_svc,
            event_service=event_svc,
            workspace_explorer_service=workspace_explorer_svc,
            memory_service=memory_svc,
            event_repo=event_repo,
        )


_app_container: ApplicationContainer | None = None


def get_app_container() -> ApplicationContainer:
    """Get the global ServiceContainer singleton.

    Raises ``RuntimeError`` if called before ``set_app_container()``.
    """
    if _app_container is None:
        raise RuntimeError(
            "ServiceContainer not initialized. "
            "Call set_app_container() during app lifespan startup."
        )
    return _app_container


def set_app_container(container: ApplicationContainer | None) -> None:
    """Set (or clear) the global ServiceContainer singleton."""
    global _app_container
    _app_container = container
