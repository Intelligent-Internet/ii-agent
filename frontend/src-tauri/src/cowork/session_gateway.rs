use crate::cowork::chat::{
    emit_cowork_stream_event, CoworkChatEvent, CoworkChatFile, CoworkChatFilesEvent,
    CoworkChatMessage, CoworkChatMessageEvent, CoworkChatMessageRole, CoworkChatRunStatus,
    CoworkChatRuntimeEvent, CoworkChatScope, CoworkChatSendMessageRequest,
    CoworkChatSendMessageResponse, CoworkChatSessionDetail, CoworkChatSessionEvent,
    CoworkChatSessionSummary, CoworkChatStatusEvent,
};
use crate::cowork::homepage::chat_sessions as homepage_sessions;
use crate::cowork::intelligent_folder::chat_prompt as folder_chat_prompt;
use crate::cowork::intelligent_folder::file_tree;
use crate::cowork::intelligent_folder::sessions::{
    self as folder_sessions, FolderUndoState,
};
use crate::cowork::intelligent_folder::snapshot_store::{
    PendingSnapshot, SnapshotStore, MAX_TIMELINE_LEN,
};
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
    // Intelligent Folder snapshot timeline bookkeeping: at run start
    // capture a pending pre-run snapshot; at run end push a new timeline
    // entry (or discard the pending) based on whether disk actually
    // changed. Best-effort — failures are logged and never block the
    // persistence path.
    maintain_folder_timeline(app, &mut session);
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

/// Intelligent Folder snapshot timeline bookkeeping. Runs on every
/// [`persist_local_session`] call and decides whether to (a) capture a
/// fresh pre-run snapshot, (b) push an existing pending one into the
/// session's timeline + refresh the UI hint, or (c) do nothing.
///
/// The decision is driven entirely by `session.run_status` and the
/// presence/absence of `pending.json` on disk — no other code needs to
/// call into the snapshot store for pre/post-run tracking. Intentionally
/// never fails: any error is logged and the session is persisted as-is
/// (a broken snapshot path must not break the user's chat flow).
///
/// State transitions (only active on [`LocalCoworkSession::Folder`]):
///
/// | run_status                    | pending.json? | action                       |
/// |-------------------------------|---------------|------------------------------|
/// | `Thinking` / `Waiting`        | absent        | write fresh pending snapshot |
/// | `Thinking` / `Waiting`        | present       | no-op                        |
/// | `Completed` / `Stopped` / `Idle` | present    | compare, push or discard     |
/// | `Completed` / `Stopped` / `Idle` | absent     | just refresh undo_state hint |
fn maintain_folder_timeline(app: &AppHandle, session: &mut LocalCoworkSession) {
    let folder_detail = match session {
        LocalCoworkSession::Folder(detail) => detail,
        LocalCoworkSession::Homepage(_) => return,
    };

    let session_id = folder_detail.base.id.clone();
    let source_root = folder_detail.folder_tree_pair.source_root.clone();

    let store = match SnapshotStore::for_session(app, &session_id) {
        Ok(store) => store,
        Err(error) => {
            eprintln!(
                "[cowork] timeline: store init failed for session {}: {}",
                session_id, error
            );
            return;
        }
    };

    let is_run_active = matches!(
        folder_detail.base.run_status,
        CoworkChatRunStatus::Thinking | CoworkChatRunStatus::WaitingForInput
    );

    if is_run_active {
        capture_pre_run_snapshot_if_absent(&store, &session_id, &source_root);
        // Run is still in-flight — don't touch the timeline or undo_state
        // hint yet. The final post-run persist_local_session call will
        // sync everything.
        return;
    }

    // run_status is terminal (Idle / Completed / Stopped). If there's a
    // pending marker, this is the moment to compare it against current
    // disk and either push a new timeline entry (disk changed) or drop
    // it (disk unchanged).
    commit_or_discard_pending(&store, &session_id, &source_root, folder_detail);

    // Regardless of whether anything got committed, refresh the
    // UI-facing hint from the on-disk timeline — covers the "no pending,
    // just refresh" case too so a session loaded after a restart shows
    // the correct Undo/Redo buttons.
    refresh_undo_state_hint(&store, &session_id, folder_detail);
}

fn capture_pre_run_snapshot_if_absent(
    store: &SnapshotStore,
    session_id: &str,
    source_root: &str,
) {
    match store.read_pending() {
        Ok(Some(_)) => {
            // Already captured for this run — do not overwrite, otherwise
            // mid-run status updates would keep rewriting pending against
            // a disk that the agent is already modifying.
        }
        Ok(None) => {
            let pre_run_tree = match file_tree::read_path_tree(source_root.to_string(), None) {
                Ok(tree) => tree,
                Err(error) => {
                    eprintln!(
                        "[cowork] timeline: pre-run tree scan failed for session {}: {}",
                        session_id, error
                    );
                    return;
                }
            };
            let pre_run_tree_hash = match folder_sessions::hash_tree(&pre_run_tree) {
                Ok(hash) => hash,
                Err(error) => {
                    eprintln!(
                        "[cowork] timeline: pre-run hash failed for session {}: {}",
                        session_id, error
                    );
                    return;
                }
            };
            let manifest = match store.snapshot(std::path::Path::new(source_root)) {
                Ok(manifest) => manifest,
                Err(error) => {
                    eprintln!(
                        "[cowork] timeline: pre-run snapshot failed for session {}: {}",
                        session_id, error
                    );
                    return;
                }
            };
            let pending = PendingSnapshot {
                pre_run_tree_hash,
                manifest,
            };
            if let Err(error) = store.write_pending(&pending) {
                eprintln!(
                    "[cowork] timeline: write_pending failed for session {}: {}",
                    session_id, error
                );
            }
        }
        Err(error) => {
            eprintln!(
                "[cowork] timeline: read_pending failed for session {}: {}",
                session_id, error
            );
        }
    }
}

fn commit_or_discard_pending(
    store: &SnapshotStore,
    session_id: &str,
    source_root: &str,
    _folder_detail: &mut folder_sessions::CoworkChatSessionDetail,
) {
    let pending = match store.read_pending() {
        Ok(Some(pending)) => pending,
        Ok(None) => return,
        Err(error) => {
            eprintln!(
                "[cowork] timeline: read_pending failed for session {}: {}",
                session_id, error
            );
            return;
        }
    };

    let post_run_tree = match file_tree::read_path_tree(source_root.to_string(), None) {
        Ok(tree) => tree,
        Err(error) => {
            eprintln!(
                "[cowork] timeline: post-run tree scan failed for session {}: {}",
                session_id, error
            );
            let _ = store.clear_pending();
            let _ = store.gc_unreferenced_blobs();
            return;
        }
    };
    let post_run_hash = match folder_sessions::hash_tree(&post_run_tree) {
        Ok(hash) => hash,
        Err(error) => {
            eprintln!(
                "[cowork] timeline: post-run hash failed for session {}: {}",
                session_id, error
            );
            let _ = store.clear_pending();
            let _ = store.gc_unreferenced_blobs();
            return;
        }
    };

    if pending.pre_run_tree_hash == post_run_hash {
        // Disk didn't change → discard pending, leave timeline untouched.
        let _ = store.clear_pending();
        let _ = store.gc_unreferenced_blobs();
        return;
    }

    // Disk DID change → push a new entry into the timeline.
    if let Err(error) = push_post_run_snapshot(
        store,
        session_id,
        std::path::Path::new(source_root),
        &pending,
        post_run_hash,
    ) {
        eprintln!(
            "[cowork] timeline: push_post_run_snapshot failed for session {}: {}",
            session_id, error
        );
    }
    let _ = store.clear_pending();
    let _ = store.gc_unreferenced_blobs();
}

/// Commit a change into the timeline. This is the heart of the
/// `/snapshot history/` design: it handles seeding an empty timeline,
/// rebasing when `timeline[cursor]` drifted out of sync with disk,
/// truncating future branches when the user was detached, pushing the
/// new state, and enforcing the retention cap.
///
/// **Invariant maintained**: after this function returns Ok, the
/// timeline has a `cursor` pointing at a snapshot whose
/// `disk_tree_hash` equals the `post_run_hash` we just computed. The
/// caller (post-run hook) is responsible for clearing the pending
/// marker and running GC.
fn push_post_run_snapshot(
    store: &SnapshotStore,
    session_id: &str,
    source_root: &std::path::Path,
    pending: &PendingSnapshot,
    post_run_hash: String,
) -> Result<(), String> {
    let mut timeline = store.read_timeline()?;

    // Step 1: if the user is detached (cursor < len-1), any snapshots in
    // the future are now orphaned by this new commit — git-style discard.
    if timeline.cursor + 1 < timeline.snapshots.len() {
        let discarded: Vec<String> = timeline
            .snapshots
            .drain(timeline.cursor + 1..)
            .map(|meta| meta.id)
            .collect();
        for id in &discarded {
            let _ = store.delete_manifest(id);
        }
    }

    // Step 2: ensure timeline[cursor] matches the pre-run disk state. If
    // the timeline is empty, or the cursor snapshot's hash doesn't match
    // pending.pre_run_tree_hash (e.g. timeline was seeded from an older
    // run and disk has drifted, or this is the very first commit ever),
    // push the pending manifest as a new "pre-run" baseline entry first.
    let cursor_matches_pre_run = timeline
        .snapshots
        .get(timeline.cursor)
        .map(|meta| meta.disk_tree_hash == pending.pre_run_tree_hash)
        .unwrap_or(false);

    if !cursor_matches_pre_run {
        let baseline_meta =
            store.push_snapshot(&pending.manifest, pending.pre_run_tree_hash.clone())?;
        if timeline.snapshots.is_empty() {
            timeline.snapshots.push(baseline_meta);
            timeline.cursor = 0;
        } else {
            // Rebasing: insert the baseline right after the current
            // cursor so that subsequent undo still walks older history.
            let insert_at = timeline.cursor + 1;
            timeline.snapshots.insert(insert_at, baseline_meta);
            timeline.cursor = insert_at;
        }
    }

    // Step 3: snapshot the current (post-run) disk and push as a new
    // entry after the baseline.
    let post_run_manifest = store.snapshot(source_root)?;
    let post_run_meta = store.push_snapshot(&post_run_manifest, post_run_hash)?;
    timeline.snapshots.push(post_run_meta);
    timeline.cursor = timeline.snapshots.len() - 1;

    // Step 4: enforce retention cap. Drop oldest entries first and
    // shift cursor to compensate.
    while timeline.snapshots.len() > MAX_TIMELINE_LEN {
        let dropped = timeline.snapshots.remove(0);
        let _ = store.delete_manifest(&dropped.id);
        if timeline.cursor > 0 {
            timeline.cursor -= 1;
        }
    }

    store.write_timeline(&timeline)?;

    let _ = session_id; // reserved for future structured logging
    Ok(())
}

/// Pull the current timeline from disk and mirror its navigation state
/// onto the session's `undo_state` hint. Best-effort — if the timeline
/// is unreadable, we leave the existing hint alone rather than wiping
/// it to a default (which would hide the button the next render).
fn refresh_undo_state_hint(
    store: &SnapshotStore,
    session_id: &str,
    folder_detail: &mut folder_sessions::CoworkChatSessionDetail,
) {
    let timeline = match store.read_timeline() {
        Ok(timeline) => timeline,
        Err(error) => {
            eprintln!(
                "[cowork] timeline: read_timeline failed for session {}: {}",
                session_id, error
            );
            return;
        }
    };
    let (current, total) = timeline.display_position();
    folder_detail.undo_state = FolderUndoState {
        can_undo: timeline.can_undo(),
        can_redo: timeline.can_redo(),
        current,
        total,
    };
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
