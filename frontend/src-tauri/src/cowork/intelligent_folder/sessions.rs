pub use crate::cowork::chat::{CoworkChatRunStatus, CoworkChatScope, CoworkChatSessionSummary};

use crate::cowork::chat::CoworkChatSessionDetail as BaseCoworkChatSessionDetail;
use crate::cowork::intelligent_folder::file_tree::{self, FileTreeNode, FileTreeNodeKind};
use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs,
    ops::{Deref, DerefMut},
    path::PathBuf,
};
use tauri::{AppHandle, Manager};

const STORE_DIR_NAME: &str = "cowork";
const SESSION_STORE_DIR_NAME: &str = "folder-sessions";
const LEGACY_STORE_FILE_NAME: &str = "folder-sessions.json";

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct CoworkFolderTreePair {
    pub source_root: String,
    pub result_root: String,
    pub source_tree: FileTreeNode,
    pub result_tree: Option<FileTreeNode>,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct CoworkChatSessionDetail {
    #[serde(flatten)]
    pub base: BaseCoworkChatSessionDetail,
    pub folder_tree_pair: CoworkFolderTreePair,
}

impl Deref for CoworkChatSessionDetail {
    type Target = BaseCoworkChatSessionDetail;

    fn deref(&self) -> &Self::Target {
        &self.base
    }
}

impl DerefMut for CoworkChatSessionDetail {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.base
    }
}

#[derive(Debug, Serialize, Deserialize, Default)]
struct FolderSessionStore {
    sessions: Vec<CoworkChatSessionDetail>,
}

#[tauri::command]
pub fn list_folder_sessions(app: AppHandle) -> Result<Vec<CoworkChatSessionSummary>, String> {
    let mut sessions = load_sessions(&app)?;
    sort_sessions(&mut sessions);

    Ok(sessions.into_iter().map(build_summary).collect())
}

#[tauri::command]
pub fn get_folder_session(
    app: AppHandle,
    session_id: String,
) -> Result<CoworkChatSessionDetail, String> {
    load_session(&app, &session_id)
}

#[tauri::command]
pub fn create_folder_session(
    app: AppHandle,
    tree_pair: CoworkFolderTreePair,
) -> Result<CoworkChatSessionDetail, String> {
    validate_tree_pair(&tree_pair)?;

    let now = now_iso();
    let session = CoworkChatSessionDetail {
        base: BaseCoworkChatSessionDetail {
            id: generate_session_id(),
            scope: CoworkChatScope::IntelligentFolder,
            title: build_session_title(&tree_pair.source_root),
            preview: build_session_preview(&tree_pair.source_root),
            updated_at: now,
            message_count: 0,
            runtime_kind: None,
            runtime_session_id: None,
            messages: Vec::new(),
            runtime_events: Vec::new(),
            files: Vec::new(),
            run_status: CoworkChatRunStatus::Idle,
        },
        folder_tree_pair: tree_pair,
    };

    write_session(&app, &session)?;

    Ok(session)
}

#[tauri::command]
pub fn update_folder_session(
    app: AppHandle,
    session: CoworkChatSessionDetail,
) -> Result<CoworkChatSessionDetail, String> {
    validate_session(&session)?;

    let normalized_session = normalize_session(session);

    write_session(&app, &normalized_session)?;

    Ok(normalized_session)
}

#[tauri::command]
pub fn rename_folder_session(
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
pub fn delete_folder_session(app: AppHandle, session_id: String) -> Result<(), String> {
    delete_session(&app, &session_id)
}

pub fn sync_result_tree_from_disk(session: &mut CoworkChatSessionDetail) -> Result<(), String> {
    let latest_tree =
        file_tree::read_path_tree(session.folder_tree_pair.source_root.clone(), None)?;
    let source_hash = hash_tree(&session.folder_tree_pair.source_tree)?;
    let latest_hash = hash_tree(&latest_tree)?;

    session.folder_tree_pair.result_root = session.folder_tree_pair.source_root.clone();
    session.folder_tree_pair.result_tree = if source_hash == latest_hash {
        None
    } else {
        Some(latest_tree)
    };

    Ok(())
}

fn validate_session(session: &CoworkChatSessionDetail) -> Result<(), String> {
    if session.scope != CoworkChatScope::IntelligentFolder {
        return Err("Only intelligent-folder sessions can be persisted locally".to_string());
    }

    validate_tree_pair(&session.folder_tree_pair)
}

fn hash_tree(tree: &FileTreeNode) -> Result<String, String> {
    let serialized = serde_json::to_vec(tree)
        .map_err(|error| format!("Failed to serialize folder tree for hashing: {}", error))?;
    let digest = Sha256::digest(serialized);
    Ok(digest.iter().map(|value| format!("{value:02x}")).collect())
}

fn validate_tree_pair(tree_pair: &CoworkFolderTreePair) -> Result<(), String> {
    if tree_pair.source_root.trim().is_empty() {
        return Err("Folder session source_root is required".to_string());
    }

    if tree_pair.result_root.trim().is_empty() {
        return Err("Folder session result_root is required".to_string());
    }

    if tree_pair.source_tree.kind != FileTreeNodeKind::Folder {
        return Err("Folder session source_tree root must be a folder".to_string());
    }

    if let Some(result_tree) = &tree_pair.result_tree {
        if result_tree.kind != FileTreeNodeKind::Folder {
            return Err("Folder session result_tree root must be a folder".to_string());
        }
    }

    Ok(())
}

fn build_summary(session: CoworkChatSessionDetail) -> CoworkChatSessionSummary {
    let normalized_session = normalize_session(session);

    CoworkChatSessionSummary {
        id: normalized_session.base.id,
        scope: normalized_session.base.scope,
        title: normalized_session.base.title,
        preview: normalized_session.base.preview,
        updated_at: normalized_session.base.updated_at,
        message_count: normalized_session.base.message_count,
    }
}

fn build_session_title(source_root: &str) -> String {
    let trimmed = source_root.trim().trim_end_matches(['\\', '/']);
    let folder_name = trimmed
        .rsplit(['\\', '/'])
        .find(|segment| !segment.is_empty())
        .unwrap_or(trimmed);

    if folder_name.is_empty() {
        "Folder session".to_string()
    } else {
        folder_name.to_string()
    }
}

fn build_session_preview(source_root: &str) -> String {
    format!("Source: {}", build_session_title(source_root))
}

fn generate_session_id() -> String {
    format!("cowork-folder-{}", Utc::now().timestamp_millis())
}

fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn normalize_session(mut session: CoworkChatSessionDetail) -> CoworkChatSessionDetail {
    session.base.normalize_runtime_binding();
    session.base.message_count = session.base.messages.len();
    session.base.preview = build_session_preview(&session.folder_tree_pair.source_root);
    if session.base.messages.is_empty()
        && session.base.runtime_events.is_empty()
        && session.base.runtime_session_id.is_none()
        && session.base.run_status == CoworkChatRunStatus::Completed
    {
        session.base.run_status = CoworkChatRunStatus::Idle;
    }

    session
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
    migrate_legacy_store(app)?;

    let store_dir = session_store_dir_path(app)?;
    let entries = fs::read_dir(&store_dir).map_err(|error| {
        format!(
            "Failed to read folder sessions directory {}: {}",
            store_dir.display(),
            error
        )
    })?;
    let mut sessions = Vec::new();

    for entry in entries {
        let entry = entry.map_err(|error| {
            format!(
                "Failed to read an entry in folder sessions directory {}: {}",
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
    migrate_legacy_store(app)?;

    let session_file = session_file_path(app, session_id)?;
    if !session_file.exists() {
        return Err(format!("Folder session not found: {}", session_id.trim()));
    }

    Ok(normalize_session(read_session_file(&session_file)?))
}

fn write_session(app: &AppHandle, session: &CoworkChatSessionDetail) -> Result<(), String> {
    migrate_legacy_store(app)?;

    let session_file = session_file_path(app, &session.id)?;
    let contents = serde_json::to_string_pretty(session).map_err(|error| {
        format!(
            "Failed to serialize folder session {}: {}",
            session.id, error
        )
    })?;

    fs::write(&session_file, contents).map_err(|error| {
        format!(
            "Failed to write folder session file {}: {}",
            session_file.display(),
            error
        )
    })
}

fn delete_session(app: &AppHandle, session_id: &str) -> Result<(), String> {
    migrate_legacy_store(app)?;

    let session_file = session_file_path(app, session_id)?;
    if !session_file.exists() {
        return Err(format!("Folder session not found: {}", session_id.trim()));
    }

    fs::remove_file(&session_file).map_err(|error| {
        format!(
            "Failed to delete folder session file {}: {}",
            session_file.display(),
            error
        )
    })
}

fn read_session_file(path: &PathBuf) -> Result<CoworkChatSessionDetail, String> {
    let contents = fs::read_to_string(path).map_err(|error| {
        format!(
            "Failed to read folder session file {}: {}",
            path.display(),
            error
        )
    })?;

    if contents.trim().is_empty() {
        return Err(format!(
            "Folder session file is empty: {}",
            path.display()
        ));
    }

    serde_json::from_str(&contents).map_err(|error| {
        format!(
            "Failed to parse folder session file {}: {}",
            path.display(),
            error
        )
    })
}

fn migrate_legacy_store(app: &AppHandle) -> Result<(), String> {
    let legacy_store_file = legacy_store_file_path(app)?;
    if !legacy_store_file.exists() {
        return Ok(());
    }

    let contents = fs::read_to_string(&legacy_store_file)
        .map_err(|error| format!("Failed to read folder session store: {}", error))?;

    if contents.trim().is_empty() {
        fs::remove_file(&legacy_store_file).map_err(|error| {
            format!(
                "Failed to remove empty legacy folder session store {}: {}",
                legacy_store_file.display(),
                error
            )
        })?;
        return Ok(());
    }

    let legacy_store: FolderSessionStore = serde_json::from_str(&contents)
        .map_err(|error| format!("Failed to parse folder session store: {}", error))?;

    for session in legacy_store.sessions {
        let session_file = session_file_path(app, &session.id)?;
        let session_contents = serde_json::to_string_pretty(&session).map_err(|error| {
            format!(
                "Failed to serialize migrated folder session {}: {}",
                session.id, error
            )
        })?;

        fs::write(&session_file, session_contents).map_err(|error| {
            format!(
                "Failed to write migrated folder session file {}: {}",
                session_file.display(),
                error
            )
        })?;
    }

    fs::remove_file(&legacy_store_file).map_err(|error| {
        format!(
            "Failed to remove legacy folder session store {}: {}",
            legacy_store_file.display(),
            error
        )
    })
}

fn normalize_session_id(session_id: &str) -> Result<String, String> {
    let trimmed = session_id.trim();
    if trimmed.is_empty() {
        return Err("Folder session id is required".to_string());
    }

    if trimmed == "." || trimmed == ".." {
        return Err(format!("Invalid folder session id: {}", trimmed));
    }

    if trimmed.chars().any(|character| {
        character.is_control()
            || matches!(
                character,
                '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*'
            )
    }) {
        return Err(format!("Invalid folder session id: {}", trimmed));
    }

    Ok(trimmed.to_string())
}

fn store_root_dir_path(app: &AppHandle) -> Result<PathBuf, String> {
    let mut data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Failed to resolve app data directory: {}", error))?;

    data_dir.push(STORE_DIR_NAME);

    fs::create_dir_all(&data_dir)
        .map_err(|error| format!("Failed to create folder session directory: {}", error))?;

    Ok(data_dir)
}

fn session_store_dir_path(app: &AppHandle) -> Result<PathBuf, String> {
    let mut store_root = store_root_dir_path(app)?;
    store_root.push(SESSION_STORE_DIR_NAME);

    fs::create_dir_all(&store_root).map_err(|error| {
        format!(
            "Failed to create folder sessions directory {}: {}",
            store_root.display(),
            error
        )
    })?;

    Ok(store_root)
}

fn legacy_store_file_path(app: &AppHandle) -> Result<PathBuf, String> {
    let mut store_root = store_root_dir_path(app)?;
    store_root.push(LEGACY_STORE_FILE_NAME);
    Ok(store_root)
}

fn session_file_path(app: &AppHandle, session_id: &str) -> Result<PathBuf, String> {
    let normalized_session_id = normalize_session_id(session_id)?;
    let mut store_dir = session_store_dir_path(app)?;
    store_dir.push(format!("{normalized_session_id}.json"));
    Ok(store_dir)
}
