use super::{DesktopTool, DesktopToolContext, TOOL_TODO_WRITE};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_TODO_WRITE.to_string(),
            aliases: Vec::new(),
            display_name: "Write desktop todo list".to_string(),
            description:
                "Store and update a structured todo list for the current desktop cowork run."
                    .to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"]
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"]
                                }
                            },
                            "required": ["id", "content", "status", "priority"]
                        },
                        "description": "The updated todo list for the current run."
                    }
                },
                "required": ["todos"]
            }),
        },
        execute,
        false,
    )
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let todos = tool_input
        .get("todos")
        .cloned()
        .ok_or_else(|| "TodoWrite requires todos".to_string())?;
    let todo_count = todos.as_array().map(Vec::len).unwrap_or(0);
    ctx.set_todos(todos);
    Ok(format!(
        "Stored {} desktop todo items for this cowork run",
        todo_count
    ))
}
