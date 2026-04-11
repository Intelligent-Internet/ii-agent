use crate::cowork::chat::{
    emit_cowork_stream_event, CoworkChatEvent, CoworkChatFile, CoworkChatFilesEvent,
    CoworkChatMessage, CoworkChatMessageEvent, CoworkChatMessageRole, CoworkChatRunStatus,
    CoworkChatRuntimeEvent, CoworkChatScope, CoworkChatSendMessageRequest,
    CoworkChatSendMessageResponse, CoworkChatSessionDetail, CoworkChatSessionEvent,
    CoworkChatSessionSummary, CoworkChatStatusEvent,
};
use crate::cowork::homepage::chat_sessions as homepage_sessions;
use crate::cowork::intelligent_folder::chat_prompt as folder_chat_prompt;
use crate::cowork::intelligent_folder::sessions as folder_sessions;
use crate::cowork::runtime::CoworkRuntimeSessionSnapshot;
use crate::cowork::time_utils::{generate_message_id, now_iso};
use tauri::AppHandle;

#[derive(Clone)]
pub enum LocalCoworkSession {
    Homepage(CoworkChatSessionDetail),
    Folder(folder_sessions::CoworkChatSessionDetail),
}

impl LocalCoworkSession {
    pub fn base(&self) -> &CoworkChatSessionDetail {
        match self {
            Self::Homepage(session) => session,
            Self::Folder(session) => &session.base,
        }
    }

    pub fn base_mut(&mut self) -> &mut CoworkChatSessionDetail {
        match self {
            Self::Homepage(session) => session,
            Self::Folder(session) => &mut session.base,
        }
    }
}

trait FeatureSessionStore {
    fn load(&self, app: &AppHandle, session_id: &str) -> Result<LocalCoworkSession, String>;

    fn load_or_create(
        &self,
        app: &AppHandle,
        request: &CoworkChatSendMessageRequest,
    ) -> Result<(LocalCoworkSession, bool), String>;

    fn save(
        &self,
        app: &AppHandle,
        session: LocalCoworkSession,
    ) -> Result<LocalCoworkSession, String>;
}

struct HomepageSessionStore;
struct FolderSessionStore;

static HOMEPAGE_SESSION_STORE: HomepageSessionStore = HomepageSessionStore;
static FOLDER_SESSION_STORE: FolderSessionStore = FolderSessionStore;

impl FeatureSessionStore for HomepageSessionStore {
    fn load(&self, app: &AppHandle, session_id: &str) -> Result<LocalCoworkSession, String> {
        homepage_sessions::get_homepage_chat_session(app.clone(), session_id.to_string())
            .map(LocalCoworkSession::Homepage)
    }

    fn load_or_create(
        &self,
        app: &AppHandle,
        request: &CoworkChatSendMessageRequest,
    ) -> Result<(LocalCoworkSession, bool), String> {
        if let Some(session_id) = request.session_id.as_ref() {
            let session =
                homepage_sessions::get_homepage_chat_session(app.clone(), session_id.clone())?;
            Ok((LocalCoworkSession::Homepage(session), false))
        } else {
            let title = build_homepage_session_title(&request.content);
            let session = homepage_sessions::create_homepage_chat_session(app.clone(), title)?;
            Ok((LocalCoworkSession::Homepage(session), true))
        }
    }

    fn save(
        &self,
        app: &AppHandle,
        session: LocalCoworkSession,
    ) -> Result<LocalCoworkSession, String> {
        let LocalCoworkSession::Homepage(detail) = session else {
            return Err("Homepage session store received a non-homepage session".to_string());
        };

        homepage_sessions::update_homepage_chat_session(app.clone(), detail)
            .map(LocalCoworkSession::Homepage)
    }
}

impl FeatureSessionStore for FolderSessionStore {
    fn load(&self, app: &AppHandle, session_id: &str) -> Result<LocalCoworkSession, String> {
        folder_sessions::get_folder_session(app.clone(), session_id.to_string())
            .map(LocalCoworkSession::Folder)
    }

    fn load_or_create(
        &self,
        app: &AppHandle,
        request: &CoworkChatSendMessageRequest,
    ) -> Result<(LocalCoworkSession, bool), String> {
        let session_id = request
            .session_id
            .as_ref()
            .ok_or_else(|| "Folder cowork session_id is required".to_string())?;
        let session = folder_sessions::get_folder_session(app.clone(), session_id.clone())?;
        Ok((LocalCoworkSession::Folder(session), false))
    }

    fn save(
        &self,
        app: &AppHandle,
        session: LocalCoworkSession,
    ) -> Result<LocalCoworkSession, String> {
        let LocalCoworkSession::Folder(detail) = session else {
            return Err("Folder session store received a non-folder session".to_string());
        };

        folder_sessions::update_folder_session(app.clone(), detail)
            .map(LocalCoworkSession::Folder)
    }
}

pub fn load_or_create_local_session(
    app: &AppHandle,
    request: &CoworkChatSendMessageRequest,
) -> Result<(LocalCoworkSession, bool), String> {
    let (mut session, is_new) =
        resolve_store_for_scope(request.scope).load_or_create(app, request)?;
    normalize_local_session_runtime(&mut session);
    Ok((session, is_new))
}

pub fn persist_local_session(
    app: &AppHandle,
    mut session: LocalCoworkSession,
) -> Result<LocalCoworkSession, String> {
    normalize_local_session_runtime(&mut session);
    let mut persisted = resolve_store_for_session(&session).save(app, session)?;
    normalize_local_session_runtime(&mut persisted);
    Ok(persisted)
}

pub fn load_local_session(
    app: &AppHandle,
    scope: CoworkChatScope,
    session_id: &str,
) -> Result<LocalCoworkSession, String> {
    let mut session = resolve_store_for_scope(scope).load(app, session_id)?;
    normalize_local_session_runtime(&mut session);
    Ok(session)
}

pub fn build_send_response(
    session: &LocalCoworkSession,
    include_session_created: bool,
) -> CoworkChatSendMessageResponse {
    let base = session.base();
    let mut events = Vec::new();

    if include_session_created {
        events.push(build_session_created_event(base));
    }

    events.push(build_session_updated_event(base));
    events.push(build_status_updated_event(
        base.scope,
        base.id.clone(),
        base.run_status,
    ));

    CoworkChatSendMessageResponse {
        session_id: base.id.clone(),
        events,
    }
}

pub fn persist_runtime_error(
    app: &AppHandle,
    mut session: LocalCoworkSession,
    error_message: String,
) -> Result<LocalCoworkSession, String> {
    let base = session.base_mut();

    base.messages.push(build_local_message(
        CoworkChatMessageRole::Assistant,
        error_message,
        false,
        None,
    ));
    base.updated_at = now_iso();
    base.preview = build_preview_from_messages(&base.messages);
    base.message_count = base.messages.len();
    base.run_status = CoworkChatRunStatus::Stopped;

    sync_folder_result_tree(&mut session)?;
    persist_local_session(app, session)
}

pub fn persist_stream_status(
    app: &AppHandle,
    scope: CoworkChatScope,
    session_id: &str,
    status: CoworkChatRunStatus,
) -> Result<(), String> {
    let mut session = load_local_session(app, scope, session_id)?;
    let base = session.base_mut();

    base.run_status = status;
    base.updated_at = now_iso();
    persist_local_session(app, session).map(|_| ())
}

pub fn persist_stream_runtime_event(
    app: &AppHandle,
    event: &CoworkChatRuntimeEvent,
    status: Option<CoworkChatRunStatus>,
) -> Result<(), String> {
    let mut session = load_local_session(app, event.scope, &event.session_id)?;
    let base = session.base_mut();

    if !base
        .runtime_events
        .iter()
        .any(|current| is_same_runtime_event(current, event))
    {
        base.runtime_events.push(event.clone());
        sort_runtime_events(&mut base.runtime_events);
    }

    base.updated_at = event.emitted_at.clone();
    if let Some(next_status) = status {
        base.run_status = next_status;
    }

    persist_local_session(app, session).map(|_| ())
}

pub fn apply_runtime_session_snapshot(
    session: &mut LocalCoworkSession,
    runtime_snapshot: CoworkRuntimeSessionSnapshot,
) {
    let base = session.base_mut();

    base.runtime_kind = Some(runtime_snapshot.runtime_kind);
    base.runtime_session_id = Some(runtime_snapshot.runtime_session_id);
    base.messages = runtime_snapshot.messages;
    base.message_count = base.messages.len();
    base.files = runtime_snapshot.files;
    base.runtime_events =
        merge_runtime_events(base.runtime_events.clone(), runtime_snapshot.runtime_events);
    base.updated_at = runtime_snapshot.updated_at;
    base.preview = build_preview_from_messages(&base.messages);
    base.run_status = runtime_snapshot.run_status;
}

pub fn clear_runtime_binding(session: &mut LocalCoworkSession) {
    let base = session.base_mut();
    base.runtime_kind = None;
    base.runtime_session_id = None;
}

pub fn sync_folder_result_tree(session: &mut LocalCoworkSession) -> Result<(), String> {
    match session {
        LocalCoworkSession::Homepage(_) => Ok(()),
        LocalCoworkSession::Folder(detail) => {
            folder_sessions::sync_result_tree_from_disk(detail)
        }
    }
}

pub fn resolve_prompt_context(
    session: &LocalCoworkSession,
    explicit_prompt_context: Option<String>,
) -> Option<String> {
    explicit_prompt_context.or_else(|| match session {
        LocalCoworkSession::Homepage(_) => None,
        LocalCoworkSession::Folder(detail) => {
            Some(folder_chat_prompt::build_folder_prompt_context(detail))
        }
    })
}

pub fn build_local_message(
    role: CoworkChatMessageRole,
    content: String,
    is_think_message: bool,
    created_at: Option<String>,
) -> CoworkChatMessage {
    CoworkChatMessage {
        id: generate_message_id(),
        role,
        content,
        created_at: created_at.unwrap_or_else(now_iso),
        is_think_message: is_think_message.then_some(true),
    }
}

pub fn build_session_created_event(session: &CoworkChatSessionDetail) -> CoworkChatEvent {
    CoworkChatEvent::Session(CoworkChatSessionEvent {
        event_type: "session.created".to_string(),
        session: build_summary(session),
    })
}

pub fn build_session_updated_event(session: &CoworkChatSessionDetail) -> CoworkChatEvent {
    CoworkChatEvent::Session(CoworkChatSessionEvent {
        event_type: "session.updated".to_string(),
        session: build_summary(session),
    })
}

pub fn build_status_updated_event(
    scope: CoworkChatScope,
    session_id: String,
    status: CoworkChatRunStatus,
) -> CoworkChatEvent {
    CoworkChatEvent::Status(CoworkChatStatusEvent {
        event_type: "status.updated".to_string(),
        scope,
        session_id,
        status,
    })
}

pub fn build_message_created_event(
    scope: CoworkChatScope,
    session_id: String,
    message: CoworkChatMessage,
) -> CoworkChatEvent {
    CoworkChatEvent::Message(CoworkChatMessageEvent {
        event_type: "message.created".to_string(),
        scope,
        session_id,
        message,
    })
}

pub fn build_files_updated_event(
    scope: CoworkChatScope,
    session_id: String,
    files: Vec<CoworkChatFile>,
) -> CoworkChatEvent {
    CoworkChatEvent::Files(CoworkChatFilesEvent {
        event_type: "files.updated".to_string(),
        scope,
        session_id,
        files,
    })
}

pub fn emit_local_session_started(
    app: &AppHandle,
    session: &LocalCoworkSession,
    include_session_created: bool,
) {
    let base = session.base();

    if include_session_created {
        let _ = emit_cowork_stream_event(app, &build_session_created_event(base));
    }

    let _ = emit_cowork_stream_event(app, &build_session_updated_event(base));

    if let Some(message) = base.messages.last().cloned() {
        let _ = emit_cowork_stream_event(
            app,
            &build_message_created_event(base.scope, base.id.clone(), message),
        );
    }

    let _ = emit_cowork_stream_event(
        app,
        &build_status_updated_event(base.scope, base.id.clone(), base.run_status),
    );
}

pub fn emit_session_updated(app: &AppHandle, session: &LocalCoworkSession) {
    let _ = emit_cowork_stream_event(app, &build_session_updated_event(session.base()));
}

pub fn emit_local_terminal_state(
    app: &AppHandle,
    session: &LocalCoworkSession,
    include_latest_message: bool,
) {
    let base = session.base();

    let _ = emit_cowork_stream_event(app, &build_session_updated_event(base));

    if include_latest_message {
        if let Some(message) = base.messages.last().cloned() {
            let _ = emit_cowork_stream_event(
                app,
                &build_message_created_event(base.scope, base.id.clone(), message),
            );
        }
    }

    let _ = emit_cowork_stream_event(
        app,
        &build_files_updated_event(base.scope, base.id.clone(), base.files.clone()),
    );

    let _ = emit_cowork_stream_event(
        app,
        &build_status_updated_event(base.scope, base.id.clone(), base.run_status),
    );
}

fn normalize_local_session_runtime(session: &mut LocalCoworkSession) {
    session.base_mut().normalize_runtime_binding();
}

fn merge_runtime_events(
    existing_events: Vec<CoworkChatRuntimeEvent>,
    incoming_events: Vec<CoworkChatRuntimeEvent>,
) -> Vec<CoworkChatRuntimeEvent> {
    let mut merged = existing_events;

    for event in incoming_events {
        if !merged
            .iter()
            .any(|current| is_same_runtime_event(current, &event))
        {
            merged.push(event);
        }
    }

    sort_runtime_events(&mut merged);
    merged
}

fn sort_runtime_events(events: &mut [CoworkChatRuntimeEvent]) {
    events.sort_by(|left, right| {
        let left_time = left
            .runtime_created_at
            .as_deref()
            .unwrap_or(left.emitted_at.as_str());
        let right_time = right
            .runtime_created_at
            .as_deref()
            .unwrap_or(right.emitted_at.as_str());

        left_time
            .cmp(right_time)
            .then_with(|| left.runtime_event_type.cmp(&right.runtime_event_type))
            .then_with(|| left.runtime_event_id.cmp(&right.runtime_event_id))
            .then_with(|| left.emitted_at.cmp(&right.emitted_at))
    });
}

fn is_same_runtime_event(left: &CoworkChatRuntimeEvent, right: &CoworkChatRuntimeEvent) -> bool {
    match (
        left.runtime_event_id.as_deref(),
        right.runtime_event_id.as_deref(),
    ) {
        (Some(left_id), Some(right_id)) => {
            left.runtime_event_type == right.runtime_event_type && left_id == right_id
        }
        _ => {
            left.runtime_event_type == right.runtime_event_type
                && left.runtime_created_at == right.runtime_created_at
                && left.emitted_at == right.emitted_at
                && left.content == right.content
        }
    }
}

fn resolve_store_for_scope(scope: CoworkChatScope) -> &'static dyn FeatureSessionStore {
    match scope {
        CoworkChatScope::Homepage => &HOMEPAGE_SESSION_STORE,
        CoworkChatScope::IntelligentFolder => &FOLDER_SESSION_STORE,
    }
}

fn resolve_store_for_session(session: &LocalCoworkSession) -> &'static dyn FeatureSessionStore {
    match session {
        LocalCoworkSession::Homepage(_) => &HOMEPAGE_SESSION_STORE,
        LocalCoworkSession::Folder(_) => &FOLDER_SESSION_STORE,
    }
}

fn build_summary(session: &CoworkChatSessionDetail) -> CoworkChatSessionSummary {
    CoworkChatSessionSummary {
        id: session.id.clone(),
        scope: session.scope,
        title: session.title.clone(),
        preview: session.preview.clone(),
        updated_at: session.updated_at.clone(),
        message_count: session.message_count,
    }
}

fn build_preview_from_messages(messages: &[CoworkChatMessage]) -> String {
    messages
        .iter()
        .rev()
        .find(|message| {
            message.role == CoworkChatMessageRole::Assistant && !message.content.trim().is_empty()
        })
        .or_else(|| {
            messages
                .iter()
                .rev()
                .find(|message| !message.content.trim().is_empty())
        })
        .map(|message| truncate_preview(&message.content))
        .unwrap_or_default()
}

fn build_homepage_session_title(content: &str) -> String {
    let normalized = content.split_whitespace().collect::<Vec<_>>().join(" ");
    let title: String = normalized.chars().take(60).collect();

    if title.trim().is_empty() {
        "New cowork chat".to_string()
    } else {
        title.trim().to_string()
    }
}

fn truncate_preview(value: &str) -> String {
    let normalized = value.split_whitespace().collect::<Vec<_>>().join(" ");
    if normalized.chars().count() <= 120 {
        normalized
    } else {
        let truncated: String = normalized.chars().take(117).collect();
        format!("{truncated}...")
    }
}
