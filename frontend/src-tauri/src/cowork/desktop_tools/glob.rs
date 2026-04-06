use super::{DesktopTool, DesktopToolContext, TOOL_GLOB};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_LIMIT: usize = 100;
const COMMON_SKIP_DIRS: &[&str] = &[".git", "node_modules", "target", "__pycache__"];

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_GLOB.to_string(),
            aliases: Vec::new(),
            display_name: "Find local files by glob".to_string(),
            description: "Find files inside the selected local desktop folder using a glob pattern such as '**/*.rs' or 'src/**/*.ts'. This runs on the desktop app.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match relative to the chosen search path, for example '**/*.rs'."
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional base directory path within the selected desktop scope. It may be absolute or relative to the scope root."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of matches to return. Defaults to 100."
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "If true, include hidden files and common ignored directories. Defaults to false."
                    }
                },
                "required": ["pattern"]
            }),
        },
        execute,
        false,
    )
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let pattern = tool_input
        .get("pattern")
        .and_then(Value::as_str)
        .ok_or_else(|| "glob requires pattern".to_string())?
        .trim();
    if pattern.is_empty() {
        return Err("glob pattern cannot be empty".to_string());
    }

    let matcher =
        ::glob::Pattern::new(pattern).map_err(|error| format!("Invalid glob pattern: {error}"))?;
    let search_root = resolve_search_root(ctx, tool_input.get("path").and_then(Value::as_str))?;
    let limit = tool_input
        .get("limit")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_LIMIT as u64) as usize;
    let include_hidden = tool_input
        .get("include_hidden")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    if limit == 0 {
        return Err("glob limit must be 1 or greater".to_string());
    }

    let mut matches = Vec::new();
    let mut truncated = false;
    collect_matches(
        &search_root,
        &search_root,
        &matcher,
        include_hidden,
        limit,
        &mut matches,
        &mut truncated,
    )?;

    if matches.is_empty() {
        return Ok(format!("No local files matched glob pattern: {pattern}"));
    }

    if truncated {
        matches.push(format!("[glob truncated at {} results]", limit));
    }

    Ok(matches.join("\n"))
}

fn resolve_search_root(
    ctx: &DesktopToolContext<'_>,
    path: Option<&str>,
) -> Result<PathBuf, String> {
    let resolved = match path {
        Some(value) => ctx.resolve_scoped_path(value, false)?,
        None => ctx.working_directory().to_path_buf(),
    };

    if !resolved.is_dir() {
        return Err(format!(
            "glob path is not a directory: {}",
            resolved.display()
        ));
    }

    Ok(resolved)
}

#[allow(clippy::too_many_arguments)]
fn collect_matches(
    root: &Path,
    current: &Path,
    matcher: &::glob::Pattern,
    include_hidden: bool,
    limit: usize,
    matches: &mut Vec<String>,
    truncated: &mut bool,
) -> Result<(), String> {
    if matches.len() >= limit {
        *truncated = true;
        return Ok(());
    }

    let entries = fs::read_dir(current)
        .map_err(|error| format!("Failed to read directory {}: {}", current.display(), error))?;

    for entry_result in entries {
        let entry =
            entry_result.map_err(|error| format!("Failed to read directory entry: {}", error))?;
        let path = entry.path();
        let file_name = entry.file_name().to_string_lossy().to_string();
        if should_skip_name(&file_name, include_hidden) {
            continue;
        }

        let relative_path = path
            .strip_prefix(root)
            .map_err(|error| format!("Failed to compute relative path: {error}"))?;
        let relative_pattern_path = normalize_path_for_pattern(relative_path);
        if path.is_file() && matcher.matches(&relative_pattern_path) {
            if matches.len() < limit {
                matches.push(path.display().to_string());
            } else {
                *truncated = true;
            }
        }

        if path.is_dir() {
            collect_matches(
                root,
                &path,
                matcher,
                include_hidden,
                limit,
                matches,
                truncated,
            )?;
            if matches.len() >= limit {
                break;
            }
        }
    }

    Ok(())
}

fn should_skip_name(name: &str, include_hidden: bool) -> bool {
    if include_hidden {
        return false;
    }

    name.starts_with('.') || COMMON_SKIP_DIRS.iter().any(|value| value == &name)
}

fn normalize_path_for_pattern(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}
