//! Tauri commands for cowork Intelligent Folder undo / redo navigation.
//!
//! The cowork folder session keeps a **timeline** of snapshots (see
//! [`crate::cowork::intelligent_folder::snapshot_store`]) with a `cursor`
//! pointing at whichever snapshot is currently materialised on disk.
//! Undo and Redo simply move the cursor by ±1 and re-apply the
//! corresponding manifest:
//!
//! ```text
//!   [snap0]  [snap1]  [snap2]  [snap3]
//!                       ^ cursor here
//!   --> Undo  --> cursor = 1, disk = snap1
//!   --> Redo  --> cursor = 3, disk = snap3
//! ```
//!
//! After a successful swap we refresh the session's UI-facing
//! `undo_state` hint and `result_tree` so the frontend can render the
//! button counter and tree view without a follow-up fetch.

use super::sessions::{
    self, sync_result_tree_from_disk, CoworkChatSessionDetail, FolderUndoState,
};
use super::snapshot_store::{SnapshotStore, Timeline};
use crate::cowork::time_utils::now_iso;
use std::path::Path;
use tauri::AppHandle;

#[tauri::command]
pub fn undo_cowork_folder(
    app: AppHandle,
    session_id: String,
) -> Result<CoworkChatSessionDetail, String> {
    navigate_timeline(&app, &session_id, Direction::Backward)
}

#[tauri::command]
pub fn redo_cowork_folder(
    app: AppHandle,
    session_id: String,
) -> Result<CoworkChatSessionDetail, String> {
    navigate_timeline(&app, &session_id, Direction::Forward)
}

#[derive(Clone, Copy)]
enum Direction {
    /// Move cursor back by 1 (Undo).
    Backward,
    /// Move cursor forward by 1 (Redo).
    Forward,
}

impl Direction {
    fn verb(self) -> &'static str {
        match self {
            Direction::Backward => "undo",
            Direction::Forward => "redo",
        }
    }

    /// Compute the target cursor given the current timeline, or return
    /// an error if moving in that direction isn't possible.
    fn target_cursor(self, timeline: &Timeline) -> Result<usize, String> {
        if timeline.snapshots.is_empty() {
            return Err(format!(
                "Cannot {}: no snapshots have been captured yet",
                self.verb()
            ));
        }
        match self {
            Direction::Backward => {
                if !timeline.can_undo() {
                    return Err("Cannot undo: already at the oldest snapshot".to_string());
                }
                Ok(timeline.cursor - 1)
            }
            Direction::Forward => {
                if !timeline.can_redo() {
                    return Err("Cannot redo: already at the newest snapshot".to_string());
                }
                Ok(timeline.cursor + 1)
            }
        }
    }
}

fn navigate_timeline(
    app: &AppHandle,
    session_id: &str,
    direction: Direction,
) -> Result<CoworkChatSessionDetail, String> {
    let mut session = sessions::get_folder_session(app.clone(), session_id.to_string())?;

    let store = SnapshotStore::for_session(app, session_id)?;
    let mut timeline = store.read_timeline()?;

    let target_cursor = direction.target_cursor(&timeline)?;
    let target_meta = timeline.snapshots[target_cursor].clone();

    // Materialise the target manifest onto disk.
    let manifest = store.read_manifest(&target_meta.id).map_err(|error| {
        format!(
            "Cowork {}: failed to read manifest {}: {}",
            direction.verb(),
            target_meta.id,
            error
        )
    })?;
    let source_root = Path::new(&session.folder_tree_pair.source_root);
    store.apply_manifest(&manifest, source_root).map_err(|error| {
        format!(
            "Cowork {}: failed to apply manifest {}: {}",
            direction.verb(),
            target_meta.id,
            error
        )
    })?;

    // Advance cursor and persist the updated timeline. GC is a best-effort
    // cleanup — not fatal if it fails.
    timeline.cursor = target_cursor;
    store.write_timeline(&timeline)?;
    if let Err(error) = store.gc_unreferenced_blobs() {
        eprintln!(
            "[cowork] {}: gc_unreferenced_blobs failed: {}",
            direction.verb(),
            error
        );
    }

    // Refresh UI-facing state on the session hint + the tree viewer.
    sync_result_tree_from_disk(&mut session)?;
    session.undo_state = FolderUndoState {
        can_undo: timeline.can_undo(),
        can_redo: timeline.can_redo(),
        current: timeline.display_position().0,
        total: timeline.display_position().1,
    };
    session.base.updated_at = now_iso();

    let persisted = sessions::update_folder_session(app.clone(), session)?;
    Ok(persisted)
}
