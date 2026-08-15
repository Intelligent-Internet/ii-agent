use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
};

const DEFAULT_MAX_DEPTH: usize = 10;
const DEFAULT_MAX_ENTRIES: usize = 10_000;

#[derive(Debug, Deserialize)]
pub struct ReadPathTreeOptions {
    pub max_depth: Option<usize>,
    pub max_entries: Option<usize>,
    pub include_hidden: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum FileTreeNodeKind {
    Folder,
    File,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct FileTreeNode {
    pub id: String,
    pub name: String,
    pub kind: FileTreeNodeKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub extension: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub size: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_modified: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub children: Option<Vec<FileTreeNode>>,
}

struct TraversalState {
    max_depth: usize,
    remaining_entries: usize,
    max_entries: usize,
    include_hidden: bool,
}

impl TraversalState {
    fn new(options: Option<ReadPathTreeOptions>) -> Self {
        let options = options.unwrap_or(ReadPathTreeOptions {
            max_depth: None,
            max_entries: None,
            include_hidden: None,
        });

        let max_depth = options.max_depth.unwrap_or(DEFAULT_MAX_DEPTH);
        let max_entries = options.max_entries.unwrap_or(DEFAULT_MAX_ENTRIES).max(1);

        Self {
            max_depth,
            remaining_entries: max_entries,
            max_entries,
            include_hidden: options.include_hidden.unwrap_or(false),
        }
    }

    fn claim_entry(&mut self) -> Result<(), String> {
        if self.remaining_entries == 0 {
            return Err(format!(
                "Path tree exceeded the entry limit ({}) before traversal finished",
                self.max_entries
            ));
        }

        self.remaining_entries -= 1;
        Ok(())
    }
}

#[tauri::command]
pub fn read_path_tree(
    path: String,
    options: Option<ReadPathTreeOptions>,
) -> Result<FileTreeNode, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("Path is required".to_string());
    }

    let root_path = PathBuf::from(trimmed);
    if !root_path.exists() {
        return Err(format!("Path does not exist: {}", trimmed));
    }

    let metadata = fs::symlink_metadata(&root_path)
        .map_err(|error| format!("Failed to read metadata for {}: {}", trimmed, error))?;
    let mut state = TraversalState::new(options);

    build_node(&root_path, metadata, 0, &mut state)
}

fn build_node(
    path: &Path,
    metadata: fs::Metadata,
    depth: usize,
    state: &mut TraversalState,
) -> Result<FileTreeNode, String> {
    state.claim_entry()?;

    let is_symlink = metadata.file_type().is_symlink();
    let is_dir = metadata.is_dir() && !is_symlink;
    let name = node_name(path);
    let id = normalize_path(path);

    if !is_dir {
        return Ok(FileTreeNode {
            id,
            name,
            kind: FileTreeNodeKind::File,
            extension: file_extension(path),
            size: Some(format_bytes(metadata.len())),
            last_modified: format_modified_time(&metadata),
            children: None,
        });
    }

    if depth >= state.max_depth {
        return Ok(FileTreeNode {
            id,
            name,
            kind: FileTreeNodeKind::Folder,
            extension: None,
            size: None,
            last_modified: format_modified_time(&metadata),
            children: Some(Vec::new()),
        });
    }

    let mut children = Vec::new();
    let mut entries = fs::read_dir(path)
        .map_err(|error| format!("Failed to read directory {}: {}", path.display(), error))?
        .filter_map(|entry| entry.ok())
        .filter(|entry| state.include_hidden || !is_hidden_entry(entry))
        .filter_map(|entry| {
            let child_path = entry.path();
            let metadata = fs::symlink_metadata(&child_path).ok()?;
            Some((child_path, metadata))
        })
        .collect::<Vec<_>>();

    entries.sort_by(|(left_path, left_metadata), (right_path, right_metadata)| {
        let left_is_dir = left_metadata.is_dir() && !left_metadata.file_type().is_symlink();
        let right_is_dir = right_metadata.is_dir() && !right_metadata.file_type().is_symlink();

        right_is_dir
            .cmp(&left_is_dir)
            .then_with(|| {
                node_name(left_path)
                    .to_lowercase()
                    .cmp(&node_name(right_path).to_lowercase())
            })
            .then_with(|| node_name(left_path).cmp(&node_name(right_path)))
    });

    for (child_path, child_metadata) in entries {
        let child_node = build_node(&child_path, child_metadata, depth + 1, state)?;
        children.push(child_node);
    }

    Ok(FileTreeNode {
        id,
        name,
        kind: FileTreeNodeKind::Folder,
        extension: None,
        size: None,
        last_modified: format_modified_time(&metadata),
        children: Some(children),
    })
}

fn node_name(path: &Path) -> String {
    path.file_name()
        .map(|value| value.to_string_lossy().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| normalize_path(path))
}

fn normalize_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn file_extension(path: &Path) -> Option<String> {
    path.extension()
        .and_then(|value| value.to_str())
        .map(|value| value.to_lowercase())
        .filter(|value| !value.is_empty())
}

fn is_hidden_entry(entry: &fs::DirEntry) -> bool {
    let is_dot_file = entry
        .file_name()
        .to_str()
        .map(|name| name.starts_with('.'))
        .unwrap_or(false);

    if is_dot_file {
        return true;
    }

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::fs::MetadataExt;

        const FILE_ATTRIBUTE_HIDDEN: u32 = 0x2;

        if let Ok(metadata) = entry.metadata() {
            return metadata.file_attributes() & FILE_ATTRIBUTE_HIDDEN != 0;
        }
    }

    false
}

fn format_bytes(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];

    if bytes < 1024 {
        return format!("{} B", bytes);
    }

    let mut value = bytes as f64;
    let mut unit_index = 0usize;

    while value >= 1024.0 && unit_index < UNITS.len() - 1 {
        value /= 1024.0;
        unit_index += 1;
    }

    if value >= 100.0 || value.fract() < 0.05 {
        format!("{:.0} {}", value, UNITS[unit_index])
    } else {
        format!("{:.1} {}", value, UNITS[unit_index])
    }
}

fn format_modified_time(metadata: &fs::Metadata) -> Option<String> {
    let modified = metadata.modified().ok()?;
    let date_time = DateTime::<Utc>::from(modified);
    Some(date_time.to_rfc3339_opts(SecondsFormat::Secs, true))
}

#[cfg(test)]
mod tests {
    use super::{
        build_node, format_bytes, format_modified_time, FileTreeNodeKind, TraversalState,
    };
    use std::{
        fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    fn temp_test_dir() -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after unix epoch")
            .as_nanos();

        std::env::temp_dir().join(format!("ii-agent-tauri-tree-{unique}"))
    }

    #[test]
    fn formats_bytes_for_ui() {
        assert_eq!(format_bytes(512), "512 B");
        assert_eq!(format_bytes(1_536), "1.5 KB");
        assert_eq!(format_bytes(104_857_600), "100 MB");
    }

    #[test]
    fn formats_modified_time_as_rfc3339() {
        let root = temp_test_dir();
        fs::write(&root, b"hello world").expect("should create test file");

        let metadata = fs::symlink_metadata(&root).expect("should read metadata");
        let modified = format_modified_time(&metadata)
            .expect("test file metadata should expose modified time");

        assert!(modified.ends_with('Z'));
        assert!(modified.contains('T'));

        fs::remove_file(&root).expect("should clean up test file");
    }

    #[test]
    fn builds_directory_tree() {
        let root = temp_test_dir();
        let nested = root.join("nested");
        let file_path = nested.join("demo.txt");

        fs::create_dir_all(&nested).expect("should create test directories");
        fs::write(&file_path, b"hello world").expect("should create test file");

        let metadata = fs::symlink_metadata(&root).expect("should read root metadata");
        let mut state = TraversalState::new(None);
        let tree = build_node(&root, metadata, 0, &mut state).expect("should build tree");

        assert_eq!(tree.kind, FileTreeNodeKind::Folder);
        assert_eq!(tree.name, root.to_string_lossy().replace('\\', "/"));

        let children = tree.children.expect("folder should include children");
        assert_eq!(children.len(), 1);
        assert_eq!(children[0].name, "nested");
        assert_eq!(children[0].kind, FileTreeNodeKind::Folder);

        let nested_children = children[0]
            .children
            .clone()
            .expect("nested folder should include children");
        assert_eq!(nested_children.len(), 1);
        assert_eq!(nested_children[0].name, "demo.txt");
        assert_eq!(nested_children[0].kind, FileTreeNodeKind::File);
        assert_eq!(nested_children[0].extension.as_deref(), Some("txt"));
        assert!(nested_children[0].last_modified.is_some());

        fs::remove_dir_all(&root).expect("should clean up test directory");
    }
}
