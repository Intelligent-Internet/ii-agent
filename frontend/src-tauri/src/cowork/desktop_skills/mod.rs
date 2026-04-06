use crate::cowork::agent_presets::shared::DesktopSkillCapability;

#[derive(Clone)]
pub struct DesktopSkill {
    capability: DesktopSkillCapability,
}

impl DesktopSkill {
    pub fn name(&self) -> &str {
        self.capability.name.as_str()
    }

    pub fn into_capability(self) -> DesktopSkillCapability {
        self.capability
    }
}

pub fn common_desktop_skills() -> Vec<DesktopSkill> {
    Vec::new()
}

pub fn common_desktop_skill_capabilities() -> Vec<DesktopSkillCapability> {
    common_desktop_skills()
        .into_iter()
        .map(DesktopSkill::into_capability)
        .collect()
}
