use super::{DesktopTool, DesktopToolContext, TOOL_WRITE};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_WRITE.to_string(),
            aliases: Vec::new(),
            display_name: "Write local file".to_string(),
            description: "Write or overwrite a local file within the selected desktop folder."
                .to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The file path to write. It may be absolute or relative to the current desktop scope."
                    },
                    "path": {
                        "type": "string",
                        "description": "Alias for file_path. It may be absolute or relative to the current desktop scope."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file."
                    }
                },
                "required": ["content"]
            }),
        },
        execute,
        true,
    )
    .with_aliases(&["write_file"])
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let file_path = tool_input
        .get("file_path")
        .or_else(|| tool_input.get("path"))
        .and_then(Value::as_str)
        .ok_or_else(|| "Write requires file_path or path".to_string())?;
    let content = tool_input
        .get("content")
        .and_then(Value::as_str)
        .ok_or_else(|| "Write requires content".to_string())?;
    let resolved_path = ctx.resolve_scoped_path(file_path, true)?;
    if let Some(parent) = resolved_path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| {
            format!(
                "Failed to create parent directory {}: {}",
                parent.display(),
                error
            )
        })?;
    }
    std::fs::write(&resolved_path, content)
        .map_err(|error| format!("Failed to write {}: {}", resolved_path.display(), error))?;
    Ok(format!("Wrote {}", resolved_path.display()))
}
