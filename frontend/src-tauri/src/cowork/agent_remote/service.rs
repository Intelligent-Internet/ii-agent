use super::auth::{self, RemoteAuthState};
use super::{
    build_remote_command, build_remote_content, ensure_remote_session_uses_v1,
    fetch_remote_session_info, fetch_remote_session_snapshot, resolve_remote_model_selection,
    run_remote_agent_request, should_recreate_remote_session, V1_BACKEND_REQUIRED_MESSAGE,
    V1_REQUIRED_MESSAGE,
};
use crate::cowork::agent_presets;
use crate::cowork::chat::{
    CoworkAgentRuntimeKind, CoworkChatMessageRole, CoworkChatSendMessageRequest,
    CoworkChatSendMessageResponse,
};
use crate::cowork::session_gateway;
use crate::cowork::time_utils::now_iso;
use reqwest::Client;
use serde_json::{json, Value};
use tauri::{AppHandle, State};

pub async fn send_remote_chat_message(
    app: AppHandle,
    state: State<'_, RemoteAuthState>,
    request: CoworkChatSendMessageRequest,
) -> Result<CoworkChatSendMessageResponse, String> {
    let normalized_content = request.content.trim().to_string();
    if normalized_content.is_empty() {
        return Err("Cowork message content is required".to_string());
    }

    let normalized_model_id = request.model_id.trim().to_string();
    if normalized_model_id.is_empty() {
        return Err("Cowork model_id is required".to_string());
    }

    let (mut local_session, is_new_session) =
        session_gateway::load_or_create_local_session(&app, &request)?;
    ensure_remote_runtime_session(local_session.base())?;

    let user_message = session_gateway::build_local_message(
        CoworkChatMessageRole::User,
        normalized_content.clone(),
        false,
        None,
    );

    {
        let base = local_session.base_mut();
        base.messages.push(user_message);
        base.updated_at = now_iso();
        base.run_status = crate::cowork::chat::CoworkChatRunStatus::Thinking;
        if base.preview.trim().is_empty() {
            base.preview = normalized_content.clone();
        }
    }

    local_session = session_gateway::persist_local_session(&app, local_session)?;
    session_gateway::emit_local_session_started(&app, &local_session, is_new_session);

    let auth_context = auth::get_auth_context(&state);
    let access_token = match auth_context.access_token {
        Some(token) => token,
        None => {
            local_session = persist_runtime_error_with_latest(
                &app,
                local_session,
                auth::AUTH_REQUIRED_MESSAGE.to_string(),
            )?;
            session_gateway::emit_local_terminal_state(&app, &local_session, true);
            return Ok(session_gateway::build_send_response(
                &local_session,
                is_new_session,
            ));
        }
    };
    let api_base_url = auth_context
        .api_base_url
        .ok_or_else(|| "Cowork API base URL is not configured".to_string())?;

    let client = Client::new();
    let mut active_runtime_session_id = local_session.base().runtime_session_id.clone();
    if let Some(runtime_session_id) = active_runtime_session_id.clone() {
        match fetch_remote_session_info(&client, &api_base_url, &access_token, &runtime_session_id)
            .await
        {
            Ok(session_info) => {
                if ensure_remote_session_uses_v1(&session_info).is_err() {
                    session_gateway::clear_runtime_binding(&mut local_session);
                    local_session = session_gateway::persist_local_session(&app, local_session)?;
                    active_runtime_session_id = None;
                }
            }
            Err(error_message) => {
                if should_recreate_remote_session(&error_message) {
                    session_gateway::clear_runtime_binding(&mut local_session);
                    local_session = session_gateway::persist_local_session(&app, local_session)?;
                    session_gateway::emit_session_updated(&app, &local_session);
                    active_runtime_session_id = None;
                } else {
                    local_session =
                        persist_runtime_error_with_latest(&app, local_session, error_message)?;
                    session_gateway::emit_local_terminal_state(&app, &local_session, true);
                    return Ok(session_gateway::build_send_response(
                        &local_session,
                        is_new_session,
                    ));
                }
            }
        }
    }

    let should_resume_remote = active_runtime_session_id.is_some();
    let model_selection = match resolve_remote_model_selection(
        &client,
        &api_base_url,
        &access_token,
        &normalized_model_id,
    )
    .await
    {
        Ok(selection) => selection,
        Err(error_message) => {
            local_session = persist_runtime_error_with_latest(&app, local_session, error_message)?;
            session_gateway::emit_local_terminal_state(&app, &local_session, true);
            return Ok(session_gateway::build_send_response(
                &local_session,
                is_new_session,
            ));
        }
    };

    let prompt_context =
        session_gateway::resolve_prompt_context(&local_session, request.prompt_context.clone());
    let resolved_agent_overrides = agent_presets::resolve_agent_overrides(
        local_session.base().scope,
        prompt_context.as_deref(),
        request.tools.as_ref(),
        request.agent_overrides.clone(),
    );
    let outbound_content = build_remote_content(&normalized_content, prompt_context.as_deref());
    let runtime_metadata = build_remote_runtime_metadata(&local_session);
    let resolved_desktop_preset = agent_presets::resolve_desktop_preset(local_session.base().scope);
    let runtime_desktop_capabilities = resolved_desktop_preset
        .as_ref()
        .map(|preset| preset.capabilities.clone());

    let remote_command = match build_remote_command(
        normalized_model_id,
        model_selection,
        outbound_content,
        should_resume_remote,
        request.tools.as_ref(),
        runtime_metadata,
        runtime_desktop_capabilities,
        request.github_repository.clone(),
        Some(&resolved_agent_overrides),
    ) {
        Ok(command) => command,
        Err(error_message) => {
            local_session = persist_runtime_error_with_latest(&app, local_session, error_message)?;
            session_gateway::emit_local_terminal_state(&app, &local_session, true);
            return Ok(session_gateway::build_send_response(
                &local_session,
                is_new_session,
            ));
        }
    };

    let run_outcome = match run_remote_agent_request(
        &api_base_url,
        &access_token,
        active_runtime_session_id,
        remote_command,
        app.clone(),
        local_session.base().scope,
        resolved_desktop_preset.map(|preset| preset.runtime),
        local_session.base().id.clone(),
    )
    .await
    {
        Ok(outcome) => outcome,
        Err(error_message) => {
            local_session = persist_runtime_error_with_latest(&app, local_session, error_message)?;
            session_gateway::emit_local_terminal_state(&app, &local_session, true);
            return Ok(session_gateway::build_send_response(
                &local_session,
                is_new_session,
            ));
        }
    };

    local_session = reload_latest_local_session(&app, &local_session);

    let runtime_snapshot = match fetch_remote_session_snapshot(
        &client,
        &api_base_url,
        &access_token,
        local_session.base().scope,
        &local_session.base().id,
        &run_outcome.runtime_session_id,
    )
    .await
    {
        Ok(snapshot) => snapshot,
        Err(error_message) => {
            let display_error = if !should_resume_remote && error_message == V1_REQUIRED_MESSAGE {
                V1_BACKEND_REQUIRED_MESSAGE.to_string()
            } else {
                error_message
            };
            local_session = persist_runtime_error_with_latest(&app, local_session, display_error)?;
            session_gateway::emit_local_terminal_state(&app, &local_session, true);
            return Ok(session_gateway::build_send_response(
                &local_session,
                is_new_session,
            ));
        }
    };

    local_session = reload_latest_local_session(&app, &local_session);
    session_gateway::apply_runtime_session_snapshot(&mut local_session, runtime_snapshot);
    session_gateway::sync_organize_result_tree(&mut local_session)?;
    local_session = session_gateway::persist_local_session(&app, local_session)?;
    session_gateway::emit_local_terminal_state(&app, &local_session, false);

    Ok(session_gateway::build_send_response(
        &local_session,
        is_new_session,
    ))
}

fn ensure_remote_runtime_session(
    session: &crate::cowork::chat::CoworkChatSessionDetail,
) -> Result<(), String> {
    match session.runtime_kind {
        Some(CoworkAgentRuntimeKind::Remote) | None => Ok(()),
        Some(CoworkAgentRuntimeKind::Local) => Err(
            "This Cowork session is already bound to the local runtime and cannot be sent through the remote runtime."
                .to_string(),
        ),
    }
}

fn reload_latest_local_session(
    app: &AppHandle,
    session: &session_gateway::LocalCoworkSession,
) -> session_gateway::LocalCoworkSession {
    session_gateway::load_local_session(app, session.base().scope, &session.base().id)
        .unwrap_or_else(|_| session.clone())
}

fn persist_runtime_error_with_latest(
    app: &AppHandle,
    session: session_gateway::LocalCoworkSession,
    error_message: String,
) -> Result<session_gateway::LocalCoworkSession, String> {
    let latest_session = reload_latest_local_session(app, &session);
    session_gateway::persist_runtime_error(app, latest_session, error_message)
}

fn build_remote_runtime_metadata(session: &session_gateway::LocalCoworkSession) -> Option<Value> {
    match session {
        session_gateway::LocalCoworkSession::Homepage(_) => None,
        session_gateway::LocalCoworkSession::Organize(detail) => Some(json!({
            "cowork": {
                "scope": "organize-file-folder",
                "execution_context": "desktop",
                "tool_runtime": "desktop_builtin",
                "tool_binding_mode": "desktop_only",
                "local_session_id": detail.base.id.clone(),
                "source_root": detail.organize_tree_pair.source_root.clone(),
                "result_root": detail.organize_tree_pair.result_root.clone(),
            }
        })),
    }
}
