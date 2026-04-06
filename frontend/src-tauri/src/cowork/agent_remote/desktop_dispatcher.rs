use crate::cowork::agent_presets::DesktopRuntimePreset;
use crate::cowork::chat::{
    emit_cowork_stream_event, CoworkChatEvent, CoworkChatRunStatus, CoworkChatRuntimeEvent,
    CoworkChatScope,
};
use crate::cowork::desktop_skills::DesktopSkill;
use crate::cowork::desktop_tools::{
    find_desktop_tool, DesktopExecutionScope, DesktopTool, DesktopToolContext, DesktopToolRuntime,
};
use crate::cowork::session_gateway;
use crate::cowork::time_utils::now_iso;
use serde::Deserialize;
use serde_json::{json, Value};
use tauri::AppHandle;

#[derive(Debug, Deserialize)]
struct PausedToolDescriptor {
    #[serde(default)]
    tool_call_id: Option<String>,
    #[serde(default)]
    tool_name: Option<String>,
    #[serde(default)]
    tool_input: Option<Value>,
    #[serde(default)]
    requires_confirmation: Option<bool>,
    #[serde(default)]
    requires_user_input: Option<bool>,
    #[serde(default)]
    external_execution_required: Option<bool>,
}

struct DesktopDispatcher<'a> {
    app: &'a AppHandle,
    local_session_id: &'a str,
    preset: &'a DesktopRuntimePreset,
    execution_scope: DesktopExecutionScope,
    runtime: &'a mut DesktopToolRuntime,
}

impl<'a> DesktopDispatcher<'a> {
    fn new(
        app: &'a AppHandle,
        runtime_preset: &'a DesktopRuntimePreset,
        local_session_id: &'a str,
        runtime: &'a mut DesktopToolRuntime,
    ) -> Result<Self, String> {
        let execution_scope = (runtime_preset.load_execution_scope)(app, local_session_id)?;
        Ok(Self {
            app,
            local_session_id,
            preset: runtime_preset,
            execution_scope,
            runtime,
        })
    }

    fn find_tool(&self, tool_name: &str) -> Result<DesktopTool, String> {
        find_desktop_tool(&self.preset.tools, tool_name)
            .cloned()
            .ok_or_else(|| {
            let available_skills = self.skill_names().join(", ");
            if available_skills.is_empty() {
                format!("Desktop tool is not available for this preset: {tool_name}")
            } else {
                format!(
                    "Desktop tool is not available for this preset: {tool_name}. Available desktop skills: {available_skills}"
                )
            }
        })
    }

    fn skill_names(&self) -> Vec<&str> {
        self.preset.skills.iter().map(DesktopSkill::name).collect()
    }

    fn tool_context(&mut self) -> DesktopToolContext<'_> {
        DesktopToolContext::new(
            self.app,
            self.local_session_id,
            &self.execution_scope,
            self.runtime,
            self.preset.refresh_scope,
        )
    }
}

pub fn auto_execute_external_tools(
    app: &AppHandle,
    scope: CoworkChatScope,
    runtime_preset: Option<&DesktopRuntimePreset>,
    local_session_id: &str,
    content: &Value,
    runtime: &mut DesktopToolRuntime,
) -> Result<Option<Vec<Value>>, String> {
    let Some(runtime_preset) = runtime_preset else {
        return Ok(None);
    };

    let tools = parse_external_tools(content)?;
    if tools.is_empty() {
        return Ok(None);
    }

    let mut dispatcher = DesktopDispatcher::new(app, runtime_preset, local_session_id, runtime)?;
    emit_desktop_runtime_status(app, scope, local_session_id, CoworkChatRunStatus::Thinking);
    let mut tool_results = Vec::new();
    let mut should_refresh_scope = false;

    for tool in tools {
        let tool_name = tool.tool_name.clone().unwrap_or_default();
        let tool_input = tool
            .tool_input
            .clone()
            .unwrap_or(Value::Object(Default::default()));
        let tool_call_id = tool.tool_call_id.clone().unwrap_or_default();

        let desktop_tool = dispatcher.find_tool(&tool_name)?;
        emit_desktop_tool_call_event(
            app,
            scope,
            local_session_id,
            &tool_call_id,
            &desktop_tool,
            &tool_name,
            &tool_input,
        );
        let execution_result = {
            let mut tool_context = dispatcher.tool_context();
            desktop_tool.execute(&mut tool_context, &tool_input)
        };
        let is_error = execution_result.is_err();
        let llm_content = execution_result.unwrap_or_else(|error| error);
        emit_desktop_tool_result_event(
            app,
            scope,
            local_session_id,
            &tool_call_id,
            &desktop_tool,
            &tool_name,
            &tool_input,
            &llm_content,
            is_error,
        );

        if desktop_tool.refreshes_scope() && !is_error {
            should_refresh_scope = true;
        }

        tool_results.push(json!({
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "llm_content": llm_content,
            "user_display_content": Value::Null,
            "is_error": is_error,
            "is_interrupted": false,
        }));
    }

    if should_refresh_scope {
        let tool_context = dispatcher.tool_context();
        let _ = tool_context.refresh_scope_snapshot();
    }

    Ok(Some(tool_results))
}

fn parse_external_tools(content: &Value) -> Result<Vec<PausedToolDescriptor>, String> {
    let tools_value = content
        .get("tools")
        .and_then(Value::as_array)
        .ok_or_else(|| "Tool confirmation event did not include tools".to_string())?;

    let mut external_tools = Vec::new();
    for item in tools_value {
        let tool: PausedToolDescriptor = serde_json::from_value(item.clone())
            .map_err(|error| format!("Failed to parse external tool request: {error}"))?;
        if tool.requires_confirmation.unwrap_or(false) || tool.requires_user_input.unwrap_or(false)
        {
            return Ok(Vec::new());
        }
        if tool.external_execution_required.unwrap_or(false) {
            let has_tool_call_id = tool
                .tool_call_id
                .as_deref()
                .map(str::trim)
                .map(|value| !value.is_empty())
                .unwrap_or(false);
            if !has_tool_call_id {
                return Err(
                    "External desktop tool request did not include a tool_call_id".to_string(),
                );
            }
            external_tools.push(tool);
        }
    }

    Ok(external_tools)
}

fn emit_desktop_runtime_status(
    app: &AppHandle,
    scope: CoworkChatScope,
    local_session_id: &str,
    status: CoworkChatRunStatus,
) {
    let _ = session_gateway::persist_stream_status(app, scope, local_session_id, status);
    let event =
        session_gateway::build_status_updated_event(scope, local_session_id.to_string(), status);
    let _ = emit_cowork_stream_event(app, &event);
}

fn emit_desktop_tool_call_event(
    app: &AppHandle,
    scope: CoworkChatScope,
    local_session_id: &str,
    tool_call_id: &str,
    tool: &DesktopTool,
    tool_name: &str,
    tool_input: &Value,
) {
    emit_desktop_runtime_event(
        app,
        scope,
        local_session_id,
        "tool_call",
        format!("desktop-tool-call:{tool_call_id}"),
        json!({
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_display_name": tool.display_name(),
            "display_name": tool.display_name(),
            "tool_input": tool_input,
            "agent_name": "desktop",
        }),
    );
}

fn emit_desktop_tool_result_event(
    app: &AppHandle,
    scope: CoworkChatScope,
    local_session_id: &str,
    tool_call_id: &str,
    tool: &DesktopTool,
    tool_name: &str,
    tool_input: &Value,
    result: &str,
    is_error: bool,
) {
    emit_desktop_runtime_event(
        app,
        scope,
        local_session_id,
        "tool_result",
        format!("desktop-tool-result:{tool_call_id}"),
        json!({
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_display_name": tool.display_name(),
            "display_name": tool.display_name(),
            "tool_input": tool_input,
            "result": result,
            "is_error": is_error,
            "agent_name": "desktop",
        }),
    );
}

fn emit_desktop_runtime_event(
    app: &AppHandle,
    scope: CoworkChatScope,
    local_session_id: &str,
    runtime_event_type: &str,
    runtime_event_id: String,
    content: Value,
) {
    let created_at = now_iso();
    let event = CoworkChatEvent::Runtime(CoworkChatRuntimeEvent {
        event_type: "runtime.event".to_string(),
        scope,
        session_id: local_session_id.to_string(),
        runtime_event_type: runtime_event_type.to_string(),
        runtime_event_id: Some(runtime_event_id),
        runtime_created_at: Some(created_at.clone()),
        run_status: Some("running".to_string()),
        emitted_at: created_at,
        content,
    });
    if let CoworkChatEvent::Runtime(runtime_event_payload) = &event {
        let _ = session_gateway::persist_stream_runtime_event(
            app,
            runtime_event_payload,
            Some(CoworkChatRunStatus::Thinking),
        );
    }
    let _ = emit_cowork_stream_event(app, &event);
}
