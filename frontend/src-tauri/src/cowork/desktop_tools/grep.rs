use super::{DesktopTool, DesktopToolContext, TOOL_GREP};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_MATCH_LIMIT: usize = 50;
const COMMON_SKIP_DIRS: &[&str] = &[".git", "node_modules", "target", "__pycache__"];

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_GREP.to_string(),
            aliases: Vec::new(),
            display_name: "Search local files by regex".to_string(),
            description: "Search local files inside the selected desktop folder using a regex pattern. Returns absolute file paths with line numbers. This runs on the desktop app.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regex pattern to search for."
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional file or directory path within the selected desktop scope. It may be absolute or relative to the scope root."
                    },
                    "glob": {
                        "type": "string",
                        "description": "Optional glob filter relative to the search directory, for example '**/*.rs' or '*.ts'."
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "If true, perform a case-insensitive regex search."
                    },
                    "context": {
                        "type": "integer",
                        "description": "Number of context lines before and after each match. Defaults to 0."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of regex matches to return. Defaults to 50."
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
        .ok_or_else(|| "grep requires pattern".to_string())?;
    let regex = build_regex(pattern, tool_input)?;
    let search_path = resolve_search_path(ctx, tool_input.get("path").and_then(Value::as_str))?;
    let matcher = tool_input
        .get("glob")
        .and_then(Value::as_str)
        .map(::glob::Pattern::new)
        .transpose()
        .map_err(|error| format!("Invalid grep glob filter: {error}"))?;
    let context_lines = tool_input
        .get("context")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    let limit = tool_input
        .get("limit")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_MATCH_LIMIT as u64) as usize;
    let include_hidden = tool_input
        .get("include_hidden")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    if limit == 0 {
        return Err("grep limit must be 1 or greater".to_string());
    }

    let mut results = Vec::new();
    let mut match_count = 0usize;

    if search_path.is_file() {
        search_file(
            &search_path,
            &regex,
            context_lines,
            limit,
            &mut match_count,
            &mut results,
        )?;
    } else {
        search_directory(
            &search_path,
            &search_path,
            &regex,
            matcher.as_ref(),
            context_lines,
            limit,
            include_hidden,
            &mut match_count,
            &mut results,
        )?;
    }

    if results.is_empty() {
        return Ok(format!("No local matches found for regex: {pattern}"));
    }

    Ok(results.join("\n"))
}

fn build_regex(pattern: &str, tool_input: &Value) -> Result<regex::Regex, String> {
    let case_insensitive = tool_input
        .get("case_insensitive")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    regex::RegexBuilder::new(pattern)
        .case_insensitive(case_insensitive)
        .build()
        .map_err(|error| format!("Invalid regex pattern: {error}"))
}

fn resolve_search_path(
    ctx: &DesktopToolContext<'_>,
    path: Option<&str>,
) -> Result<PathBuf, String> {
    match path {
        Some(value) => ctx.resolve_scoped_path(value, false),
        None => Ok(ctx.working_directory().to_path_buf()),
    }
}

#[allow(clippy::too_many_arguments)]
fn search_directory(
    root: &Path,
    current: &Path,
    regex: &regex::Regex,
    matcher: Option<&::glob::Pattern>,
    context_lines: usize,
    limit: usize,
    include_hidden: bool,
    match_count: &mut usize,
    results: &mut Vec<String>,
) -> Result<(), String> {
    if *match_count >= limit {
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

        if path.is_dir() {
            search_directory(
                root,
                &path,
                regex,
                matcher,
                context_lines,
                limit,
                include_hidden,
                match_count,
                results,
            )?;
        } else if matches_glob(root, &path, matcher)? {
            search_file(&path, regex, context_lines, limit, match_count, results)?;
        }

        if *match_count >= limit {
            break;
        }
    }

    Ok(())
}

fn search_file(
    path: &Path,
    regex: &regex::Regex,
    context_lines: usize,
    limit: usize,
    match_count: &mut usize,
    results: &mut Vec<String>,
) -> Result<(), String> {
    let content = match fs::read_to_string(path) {
        Ok(value) => value,
        Err(_) => return Ok(()),
    };
    let lines = content.lines().collect::<Vec<_>>();

    for (index, line) in lines.iter().enumerate() {
        if !regex.is_match(line) {
            continue;
        }

        *match_count += 1;
        if *match_count > limit {
            break;
        }

        let start = index.saturating_sub(context_lines);
        let end = (index + context_lines + 1).min(lines.len());
        for line_index in start..end {
            let marker = if line_index == index { ">" } else { ":" };
            results.push(format!(
                "{}:{}{} {}",
                path.display(),
                line_index + 1,
                marker,
                lines[line_index]
            ));
        }
        if context_lines > 0 {
            results.push("---".to_string());
        }
    }

    Ok(())
}

fn matches_glob(
    root: &Path,
    path: &Path,
    matcher: Option<&::glob::Pattern>,
) -> Result<bool, String> {
    let Some(matcher) = matcher else {
        return Ok(true);
    };

    let relative_path = path
        .strip_prefix(root)
        .map_err(|error| format!("Failed to compute relative path: {error}"))?;
    Ok(matcher.matches(&relative_path.to_string_lossy().replace('\\', "/")))
}

fn should_skip_name(name: &str, include_hidden: bool) -> bool {
    if include_hidden {
        return false;
    }

    name.starts_with('.') || COMMON_SKIP_DIRS.iter().any(|value| value == &name)
}
