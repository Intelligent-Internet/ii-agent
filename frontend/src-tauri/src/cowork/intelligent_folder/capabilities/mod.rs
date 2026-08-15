use crate::cowork::agent_presets::shared::{DesktopSkillCapability, DesktopToolCapability};
use crate::cowork::desktop_skills::DesktopSkill;
use crate::cowork::desktop_tools::DesktopTool;

pub fn desktop_tools() -> Vec<DesktopTool> {
    Vec::new()
}

pub fn desktop_tool_capabilities() -> Vec<DesktopToolCapability> {
    desktop_tools()
        .into_iter()
        .map(DesktopTool::into_capability)
        .collect()
}

pub fn desktop_runtime_skills() -> Vec<DesktopSkill> {
    Vec::new()
}

pub fn desktop_skill_capabilities() -> Vec<DesktopSkillCapability> {
    desktop_runtime_skills()
        .into_iter()
        .map(DesktopSkill::into_capability)
        .collect()
}
