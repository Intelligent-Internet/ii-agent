use super::{DesktopTool, DesktopToolContext, TOOL_APPLY_PATCH};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};
use std::path::Path;

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_APPLY_PATCH.to_string(),
            aliases: Vec::new(),
            display_name: "Apply local patch".to_string(),
            description: "Apply a structured patch to local files inside the selected desktop folder. Use absolute paths in patch headers.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "The patch envelope starting with *** Begin Patch and ending with *** End Patch."
                    }
                },
                "required": ["input"]
            }),
        },
        execute,
        true,
    )
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let input = tool_input
        .get("input")
        .and_then(Value::as_str)
        .ok_or_else(|| "apply_patch requires input".to_string())?;
    let operations = parse_patch_operations(input)?;
    let mut summaries = Vec::new();
    for operation in operations {
        match operation {
            PatchOperation::AddFile { path, lines } => {
                let resolved_path = ctx.resolve_scoped_path(&path, true)?;
                if let Some(parent) = resolved_path.parent() {
                    std::fs::create_dir_all(parent).map_err(|error| {
                        format!(
                            "Failed to create parent directory {}: {}",
                            parent.display(),
                            error
                        )
                    })?;
                }
                std::fs::write(&resolved_path, lines.join("\n")).map_err(|error| {
                    format!("Failed to create {}: {}", resolved_path.display(), error)
                })?;
                summaries.push(format!("Added {}", resolved_path.display()));
            }
            PatchOperation::DeleteFile { path } => {
                let resolved_path = ctx.resolve_scoped_path(&path, false)?;
                std::fs::remove_file(&resolved_path).map_err(|error| {
                    format!("Failed to delete {}: {}", resolved_path.display(), error)
                })?;
                summaries.push(format!("Deleted {}", resolved_path.display()));
            }
            PatchOperation::UpdateFile {
                path,
                move_to,
                hunks,
            } => {
                let resolved_path = ctx.resolve_scoped_path(&path, false)?;
                let contents = std::fs::read_to_string(&resolved_path).map_err(|error| {
                    format!("Failed to read {}: {}", resolved_path.display(), error)
                })?;
                let mut lines = contents
                    .lines()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>();
                let mut cursor = 0usize;
                for hunk in hunks {
                    cursor = apply_patch_hunk(&mut lines, &hunk, cursor, &resolved_path)?;
                }

                let output_path = move_to
                    .as_deref()
                    .map(|target| ctx.resolve_scoped_path(target, true))
                    .transpose()?
                    .unwrap_or_else(|| resolved_path.clone());
                if let Some(parent) = output_path.parent() {
                    std::fs::create_dir_all(parent).map_err(|error| {
                        format!(
                            "Failed to create parent directory {}: {}",
                            parent.display(),
                            error
                        )
                    })?;
                }
                std::fs::write(&output_path, lines.join("\n")).map_err(|error| {
                    format!("Failed to write {}: {}", output_path.display(), error)
                })?;
                if output_path != resolved_path {
                    let _ = std::fs::remove_file(&resolved_path);
                    summaries.push(format!(
                        "Updated {} and moved to {}",
                        resolved_path.display(),
                        output_path.display()
                    ));
                } else {
                    summaries.push(format!("Updated {}", output_path.display()));
                }
            }
        }
    }

    Ok(summaries.join("\n"))
}

enum PatchOperation {
    AddFile {
        path: String,
        lines: Vec<String>,
    },
    DeleteFile {
        path: String,
    },
    UpdateFile {
        path: String,
        move_to: Option<String>,
        hunks: Vec<Vec<String>>,
    },
}

fn parse_patch_operations(input: &str) -> Result<Vec<PatchOperation>, String> {
    let lines = input.lines().collect::<Vec<_>>();
    if lines.first().copied() != Some("*** Begin Patch") {
        return Err("apply_patch input must start with *** Begin Patch".to_string());
    }
    if lines.last().copied() != Some("*** End Patch") {
        return Err("apply_patch input must end with *** End Patch".to_string());
    }

    let mut operations = Vec::new();
    let mut index = 1usize;
    while index + 1 < lines.len() {
        let line = lines[index];
        if let Some(path) = line.strip_prefix("*** Add File: ") {
            index += 1;
            let mut add_lines = Vec::new();
            while index < lines.len() && !lines[index].starts_with("*** ") {
                let content = lines[index]
                    .strip_prefix('+')
                    .ok_or_else(|| "apply_patch Add File lines must start with +".to_string())?;
                add_lines.push(content.to_string());
                index += 1;
            }
            operations.push(PatchOperation::AddFile {
                path: path.to_string(),
                lines: add_lines,
            });
            continue;
        }

        if let Some(path) = line.strip_prefix("*** Delete File: ") {
            operations.push(PatchOperation::DeleteFile {
                path: path.to_string(),
            });
            index += 1;
            continue;
        }

        if let Some(path) = line.strip_prefix("*** Update File: ") {
            index += 1;
            let mut move_to = None;
            if index < lines.len() {
                if let Some(target) = lines[index].strip_prefix("*** Move to: ") {
                    move_to = Some(target.to_string());
                    index += 1;
                }
            }

            let mut hunks = Vec::new();
            while index < lines.len() && !lines[index].starts_with("*** ") {
                if lines[index].starts_with("@@") {
                    index += 1;
                    let mut hunk_lines = Vec::new();
                    while index < lines.len()
                        && !lines[index].starts_with("@@")
                        && !lines[index].starts_with("*** ")
                    {
                        if lines[index] == "*** End of File" {
                            index += 1;
                            break;
                        }
                        hunk_lines.push(lines[index].to_string());
                        index += 1;
                    }
                    hunks.push(hunk_lines);
                    continue;
                }
                return Err(format!("Unexpected apply_patch line: {}", lines[index]));
            }

            operations.push(PatchOperation::UpdateFile {
                path: path.to_string(),
                move_to,
                hunks,
            });
            continue;
        }

        return Err(format!("Unsupported apply_patch header: {}", line));
    }

    Ok(operations)
}

fn apply_patch_hunk(
    lines: &mut Vec<String>,
    hunk_lines: &[String],
    start_cursor: usize,
    file_path: &Path,
) -> Result<usize, String> {
    let mut old_block = Vec::new();
    let mut new_block = Vec::new();
    for line in hunk_lines {
        let (prefix, content) = line.split_at(1);
        match prefix {
            " " => {
                old_block.push(content.to_string());
                new_block.push(content.to_string());
            }
            "-" => old_block.push(content.to_string()),
            "+" => new_block.push(content.to_string()),
            _ => return Err(format!("Unsupported apply_patch hunk line: {}", line)),
        }
    }

    if old_block.is_empty() {
        return Err(format!(
            "apply_patch hunks without context are not supported for {}",
            file_path.display()
        ));
    }

    let match_index = find_line_block(lines, &old_block, start_cursor).ok_or_else(|| {
        format!(
            "apply_patch could not match hunk in {}",
            file_path.display()
        )
    })?;
    lines.splice(
        match_index..match_index + old_block.len(),
        new_block.clone(),
    );
    Ok(match_index + new_block.len())
}

fn find_line_block(lines: &[String], block: &[String], start_cursor: usize) -> Option<usize> {
    if block.len() > lines.len() {
        return None;
    }
    for start in start_cursor..=lines.len().saturating_sub(block.len()) {
        if lines[start..start + block.len()] == *block {
            return Some(start);
        }
    }
    None
}
