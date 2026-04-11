use crate::cowork::chat::{CoworkChatRunStatus, CoworkChatScope, CoworkChatSessionDetail};
use crate::cowork::session_gateway;
use crate::cowork::time_utils::now_iso;
use tauri::AppHandle;

#[tauri::command]
pub fn stop_cowork_chat_session(
    app: AppHandle,
    scope: CoworkChatScope,
    session_id: String,
) -> Result<CoworkChatSessionDetail, String> {
    let mut local_session = session_gateway::load_local_session(&app, scope, &session_id)?;

    {
        let base = local_session.base_mut();
        if matches!(
            base.run_status,
            CoworkChatRunStatus::Thinking | CoworkChatRunStatus::WaitingForInput
        ) {
            base.run_status = CoworkChatRunStatus::Stopped;
            base.updated_at = now_iso();
        }
    }

    session_gateway::sync_folder_result_tree(&mut local_session)?;
    local_session = session_gateway::persist_local_session(&app, local_session)?;
    session_gateway::emit_local_terminal_state(&app, &local_session, false);

    Ok(local_session.base().clone())
}
