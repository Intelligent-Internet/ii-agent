use crate::cowork::agent_remote::{auth::RemoteAuthState, service as remote_service};
use crate::cowork::chat::{
    CoworkAgentRuntimeKind, CoworkChatFile, CoworkChatMessage, CoworkChatRunStatus,
    CoworkChatRuntimeEvent, CoworkChatSendMessageRequest, CoworkChatSendMessageResponse,
};
use futures_util::FutureExt;
use std::any::Any;
use std::future::Future;
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

pub(crate) async fn guard_async_command<T, F>(label: &str, future: F) -> Result<T, String>
where
    F: Future<Output = Result<T, String>>,
{
    match std::panic::AssertUnwindSafe(future).catch_unwind().await {
        Ok(result) => result,
        Err(payload) => Err(format!(
            "{label} panicked: {}",
            panic_payload_message(payload.as_ref())
        )),
    }
}

fn panic_payload_message(payload: &(dyn Any + Send)) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        (*message).to_string()
    } else if let Some(message) = payload.downcast_ref::<String>() {
        message.clone()
    } else {
        "non-string panic payload".to_string()
    }
}

#[tauri::command]
pub async fn send_cowork_chat_message(
    app: AppHandle,
    remote_auth_state: State<'_, RemoteAuthState>,
    request: CoworkChatSendMessageRequest,
) -> Result<CoworkChatSendMessageResponse, String> {
    guard_async_command("send_cowork_chat_message", async move {
        match request.requested_runtime_kind() {
            CoworkAgentRuntimeKind::Remote => {
                remote_service::send_remote_chat_message(app, remote_auth_state, request).await
            }
            CoworkAgentRuntimeKind::Local => {
                Err("Cowork local runtime is not implemented yet.".to_string())
            }
        }
    })
    .await
}
