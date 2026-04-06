pub mod homepage;
pub mod organize;
pub mod shared;

use crate::cowork::chat::{CoworkAgentOverrides, CoworkChatScope, CoworkChatToolSettings};
use crate::cowork::desktop_skills::DesktopSkill;
use crate::cowork::desktop_tools::{
    DesktopExecutionScopeLoaderFn, DesktopExecutionScopeRefreshFn, DesktopTool,
};
use shared::DesktopCapabilities;

pub struct DesktopRuntimePreset {
    pub tools: Vec<DesktopTool>,
    pub skills: Vec<DesktopSkill>,
    pub load_execution_scope: DesktopExecutionScopeLoaderFn,
    pub refresh_scope: Option<DesktopExecutionScopeRefreshFn>,
}

pub struct ResolvedDesktopPreset {
    pub capabilities: DesktopCapabilities,
    pub runtime: DesktopRuntimePreset,
}

pub fn resolve_agent_overrides(
    scope: CoworkChatScope,
    prompt_context: Option<&str>,
    tools: Option<&CoworkChatToolSettings>,
    runtime_overrides: Option<CoworkAgentOverrides>,
) -> CoworkAgentOverrides {
    let builtin = match scope {
        CoworkChatScope::Homepage => homepage::homepage_builtin_agent_overrides(prompt_context),
        CoworkChatScope::OrganizeFileFolder => {
            organize::organize_builtin_agent_overrides(prompt_context)
        }
    };

    let merged = shared::merge_agent_overrides(builtin, runtime_overrides);
    match scope {
        CoworkChatScope::Homepage => shared::apply_tool_settings(merged, tools),
        CoworkChatScope::OrganizeFileFolder => shared::lock_tool_names_to_desktop(merged),
    }
}

pub fn resolve_desktop_preset(scope: CoworkChatScope) -> Option<ResolvedDesktopPreset> {
    match scope {
        CoworkChatScope::Homepage => None,
        CoworkChatScope::OrganizeFileFolder => Some(ResolvedDesktopPreset {
            capabilities: organize::build_organize_desktop_capabilities(),
            runtime: organize::build_organize_desktop_runtime(),
        }),
    }
}
