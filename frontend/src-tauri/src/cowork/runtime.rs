use crate::cowork::agent_remote::{auth::RemoteAuthState, service as remote_service};
use crate::cowork::chat::{
    CoworkAgentRuntimeKind, CoworkChatFile, CoworkChatMessage, CoworkChatRunStatus,
    CoworkChatRuntimeEvent, CoworkChatSendMessageRequest, CoworkChatSendMessageResponse,
};
use tauri::{AppHandle, State};

pub struct CoworkRuntimeSessionSnapshot {
    pub runtime_kind: CoworkAgentRuntimeKind,
    pub runtime_session_id: String,
    pub updated_at: String,
    pub messages: Vec<CoworkChatMessage>,
    pub files: Vec<CoworkChatFile>,
    pub run_status: CoworkChatRunStatus,
    pub runtime_events: Vec<CoworkChatRuntimeEvent>,
}

#[tauri::command]
pub async fn send_cowork_chat_message(
    app: AppHandle,
    remote_auth_state: State<'_, RemoteAuthState>,
    request: CoworkChatSendMessageRequest,
) -> Result<CoworkChatSendMessageResponse, String> {
    match request.requested_runtime_kind() {
        CoworkAgentRuntimeKind::Remote => {
            remote_service::send_remote_chat_message(app, remote_auth_state, request).await
        }
        CoworkAgentRuntimeKind::Local => {
            Err("Cowork local runtime is not implemented yet.".to_string())
        }
    }
}
