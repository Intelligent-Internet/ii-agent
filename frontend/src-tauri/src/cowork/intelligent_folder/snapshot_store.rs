//! Content-addressable snapshot store with timeline history for cowork
//! Intelligent Folder sessions.
//!
//! Each folder session gets a **timeline** of snapshots (up to
//! [`MAX_TIMELINE_LEN`] deep) backed by a shared content-addressable
//! blob pool:
//!
//! ```text
//! {app_data}/cowork/folder-snapshots/{session_id}/
//! ├── blobs/
//! │   ├── ab/
//! │   │   └── abc…def               # file bytes, filename = full sha256
//! │   └── 7f/
//! │       └── 7f9a…
//! ├── snapshots/
//! │   ├── 001-01HRAB….json           # per-snapshot manifest
//! │   ├── 002-01HRAC….json
//! │   └── …
//! ├── timeline.json                  # ordered list + cursor
//! └── pending.json                   # pre-run marker (transient)
//! ```
//!
//! ### Blob pool (content-addressable)
//!
//! Every file is hashed (SHA-256) and its bytes are written to
//! `blobs/{first2}/{full_hash}` exactly once — identical contents dedupe
//! automatically across snapshots. This is what keeps a long timeline
//! cheap: if the agent only modifies 5 files out of 10k between
//! snapshots, only those 5 new blobs are added to the pool.
//!
//! ### Timeline ([`Timeline`])
//!
//! `timeline.json` is the authoritative ordered history:
//!
//! - `snapshots[i]` holds a [`SnapshotMeta`] pointing at a manifest file
//!   and recording the file-tree hash of the disk state it captured.
//! - `cursor` is the index of the snapshot **currently materialised on
//!   disk**. `cursor == snapshots.len() - 1` means the user is at the
//!   newest checkpoint; `cursor < len - 1` means they've undone one or
//!   more steps ("detached").
//! - Undo/Redo move the cursor by ±1 and re-materialise the corresponding
//!   manifest on disk.
//! - Sending a new chat message while detached **truncates**
//!   `snapshots[cursor+1..]` (git-style), then appends the fresh
//!   post-run state. Old future branches are dropped.
//! - If the timeline grows past [`MAX_TIMELINE_LEN`], the oldest entry is
//!   dropped and the cursor shifts to compensate.
//!
//! ### Pending marker ([`PendingSnapshot`])
//!
//! Captured at run start (pre-run hook in `session_gateway`). Its
//! `pre_run_tree_hash` lets the post-run code cheaply decide "did disk
//! actually change?" without comparing whole manifests. Its `manifest`
//! is used to *seed* the timeline when it's empty (or to *rebase* it
//! when the current cursor entry is out-of-sync with disk, e.g. due to
//! external modification). On every commit/discard the pending file is
//! cleared and orphaned blobs GC'd.
//!
//! ### Crash safety
//!
//! - Blobs, manifest files, `timeline.json`, and `pending.json` are all
//!   written via `*.tmp` → `rename`, so readers only ever see fully
//!   formed content.
//! - The materialise step (copying bytes from blobs back to
//!   `source_root`) uses per-file tmp + rename. A crash mid-apply leaves
//!   the user's folder in a mixed state — same risk profile as the
//!   agent itself. Documented as a known limitation.
//! - Timeline truncation and retention writes are a single atomic rename
//!   of `timeline.json`; manifest files left behind from a half-finished
//!   truncation are reclaimed by the next GC pass.
//!
//! Symlinks are stored as-is (target path recorded, not followed). All
//! files including hidden, `.git`, `node_modules`, etc. are included —
//! no ignore list, by the user's explicit choice.

use super::sessions::folder_snapshot_session_dir;
use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{self, Read},
    path::{Component, Path, PathBuf},
    time::UNIX_EPOCH,
};
use tauri::AppHandle;

const BLOBS_DIR_NAME: &str = "blobs";
const BLOB_SUFFIX: &str = ".zst";
const SNAPSHOTS_DIR_NAME: &str = "snapshots";
const TIMELINE_FILE_NAME: &str = "timeline.json";
const TIMELINE_TMP_FILE_NAME: &str = "timeline.json.tmp";
const PENDING_FILE_NAME: &str = "pending.json";
const PENDING_TMP_FILE_NAME: &str = "pending.json.tmp";
const STAT_CACHE_FILE_NAME: &str = "stat-cache.json";
const STAT_CACHE_TMP_FILE_NAME: &str = "stat-cache.json.tmp";

/// Zstd compression level. 3 is the default — good compression ratio on
/// text (~60-75% reduction) with minimal CPU overhead (~400 MB/s on
/// modern CPUs). Higher levels plateau quickly for code/text content.
const ZSTD_LEVEL: i32 = 3;

/// Maximum number of snapshots retained per session. Older entries are
/// dropped from the front of the timeline (with cursor shifted to
/// compensate) when a new snapshot would push the list past this limit.
/// Keeps disk usage bounded — worst case ~20× the size of files changed
/// across the retained runs, thanks to CAS dedup.
pub const MAX_TIMELINE_LEN: usize = 20;

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
#[serde(rename_all = "snake_case", tag = "kind")]
pub enum ManifestEntry {
    Dir {
        rel_path: String,
    },
    File {
        rel_path: String,
        sha256: String,
    },
    Symlink {
        rel_path: String,
        target: String,
    },
}

impl ManifestEntry {
    fn rel_path(&self) -> &str {
        match self {
            ManifestEntry::Dir { rel_path }
            | ManifestEntry::File { rel_path, .. }
            | ManifestEntry::Symlink { rel_path, .. } => rel_path,
        }
    }
}

/// A single captured disk state: the sorted list of every file, directory,
/// and symlink under `source_root`, with file content referenced by sha256
/// into the shared blob pool.
#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct Manifest {
    pub entries: Vec<ManifestEntry>,
}

/// Lightweight descriptor of one snapshot recorded in `timeline.json`.
/// The heavy manifest lives in its own file (`snapshots/{id}.json`) so
/// the timeline file stays small and cheap to read/rewrite.
#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct SnapshotMeta {
    /// Opaque ID used as the manifest filename (`snapshots/{id}.json`).
    /// Monotonic-ish so lexicographic sort matches creation order, with a
    /// trailing random tag to avoid collisions if two runs finish in the
    /// same millisecond.
    pub id: String,
    /// ISO-8601 timestamp (millis precision, UTC).
    pub created_at: String,
    /// Hash of the file-tree (via `folder_sessions::hash_tree`) of the
    /// disk state this snapshot captures. Used by the post-run hook to
    /// cheaply check "does `timeline[cursor]` still match current disk?"
    /// without having to re-materialise the manifest.
    pub disk_tree_hash: String,
}

/// Persisted history for one session. `cursor` is always in
/// `0..snapshots.len()` — an empty timeline is valid (`cursor == 0`,
/// no snapshots).
#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq, Default)]
pub struct Timeline {
    pub snapshots: Vec<SnapshotMeta>,
    pub cursor: usize,
}

impl Timeline {
    /// Clamp cursor to a valid index on load, in case the file was
    /// corrupted or externally edited.
    fn sanitized(mut self) -> Self {
        if self.snapshots.is_empty() {
            self.cursor = 0;
        } else if self.cursor >= self.snapshots.len() {
            self.cursor = self.snapshots.len() - 1;
        }
        self
    }

    pub fn can_undo(&self) -> bool {
        self.cursor > 0 && !self.snapshots.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.snapshots.is_empty() && self.cursor + 1 < self.snapshots.len()
    }

    /// 1-based index of the current snapshot for UI display
    /// (`"{current}/{total}"`). Returns `(0, 0)` when the timeline is
    /// empty so the UI can hide itself.
    pub fn display_position(&self) -> (usize, usize) {
        if self.snapshots.is_empty() {
            (0, 0)
        } else {
            (self.cursor + 1, self.snapshots.len())
        }
    }
}

/// Cache entry for a single file, used to skip re-hashing unchanged
/// files during snapshot scans. Indexed by relative path.
#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct StatCacheEntry {
    /// Modification time in nanoseconds since UNIX epoch.
    pub mtime_nanos: u128,
    /// File size in bytes.
    pub size: u64,
    /// SHA-256 of the **uncompressed** file contents. Same as the blob
    /// pool key, so we can skip both the `fs::read` and the `sha2` hash
    /// computation on a cache hit.
    pub sha256: String,
}

/// Persisted stat cache: `rel_path → StatCacheEntry`. Lives in
/// `{session_dir}/stat-cache.json` and is rewritten atomically after
/// every snapshot scan. Safe to delete externally — a missing cache
/// just means the next scan will re-hash everything.
///
/// **Correctness note**: mtime can lie on some filesystems (clones,
/// NFS, Docker volumes). If it does, we'll reuse a stale sha256 →
/// create a manifest pointing at the OLD blob → the user's disk state
/// appears unchanged when it isn't. Worst case: a change gets missed,
/// undo can't restore it. Best case: user triggers a subsequent run
/// that touches the same file via a real content edit, the mtime
/// updates, and the cache catches up.
///
/// This is an acceptable trade-off because: (1) this is a UI undo
/// buffer, not a backup tool; (2) Git uses the same trick and it
/// works fine for 99% of workflows; (3) the CAS layer below us
/// prevents any actual data corruption — the worst outcome is
/// suboptimal undo.
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct StatCache {
    pub entries: HashMap<String, StatCacheEntry>,
}

/// Pre-run marker: a frozen snapshot of disk taken the moment a new agent
/// run started, held on disk so the post-run code can compare against the
/// live disk state (even after process restart) and decide whether to
/// commit the snapshot into the timeline.
///
/// `pre_run_tree_hash` is the `hash_tree(FileTreeNode)` value of the
/// pre-run disk state. It's stored alongside the manifest so the post-run
/// comparison can be done without having to re-materialize the pre-run
/// state from blobs — we just re-scan disk, hash the result, and compare.
#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct PendingSnapshot {
    pub pre_run_tree_hash: String,
    pub manifest: Manifest,
}

/// Store bound to a single cowork folder session.
pub struct SnapshotStore {
    session_dir: PathBuf,
}

impl SnapshotStore {
    /// Resolve the per-session snapshot directory from the app handle. Does
    /// not create any files — callers hit [`Self::snapshot`], [`Self::apply`],
    /// etc. which lazy-create subdirs as needed.
    pub fn for_session(app: &AppHandle, session_id: &str) -> Result<Self, String> {
        let session_dir = folder_snapshot_session_dir(app, session_id)?;
        Ok(Self { session_dir })
    }

    /// Test-only constructor: bypasses the Tauri app handle and uses the
    /// provided directory directly.
    #[cfg(test)]
    pub fn from_dir(session_dir: PathBuf) -> Self {
        Self { session_dir }
    }

    fn blobs_dir(&self) -> PathBuf {
        self.session_dir.join(BLOBS_DIR_NAME)
    }

    fn snapshots_dir(&self) -> PathBuf {
        self.session_dir.join(SNAPSHOTS_DIR_NAME)
    }

    fn timeline_path(&self) -> PathBuf {
        self.session_dir.join(TIMELINE_FILE_NAME)
    }

    fn timeline_tmp_path(&self) -> PathBuf {
        self.session_dir.join(TIMELINE_TMP_FILE_NAME)
    }

    fn pending_path(&self) -> PathBuf {
        self.session_dir.join(PENDING_FILE_NAME)
    }

    fn pending_tmp_path(&self) -> PathBuf {
        self.session_dir.join(PENDING_TMP_FILE_NAME)
    }

    fn manifest_path(&self, snapshot_id: &str) -> PathBuf {
        self.snapshots_dir().join(format!("{snapshot_id}.json"))
    }

    fn manifest_tmp_path(&self, snapshot_id: &str) -> PathBuf {
        self.snapshots_dir().join(format!("{snapshot_id}.json.tmp"))
    }

    fn stat_cache_path(&self) -> PathBuf {
        self.session_dir.join(STAT_CACHE_FILE_NAME)
    }

    fn stat_cache_tmp_path(&self) -> PathBuf {
        self.session_dir.join(STAT_CACHE_TMP_FILE_NAME)
    }

    /// Absolute path to a blob's on-disk location. All blob files are
    /// zstd-compressed (`.zst` suffix); the sha256 in the filename
    /// always refers to the **uncompressed** contents so dedup keys
    /// stay consistent with caller-visible hashes.
    fn blob_path_for(&self, hash: &str) -> PathBuf {
        // Shard by first 2 hex chars to keep any one directory small.
        let mut path = self.blobs_dir();
        path.push(&hash[..2]);
        path.push(format!("{hash}{BLOB_SUFFIX}"));
        path
    }

    /// Load the persisted stat cache for this session. Returns an empty
    /// cache when the file is missing or corrupt — the next scan will
    /// re-hash everything and rebuild it from scratch, which is slower
    /// but always correct.
    pub fn read_stat_cache(&self) -> StatCache {
        let path = self.stat_cache_path();
        if !path.exists() {
            return StatCache::default();
        }
        match fs::read_to_string(&path) {
            Ok(contents) => serde_json::from_str(&contents).unwrap_or_else(|error| {
                eprintln!(
                    "[cowork] stat-cache: failed to parse {} ({}), resetting",
                    path.display(),
                    error
                );
                StatCache::default()
            }),
            Err(error) => {
                eprintln!(
                    "[cowork] stat-cache: failed to read {} ({}), resetting",
                    path.display(),
                    error
                );
                StatCache::default()
            }
        }
    }

    /// Atomically persist the stat cache. Best-effort — a failure here
    /// is logged but not propagated, because losing the cache only
    /// degrades snapshot speed, never correctness.
    pub fn write_stat_cache(&self, cache: &StatCache) {
        if let Err(error) = self.try_write_stat_cache(cache) {
            eprintln!(
                "[cowork] stat-cache: failed to persist cache: {}",
                error
            );
        }
    }

    fn try_write_stat_cache(&self, cache: &StatCache) -> Result<(), String> {
        fs::create_dir_all(&self.session_dir).map_err(|error| {
            format!(
                "Failed to create session dir {}: {}",
                self.session_dir.display(),
                error
            )
        })?;
        let tmp_path = self.stat_cache_tmp_path();
        let serialized = serde_json::to_vec(cache).map_err(|error| {
            format!("Failed to serialize stat cache: {}", error)
        })?;
        fs::write(&tmp_path, serialized).map_err(|error| {
            format!(
                "Failed to write stat cache tmp file {}: {}",
                tmp_path.display(),
                error
            )
        })?;
        fs::rename(&tmp_path, self.stat_cache_path()).map_err(|error| {
            format!(
                "Failed to commit stat cache to {}: {}",
                self.stat_cache_path().display(),
                error
            )
        })
    }

    /// Walk `source_root` recursively, copy every unique file into the
    /// blob pool, and return an in-memory manifest. The returned
    /// manifest is not persisted yet — the caller chooses whether to
    /// commit it via [`Self::push_snapshot`] or discard it by calling
    /// [`Self::gc_unreferenced_blobs`] without referencing its blobs
    /// anywhere.
    ///
    /// Two storage optimizations are applied during the walk:
    ///
    /// 1. **Stat cache** avoids hashing files whose `(mtime, size)`
    ///    haven't changed since the last scan, reusing the previously
    ///    computed sha256. Saves ~50× snapshot time on subsequent runs.
    /// 2. **Zstd compression** shrinks text-heavy blobs 60-80% (applied
    ///    inside [`Self::store_blob`]).
    pub fn snapshot(&self, source_root: &Path) -> Result<Manifest, String> {
        if !source_root.exists() {
            return Err(format!(
                "Snapshot source does not exist: {}",
                source_root.display()
            ));
        }
        if !source_root.is_dir() {
            return Err(format!(
                "Snapshot source is not a directory: {}",
                source_root.display()
            ));
        }

        fs::create_dir_all(self.blobs_dir()).map_err(|error| {
            format!(
                "Failed to create snapshot blobs dir {}: {}",
                self.blobs_dir().display(),
                error
            )
        })?;

        let previous_cache = self.read_stat_cache();
        let mut next_cache = StatCache::default();
        let mut entries = Vec::new();
        walk_source_tree(
            source_root,
            source_root,
            &mut entries,
            self,
            &previous_cache,
            &mut next_cache,
        )?;
        // Sort pre-order by rel_path so manifests are deterministic regardless
        // of OS `read_dir` ordering.
        entries.sort_by(|left, right| left.rel_path().cmp(right.rel_path()));

        // Best-effort persist the refreshed cache for the next scan.
        self.write_stat_cache(&next_cache);

        Ok(Manifest { entries })
    }

    /// Read the persisted timeline. Returns an empty timeline (cursor=0,
    /// snapshots=[]) if `timeline.json` does not exist. Applies a clamp
    /// to `cursor` so a corrupted/hand-edited file can't break callers
    /// that assume `cursor` is a valid index.
    pub fn read_timeline(&self) -> Result<Timeline, String> {
        let timeline_path = self.timeline_path();
        if !timeline_path.exists() {
            return Ok(Timeline::default());
        }

        let contents = fs::read_to_string(&timeline_path).map_err(|error| {
            format!(
                "Failed to read timeline {}: {}",
                timeline_path.display(),
                error
            )
        })?;

        let timeline: Timeline = serde_json::from_str(&contents).map_err(|error| {
            format!(
                "Failed to parse timeline {}: {}",
                timeline_path.display(),
                error
            )
        })?;

        Ok(timeline.sanitized())
    }

    /// Atomically replace `timeline.json` on disk. Writes to a sibling
    /// `.tmp` file first and then renames into place so readers never
    /// see partial content.
    pub fn write_timeline(&self, timeline: &Timeline) -> Result<(), String> {
        fs::create_dir_all(&self.session_dir).map_err(|error| {
            format!(
                "Failed to create session snapshot dir {}: {}",
                self.session_dir.display(),
                error
            )
        })?;

        let tmp_path = self.timeline_tmp_path();
        let serialized = serde_json::to_vec_pretty(timeline).map_err(|error| {
            format!("Failed to serialize timeline: {}", error)
        })?;
        fs::write(&tmp_path, serialized).map_err(|error| {
            format!(
                "Failed to write timeline tmp file {}: {}",
                tmp_path.display(),
                error
            )
        })?;
        fs::rename(&tmp_path, self.timeline_path()).map_err(|error| {
            format!(
                "Failed to commit timeline to {}: {}",
                self.timeline_path().display(),
                error
            )
        })?;

        Ok(())
    }

    /// Read a snapshot manifest by id. Used when Undo/Redo needs to
    /// materialize a specific timeline entry on disk.
    pub fn read_manifest(&self, snapshot_id: &str) -> Result<Manifest, String> {
        let path = self.manifest_path(snapshot_id);
        let contents = fs::read_to_string(&path).map_err(|error| {
            format!(
                "Failed to read snapshot manifest {}: {}",
                path.display(),
                error
            )
        })?;
        serde_json::from_str(&contents).map_err(|error| {
            format!(
                "Failed to parse snapshot manifest {}: {}",
                path.display(),
                error
            )
        })
    }

    /// Atomically write a snapshot manifest. Caller is responsible for
    /// choosing a unique `snapshot_id`.
    fn write_manifest(
        &self,
        snapshot_id: &str,
        manifest: &Manifest,
    ) -> Result<(), String> {
        fs::create_dir_all(self.snapshots_dir()).map_err(|error| {
            format!(
                "Failed to create snapshots dir {}: {}",
                self.snapshots_dir().display(),
                error
            )
        })?;

        let tmp_path = self.manifest_tmp_path(snapshot_id);
        let serialized = serde_json::to_vec_pretty(manifest).map_err(|error| {
            format!("Failed to serialize manifest {snapshot_id}: {error}")
        })?;
        fs::write(&tmp_path, serialized).map_err(|error| {
            format!(
                "Failed to write manifest tmp file {}: {}",
                tmp_path.display(),
                error
            )
        })?;
        fs::rename(&tmp_path, self.manifest_path(snapshot_id)).map_err(|error| {
            format!(
                "Failed to commit manifest {}: {}",
                self.manifest_path(snapshot_id).display(),
                error
            )
        })?;

        Ok(())
    }

    /// Delete a snapshot manifest file. Idempotent — a missing file is a
    /// no-op. Does **not** touch blobs; the caller is expected to follow
    /// up with `gc_unreferenced_blobs()` after a batch of deletions so
    /// the pool stays in sync with the remaining timeline entries.
    pub fn delete_manifest(&self, snapshot_id: &str) -> Result<(), String> {
        let path = self.manifest_path(snapshot_id);
        if path.exists() {
            fs::remove_file(&path).map_err(|error| {
                format!(
                    "Failed to delete manifest {}: {}",
                    path.display(),
                    error
                )
            })?;
        }
        Ok(())
    }

    /// Persist a new `Manifest` as a fresh snapshot and return its
    /// metadata. The caller is responsible for splicing the returned
    /// [`SnapshotMeta`] into the timeline and writing it back via
    /// [`Self::write_timeline`].
    ///
    /// `disk_tree_hash` should be the `hash_tree` of the file-tree that
    /// this manifest represents, so the post-run "does disk still match
    /// this snapshot?" check can be a pure string compare.
    pub fn push_snapshot(
        &self,
        manifest: &Manifest,
        disk_tree_hash: String,
    ) -> Result<SnapshotMeta, String> {
        let id = new_snapshot_id();
        self.write_manifest(&id, manifest)?;
        Ok(SnapshotMeta {
            id,
            created_at: Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true),
            disk_tree_hash,
        })
    }

    /// Atomically write the pre-run pending marker. Called at the moment
    /// a new run starts, to capture the disk state that the post-run hook
    /// can later compare against and either commit (disk changed) or
    /// discard (disk unchanged).
    ///
    /// Safe to call when a `pending.json` already exists — it overwrites.
    /// The caller decides the overwrite policy (session_gateway checks
    /// "does pending already exist?" to make the pre-run hook idempotent
    /// within a single run while still allowing chained runs to
    /// re-snapshot).
    pub fn write_pending(&self, pending: &PendingSnapshot) -> Result<(), String> {
        fs::create_dir_all(&self.session_dir).map_err(|error| {
            format!(
                "Failed to create session snapshot dir {}: {}",
                self.session_dir.display(),
                error
            )
        })?;

        let tmp_path = self.pending_tmp_path();
        let serialized = serde_json::to_vec_pretty(pending).map_err(|error| {
            format!("Failed to serialize pending snapshot: {}", error)
        })?;
        fs::write(&tmp_path, serialized).map_err(|error| {
            format!(
                "Failed to write pending snapshot tmp file {}: {}",
                tmp_path.display(),
                error
            )
        })?;
        fs::rename(&tmp_path, self.pending_path()).map_err(|error| {
            format!(
                "Failed to commit pending snapshot to {}: {}",
                self.pending_path().display(),
                error
            )
        })?;

        Ok(())
    }

    /// Read the pending marker if it exists. Returns `Ok(None)` when
    /// there's nothing pending (normal case: no run has started since the
    /// last `take_pending` call).
    pub fn read_pending(&self) -> Result<Option<PendingSnapshot>, String> {
        let pending_path = self.pending_path();
        if !pending_path.exists() {
            return Ok(None);
        }

        let contents = fs::read_to_string(&pending_path).map_err(|error| {
            format!(
                "Failed to read pending snapshot {}: {}",
                pending_path.display(),
                error
            )
        })?;

        let pending: PendingSnapshot = serde_json::from_str(&contents).map_err(|error| {
            format!(
                "Failed to parse pending snapshot {}: {}",
                pending_path.display(),
                error
            )
        })?;

        Ok(Some(pending))
    }

    /// Remove the pending marker. Idempotent — does nothing if already
    /// absent. Does NOT touch blobs; callers should follow up with
    /// `gc_unreferenced_blobs()` to reclaim the pending snapshot's blobs
    /// if they're not referenced by `slot.json`.
    pub fn clear_pending(&self) -> Result<(), String> {
        let pending_path = self.pending_path();
        if pending_path.exists() {
            fs::remove_file(&pending_path).map_err(|error| {
                format!(
                    "Failed to remove pending snapshot {}: {}",
                    pending_path.display(),
                    error
                )
            })?;
        }
        Ok(())
    }

    /// Materialise the given manifest onto `source_root`: files on disk
    /// that are not in the manifest get removed, files missing on disk
    /// (or whose sha256 doesn't match) get rewritten from the blob pool,
    /// and directories/symlinks are created as needed.
    ///
    /// This is a pure "make disk match manifest" operation — it does
    /// **not** touch the timeline or pending marker. The caller
    /// (`undo_commands` / session_gateway) is responsible for updating
    /// the timeline cursor after a successful apply.
    pub fn apply_manifest(
        &self,
        manifest: &Manifest,
        source_root: &Path,
    ) -> Result<(), String> {
        if !source_root.exists() {
            fs::create_dir_all(source_root).map_err(|error| {
                format!(
                    "Failed to recreate source root {}: {}",
                    source_root.display(),
                    error
                )
            })?;
        }

        // Build set of rel_paths the manifest wants on disk.
        let wanted: HashSet<&str> =
            manifest.entries.iter().map(|entry| entry.rel_path()).collect();

        // Walk current disk, delete anything not in `wanted`. Walk files
        // first, directories second (bottom-up) so non-empty dir removal
        // works.
        let mut disk_files = Vec::new();
        let mut disk_dirs = Vec::new();
        let mut disk_symlinks = Vec::new();
        collect_disk_entries(
            source_root,
            source_root,
            &mut disk_files,
            &mut disk_dirs,
            &mut disk_symlinks,
        )?;

        for (rel_path, abs_path) in &disk_symlinks {
            if !wanted.contains(rel_path.as_str()) {
                let _ = fs::remove_file(abs_path);
            }
        }
        for (rel_path, abs_path) in &disk_files {
            if !wanted.contains(rel_path.as_str()) {
                fs::remove_file(abs_path).map_err(|error| {
                    format!(
                        "Failed to remove {} during snapshot apply: {}",
                        abs_path.display(),
                        error
                    )
                })?;
            }
        }
        // Sort dirs longest-first so we remove children before parents.
        disk_dirs.sort_by(|left, right| right.0.len().cmp(&left.0.len()));
        for (rel_path, abs_path) in &disk_dirs {
            if !wanted.contains(rel_path.as_str()) {
                // Only remove if empty after file cleanup. If it's still
                // populated (e.g. nested wanted file survived), skip.
                let _ = fs::remove_dir(abs_path);
            }
        }

        // Now materialise the manifest: create dirs, write files, create
        // symlinks. We walk `manifest.entries` in pre-order (already
        // sorted by rel_path, which is lexicographic and close enough to
        // pre-order for parent-before-child — we double-guard by
        // `create_dir_all` for files).
        for entry in &manifest.entries {
            let rel_path = entry.rel_path();
            let abs_path = source_root.join(sanitize_rel_path(rel_path)?);

            match entry {
                ManifestEntry::Dir { .. } => {
                    fs::create_dir_all(&abs_path).map_err(|error| {
                        format!(
                            "Failed to create directory {}: {}",
                            abs_path.display(),
                            error
                        )
                    })?;
                }
                ManifestEntry::File { sha256, .. } => {
                    // Skip rewrite if disk already matches (saves I/O).
                    if file_matches_hash(&abs_path, sha256).unwrap_or(false) {
                        continue;
                    }

                    if let Some(parent) = abs_path.parent() {
                        fs::create_dir_all(parent).map_err(|error| {
                            format!(
                                "Failed to create parent dir {}: {}",
                                parent.display(),
                                error
                            )
                        })?;
                    }

                    let bytes = self.read_blob(sha256)?;

                    // Atomic write via tmp + rename. Use a dotfile tmp name
                    // alongside the target so it shares the same filesystem.
                    let tmp_path = tmp_sibling(&abs_path);
                    fs::write(&tmp_path, bytes).map_err(|error| {
                        format!(
                            "Failed to write tmp file {}: {}",
                            tmp_path.display(),
                            error
                        )
                    })?;
                    fs::rename(&tmp_path, &abs_path).map_err(|error| {
                        format!(
                            "Failed to commit file {}: {}",
                            abs_path.display(),
                            error
                        )
                    })?;
                }
                ManifestEntry::Symlink { target, .. } => {
                    // Remove any existing entry at that path first so we
                    // don't clash with an existing regular file.
                    let _ = fs::remove_file(&abs_path);
                    if let Some(parent) = abs_path.parent() {
                        fs::create_dir_all(parent).map_err(|error| {
                            format!(
                                "Failed to create parent dir {}: {}",
                                parent.display(),
                                error
                            )
                        })?;
                    }
                    create_symlink(target, &abs_path)?;
                }
            }
        }

        Ok(())
    }

    /// Remove any blob files that are not referenced by:
    ///
    /// - any manifest in the current timeline, OR
    /// - the in-flight pending marker (if any).
    ///
    /// Also cleans up orphaned `snapshots/*.json` files whose IDs are
    /// no longer in the timeline (left behind by a half-completed
    /// truncation, retention drop, or crash).
    ///
    /// Idempotent: safe to call more than once.
    pub fn gc_unreferenced_blobs(&self) -> Result<(), String> {
        // First, collect every sha256 that is reachable from the live
        // timeline + pending marker. This is the "keep set".
        let mut referenced: HashSet<String> = HashSet::new();

        let timeline = self.read_timeline()?;
        let alive_ids: HashSet<String> =
            timeline.snapshots.iter().map(|s| s.id.clone()).collect();

        for snapshot in &timeline.snapshots {
            // Best-effort: if a manifest is unreadable (e.g. corrupted),
            // we log and keep GC running — better to leak blobs than to
            // wipe the pool outright.
            match self.read_manifest(&snapshot.id) {
                Ok(manifest) => {
                    for entry in &manifest.entries {
                        if let ManifestEntry::File { sha256, .. } = entry {
                            referenced.insert(sha256.clone());
                        }
                    }
                }
                Err(error) => {
                    eprintln!(
                        "[cowork] gc: failed to read manifest {} during scan: {}",
                        snapshot.id, error
                    );
                }
            }
        }

        if let Some(pending) = self.read_pending()? {
            for entry in &pending.manifest.entries {
                if let ManifestEntry::File { sha256, .. } = entry {
                    referenced.insert(sha256.clone());
                }
            }
        }

        // Clean up orphan manifest files (IDs not in the timeline).
        if let Ok(entries) = fs::read_dir(self.snapshots_dir()) {
            for entry in entries.flatten() {
                let path = entry.path();
                let Some(file_name) = path.file_name().and_then(|n| n.to_str()) else {
                    continue;
                };
                // Strip `.json` / `.json.tmp` and check membership in
                // `alive_ids`. `.tmp` leftovers are always orphans.
                if file_name.ends_with(".json.tmp") {
                    let _ = fs::remove_file(&path);
                    continue;
                }
                let Some(id) = file_name.strip_suffix(".json") else {
                    continue;
                };
                if !alive_ids.contains(id) {
                    let _ = fs::remove_file(&path);
                }
            }
        }

        let blobs_dir = self.blobs_dir();
        if !blobs_dir.exists() {
            return Ok(());
        }

        let shard_entries = match fs::read_dir(&blobs_dir) {
            Ok(iter) => iter,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(error) => {
                return Err(format!(
                    "Failed to scan blobs dir {}: {}",
                    blobs_dir.display(),
                    error
                ))
            }
        };

        for shard_entry in shard_entries.flatten() {
            let shard_path = shard_entry.path();
            if !shard_path.is_dir() {
                continue;
            }

            let blob_iter = match fs::read_dir(&shard_path) {
                Ok(iter) => iter,
                Err(_) => continue,
            };
            for blob_entry in blob_iter.flatten() {
                let blob_path = blob_entry.path();
                let Some(file_name) = blob_path.file_name().and_then(|n| n.to_str()) else {
                    continue;
                };
                // Skip any `.tmp` leftovers from interrupted writes —
                // they're orphaned tmp files from a crashed snapshot, not
                // valid blobs. Clean them up.
                if file_name.ends_with(".tmp") {
                    let _ = fs::remove_file(&blob_path);
                    continue;
                }
                // Strip the compression suffix to recover the canonical
                // sha256 key before looking it up in the reference set.
                // Legacy (uncompressed) blobs would have no suffix — we
                // treat those as orphans and sweep them too, since the
                // current code only writes `.zst` files.
                let Some(hash) = file_name.strip_suffix(BLOB_SUFFIX) else {
                    let _ = fs::remove_file(&blob_path);
                    continue;
                };
                if !referenced.contains(hash) {
                    let _ = fs::remove_file(&blob_path);
                }
            }

            // Remove now-empty shard dir.
            if fs::read_dir(&shard_path)
                .map(|mut iter| iter.next().is_none())
                .unwrap_or(false)
            {
                let _ = fs::remove_dir(&shard_path);
            }
        }

        Ok(())
    }

    /// Copy a single file's bytes into the blob pool, returning its sha256.
    /// If the blob already exists, we skip the write.
    /// Hash, compress, and atomically write a file's contents into the
    /// CAS pool. Returns the sha256 of the **uncompressed** bytes (the
    /// CAS key). If an identical blob already exists, skip the write.
    ///
    /// Blobs on disk are always zstd-compressed. The compression
    /// happens at store time; consumers use [`Self::read_blob`] to get
    /// the original bytes back.
    fn store_blob(&self, bytes: &[u8]) -> Result<String, String> {
        let hash = sha256_hex(bytes);
        let blob_path = self.blob_path_for(&hash);
        if blob_path.exists() {
            return Ok(hash);
        }

        if let Some(parent) = blob_path.parent() {
            fs::create_dir_all(parent).map_err(|error| {
                format!(
                    "Failed to create blob shard dir {}: {}",
                    parent.display(),
                    error
                )
            })?;
        }

        let compressed = zstd::encode_all(bytes, ZSTD_LEVEL).map_err(|error| {
            format!(
                "Failed to zstd-compress blob {}: {}",
                hash, error
            )
        })?;

        // Append `.tmp` to the full filename (not set_extension, which
        // would replace `.zst` and lose the suffix info).
        let tmp_path = {
            let parent = blob_path.parent().unwrap_or_else(|| Path::new("."));
            let file_name = blob_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| format!("{hash}{BLOB_SUFFIX}"));
            parent.join(format!("{file_name}.tmp"))
        };
        fs::write(&tmp_path, &compressed).map_err(|error| {
            format!(
                "Failed to write blob tmp file {}: {}",
                tmp_path.display(),
                error
            )
        })?;
        fs::rename(&tmp_path, &blob_path).map_err(|error| {
            format!(
                "Failed to commit blob {}: {}",
                blob_path.display(),
                error
            )
        })?;
        Ok(hash)
    }

    /// Load a blob from the CAS pool and decompress it. Returns the
    /// original uncompressed bytes. Used by [`Self::apply_manifest`]
    /// when materializing a snapshot onto disk.
    fn read_blob(&self, hash: &str) -> Result<Vec<u8>, String> {
        let blob_path = self.blob_path_for(hash);
        let compressed = fs::read(&blob_path).map_err(|error| {
            format!(
                "Failed to read blob {}: {}",
                blob_path.display(),
                error
            )
        })?;
        zstd::decode_all(compressed.as_slice()).map_err(|error| {
            format!(
                "Failed to zstd-decompress blob {}: {}",
                blob_path.display(),
                error
            )
        })
    }
}

// ============================================================================
// Helpers
// ============================================================================

fn walk_source_tree(
    root: &Path,
    current: &Path,
    entries: &mut Vec<ManifestEntry>,
    store: &SnapshotStore,
    previous_cache: &StatCache,
    next_cache: &mut StatCache,
) -> Result<(), String> {
    let read_dir = fs::read_dir(current).map_err(|error| {
        format!(
            "Failed to read directory {} during snapshot: {}",
            current.display(),
            error
        )
    })?;

    for entry_result in read_dir {
        let entry = entry_result.map_err(|error| {
            format!(
                "Failed to iterate {} during snapshot: {}",
                current.display(),
                error
            )
        })?;
        let abs_path = entry.path();
        let metadata = fs::symlink_metadata(&abs_path).map_err(|error| {
            format!(
                "Failed to stat {} during snapshot: {}",
                abs_path.display(),
                error
            )
        })?;

        let rel_path = rel_path_string(root, &abs_path)?;
        let file_type = metadata.file_type();

        if file_type.is_symlink() {
            let target = fs::read_link(&abs_path)
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default();
            entries.push(ManifestEntry::Symlink { rel_path, target });
            continue;
        }

        if file_type.is_dir() {
            entries.push(ManifestEntry::Dir {
                rel_path: rel_path.clone(),
            });
            walk_source_tree(root, &abs_path, entries, store, previous_cache, next_cache)?;
            continue;
        }

        if file_type.is_file() {
            let size = metadata.len();
            let mtime_nanos = metadata
                .modified()
                .ok()
                .and_then(|mtime| mtime.duration_since(UNIX_EPOCH).ok())
                .map(|dur| dur.as_nanos())
                .unwrap_or(0);

            // Stat cache fast path: if the previous scan recorded
            // this file with matching (mtime, size), reuse its sha256
            // and skip both the `fs::read` and the SHA-256 computation.
            // We still verify the blob is on disk — GC could have
            // dropped it — before trusting the cache entry.
            let cached = previous_cache.entries.get(&rel_path);
            let reuse_hash = match cached {
                Some(entry)
                    if entry.mtime_nanos == mtime_nanos
                        && entry.size == size
                        && store.blob_path_for(&entry.sha256).exists() =>
                {
                    Some(entry.sha256.clone())
                }
                _ => None,
            };

            let sha256 = if let Some(hash) = reuse_hash {
                hash
            } else {
                let bytes = fs::read(&abs_path).map_err(|error| {
                    format!(
                        "Failed to read file {} during snapshot: {}",
                        abs_path.display(),
                        error
                    )
                })?;
                store.store_blob(&bytes)?
            };

            next_cache.entries.insert(
                rel_path.clone(),
                StatCacheEntry {
                    mtime_nanos,
                    size,
                    sha256: sha256.clone(),
                },
            );
            entries.push(ManifestEntry::File { rel_path, sha256 });
            continue;
        }

        // Unknown file type (socket, device, …) — skip and log. We don't
        // want to fail the whole snapshot for one weird entry.
        eprintln!(
            "[cowork] snapshot skipping non-regular entry {} (unknown file type)",
            abs_path.display()
        );
    }

    Ok(())
}

fn collect_disk_entries(
    root: &Path,
    current: &Path,
    files: &mut Vec<(String, PathBuf)>,
    dirs: &mut Vec<(String, PathBuf)>,
    symlinks: &mut Vec<(String, PathBuf)>,
) -> Result<(), String> {
    let read_dir = match fs::read_dir(current) {
        Ok(iter) => iter,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => {
            return Err(format!(
                "Failed to read directory {}: {}",
                current.display(),
                error
            ));
        }
    };

    for entry_result in read_dir {
        let entry = entry_result.map_err(|error| {
            format!(
                "Failed to iterate {}: {}",
                current.display(),
                error
            )
        })?;
        let abs_path = entry.path();
        let metadata = match fs::symlink_metadata(&abs_path) {
            Ok(m) => m,
            Err(_) => continue,
        };
        let rel_path = rel_path_string(root, &abs_path)?;
        let file_type = metadata.file_type();

        if file_type.is_symlink() {
            symlinks.push((rel_path, abs_path));
        } else if file_type.is_dir() {
            dirs.push((rel_path.clone(), abs_path.clone()));
            collect_disk_entries(root, &abs_path, files, dirs, symlinks)?;
        } else if file_type.is_file() {
            files.push((rel_path, abs_path));
        }
    }

    Ok(())
}

fn rel_path_string(root: &Path, abs_path: &Path) -> Result<String, String> {
    let rel = abs_path.strip_prefix(root).map_err(|error| {
        format!(
            "Path {} is not within root {}: {}",
            abs_path.display(),
            root.display(),
            error
        )
    })?;
    Ok(rel.to_string_lossy().replace('\\', "/"))
}

fn sanitize_rel_path(rel_path: &str) -> Result<PathBuf, String> {
    // Reject anything that would escape the root.
    let path = PathBuf::from(rel_path);
    for component in path.components() {
        match component {
            Component::Normal(_) | Component::CurDir => {}
            _ => {
                return Err(format!(
                    "Manifest rel_path {rel_path:?} contains an unsafe component"
                ))
            }
        }
    }
    Ok(path)
}

/// Generate a fresh snapshot ID. Format: `{epoch_millis}-{rand_hex}`.
/// The leading timestamp means lexicographic sort matches creation
/// order, which is the property the [`Timeline::snapshots`] list needs
/// when we do GC by "files in `snapshots/` dir not in timeline".
/// The trailing random hex (8 chars of the current-time nanos hash)
/// prevents collisions if two runs finish in the same millisecond.
fn new_snapshot_id() -> String {
    let now = Utc::now();
    let millis = now.timestamp_millis();
    let nanos = now.timestamp_subsec_nanos();
    let rand_tag: String = Sha256::digest(nanos.to_le_bytes())
        .iter()
        .take(4)
        .map(|b| format!("{b:02x}"))
        .collect();
    format!("{millis:013}-{rand_tag}")
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|value| format!("{value:02x}")).collect()
}

fn file_matches_hash(abs_path: &Path, expected: &str) -> Result<bool, String> {
    if !abs_path.exists() {
        return Ok(false);
    }
    let metadata = match fs::symlink_metadata(abs_path) {
        Ok(m) => m,
        Err(_) => return Ok(false),
    };
    if !metadata.is_file() {
        return Ok(false);
    }

    // Stream-hash so we don't allocate huge Vecs for large files we only
    // need to compare.
    let mut file = fs::File::open(abs_path).map_err(|error| {
        format!("Failed to open {} for hash compare: {}", abs_path.display(), error)
    })?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let n = file.read(&mut buffer).map_err(|error| {
            format!(
                "Failed to read {} during hash compare: {}",
                abs_path.display(),
                error
            )
        })?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }
    let hash_hex: String = hasher
        .finalize()
        .iter()
        .map(|value| format!("{value:02x}"))
        .collect();
    Ok(hash_hex == expected)
}

fn tmp_sibling(abs_path: &Path) -> PathBuf {
    let parent = abs_path.parent().unwrap_or_else(|| Path::new("."));
    let file_name = abs_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();
    parent.join(format!(".{file_name}.cowork-tmp"))
}

#[cfg(unix)]
fn create_symlink(target: &str, link_path: &Path) -> Result<(), String> {
    use std::os::unix::fs::symlink;
    symlink(target, link_path).map_err(|error| {
        format!(
            "Failed to create symlink {} → {}: {}",
            link_path.display(),
            target,
            error
        )
    })
}

#[cfg(windows)]
fn create_symlink(target: &str, link_path: &Path) -> Result<(), String> {
    // On Windows we can't know for sure whether the target was a file or
    // directory originally. Best effort: try file first, fall back to dir.
    use std::os::windows::fs::{symlink_dir, symlink_file};
    if let Err(file_err) = symlink_file(target, link_path) {
        if let Err(dir_err) = symlink_dir(target, link_path) {
            return Err(format!(
                "Failed to create symlink {} → {} (file: {}, dir: {})",
                link_path.display(),
                target,
                file_err,
                dir_err
            ));
        }
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn create_symlink(_target: &str, _link_path: &Path) -> Result<(), String> {
    Err("Symlinks are not supported on this platform".to_string())
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

    struct TestDirs {
        src: PathBuf,
        store: PathBuf,
    }

    impl Drop for TestDirs {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.src);
            let _ = fs::remove_dir_all(&self.store);
        }
    }

    fn make_test_dirs(tag: &str) -> TestDirs {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after unix epoch")
            .as_nanos();
        let src = std::env::temp_dir().join(format!("ii-agent-snapshot-src-{tag}-{unique}"));
        let store = std::env::temp_dir().join(format!("ii-agent-snapshot-store-{tag}-{unique}"));
        fs::create_dir_all(&src).unwrap();
        fs::create_dir_all(&store).unwrap();
        TestDirs { src, store }
    }

    fn write(path: &Path, contents: &[u8]) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, contents).unwrap();
    }

    fn read_all_files_sorted(root: &Path) -> Vec<(String, Vec<u8>)> {
        let mut out = Vec::new();
        let mut files = Vec::new();
        let mut dirs = Vec::new();
        let mut syms = Vec::new();
        collect_disk_entries(root, root, &mut files, &mut dirs, &mut syms).unwrap();
        for (rel, abs) in files {
            out.push((rel, fs::read(abs).unwrap()));
        }
        out.sort_by(|a, b| a.0.cmp(&b.0));
        out
    }

    /// Helper to snapshot current disk and immediately push it onto the
    /// timeline. Mirrors what `session_gateway::push_post_run_snapshot`
    /// does in production, simplified for tests.
    fn snapshot_and_push(store: &SnapshotStore, src: &Path, tag: &str) {
        let manifest = store.snapshot(src).unwrap();
        let meta = store.push_snapshot(&manifest, format!("tree-hash-{tag}")).unwrap();
        let mut timeline = store.read_timeline().unwrap();
        timeline.snapshots.push(meta);
        timeline.cursor = timeline.snapshots.len() - 1;
        store.write_timeline(&timeline).unwrap();
    }

    #[test]
    fn snapshot_then_apply_roundtrip() {
        let dirs = make_test_dirs("roundtrip");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("a.txt"), b"hello");
        write(&dirs.src.join("sub/b.txt"), b"world");
        write(&dirs.src.join("sub/nested/c.txt"), b"nested");

        let manifest = store.snapshot(&dirs.src).unwrap();
        let original = read_all_files_sorted(&dirs.src);

        // Mutate disk in various ways: modify, delete, add.
        write(&dirs.src.join("a.txt"), b"hello-modified");
        fs::remove_file(dirs.src.join("sub/b.txt")).unwrap();
        write(&dirs.src.join("sub/added.txt"), b"brand new");
        fs::remove_file(dirs.src.join("sub/nested/c.txt")).unwrap();
        fs::remove_dir(dirs.src.join("sub/nested")).unwrap();

        // apply_manifest restores from the in-memory manifest.
        store.apply_manifest(&manifest, &dirs.src).unwrap();

        let restored = read_all_files_sorted(&dirs.src);
        assert_eq!(
            restored, original,
            "applying the manifest should restore disk byte-for-byte"
        );
    }

    #[test]
    fn timeline_push_and_navigate() {
        let dirs = make_test_dirs("timeline-nav");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        // Three states, pushed in order: A, B, C.
        write(&dirs.src.join("file.txt"), b"state-A");
        snapshot_and_push(&store, &dirs.src, "A");
        let state_a = read_all_files_sorted(&dirs.src);

        write(&dirs.src.join("file.txt"), b"state-B");
        write(&dirs.src.join("new-in-b.txt"), b"only-in-B");
        snapshot_and_push(&store, &dirs.src, "B");
        let state_b = read_all_files_sorted(&dirs.src);

        write(&dirs.src.join("file.txt"), b"state-C");
        fs::remove_file(dirs.src.join("new-in-b.txt")).unwrap();
        write(&dirs.src.join("new-in-c.txt"), b"only-in-C");
        snapshot_and_push(&store, &dirs.src, "C");
        let state_c = read_all_files_sorted(&dirs.src);

        let timeline = store.read_timeline().unwrap();
        assert_eq!(timeline.snapshots.len(), 3);
        assert_eq!(timeline.cursor, 2);
        assert!(timeline.can_undo());
        assert!(!timeline.can_redo());

        // Walk back: C -> B -> A via apply_manifest + cursor updates.
        let manifest_b = store.read_manifest(&timeline.snapshots[1].id).unwrap();
        store.apply_manifest(&manifest_b, &dirs.src).unwrap();
        assert_eq!(read_all_files_sorted(&dirs.src), state_b);

        let manifest_a = store.read_manifest(&timeline.snapshots[0].id).unwrap();
        store.apply_manifest(&manifest_a, &dirs.src).unwrap();
        assert_eq!(read_all_files_sorted(&dirs.src), state_a);

        // Walk forward: A -> C.
        let manifest_c = store.read_manifest(&timeline.snapshots[2].id).unwrap();
        store.apply_manifest(&manifest_c, &dirs.src).unwrap();
        assert_eq!(read_all_files_sorted(&dirs.src), state_c);
    }

    #[test]
    fn gc_preserves_all_timeline_blobs() {
        let dirs = make_test_dirs("gc-timeline");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        // Two distinct states with different file contents.
        write(&dirs.src.join("a.txt"), b"v1");
        snapshot_and_push(&store, &dirs.src, "v1");

        write(&dirs.src.join("a.txt"), b"v2");
        snapshot_and_push(&store, &dirs.src, "v2");

        store.gc_unreferenced_blobs().unwrap();

        // Both blobs referenced by the two snapshots must survive GC.
        let v1_hash = sha256_hex(b"v1");
        let v2_hash = sha256_hex(b"v2");
        assert!(store.blob_path_for(&v1_hash).exists(), "v1 blob must survive");
        assert!(store.blob_path_for(&v2_hash).exists(), "v2 blob must survive");
    }

    #[test]
    fn gc_drops_orphaned_manifest_files() {
        let dirs = make_test_dirs("gc-orphan");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("a.txt"), b"only");
        snapshot_and_push(&store, &dirs.src, "only");

        // Write a stray manifest file that isn't in the timeline.
        let orphan_id = "00000000000-abcd";
        let manifest = store.snapshot(&dirs.src).unwrap();
        store.write_manifest(orphan_id, &manifest).unwrap();
        assert!(store.manifest_path(orphan_id).exists());

        store.gc_unreferenced_blobs().unwrap();
        assert!(
            !store.manifest_path(orphan_id).exists(),
            "orphaned manifest file should be deleted by GC"
        );
    }

    #[test]
    fn gc_drops_blobs_no_longer_in_timeline() {
        let dirs = make_test_dirs("gc-drop");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("keep.txt"), b"keep");
        write(&dirs.src.join("drop.txt"), b"drop-me");

        // First snapshot has both files.
        snapshot_and_push(&store, &dirs.src, "both");

        // Remove drop.txt from disk and take a fresh snapshot. If we
        // simulate the retention scenario by discarding the first
        // snapshot and keeping only the second, drop-me's blob becomes
        // orphaned.
        fs::remove_file(dirs.src.join("drop.txt")).unwrap();
        let manifest = store.snapshot(&dirs.src).unwrap();
        let meta = store.push_snapshot(&manifest, "after".to_string()).unwrap();

        // Simulate retention: drop the oldest snapshot, keep only the new one.
        let mut timeline = store.read_timeline().unwrap();
        let dropped = timeline.snapshots.remove(0);
        store.delete_manifest(&dropped.id).unwrap();
        timeline.snapshots.push(meta);
        timeline.cursor = 0;
        store.write_timeline(&timeline).unwrap();

        store.gc_unreferenced_blobs().unwrap();

        let drop_hash = sha256_hex(b"drop-me");
        assert!(
            !store.blob_path_for(&drop_hash).exists(),
            "orphaned blob should be GC'd"
        );
        let keep_hash = sha256_hex(b"keep");
        assert!(
            store.blob_path_for(&keep_hash).exists(),
            "blob still referenced must survive"
        );
    }

    #[test]
    fn cas_dedup_identical_content() {
        let dirs = make_test_dirs("dedup");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("one.txt"), b"same");
        write(&dirs.src.join("two.txt"), b"same");
        write(&dirs.src.join("three.txt"), b"same");

        snapshot_and_push(&store, &dirs.src, "same");

        let hash = sha256_hex(b"same");
        let blob_path = store.blob_path_for(&hash);
        assert!(blob_path.exists(), "single shared blob should exist");

        // Count blobs in the shard directory for this hash prefix.
        let shard_dir = store.blobs_dir().join(&hash[..2]);
        let count = fs::read_dir(&shard_dir).unwrap().count();
        assert_eq!(
            count, 1,
            "CAS should dedupe identical file contents into a single blob"
        );
    }

    #[test]
    fn read_timeline_returns_empty_when_missing() {
        let dirs = make_test_dirs("missing");
        let store = SnapshotStore::from_dir(dirs.store.clone());
        let timeline = store.read_timeline().unwrap();
        assert!(timeline.snapshots.is_empty());
        assert_eq!(timeline.cursor, 0);
        assert!(!timeline.can_undo());
        assert!(!timeline.can_redo());
    }

    #[test]
    fn timeline_clamps_cursor_on_load() {
        let dirs = make_test_dirs("clamp");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        // Write a corrupted timeline with cursor out of bounds.
        write(&dirs.src.join("a.txt"), b"a");
        snapshot_and_push(&store, &dirs.src, "a");

        let corrupted = Timeline {
            snapshots: store.read_timeline().unwrap().snapshots,
            cursor: 999,
        };
        store.write_timeline(&corrupted).unwrap();

        // Next read should clamp to last valid index.
        let loaded = store.read_timeline().unwrap();
        assert_eq!(loaded.cursor, loaded.snapshots.len() - 1);
    }

    #[test]
    fn pending_write_read_clear_roundtrip() {
        let dirs = make_test_dirs("pending");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("a.txt"), b"pending-content");
        let manifest = store.snapshot(&dirs.src).unwrap();
        let pending = PendingSnapshot {
            pre_run_tree_hash: "deadbeef".to_string(),
            manifest,
        };

        assert!(store.read_pending().unwrap().is_none());

        store.write_pending(&pending).unwrap();
        let round_tripped = store.read_pending().unwrap().unwrap();
        assert_eq!(round_tripped.pre_run_tree_hash, "deadbeef");

        store.clear_pending().unwrap();
        assert!(store.read_pending().unwrap().is_none());
    }

    #[test]
    fn gc_preserves_pending_blobs() {
        let dirs = make_test_dirs("pending-gc");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("live.txt"), b"lives-in-pending");
        let manifest = store.snapshot(&dirs.src).unwrap();
        let pending = PendingSnapshot {
            pre_run_tree_hash: "hash".to_string(),
            manifest,
        };
        store.write_pending(&pending).unwrap();

        // No timeline entries, just pending. GC must NOT remove the blob.
        store.gc_unreferenced_blobs().unwrap();

        let hash = sha256_hex(b"lives-in-pending");
        let blob_path = store.blob_path_for(&hash);
        assert!(
            blob_path.exists(),
            "pending-referenced blob must survive GC: {}",
            blob_path.display()
        );
    }

    #[test]
    fn sanitize_rel_path_rejects_traversal() {
        assert!(sanitize_rel_path("../escape").is_err());
        assert!(sanitize_rel_path("a/../../b").is_err());
        assert!(sanitize_rel_path("/abs/path").is_err());
        assert!(sanitize_rel_path("ok/sub/file.txt").is_ok());
    }

    // ---- Stat cache ----

    #[test]
    fn stat_cache_reused_on_unchanged_files() {
        let dirs = make_test_dirs("stat-cache");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("a.txt"), b"original content");
        write(&dirs.src.join("b.txt"), b"other content");

        // First snapshot populates the cache with both entries.
        let _ = store.snapshot(&dirs.src).unwrap();
        let cache_v1 = store.read_stat_cache();
        assert!(cache_v1.entries.contains_key("a.txt"));
        assert!(cache_v1.entries.contains_key("b.txt"));
        let a_hash_v1 = cache_v1.entries["a.txt"].sha256.clone();

        // Delete the blob manually to prove the second snapshot would
        // detect a cache hit BUT fall through to re-hash because the
        // blob is missing. After the call the blob should be back.
        let blob_path = store.blob_path_for(&a_hash_v1);
        assert!(blob_path.exists());
        fs::remove_file(&blob_path).unwrap();
        assert!(!blob_path.exists());

        // Re-snapshot without modifying any file. The cache entries
        // should be preserved (same sha256), and the missing blob
        // should be repopulated by the fall-through path.
        let _ = store.snapshot(&dirs.src).unwrap();
        let cache_v2 = store.read_stat_cache();
        assert_eq!(cache_v2.entries["a.txt"].sha256, a_hash_v1);
        assert!(
            blob_path.exists(),
            "missing blob must be recreated on cache fall-through"
        );
    }

    #[test]
    fn stat_cache_rehashes_when_mtime_or_size_changes() {
        let dirs = make_test_dirs("stat-invalidate");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("f.txt"), b"v1");
        let _ = store.snapshot(&dirs.src).unwrap();
        let hash_v1 = store.read_stat_cache().entries["f.txt"].sha256.clone();

        // Change content (different size and — typically — different
        // mtime). The cache key should invalidate and the new blob
        // should have a different hash.
        // Brief sleep ensures mtime changes on filesystems with 1s
        // resolution — not strictly needed if we also change size.
        std::thread::sleep(std::time::Duration::from_millis(15));
        write(&dirs.src.join("f.txt"), b"v2-longer-content");
        let _ = store.snapshot(&dirs.src).unwrap();
        let hash_v2 = store.read_stat_cache().entries["f.txt"].sha256.clone();

        assert_ne!(
            hash_v1, hash_v2,
            "stat cache failed to invalidate after content change"
        );
    }

    // ---- Zstd compression ----

    #[test]
    fn blobs_are_stored_compressed() {
        let dirs = make_test_dirs("zstd");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        // Highly compressible content: repeating pattern.
        let payload = "hello world ".repeat(1000);
        write(&dirs.src.join("compressible.txt"), payload.as_bytes());
        let _ = store.snapshot(&dirs.src).unwrap();

        let hash = sha256_hex(payload.as_bytes());
        let blob_path = store.blob_path_for(&hash);
        assert!(blob_path.exists());

        let on_disk = fs::metadata(&blob_path).unwrap().len() as usize;
        assert!(
            on_disk < payload.len() / 2,
            "compressed blob ({on_disk} B) should be much smaller than \
             raw ({raw} B)",
            raw = payload.len()
        );

        // Decompress and verify round-trip.
        let round_tripped = store.read_blob(&hash).unwrap();
        assert_eq!(round_tripped, payload.as_bytes());
    }

    #[test]
    fn apply_manifest_round_trip_with_compression() {
        // End-to-end: snapshot → mutate disk → apply_manifest → verify
        // the original bytes come back even though everything was
        // zstd-compressed in the blob pool.
        let dirs = make_test_dirs("zstd-roundtrip");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        let original = b"the quick brown fox jumps over the lazy dog".repeat(100);
        write(&dirs.src.join("doc.txt"), &original);
        let manifest = store.snapshot(&dirs.src).unwrap();

        // Corrupt the file on disk.
        write(&dirs.src.join("doc.txt"), b"corrupted");

        // Restore.
        store.apply_manifest(&manifest, &dirs.src).unwrap();

        let restored = fs::read(dirs.src.join("doc.txt")).unwrap();
        assert_eq!(
            restored, original,
            "zstd decompress + restore must produce byte-exact original"
        );
    }

    #[test]
    fn blob_filename_uses_zst_suffix() {
        let dirs = make_test_dirs("suffix");
        let store = SnapshotStore::from_dir(dirs.store.clone());

        write(&dirs.src.join("x.txt"), b"any content");
        let _ = store.snapshot(&dirs.src).unwrap();

        let hash = sha256_hex(b"any content");
        let blob_path = store.blob_path_for(&hash);
        let file_name = blob_path
            .file_name()
            .unwrap()
            .to_string_lossy()
            .to_string();
        assert!(
            file_name.ends_with(".zst"),
            "blob filename should end with .zst, got {file_name}"
        );
    }
}
