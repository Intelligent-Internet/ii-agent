use super::{DesktopTool, DesktopToolContext, TOOL_LIST_DIR};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_MAX_DEPTH: usize = 3;
const DEFAULT_LIMIT: usize = 500;
const COMMON_SKIP_DIRS: &[&str] = &[".git", "node_modules", "target", "__pycache__"];

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_LIST_DIR.to_string(),
            aliases: Vec::new(),
            display_name: "List local directory".to_string(),
            description: "List files and subdirectories inside the selected local desktop folder. Supports recursive listing and returns scoped absolute paths.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional directory path within the selected desktop scope. It may be absolute or relative to the current scope root."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list contents recursively. Defaults to false."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth for recursive listing. Defaults to 3."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of entries to return. Defaults to 500."
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "If true, include hidden files and common ignored directories. Defaults to false."
                    }
                },
                "required": []
            }),
        },
        execute,
        false,
    )
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let directory_path = resolve_directory(ctx, tool_input.get("path").and_then(Value::as_str))?;
    let recursive = tool_input
        .get("recursive")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let include_hidden = tool_input
        .get("include_hidden")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let max_depth = tool_input
        .get("max_depth")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_MAX_DEPTH as u64) as usize;
    let limit = tool_input
        .get("limit")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_LIMIT as u64) as usize;

    if limit == 0 {
        return Err("list_dir limit must be 1 or greater".to_string());
    }

    let mut results = Vec::new();
    let mut truncated = false;
    if recursive {
        list_recursive(
            &directory_path,
            0,
            max_depth,
            include_hidden,
            limit,
            &mut results,
            &mut truncated,
        )?;
    } else {
        list_single(
            &directory_path,
            include_hidden,
            &mut results,
            limit,
            &mut truncated,
        )?;
    }

    if results.is_empty() {
        return Ok(format!("Directory is empty: {}", directory_path.display()));
    }

    if truncated {
        results.push(format!("[list_dir truncated at {} entries]", limit));
    }

    Ok(results.join("\n"))
}

fn resolve_directory(ctx: &DesktopToolContext<'_>, path: Option<&str>) -> Result<PathBuf, String> {
    let resolved = match path {
        Some(value) => ctx.resolve_scoped_path(value, false)?,
        None => ctx.working_directory().to_path_buf(),
    };

    if !resolved.is_dir() {
        return Err(format!("Path is not a directory: {}", resolved.display()));
    }

    Ok(resolved)
}

fn list_single(
    directory_path: &Path,
    include_hidden: bool,
    results: &mut Vec<String>,
    limit: usize,
    truncated: &mut bool,
) -> Result<(), String> {
    let mut entries = collect_entries(directory_path, include_hidden)?;
    sort_entries(&mut entries);

    for entry in entries {
        if results.len() >= limit {
            *truncated = true;
            break;
        }
        results.push(render_entry(&entry.path, 0, entry.is_dir, entry.size));
    }

    Ok(())
}

fn list_recursive(
    directory_path: &Path,
    depth: usize,
    max_depth: usize,
    include_hidden: bool,
    limit: usize,
    results: &mut Vec<String>,
    truncated: &mut bool,
) -> Result<(), String> {
    if depth > max_depth || results.len() >= limit {
        if results.len() >= limit {
            *truncated = true;
        }
        return Ok(());
    }

    let mut entries = collect_entries(directory_path, include_hidden)?;
    sort_entries(&mut entries);

    for entry in entries {
        if results.len() >= limit {
            *truncated = true;
            break;
        }

        results.push(render_entry(&entry.path, depth, entry.is_dir, entry.size));
        if entry.is_dir {
            list_recursive(
                &entry.path,
                depth + 1,
                max_depth,
                include_hidden,
                limit,
                results,
                truncated,
            )?;
        }
    }

    Ok(())
}

#[derive(Clone)]
struct DirectoryEntry {
    path: PathBuf,
    is_dir: bool,
    size: u64,
}

fn collect_entries(
    directory_path: &Path,
    include_hidden: bool,
) -> Result<Vec<DirectoryEntry>, String> {
    let entries = fs::read_dir(directory_path).map_err(|error| {
        format!(
            "Failed to read directory {}: {}",
            directory_path.display(),
            error
        )
    })?;
    let mut collected = Vec::new();

    for entry_result in entries {
        let entry =
            entry_result.map_err(|error| format!("Failed to read directory entry: {}", error))?;
        let name = entry.file_name().to_string_lossy().to_string();
        if should_skip_name(&name, include_hidden) {
            continue;
        }

        let metadata = entry.metadata().map_err(|error| {
            format!(
                "Failed to read metadata for {}: {}",
                entry.path().display(),
                error
            )
        })?;
        collected.push(DirectoryEntry {
            path: entry.path(),
            is_dir: metadata.is_dir(),
            size: metadata.len(),
        });
    }

    Ok(collected)
}

fn sort_entries(entries: &mut [DirectoryEntry]) {
    entries.sort_by(|left, right| match (left.is_dir, right.is_dir) {
        (true, false) => std::cmp::Ordering::Less,
        (false, true) => std::cmp::Ordering::Greater,
        _ => left.path.cmp(&right.path),
    });
}

fn should_skip_name(name: &str, include_hidden: bool) -> bool {
    if include_hidden {
        return false;
    }

    name.starts_with('.') || COMMON_SKIP_DIRS.iter().any(|value| value == &name)
}

fn render_entry(path: &Path, depth: usize, is_dir: bool, size: u64) -> String {
    let indent = "  ".repeat(depth);
    let label = path
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|| path.display().to_string());
    if is_dir {
        format!("{indent}[dir] {label}/")
    } else {
        format!("{indent}[file] {label} ({})", format_size(size))
    }
}

fn format_size(size: u64) -> String {
    if size < 1024 {
        format!("{size} B")
    } else if size < 1024 * 1024 {
        format!("{:.1} KB", size as f64 / 1024.0)
    } else if size < 1024 * 1024 * 1024 {
        format!("{:.1} MB", size as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.1} GB", size as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}
