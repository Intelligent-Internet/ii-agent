use crate::cowork::agent_remote::auth::{get_auth_context, RemoteAuthState};
use crate::cowork::agent_remote::cancel::emit_cancel_signal;
use crate::cowork::chat::{CoworkChatRunStatus, CoworkChatScope, CoworkChatSessionDetail};
use crate::cowork::session_gateway;
use crate::cowork::time_utils::now_iso;
use tauri::{AppHandle, State};

#[tauri::command]
pub async fn stop_cowork_chat_session(
    app: AppHandle,
    remote_auth_state: State<'_, RemoteAuthState>,
    scope: CoworkChatScope,
    session_id: String,
) -> Result<CoworkChatSessionDetail, String> {
    let mut local_session = session_gateway::load_local_session(&app, scope, &session_id)?;

    // Only dispatch a remote cancel if the session is actually mid-run. This
    // guarantees the "already completed" / "stopped twice" path never opens a
    // pointless socket connection.
    let should_dispatch_remote_cancel = matches!(
        local_session.base().run_status,
        CoworkChatRunStatus::Thinking | CoworkChatRunStatus::WaitingForInput
    );

    if should_dispatch_remote_cancel {
        let runtime_session_id = local_session.base().runtime_session_id.clone();
        // Snapshot the auth context into owned values BEFORE any .await so
        // the `State<'_, _>` reference never spans an await point (keeps the
        // future Send and sidesteps Rust's borrow-across-await diagnostics).
        let auth = get_auth_context(&remote_auth_state);
        let access_token = auth.access_token;
        let api_base_url = auth.api_base_url;

        match (runtime_session_id, access_token, api_base_url) {
            (Some(remote_session_id), Some(access_token), Some(api_base_url)) => {
                // Fire-and-forget: log any failure and continue with local
                // stop. A network hiccup here must not prevent the user from
                // seeing the UI transition to Stopped.
                if let Err(error) =
                    emit_cancel_signal(api_base_url, access_token, remote_session_id).await
                {
                    eprintln!("[cowork] remote cancel dispatch failed: {error}");
                }
            }
            (None, _, _) => {
                // Session was never bound to a Python session UUID yet — no
                // remote run to cancel.
                eprintln!(
                    "[cowork] stop: no runtime_session_id for local session {session_id}; \
                     skipping remote cancel"
                );
            }
            _ => {
                // Auth missing — user may be signed out. Local stop still runs.
                eprintln!(
                    "[cowork] stop: auth context missing; skipping remote cancel for {session_id}"
                );
            }
        }
    }

    // Existing local state update (unchanged).
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
