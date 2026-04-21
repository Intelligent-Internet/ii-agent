use super::types::{
    RemoteAgentCommandContent, RemoteAgentToolArgs, RemoteModelSelection,
    RemoteRequestedCapabilities, REMOTE_AGENT_TYPE, REMOTE_BUILD_MODE,
};
use crate::cowork::agent_presets::shared::{
    DesktopCapabilities, DesktopSkillCapability, DesktopToolCapability,
};
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
        requested_capabilities: build_requested_capabilities(agent_overrides, desktop_capabilities),
        github_repository,
        build_mode: REMOTE_BUILD_MODE,
        system_prompt: build_system_prompt(agent_overrides),
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

fn build_requested_capabilities(
    agent_overrides: Option<&CoworkAgentOverrides>,
    desktop_capabilities: Option<DesktopCapabilities>,
) -> Option<RemoteRequestedCapabilities> {
    let skill_names =
        sanitize_name_list(agent_overrides.and_then(|overrides| overrides.skill_names.as_ref()));
    let tool_names =
        sanitize_name_list(agent_overrides.and_then(|overrides| overrides.tool_names.as_ref()));

    let (client_tools, core_tools) =
        split_client_and_core_tools(desktop_capabilities.as_ref(), tool_names.as_ref());
    let (client_skills, core_skills) =
        split_client_and_core_skills(desktop_capabilities.as_ref(), skill_names.as_ref());

    if client_tools.is_none()
        && client_skills.is_none()
        && core_tools.is_none()
        && core_skills.is_none()
    {
        return None;
    }

    Some(RemoteRequestedCapabilities {
        client_tools,
        client_skills,
        core_tools,
        core_skills,
        connector: None,
    })
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

fn split_client_and_core_tools(
    desktop_capabilities: Option<&DesktopCapabilities>,
    selected_tool_names: Option<&Vec<String>>,
) -> (Option<Vec<DesktopToolCapability>>, Option<Vec<String>>) {
    let Some(desktop_capabilities) = desktop_capabilities else {
        return (None, selected_tool_names.cloned());
    };

    let mut client_tools = Vec::new();
    let mut core_tools = Vec::new();

    match selected_tool_names {
        Some(selected_names) => {
            for selected_name in selected_names {
                if let Some(capability) =
                    find_matching_client_tool(&desktop_capabilities.tools, selected_name)
                {
                    if !client_tools
                        .iter()
                        .any(|existing: &DesktopToolCapability| existing.name == capability.name)
                    {
                        client_tools.push(capability.clone());
                    }
                } else if !core_tools.iter().any(|existing| existing == selected_name) {
                    core_tools.push(selected_name.clone());
                }
            }
        }
        None => client_tools.extend(desktop_capabilities.tools.iter().cloned()),
    }

    (
        if client_tools.is_empty() {
            None
        } else {
            Some(client_tools)
        },
        if core_tools.is_empty() {
            None
        } else {
            Some(core_tools)
        },
    )
}

fn split_client_and_core_skills(
    desktop_capabilities: Option<&DesktopCapabilities>,
    selected_skill_names: Option<&Vec<String>>,
) -> (Option<Vec<DesktopSkillCapability>>, Option<Vec<String>>) {
    let Some(desktop_capabilities) = desktop_capabilities else {
        return (None, selected_skill_names.cloned());
    };

    let mut client_skills = Vec::new();
    let mut core_skills = Vec::new();

    match selected_skill_names {
        Some(selected_names) => {
            for selected_name in selected_names {
                if let Some(capability) =
                    find_matching_client_skill(&desktop_capabilities.skills, selected_name)
                {
                    if !client_skills
                        .iter()
                        .any(|existing: &DesktopSkillCapability| existing.name == capability.name)
                    {
                        client_skills.push(capability.clone());
                    }
                } else if !core_skills.iter().any(|existing| existing == selected_name) {
                    core_skills.push(selected_name.clone());
                }
            }
        }
        None => client_skills.extend(desktop_capabilities.skills.iter().cloned()),
    }

    (
        if client_skills.is_empty() {
            None
        } else {
            Some(client_skills)
        },
        if core_skills.is_empty() {
            None
        } else {
            Some(core_skills)
        },
    )
}

fn find_matching_client_tool<'a>(
    tools: &'a [DesktopToolCapability],
    selected_name: &str,
) -> Option<&'a DesktopToolCapability> {
    let normalized = selected_name.trim();
    if normalized.is_empty() {
        return None;
    }

    tools.iter().find(|tool| {
        tool.name.eq_ignore_ascii_case(normalized)
            || tool
                .aliases
                .iter()
                .any(|alias| alias.eq_ignore_ascii_case(normalized))
    })
}

fn find_matching_client_skill<'a>(
    skills: &'a [DesktopSkillCapability],
    selected_name: &str,
) -> Option<&'a DesktopSkillCapability> {
    let normalized = selected_name.trim();
    if normalized.is_empty() {
        return None;
    }

    skills
        .iter()
        .find(|skill| skill.name.eq_ignore_ascii_case(normalized))
}

#[cfg(test)]
mod tests {
    use super::{
        build_requested_capabilities, DesktopCapabilities, DesktopSkillCapability,
        DesktopToolCapability,
    };
    use crate::cowork::chat::CoworkAgentOverrides;
    use serde_json::json;

    fn sample_desktop_capabilities() -> DesktopCapabilities {
        DesktopCapabilities {
            tools: vec![DesktopToolCapability {
                name: "Read".to_string(),
                aliases: vec!["read_file".to_string()],
                display_name: "Read".to_string(),
                description: "Read a file from desktop scope.".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "path": { "type": "string" }
                    },
                    "required": ["path"]
                }),
            }],
            skills: vec![DesktopSkillCapability {
                name: "pdf".to_string(),
                description: "Process PDFs on the desktop runtime.".to_string(),
            }],
        }
    }

    #[test]
    fn builds_client_capabilities_from_desktop_capability_catalog() {
        let requested = build_requested_capabilities(
            Some(&CoworkAgentOverrides {
                system_prompt: None,
                tool_names: Some(vec!["Read".to_string()]),
                skill_names: Some(vec!["pdf".to_string()]),
                runtime_options: None,
            }),
            Some(sample_desktop_capabilities()),
        )
        .expect("requested capabilities");

        assert_eq!(requested.core_tools, None);
        assert_eq!(requested.core_skills, None);
        assert_eq!(
            requested
                .client_tools
                .expect("client tools")
                .into_iter()
                .map(|tool| tool.name)
                .collect::<Vec<_>>(),
            vec!["Read".to_string()]
        );
        assert_eq!(
            requested
                .client_skills
                .expect("client skills")
                .into_iter()
                .map(|skill| skill.name)
                .collect::<Vec<_>>(),
            vec!["pdf".to_string()]
        );
    }

    #[test]
    fn keeps_non_desktop_overrides_as_core_capabilities() {
        let requested = build_requested_capabilities(
            Some(&CoworkAgentOverrides {
                system_prompt: None,
                tool_names: Some(vec!["web_search".to_string()]),
                skill_names: Some(vec!["writer".to_string()]),
                runtime_options: None,
            }),
            Some(sample_desktop_capabilities()),
        )
        .expect("requested capabilities");

        assert_eq!(requested.client_tools, None);
        assert_eq!(requested.client_skills, None);
        assert_eq!(requested.core_tools, Some(vec!["web_search".to_string()]));
        assert_eq!(requested.core_skills, Some(vec!["writer".to_string()]));
    }

    #[test]
    fn includes_all_desktop_capabilities_when_no_subset_is_requested() {
        let requested = build_requested_capabilities(None, Some(sample_desktop_capabilities()))
            .expect("requested capabilities");

        assert_eq!(
            requested
                .client_tools
                .expect("client tools")
                .into_iter()
                .map(|tool| tool.name)
                .collect::<Vec<_>>(),
            vec!["Read".to_string()]
        );
        assert_eq!(
            requested
                .client_skills
                .expect("client skills")
                .into_iter()
                .map(|skill| skill.name)
                .collect::<Vec<_>>(),
            vec!["pdf".to_string()]
        );
        assert_eq!(requested.core_tools, None);
        assert_eq!(requested.core_skills, None);
    }
}
