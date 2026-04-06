use super::mapper::{build_backend_error_message, map_remote_snapshot};
use super::types::{
    RemoteAvailableModelsResponse, RemoteModelSelection, RemoteSessionEventsResponse,
    RemoteSessionFile, RemoteSessionInfo, RemoteSessionState, V1_REQUIRED_MESSAGE,
};
use crate::cowork::agent_remote::auth::AUTH_REQUIRED_MESSAGE;
use crate::cowork::chat::CoworkChatScope;
use crate::cowork::runtime::CoworkRuntimeSessionSnapshot;
use crate::cowork::string_utils::normalize_optional_string;
use reqwest::{header::AUTHORIZATION, Client};

pub async fn fetch_remote_session_info(
    client: &Client,
    api_base_url: &str,
    access_token: &str,
    remote_session_id: &str,
) -> Result<RemoteSessionInfo, String> {
    let response = client
        .get(format!("{api_base_url}/v1/sessions/{remote_session_id}"))
        .header(AUTHORIZATION, format!("Bearer {access_token}"))
        .send()
        .await
        .map_err(|error| format!("Failed to load Cowork agent session info: {error}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response
            .text()
            .await
            .unwrap_or_else(|_| "Unknown backend error".to_string());
        return Err(build_backend_error_message(
            status,
            &body,
            AUTH_REQUIRED_MESSAGE,
        ));
    }

    response
        .json::<RemoteSessionInfo>()
        .await
        .map_err(|error| format!("Failed to decode Cowork agent session info: {error}"))
}

pub fn ensure_remote_session_uses_v1(session_info: &RemoteSessionInfo) -> Result<(), String> {
    match session_info.api_version.as_deref() {
        Some("v1") | None => Ok(()),
        Some(_) => Err(V1_REQUIRED_MESSAGE.to_string()),
    }
}

pub fn should_recreate_remote_session(error_message: &str) -> bool {
    error_message == V1_REQUIRED_MESSAGE
        || error_message.contains("status 404")
        || error_message.contains("not found or access denied")
}

pub async fn resolve_remote_model_selection(
    client: &Client,
    api_base_url: &str,
    access_token: &str,
    model_id: &str,
) -> Result<RemoteModelSelection, String> {
    let response = client
        .get(format!("{api_base_url}/v1/user-settings/models"))
        .header(AUTHORIZATION, format!("Bearer {access_token}"))
        .send()
        .await
        .map_err(|error| format!("Failed to load available AI models for Cowork: {error}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response
            .text()
            .await
            .unwrap_or_else(|_| "Unknown backend error".to_string());
        return Err(build_backend_error_message(
            status,
            &body,
            AUTH_REQUIRED_MESSAGE,
        ));
    }

    let payload = response
        .json::<RemoteAvailableModelsResponse>()
        .await
        .map_err(|error| format!("Failed to decode available AI models for Cowork: {error}"))?;

    let model = payload
        .models
        .into_iter()
        .find(|model| model.id == model_id)
        .ok_or_else(|| {
            format!("The selected AI model `{model_id}` is not available for the current user.")
        })?;

    let source = model
        .source
        .and_then(|value| normalize_optional_string(&value))
        .ok_or_else(|| {
            format!("The selected AI model `{model_id}` does not provide a valid source.")
        })?;

    if source != "user" && source != "system" {
        return Err(format!(
            "The selected AI model `{model_id}` returned an unsupported source `{source}`."
        ));
    }

    let provider = model
        .provider
        .and_then(|value| normalize_optional_string(&value))
        .ok_or_else(|| {
            format!("The selected AI model `{model_id}` does not provide a valid provider.")
        })?;

    let provider_lower = provider.to_lowercase();
    if !matches!(
        provider_lower.as_str(),
        "openai" | "anthropic" | "gemini" | "google" | "cerebras" | "custom"
    ) {
        return Err(format!(
            "The selected AI model `{model_id}` returned an unsupported provider `{provider}`."
        ));
    }

    Ok(RemoteModelSelection {
        source,
        provider: provider_lower,
    })
}

pub async fn fetch_remote_session_snapshot(
    client: &Client,
    api_base_url: &str,
    access_token: &str,
    local_scope: CoworkChatScope,
    local_session_id: &str,
    runtime_session_id: &str,
) -> Result<CoworkRuntimeSessionSnapshot, String> {
    let remote_session =
        fetch_remote_session_state(client, api_base_url, access_token, runtime_session_id).await?;

    Ok(map_remote_snapshot(
        local_scope,
        local_session_id,
        runtime_session_id,
        remote_session.session_info.updated_at.clone(),
        &remote_session.event_response.events,
        &remote_session.files,
        remote_session.event_response.run_status.as_deref(),
    ))
}

async fn fetch_remote_session_state(
    client: &Client,
    api_base_url: &str,
    access_token: &str,
    remote_session_id: &str,
) -> Result<RemoteSessionState, String> {
    let session_info =
        fetch_remote_session_info(client, api_base_url, access_token, remote_session_id).await?;
    ensure_remote_session_uses_v1(&session_info)?;
    let event_response =
        fetch_remote_session_events(client, api_base_url, access_token, remote_session_id).await?;
    let files =
        fetch_remote_session_files(client, api_base_url, access_token, remote_session_id).await?;

    Ok(RemoteSessionState {
        session_info,
        event_response,
        files,
    })
}

async fn fetch_remote_session_events(
    client: &Client,
    api_base_url: &str,
    access_token: &str,
    remote_session_id: &str,
) -> Result<RemoteSessionEventsResponse, String> {
    let response = client
        .get(format!(
            "{api_base_url}/v1/sessions/{remote_session_id}/events"
        ))
        .header(AUTHORIZATION, format!("Bearer {access_token}"))
        .send()
        .await
        .map_err(|error| format!("Failed to load Cowork agent session events: {error}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response
            .text()
            .await
            .unwrap_or_else(|_| "Unknown backend error".to_string());
        return Err(build_backend_error_message(
            status,
            &body,
            AUTH_REQUIRED_MESSAGE,
        ));
    }

    response
        .json::<RemoteSessionEventsResponse>()
        .await
        .map_err(|error| format!("Failed to decode Cowork agent session events: {error}"))
}

async fn fetch_remote_session_files(
    client: &Client,
    api_base_url: &str,
    access_token: &str,
    remote_session_id: &str,
) -> Result<Vec<RemoteSessionFile>, String> {
    let response = client
        .get(format!("{api_base_url}/v1/sessions/{remote_session_id}/files"))
        .header(AUTHORIZATION, format!("Bearer {access_token}"))
        .send()
        .await
        .map_err(|error| format!("Failed to load Cowork agent session files: {error}"))?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response
            .text()
            .await
            .unwrap_or_else(|_| "Unknown backend error".to_string());
        return Err(build_backend_error_message(
            status,
            &body,
            AUTH_REQUIRED_MESSAGE,
        ));
    }

    response
        .json::<Vec<RemoteSessionFile>>()
        .await
        .map_err(|error| format!("Failed to decode Cowork agent session files: {error}"))
}
