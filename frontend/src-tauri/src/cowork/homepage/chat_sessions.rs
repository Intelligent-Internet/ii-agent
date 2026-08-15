use crate::cowork::chat::{
    CoworkChatRunStatus, CoworkChatScope, CoworkChatSessionDetail, CoworkChatSessionSummary,
};
use chrono::{SecondsFormat, Utc};
use std::{fs, path::PathBuf};
use tauri::{AppHandle, Manager};

const STORE_DIR_NAME: &str = "cowork";
const SESSION_STORE_DIR_NAME: &str = "chat-sessions";

#[tauri::command]
pub fn list_homepage_chat_sessions(
    app: AppHandle,
) -> Result<Vec<CoworkChatSessionSummary>, String> {
    let mut sessions = load_sessions(&app)?;
    sort_sessions(&mut sessions);

    Ok(sessions.into_iter().map(build_summary).collect())
}

#[tauri::command]
pub fn get_homepage_chat_session(
    app: AppHandle,
    session_id: String,
) -> Result<CoworkChatSessionDetail, String> {
    load_session(&app, &session_id)
}

#[tauri::command]
pub fn create_homepage_chat_session(
    app: AppHandle,
    title: String,
) -> Result<CoworkChatSessionDetail, String> {
    let normalized_title = title.trim();
    if normalized_title.is_empty() {
        return Err("Session title is required".to_string());
    }

    let now = now_iso();
    let session = CoworkChatSessionDetail {
        id: generate_session_id(),
        scope: CoworkChatScope::Homepage,
        title: normalized_title.to_string(),
        preview: String::new(),
        updated_at: now,
        message_count: 0,
        runtime_kind: None,
        runtime_session_id: None,
        messages: Vec::new(),
        runtime_events: Vec::new(),
        files: Vec::new(),
        run_status: CoworkChatRunStatus::Idle,
    };

    write_session(&app, &session)?;

    Ok(session)
}

#[tauri::command]
pub fn update_homepage_chat_session(
    app: AppHandle,
    session: CoworkChatSessionDetail,
) -> Result<CoworkChatSessionDetail, String> {
    validate_session(&session)?;

    let mut normalized_session = CoworkChatSessionDetail {
        message_count: session.messages.len(),
        ..session
    };
    normalized_session.normalize_runtime_binding();

    write_session(&app, &normalized_session)?;

    Ok(normalized_session)
}

#[tauri::command]
pub fn rename_homepage_chat_session(
    app: AppHandle,
    session_id: String,
    title: String,
) -> Result<CoworkChatSessionDetail, String> {
    let normalized_title = title.trim();
    if normalized_title.is_empty() {
        return Err("Session title is required".to_string());
    }

    let mut session = load_session(&app, &session_id)?;
    session.title = normalized_title.to_string();
    session.updated_at = now_iso();

    write_session(&app, &session)?;

    Ok(session)
}

#[tauri::command]
pub fn delete_homepage_chat_session(app: AppHandle, session_id: String) -> Result<(), String> {
    delete_session(&app, &session_id)
}

fn validate_session(session: &CoworkChatSessionDetail) -> Result<(), String> {
    if session.scope != CoworkChatScope::Homepage {
        return Err("Only homepage sessions can be persisted in chat-sessions".to_string());
    }

    Ok(())
}

fn build_summary(session: CoworkChatSessionDetail) -> CoworkChatSessionSummary {
    let normalized_session = normalize_session(session);

    CoworkChatSessionSummary {
        id: normalized_session.id,
        scope: normalized_session.scope,
        title: normalized_session.title,
        preview: normalized_session.preview,
        updated_at: normalized_session.updated_at,
        message_count: normalized_session.message_count,
    }
}

fn generate_session_id() -> String {
    format!("cowork-homepage-{}", Utc::now().timestamp_millis())
}

fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn sort_sessions(sessions: &mut [CoworkChatSessionDetail]) {
    sessions.sort_by(|left, right| {
        right
            .updated_at
            .cmp(&left.updated_at)
            .then_with(|| right.id.cmp(&left.id))
    });
}

fn load_sessions(app: &AppHandle) -> Result<Vec<CoworkChatSessionDetail>, String> {
    let store_dir = session_store_dir_path(app)?;
    let entries = fs::read_dir(&store_dir).map_err(|error| {
        format!(
            "Failed to read homepage chat sessions directory {}: {}",
            store_dir.display(),
            error
        )
    })?;
    let mut sessions = Vec::new();

    for entry in entries {
        let entry = entry.map_err(|error| {
            format!(
                "Failed to read an entry in homepage chat sessions directory {}: {}",
                store_dir.display(),
                error
            )
        })?;
        let path = entry.path();

        if !path.is_file() || path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }

        sessions.push(normalize_session(read_session_file(&path)?));
    }

    Ok(sessions)
}

fn load_session(app: &AppHandle, session_id: &str) -> Result<CoworkChatSessionDetail, String> {
    let session_file = session_file_path(app, session_id)?;
    if !session_file.exists() {
        return Err(format!(
            "Homepage chat session not found: {}",
            session_id.trim()
        ));
    }

    Ok(normalize_session(read_session_file(&session_file)?))
}

fn write_session(app: &AppHandle, session: &CoworkChatSessionDetail) -> Result<(), String> {
    let session_file = session_file_path(app, &session.id)?;
    let contents = serde_json::to_string_pretty(session).map_err(|error| {
        format!(
            "Failed to serialize homepage chat session {}: {}",
            session.id, error
        )
    })?;

    fs::write(&session_file, contents).map_err(|error| {
        format!(
            "Failed to write homepage chat session file {}: {}",
            session_file.display(),
            error
        )
    })
}

fn delete_session(app: &AppHandle, session_id: &str) -> Result<(), String> {
    let session_file = session_file_path(app, session_id)?;
    if !session_file.exists() {
        return Err(format!(
            "Homepage chat session not found: {}",
            session_id.trim()
        ));
    }

    fs::remove_file(&session_file).map_err(|error| {
        format!(
            "Failed to delete homepage chat session file {}: {}",
            session_file.display(),
            error
        )
    })
}

fn read_session_file(path: &PathBuf) -> Result<CoworkChatSessionDetail, String> {
    let contents = fs::read_to_string(path).map_err(|error| {
        format!(
            "Failed to read homepage chat session file {}: {}",
            path.display(),
            error
        )
    })?;

    if contents.trim().is_empty() {
        return Err(format!(
            "Homepage chat session file is empty: {}",
            path.display()
        ));
    }

    serde_json::from_str(&contents).map_err(|error| {
        format!(
            "Failed to parse homepage chat session file {}: {}",
            path.display(),
            error
        )
    })
}

fn normalize_session(mut session: CoworkChatSessionDetail) -> CoworkChatSessionDetail {
    session.normalize_runtime_binding();
    session
}

fn normalize_session_id(session_id: &str) -> Result<String, String> {
    let trimmed = session_id.trim();
    if trimmed.is_empty() {
        return Err("Homepage chat session id is required".to_string());
    }

    if trimmed == "." || trimmed == ".." {
        return Err(format!("Invalid homepage chat session id: {}", trimmed));
    }

    if trimmed.chars().any(|character| {
        character.is_control()
            || matches!(
                character,
                '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*'
            )
    }) {
        return Err(format!("Invalid homepage chat session id: {}", trimmed));
    }

    Ok(trimmed.to_string())
}

fn store_root_dir_path(app: &AppHandle) -> Result<PathBuf, String> {
    let mut data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Failed to resolve app data directory: {}", error))?;

    data_dir.push(STORE_DIR_NAME);

    fs::create_dir_all(&data_dir).map_err(|error| {
        format!(
            "Failed to create homepage chat session directory: {}",
            error
        )
    })?;

    Ok(data_dir)
}

fn session_store_dir_path(app: &AppHandle) -> Result<PathBuf, String> {
    let mut store_root = store_root_dir_path(app)?;
    store_root.push(SESSION_STORE_DIR_NAME);

    fs::create_dir_all(&store_root).map_err(|error| {
        format!(
            "Failed to create homepage chat sessions directory {}: {}",
            store_root.display(),
            error
        )
    })?;

    Ok(store_root)
}

fn session_file_path(app: &AppHandle, session_id: &str) -> Result<PathBuf, String> {
    let normalized_session_id = normalize_session_id(session_id)?;
    let mut store_dir = session_store_dir_path(app)?;
    store_dir.push(format!("{normalized_session_id}.json"));
    Ok(store_dir)
}
