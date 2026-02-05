"""
Shared utilities for ii-skills integration.

This module provides common interfaces for skills to interact with
the ii-agent infrastructure (database, storage, research, etc.)

Components:
- DataStore: Unified database access (portfolio, prices, outputs, deals, memory)
- SkillStorage: Cloud storage for skill outputs (GCS integration)
- SkillConfig: Unified configuration (API keys, credentials, settings)
- ResearchClient: Web search and content extraction
- MemoryService: Persistent memory across sessions
- PriceFeedService: Real-time price feeds with caching
- AlertEngine: Price and portfolio alert rules
- TelemetryLogger: Run telemetry and event hooks (ralph-inspired)
- TaskGraph: Reusable task graph executor (ralph-inspired)
- RunBudgetConfig: Execution budget constraints (ralph-inspired)
- EventSchema: Public event payload definitions (ralph-inspired)
- SkillManifest: Structured capability manifests (Goose-inspired)
- WorkspaceManager: Per-execution agent workspaces (Goose-inspired)
"""

from ii_skills.shared.datastore import DataStore, get_datastore
from ii_skills.shared.storage import SkillStorage, get_skill_storage
from ii_skills.shared.skill_config import SkillConfig, get_skill_config
from ii_skills.shared.research import ResearchClient, get_research_client
from ii_skills.shared.memory import (
    MemoryService,
    MemoryType,
    Memory,
    ConversationMemory,
    DealMemory,
)
from ii_skills.shared.price_feeds import (
    PriceFeedService,
    PriceData,
    AssetClass,
    PriceSource,
    PortfolioTracker,
)
from ii_skills.shared.alerts import (
    AlertEngine,
    PriceAlert,
    PortfolioAlert,
    AlertCondition,
    AlertPriority,
    AlertStatus,
    NotificationChannel,
    create_price_below_alert,
    create_price_above_alert,
    create_price_change_alert,
    create_portfolio_change_alert,
)

# Orchestration utilities (ralph-inspired patterns)
from ii_skills.shared.event_telemetry import (
    TelemetryLogger,
    RunContext,
    TelemetryEvent,
    RunRecord,
    RunMetrics,
    get_telemetry_logger,
    set_telemetry_logger,
)
from ii_skills.shared.task_graph import (
    TaskGraph,
    Task,
    Phase,
    TaskStatus as GraphTaskStatus,
    PhaseStatus,
    TaskResult,
    TaskGraphExecutor,
    TaskGraphCallbacks,
    LoggingCallbacks,
    ExecutionBudget,
    create_task_graph,
)
from ii_skills.shared.run_budgets import (
    RunBudgetConfig,
    BudgetEnforcer,
    BudgetProfile,
    get_budget_profile,
    get_budget_for_timeframe,
    get_budget_for_skill,
    create_custom_budget,
)
from ii_skills.shared.event_schema import (
    EventType,
    EventPayload,
    RunStartedPayload,
    RunCompletedPayload,
    RunFailedPayload,
    PhaseStartedPayload,
    PhaseCompletedPayload,
    TaskStartedPayload,
    TaskCompletedPayload,
    TaskFailedPayload,
    ProgressUpdatePayload,
    # Tool execution events
    ToolStartedPayload,
    ToolCompletedPayload,
    ToolFailedPayload,
    # Sub-agent events
    SubAgentStartPayload,
    SubAgentCompletePayload,
    SubAgentErrorPayload,
    # Utilities
    validate_payload,
    create_payload,
    parse_event,
    EventSchemaMapper,
    create_orchestrator_event_mapper,
    SCHEMA_VERSION,
)

# Tool metrics
from ii_skills.shared.tool_metrics import (
    ToolMetrics,
    ToolErrorType,
    ToolExecutionRecord,
    ToolMetricsSummary,
    ExecutionTracker,
    get_global_metrics,
    track_tool_execution,
)

# Sub-agent tracing
from ii_skills.shared.subagent_tracing import (
    SubAgentTracer,
    SubAgentEvent,
    SubAgentEventType,
    SubAgentStatus,
    SubAgentRecord,
    SubAgentContext,
    traced_subagent,
)

# Skill Manifest (Goose-inspired plugin SDK)
from ii_skills.shared.skill_manifest import (
    SkillManifest,
    ActionSchema,
    RiskLevel,
    PermissionScope,
    SkillState,
    HealthStatus,
    HealthReport,
    SkillStatus,
)

# Workspace Manager (Goose-inspired agent workspaces)
from ii_skills.shared.workspace import (
    WorkspaceManager,
    Workspace,
    WorkspaceManifest,
    ArtifactRecord,
)

# Trace Formatter (Operator UX)
from ii_skills.shared.trace_formatter import (
    TraceFormatter,
    CostReport,
    LLMUsage,
    format_duration,
    format_bytes,
    format_cost,
    format_percent,
)

# Checkpoint Manager (DAG Checkpoint/Resume)
from ii_skills.shared.checkpoint import (
    CheckpointManager,
    Checkpoint,
)

# DataStore Governance
from ii_skills.shared.datastore_governance import (
    QueryContext,
    AuditLogger,
    PermissionGuard,
)

# Session Capture (Replay)
from ii_skills.shared.session_capture import (
    SessionRecord,
    CapturedToolCall,
)

# Regression Runner (Eval Harness)
from ii_skills.shared.regression import (
    RegressionRunner,
    BaselineSnapshot,
    DiffReport,
)

# Generic phase runner
from ii_skills.shared.phase_runner import (
    PhaseRunner,
    PhaseRunnerConfig,
    PhaseRunnerCallback,
    ConsolePhaseRunnerCallback,
    Task as PhaseTask,
    Phase as RunnerPhase,
    TaskStatus as RunnerTaskStatus,
    PhaseStatus as RunnerPhaseStatus,
    create_phase,
)

__all__ = [
    # DataStore
    "DataStore",
    "get_datastore",
    # Storage
    "SkillStorage",
    "get_skill_storage",
    # Config
    "SkillConfig",
    "get_skill_config",
    # Research
    "ResearchClient",
    "get_research_client",
    # Memory (Phase 4)
    "MemoryService",
    "MemoryType",
    "Memory",
    "ConversationMemory",
    "DealMemory",
    # Price Feeds (Phase 4)
    "PriceFeedService",
    "PriceData",
    "AssetClass",
    "PriceSource",
    "PortfolioTracker",
    # Alerts (Phase 4)
    "AlertEngine",
    "PriceAlert",
    "PortfolioAlert",
    "AlertCondition",
    "AlertPriority",
    "AlertStatus",
    "NotificationChannel",
    "create_price_below_alert",
    "create_price_above_alert",
    "create_price_change_alert",
    "create_portfolio_change_alert",
    # Telemetry (ralph-inspired)
    "TelemetryLogger",
    "RunContext",
    "TelemetryEvent",
    "RunRecord",
    "RunMetrics",
    "get_telemetry_logger",
    "set_telemetry_logger",
    # Task Graph (ralph-inspired)
    "TaskGraph",
    "Task",
    "Phase",
    "GraphTaskStatus",
    "PhaseStatus",
    "TaskResult",
    "TaskGraphExecutor",
    "TaskGraphCallbacks",
    "LoggingCallbacks",
    "ExecutionBudget",
    "create_task_graph",
    # Run Budgets (ralph-inspired)
    "RunBudgetConfig",
    "BudgetEnforcer",
    "BudgetProfile",
    "get_budget_profile",
    "get_budget_for_timeframe",
    "get_budget_for_skill",
    "create_custom_budget",
    # Event Schema (ralph-inspired)
    "EventType",
    "EventPayload",
    "RunStartedPayload",
    "RunCompletedPayload",
    "RunFailedPayload",
    "PhaseStartedPayload",
    "PhaseCompletedPayload",
    "TaskStartedPayload",
    "TaskCompletedPayload",
    "TaskFailedPayload",
    "ProgressUpdatePayload",
    "ToolStartedPayload",
    "ToolCompletedPayload",
    "ToolFailedPayload",
    "SubAgentStartPayload",
    "SubAgentCompletePayload",
    "SubAgentErrorPayload",
    "validate_payload",
    "create_payload",
    "parse_event",
    "EventSchemaMapper",
    "create_orchestrator_event_mapper",
    "SCHEMA_VERSION",
    # Tool Metrics
    "ToolMetrics",
    "ToolErrorType",
    "ToolExecutionRecord",
    "ToolMetricsSummary",
    "ExecutionTracker",
    "get_global_metrics",
    "track_tool_execution",
    # Sub-agent Tracing
    "SubAgentTracer",
    "SubAgentEvent",
    "SubAgentEventType",
    "SubAgentStatus",
    "SubAgentRecord",
    "SubAgentContext",
    "traced_subagent",
    # Phase Runner
    "PhaseRunner",
    "PhaseRunnerConfig",
    "PhaseRunnerCallback",
    "ConsolePhaseRunnerCallback",
    "PhaseTask",
    "RunnerPhase",
    "RunnerTaskStatus",
    "RunnerPhaseStatus",
    "create_phase",
    # Skill Manifest (Goose-inspired)
    "SkillManifest",
    "ActionSchema",
    "RiskLevel",
    "PermissionScope",
    "SkillState",
    "HealthStatus",
    "HealthReport",
    "SkillStatus",
    # Workspace Manager (Goose-inspired)
    "WorkspaceManager",
    "Workspace",
    "WorkspaceManifest",
    "ArtifactRecord",
    # Trace Formatter (Operator UX)
    "TraceFormatter",
    "CostReport",
    "LLMUsage",
    "format_duration",
    "format_bytes",
    "format_cost",
    "format_percent",
    # Checkpoint Manager (DAG Checkpoint/Resume)
    "CheckpointManager",
    "Checkpoint",
    # DataStore Governance
    "QueryContext",
    "AuditLogger",
    "PermissionGuard",
    # Session Capture (Replay)
    "SessionRecord",
    "CapturedToolCall",
    # Regression Runner (Eval Harness)
    "RegressionRunner",
    "BaselineSnapshot",
    "DiffReport",
]
