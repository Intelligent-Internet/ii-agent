use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Emitter};

pub const COWORK_STREAM_EVENT_NAME: &str = "cowork://stream";

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
pub enum CoworkChatScope {
    #[serde(rename = "homepage")]
    Homepage,
    #[serde(rename = "intelligent-folder", alias = "intelligent_folder")]
    IntelligentFolder,
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum CoworkChatMessageRole {
    User,
    Assistant,
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CoworkChatRunStatus {
    Idle,
    Thinking,
    WaitingForInput,
    Completed,
    Stopped,
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CoworkAgentRuntimeKind {
    Remote,
    Local,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatMessage {
    pub id: String,
    pub role: CoworkChatMessageRole,
    pub content: String,
    pub created_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_think_message: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatFile {
    pub id: String,
    pub file_name: String,
    pub file_size: u64,
    pub content_type: String,
    pub created_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatSessionSummary {
    pub id: String,
    pub scope: CoworkChatScope,
    pub title: String,
    pub preview: String,
    pub updated_at: String,
    pub message_count: usize,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct CoworkChatSessionDetail {
    pub id: String,
    pub scope: CoworkChatScope,
    pub title: String,
    pub preview: String,
    pub updated_at: String,
    pub message_count: usize,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub runtime_kind: Option<CoworkAgentRuntimeKind>,
    #[serde(skip_serializing_if = "Option::is_none", alias = "remote_session_id")]
    pub runtime_session_id: Option<String>,
    pub messages: Vec<CoworkChatMessage>,
    #[serde(default, alias = "remote_events")]
    pub runtime_events: Vec<CoworkChatRuntimeEvent>,
    pub files: Vec<CoworkChatFile>,
    pub run_status: CoworkChatRunStatus,
}

impl CoworkChatSessionDetail {
    pub fn normalize_runtime_binding(&mut self) {
        if self.runtime_kind.is_none()
            && (self.runtime_session_id.is_some() || !self.runtime_events.is_empty())
        {
            self.runtime_kind = Some(CoworkAgentRuntimeKind::Remote);
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkGitHubRepositoryContext {
    pub owner: String,
    pub name: String,
    pub full_name: String,
    pub default_branch: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatToolSettings {
    pub web_search: bool,
    pub web_visit: bool,
    pub image_search: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_interpreter: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generate_image: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generate_video: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct CoworkAgentOverrides {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system_prompt: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_names: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skill_names: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none", alias = "agent_config")]
    pub runtime_options: Option<Value>,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct CoworkChatSendMessageRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub runtime_kind: Option<CoworkAgentRuntimeKind>,
    pub scope: CoworkChatScope,
    pub content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt_context: Option<String>,
    pub model_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<CoworkChatToolSettings>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub github_repository: Option<CoworkGitHubRepositoryContext>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub agent_overrides: Option<CoworkAgentOverrides>,
}

impl CoworkChatSendMessageRequest {
    pub fn requested_runtime_kind(&self) -> CoworkAgentRuntimeKind {
        self.runtime_kind.unwrap_or(CoworkAgentRuntimeKind::Remote)
    }
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatSessionEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub session: CoworkChatSessionSummary,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatStatusEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub scope: CoworkChatScope,
    pub session_id: String,
    pub status: CoworkChatRunStatus,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatMessageEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub scope: CoworkChatScope,
    pub session_id: String,
    pub message: CoworkChatMessage,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkChatFilesEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub scope: CoworkChatScope,
    pub session_id: String,
    pub files: Vec<CoworkChatFile>,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct CoworkChatRuntimeEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub scope: CoworkChatScope,
    pub session_id: String,
    #[serde(alias = "remote_event_type")]
    pub runtime_event_type: String,
    #[serde(skip_serializing_if = "Option::is_none", alias = "remote_event_id")]
    pub runtime_event_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", alias = "remote_created_at")]
    pub runtime_created_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_status: Option<String>,
    pub emitted_at: String,
    pub content: Value,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
#[serde(untagged)]
pub enum CoworkChatEvent {
    Session(CoworkChatSessionEvent),
    Message(CoworkChatMessageEvent),
    Files(CoworkChatFilesEvent),
    Status(CoworkChatStatusEvent),
    Runtime(CoworkChatRuntimeEvent),
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct CoworkChatSendMessageResponse {
    pub session_id: String,
    pub events: Vec<CoworkChatEvent>,
}

pub fn emit_cowork_stream_event(app: &AppHandle, event: &CoworkChatEvent) -> Result<(), String> {
    app.emit(COWORK_STREAM_EVENT_NAME, event)
        .map_err(|error| format!("Failed to emit cowork stream event: {error}"))
}
