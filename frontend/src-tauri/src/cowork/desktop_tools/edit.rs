use super::{DesktopTool, DesktopToolContext, TOOL_EDIT};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_EDIT.to_string(),
            aliases: Vec::new(),
            display_name: "Edit local file".to_string(),
            description: "Perform an exact string replacement inside a local file within the selected desktop folder.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The file path to edit. It may be absolute or relative to the current desktop scope."
                    },
                    "path": {
                        "type": "string",
                        "description": "Alias for file_path. It may be absolute or relative to the current desktop scope."
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to replace."
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text."
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all matches instead of only the first unique match."
                    }
                },
                "required": ["old_string", "new_string"]
            }),
        },
        execute,
        true,
    )
    .with_aliases(&["edit_file"])
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let file_path = tool_input
        .get("file_path")
        .or_else(|| tool_input.get("path"))
        .and_then(Value::as_str)
        .ok_or_else(|| "Edit requires file_path or path".to_string())?;
    let old_string = tool_input
        .get("old_string")
        .and_then(Value::as_str)
        .ok_or_else(|| "Edit requires old_string".to_string())?;
    let new_string = tool_input
        .get("new_string")
        .and_then(Value::as_str)
        .ok_or_else(|| "Edit requires new_string".to_string())?;
    let replace_all = tool_input
        .get("replace_all")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let resolved_path = ctx.resolve_scoped_path(file_path, false)?;
    let contents = std::fs::read_to_string(&resolved_path)
        .map_err(|error| format!("Failed to read {}: {}", resolved_path.display(), error))?;

    let match_count = contents.matches(old_string).count();
    if match_count == 0 {
        return Err(format!(
            "Edit could not find the requested text in {}",
            resolved_path.display()
        ));
    }
    if !replace_all && match_count > 1 {
        return Err(format!(
            "Edit found {} matches in {}; use replace_all or provide more context",
            match_count,
            resolved_path.display()
        ));
    }

    let updated = if replace_all {
        contents.replace(old_string, new_string)
    } else {
        contents.replacen(old_string, new_string, 1)
    };
    std::fs::write(&resolved_path, updated)
        .map_err(|error| format!("Failed to write {}: {}", resolved_path.display(), error))?;
    Ok(format!("Edited {}", resolved_path.display()))
}
