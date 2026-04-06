use super::types::{
    RemoteAgentCommandContent, RemoteAgentToolArgs, RemoteModelSelection, REMOTE_AGENT_TYPE,
    REMOTE_BUILD_MODE,
};
use crate::cowork::agent_presets::shared::DesktopCapabilities;
use crate::cowork::chat::{
    CoworkAgentOverrides, CoworkChatToolSettings, CoworkGitHubRepositoryContext,
};
use crate::cowork::string_utils::normalize_optional_string;
use serde_json::Value;

pub fn build_remote_command(
    model_id: String,
    model_selection: RemoteModelSelection,
    text: String,
    resume: bool,
    tools: Option<&CoworkChatToolSettings>,
    metadata: Option<Value>,
    desktop_capabilities: Option<DesktopCapabilities>,
    github_repository: Option<CoworkGitHubRepositoryContext>,
    agent_overrides: Option<&CoworkAgentOverrides>,
) -> Result<Value, String> {
    let skill_names =
        sanitize_name_list(agent_overrides.and_then(|overrides| overrides.skill_names.as_ref()));
    let tool_names =
        sanitize_name_list(agent_overrides.and_then(|overrides| overrides.tool_names.as_ref()));

    serde_json::to_value(RemoteAgentCommandContent {
        model_id,
        provider: model_selection.provider,
        source: model_selection.source,
        agent_type: REMOTE_AGENT_TYPE,
        tool_args: map_remote_tool_args(tools),
        thinking_tokens: 0,
        text,
        resume,
        files: Vec::new(),
        metadata,
        desktop_capabilities,
        github_repository,
        build_mode: REMOTE_BUILD_MODE,
        system_prompt: build_system_prompt(agent_overrides),
        tool_names,
        skill_names,
        agent_config: agent_overrides.and_then(|overrides| overrides.runtime_options.clone()),
    })
    .map_err(|error| format!("Failed to encode Cowork agent command: {error}"))
}

fn map_remote_tool_args(tools: Option<&CoworkChatToolSettings>) -> RemoteAgentToolArgs {
    let media_generation = tools
        .map(|settings| {
            settings.generate_image.unwrap_or(false) || settings.generate_video.unwrap_or(false)
        })
        .unwrap_or(false);

    RemoteAgentToolArgs {
        task_agent: false,
        deep_research: false,
        pdf: true,
        media_generation,
        audio_generation: false,
        browser: false,
        enable_reviewer: false,
        design_document: false,
        codex_tools: false,
        claude_code: false,
    }
}

fn build_system_prompt(agent_overrides: Option<&CoworkAgentOverrides>) -> Option<String> {
    agent_overrides
        .and_then(|overrides| overrides.system_prompt.clone())
        .as_deref()
        .and_then(normalize_optional_string)
}

fn sanitize_name_list(values: Option<&Vec<String>>) -> Option<Vec<String>> {
    let mut normalized = Vec::new();
    if let Some(items) = values {
        for item in items {
            if let Some(value) = normalize_optional_string(item) {
                if !normalized.contains(&value) {
                    normalized.push(value);
                }
            }
        }
    }

    if normalized.is_empty() {
        None
    } else {
        Some(normalized)
    }
}
