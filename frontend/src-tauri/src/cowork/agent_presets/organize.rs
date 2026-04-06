use super::shared;
use super::shared::{DesktopCapabilities, DesktopSkillCapability, DesktopToolCapability};
use super::DesktopRuntimePreset;
use crate::cowork::chat::CoworkAgentOverrides;
use crate::cowork::desktop_skills::DesktopSkill;
use crate::cowork::desktop_tools::{DesktopExecutionScope, DesktopTool};
use crate::cowork::organize::capabilities;
use crate::cowork::organize::sessions;
use crate::cowork::session_gateway::{self, LocalCoworkSession};
use std::fs;
use tauri::AppHandle;

pub fn organize_builtin_agent_overrides(prompt_context: Option<&str>) -> CoworkAgentOverrides {
    CoworkAgentOverrides {
        system_prompt: Some(build_organize_system_prompt(prompt_context)),
        tool_names: Some(build_organize_tool_names()),
        skill_names: None,
        runtime_options: Some(shared::default_runtime_options("organize_cowork_agent")),
    }
}

pub fn build_organize_desktop_capabilities() -> DesktopCapabilities {
    DesktopCapabilities {
        tools: merge_tool_capabilities(
            shared::desktop_built_tools(),
            capabilities::desktop_tool_capabilities(),
        ),
        skills: build_organize_desktop_skills(),
    }
}

pub fn build_organize_desktop_runtime() -> DesktopRuntimePreset {
    DesktopRuntimePreset {
        tools: build_organize_runtime_tools(),
        skills: build_organize_runtime_skills(),
        load_execution_scope: load_organize_execution_scope,
        refresh_scope: Some(refresh_organize_execution_scope),
    }
}

fn build_organize_desktop_tools() -> Vec<DesktopToolCapability> {
    build_organize_desktop_capabilities().tools
}

fn build_organize_desktop_skills() -> Vec<DesktopSkillCapability> {
    merge_skill_capabilities(
        shared::desktop_built_skills(),
        capabilities::desktop_skill_capabilities(),
    )
}

fn build_organize_tool_names() -> Vec<String> {
    build_organize_desktop_tools()
        .into_iter()
        .map(|tool| tool.name)
        .collect()
}

fn build_organize_runtime_tools() -> Vec<DesktopTool> {
    merge_runtime_tools(
        shared::desktop_runtime_tools(),
        capabilities::desktop_tools(),
    )
}

fn build_organize_runtime_skills() -> Vec<DesktopSkill> {
    merge_runtime_skills(
        shared::desktop_runtime_skills(),
        capabilities::desktop_runtime_skills(),
    )
}

fn build_organize_system_prompt(prompt_context: Option<&str>) -> String {
    let mut prompt = "You are the Cowork organize agent inside II Agent desktop.\n\
Focus on analyzing and reorganizing the user's local file and folder structure with careful, tool-assisted reasoning.\n\
Treat this mode as organize-file-folder scope for a desktop-selected folder.\n\
Use only the built desktop tools provided for local file inspection and edits.\n\
Do not assume backend-only, browser, connector, repository, or web tools exist in this mode."
        .to_string();

    if let Some(source_root) = extract_prompt_value(prompt_context, "Input folder path:")
        .or_else(|| extract_prompt_value(prompt_context, "Source root:"))
    {
        prompt.push_str("\n\n[Organize scope]");
        prompt.push_str("\nMode scope: organize-file-folder");
        prompt.push_str("\nInput folder path: ");
        prompt.push_str(&source_root);

        if let Some(result_root) = extract_prompt_value(prompt_context, "Result root:") {
            prompt.push_str("\nResult folder path: ");
            prompt.push_str(&result_root);
        }
    }

    prompt
}

fn extract_prompt_value(prompt_context: Option<&str>, label: &str) -> Option<String> {
    let prompt_context = prompt_context?;

    prompt_context.lines().find_map(|line| {
        line.strip_prefix(label)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
    })
}

fn merge_tool_capabilities(
    common_tools: Vec<DesktopToolCapability>,
    mode_tools: Vec<DesktopToolCapability>,
) -> Vec<DesktopToolCapability> {
    let mut merged = common_tools;
    for tool in mode_tools {
        if merged.iter().any(|existing| existing.name == tool.name) {
            continue;
        }
        merged.push(tool);
    }
    merged
}

fn merge_runtime_tools(
    common_tools: Vec<DesktopTool>,
    mode_tools: Vec<DesktopTool>,
) -> Vec<DesktopTool> {
    let mut merged = common_tools;
    for tool in mode_tools {
        if merged.iter().any(|existing| existing.name() == tool.name()) {
            continue;
        }
        merged.push(tool);
    }
    merged
}

fn merge_skill_capabilities(
    common_skills: Vec<DesktopSkillCapability>,
    mode_skills: Vec<DesktopSkillCapability>,
) -> Vec<DesktopSkillCapability> {
    let mut merged = common_skills;
    for skill in mode_skills {
        if merged.iter().any(|existing| existing.name == skill.name) {
            continue;
        }
        merged.push(skill);
    }
    merged
}

fn merge_runtime_skills(
    common_skills: Vec<DesktopSkill>,
    mode_skills: Vec<DesktopSkill>,
) -> Vec<DesktopSkill> {
    let mut merged = common_skills;
    for skill in mode_skills {
        if merged
            .iter()
            .any(|existing| existing.name() == skill.name())
        {
            continue;
        }
        merged.push(skill);
    }
    merged
}

fn load_organize_execution_scope(
    app: &AppHandle,
    local_session_id: &str,
) -> Result<DesktopExecutionScope, String> {
    let local_session = session_gateway::load_local_session(
        app,
        crate::cowork::chat::CoworkChatScope::OrganizeFileFolder,
        local_session_id,
    )?;
    let LocalCoworkSession::Organize(detail) = local_session else {
        return Err("Desktop organize tool execution requires an organize session".to_string());
    };

    let root_path = detail.organize_tree_pair.source_root.clone();
    let canonical_root = fs::canonicalize(&root_path).map_err(|error| {
        format!(
            "Failed to resolve organize source_root {}: {}",
            root_path, error
        )
    })?;

    Ok(DesktopExecutionScope::new(canonical_root))
}

fn refresh_organize_execution_scope(
    app: &AppHandle,
    local_session_id: &str,
    _execution_scope: &DesktopExecutionScope,
) -> Result<(), String> {
    let local_session = session_gateway::load_local_session(
        app,
        crate::cowork::chat::CoworkChatScope::OrganizeFileFolder,
        local_session_id,
    )?;
    let LocalCoworkSession::Organize(mut detail) = local_session else {
        return Ok(());
    };
    sessions::sync_result_tree_from_disk(&mut detail)?;
    session_gateway::persist_local_session(app, LocalCoworkSession::Organize(detail))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_organize_system_prompt_embeds_local_scope() {
        let prompt = build_organize_system_prompt(Some(
            "[Local organize scope]\nInput folder path: C:/Users/demo/Documents\nResult root: C:/Users/demo/Documents",
        ));

        assert!(prompt.contains("Mode scope: organize-file-folder"));
        assert!(prompt.contains("Input folder path: C:/Users/demo/Documents"));
        assert!(prompt.contains("Result folder path: C:/Users/demo/Documents"));
        assert!(prompt.contains("Use only the built desktop tools"));
    }

    #[test]
    fn build_organize_desktop_capabilities_match_override_tool_names() {
        let overrides = organize_builtin_agent_overrides(None);
        let capabilities = build_organize_desktop_capabilities();
        let capability_tool_names = capabilities
            .tools
            .into_iter()
            .map(|tool| tool.name)
            .collect::<Vec<_>>();

        assert_eq!(overrides.tool_names, Some(capability_tool_names));
    }
}
