use super::{DesktopTool, DesktopToolContext, TOOL_READ};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};

const DEFAULT_READ_LIMIT: usize = 2000;

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_READ.to_string(),
            aliases: Vec::new(),
            display_name: "Read local file".to_string(),
            description: "Read a text file from the selected local desktop folder. The path may be absolute or relative to the current desktop scope.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The file path to read. It may be absolute or relative to the current desktop scope."
                    },
                    "path": {
                        "type": "string",
                        "description": "Alias for file_path. May be absolute or relative to the current desktop scope."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional number of lines to read. Defaults to 2000."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Optional 1-based line offset to start reading from."
                    }
                },
                "required": []
            }),
        },
        execute,
        false,
    )
    .with_aliases(&["read_file"])
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let file_path = tool_input
        .get("file_path")
        .or_else(|| tool_input.get("path"))
        .and_then(Value::as_str)
        .ok_or_else(|| "Read requires file_path or path".to_string())?;
    let resolved_path = ctx.resolve_scoped_path(file_path, false)?;
    let contents = std::fs::read_to_string(&resolved_path)
        .map_err(|error| format!("Failed to read {}: {}", resolved_path.display(), error))?;
    let offset = tool_input
        .get("offset")
        .and_then(Value::as_u64)
        .unwrap_or(1) as usize;
    let limit = tool_input
        .get("limit")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_READ_LIMIT as u64) as usize;
    if offset == 0 {
        return Err("Read offset must be 1 or greater".to_string());
    }
    if limit == 0 {
        return Err("Read limit must be 1 or greater".to_string());
    }

    let lines = contents.lines().collect::<Vec<_>>();
    let start = offset.saturating_sub(1);
    if start >= lines.len() {
        return Ok(String::new());
    }
    let end = start.saturating_add(limit).min(lines.len());
    let mut rendered = Vec::new();
    for (index, line) in lines[start..end].iter().enumerate() {
        rendered.push(format!("{}\t{}", start + index + 1, line));
    }

    Ok(rendered.join("\n"))
}
