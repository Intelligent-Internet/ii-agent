//! `desktop_skill_run` — skill body loader tool.
//!
//! This tool exposes the full markdown body of a desktop skill to the
//! backend agent. The LLM calls it with a skill name; the tool returns
//! the raw `SKILL.md` body that lives bundled inside the desktop binary.
//! The body describes the skill's supported operations, the exact
//! `wasm_run` invocations the agent should use, and any fallback
//! guidance when the backing WASM module is not registered.
//!
//! ## Execution model
//!
//! `desktop_skill_run` **never touches the WASM runtime**. It is a pure
//! text-load tool: input is a skill name, output is the body markdown.
//! After reading the body, the agent decides whether to call `wasm_run`
//! (the executor tool in [`crate::cowork::desktop_tools::wasm_run`])
//! with the shape the body recommends, or to fall back to host tools,
//! or to tell the user the task is not supported.
//!
//! This separation keeps two concerns independent:
//!
//! * **Guidance** (who decides what to do) — owned by skills, surfaced by
//!   this tool.
//! * **Execution** (who runs the isolated code) — owned by `wasm_run` +
//!   the desktop WASM runtime.
//!
//! The backend agent is expected to follow a two-step pattern for any
//! skill-driven task:
//!
//! 1. Call `desktop_skill_run(skill_name="pdf")` to load the pdf skill's
//!    body into context.
//! 2. Follow the body's instructions — usually that means calling
//!    `wasm_run(module=..., input_json=..., input_files=...)` with the
//!    exact shape documented there.

use super::find_builtin_skill;
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use crate::cowork::desktop_tools::{DesktopTool, DesktopToolContext};
use serde_json::{json, Value};

pub const TOOL_DESKTOP_SKILL_RUN: &str = "desktop_skill_run";

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_DESKTOP_SKILL_RUN.to_string(),
            aliases: Vec::new(),
            display_name: "Load a desktop skill body".to_string(),
            description: "Load the full markdown body of a desktop skill by name. Use this BEFORE attempting to process a complex document format (pdf, docx, xlsx, pptx) so you can read the skill's decision tree and the exact wasm_run invocation it recommends. This tool does NOT execute anything — it only returns the skill's instructions. After reading the body, call wasm_run yourself with the shape the body documents. If the body reports that the backing WebAssembly module is not yet registered, fall back to filename-level operations and tell the user what is not supported.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the desktop skill to load. Known names: 'pdf', 'docx', 'xlsx', 'pptx'."
                    }
                },
                "required": ["skill_name"]
            }),
        },
        execute,
        false,
    )
}

fn execute(_ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let skill_name = tool_input
        .get("skill_name")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "desktop_skill_run requires a 'skill_name' string".to_string())?;

    let skill = find_builtin_skill(skill_name).ok_or_else(|| {
        format!(
            "desktop_skill_run: unknown skill '{skill_name}'. Known skills: pdf, docx, xlsx, pptx."
        )
    })?;

    let runtime_label = skill.runtime().as_str();
    let module_label = skill
        .wasm_module()
        .map(|name| format!("\nwasm_module: {name}"))
        .unwrap_or_default();

    Ok(format!(
        "# Skill: {name}\n\
description: {description}\n\
runtime: {runtime}{module_label}\n\
\n\
Follow the instructions below. When the body tells you to call wasm_run, use the exact shape documented. Do not invent parameters the body does not mention.\n\
\n\
---\n\
\n\
{body}",
        name = skill.name(),
        description = skill.description(),
        runtime = runtime_label,
        module_label = module_label,
        body = skill.body(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn desktop_tool_descriptor_is_wellformed() {
        let tool = desktop_tool();
        assert_eq!(tool.name(), TOOL_DESKTOP_SKILL_RUN);
        assert!(!tool.display_name().is_empty());
        let cap = tool.clone().into_capability();
        let schema = cap.input_schema.as_object().expect("schema is object");
        let required = schema
            .get("required")
            .and_then(Value::as_array)
            .expect("required list");
        assert_eq!(required.len(), 1);
        assert_eq!(required[0].as_str(), Some("skill_name"));
    }

    // The tool's execute() signature needs a DesktopToolContext which
    // carries an AppHandle. Rather than mocking the full Tauri surface
    // here, we test the core lookup logic directly against the skill
    // registry — that exercises the only path execute() actually runs
    // for a valid skill name.
    #[test]
    fn loads_pdf_skill_body() {
        let skill = find_builtin_skill("pdf").expect("pdf skill registered");
        assert_eq!(skill.name(), "pdf");
        assert!(!skill.body().is_empty(), "pdf body must not be empty");
        let lower = skill.body().to_ascii_lowercase();
        assert!(
            lower.contains("wasm_run") || lower.contains("pdf_processor"),
            "pdf body must reference wasm_run or pdf_processor so the agent knows how to invoke it"
        );
    }

    #[test]
    fn unknown_skill_is_reported_clearly() {
        // This mirrors the error branch in execute() without needing a
        // DesktopToolContext: if find_builtin_skill returns None, we
        // should produce a helpful error listing known skill names.
        assert!(find_builtin_skill("no-such-skill").is_none());
    }
}
