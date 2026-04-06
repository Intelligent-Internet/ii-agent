use crate::cowork::agent_presets::shared::DesktopCapabilities;
use crate::cowork::chat::CoworkGitHubRepositoryContext;
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const V1_REQUIRED_MESSAGE: &str =
    "Cowork backend session is not using api_version=v1, so IIAgent is not active for this session.";
pub const V1_BACKEND_REQUIRED_MESSAGE: &str =
    "Cowork backend is still creating sessions without api_version=v1. Enable the backend agent_v1_version_toggle, then start a new Cowork chat session.";
pub const SOCKET_EVENT_TIMEOUT_SECS: u64 = 180;
pub const REMOTE_AGENT_TYPE: &str = "general";
pub const REMOTE_BUILD_MODE: &str = "build";
pub const REMOTE_SOCKET_MESSAGE_TYPE: &str = "cowork_query";

#[derive(Debug, Serialize)]
pub(super) struct RemoteAgentCommandContent {
    pub model_id: String,
    pub provider: String,
    pub source: String,
    pub agent_type: &'static str,
    pub tool_args: RemoteAgentToolArgs,
    pub thinking_tokens: u32,
    pub text: String,
    pub resume: bool,
    pub files: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub desktop_capabilities: Option<DesktopCapabilities>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub github_repository: Option<CoworkGitHubRepositoryContext>,
    pub build_mode: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_prompt: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_names: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skill_names: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub agent_config: Option<Value>,
}

#[derive(Debug, Serialize)]
pub(super) struct RemoteAgentToolArgs {
    pub task_agent: bool,
    pub deep_research: bool,
    pub pdf: bool,
    pub media_generation: bool,
    pub audio_generation: bool,
    pub browser: bool,
    pub enable_reviewer: bool,
    pub design_document: bool,
    pub codex_tools: bool,
    pub claude_code: bool,
}

#[derive(Debug)]
pub struct RemoteAgentRunOutcome {
    pub runtime_session_id: String,
}

#[derive(Debug, Deserialize)]
pub struct RemoteSessionInfo {
    #[serde(default)]
    pub api_version: Option<String>,
    #[serde(default)]
    pub(super) updated_at: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(super) struct RemoteAvailableModelsResponse {
    #[serde(default)]
    pub models: Vec<RemoteAvailableModel>,
}

#[derive(Debug, Deserialize)]
pub(super) struct RemoteAvailableModel {
    pub id: String,
    #[serde(default, alias = "api_type")]
    pub provider: Option<String>,
    #[serde(default)]
    pub source: Option<String>,
}

pub struct RemoteModelSelection {
    pub source: String,
    pub provider: String,
}

#[derive(Debug, Deserialize)]
pub(super) struct RemoteSessionEventsResponse {
    #[serde(default)]
    pub events: Vec<RemoteSessionEventRecord>,
    #[serde(default)]
    pub run_status: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(super) struct RemoteSessionEventRecord {
    pub id: String,
    /// Backend sends "event_type" (dotted name like "agent.response");
    /// also accept legacy "type" field via alias.
    #[serde(default, alias = "type")]
    pub event_type: String,
    #[serde(default)]
    pub content: Value,
    #[serde(default, alias = "timestamp")]
    pub created_at: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(super) struct RemoteSessionFile {
    pub id: String,
    pub name: String,
    pub size: u64,
    #[serde(default)]
    pub content_type: String,
    #[serde(default)]
    pub url: Option<String>,
}

#[derive(Debug, Clone)]
pub(super) struct RemoteSocketChatEvent {
    pub event_id: Option<String>,
    pub event_type: String,
    pub content: Value,
    pub created_at: Option<String>,
    pub run_status: Option<String>,
    pub run_id: Option<String>,
}

#[derive(Debug)]
pub(super) enum RemoteSocketSignal {
    ChatEvent(RemoteSocketChatEvent),
    ClientError(String),
}

pub(super) struct RemoteSessionState {
    pub session_info: RemoteSessionInfo,
    pub event_response: RemoteSessionEventsResponse,
    pub files: Vec<RemoteSessionFile>,
}
