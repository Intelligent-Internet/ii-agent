use crate::cowork::string_utils::normalize_optional_string;
use std::sync::Mutex;
use tauri::State;

pub const AUTH_REQUIRED_MESSAGE: &str =
    "Current user token is not available in Cowork desktop mode. Please sign in again.";

#[derive(Debug, Default, Clone)]
pub struct RemoteAuthContext {
    pub access_token: Option<String>,
    pub api_base_url: Option<String>,
}

#[derive(Debug, Default)]
pub struct RemoteAuthState {
    pub inner: Mutex<RemoteAuthContext>,
}

#[tauri::command]
pub fn sync_cowork_auth_context(
    state: State<'_, RemoteAuthState>,
    access_token: Option<String>,
    api_base_url: String,
) -> Result<(), String> {
    let normalized_base_url = normalize_api_base_url(&api_base_url)?;
    let normalized_token = access_token.and_then(|token| normalize_optional_string(&token));

    let mut auth_context = state
        .inner
        .lock()
        .map_err(|_| "Failed to lock cowork remote auth context".to_string())?;

    auth_context.access_token = normalized_token;
    auth_context.api_base_url = Some(normalized_base_url);

    Ok(())
}

pub fn get_auth_context(state: &State<'_, RemoteAuthState>) -> RemoteAuthContext {
    state
        .inner
        .lock()
        .map(|guard| guard.clone())
        .unwrap_or_default()
}

fn normalize_api_base_url(value: &str) -> Result<String, String> {
    let normalized = value.trim().trim_end_matches('/').to_string();
    if normalized.is_empty() {
        return Err("Cowork API base URL is required".to_string());
    }
    Ok(normalized)
}
