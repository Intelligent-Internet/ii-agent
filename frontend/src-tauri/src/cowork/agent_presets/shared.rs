use crate::cowork::chat::{CoworkAgentOverrides, CoworkChatToolSettings};
use crate::cowork::desktop_skills::DesktopSkill;
use crate::cowork::desktop_tools::{resolve_desktop_tool_name, DesktopTool};
use serde::Serialize;
use serde_json::{Map, Value};

#[derive(Debug, Clone, Serialize)]
pub struct DesktopCapabilities {
    pub tools: Vec<DesktopToolCapability>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub skills: Vec<DesktopSkillCapability>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DesktopToolCapability {
    pub name: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub aliases: Vec<String>,
    pub display_name: String,
    pub description: String,
    pub input_schema: Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct DesktopSkillCapability {
    pub name: String,
    pub description: String,
}

pub const TOOL_WEB_SEARCH: &str = "web_search";
pub const TOOL_WEB_VISIT: &str = "web_visit";

pub fn base_tool_names() -> Vec<String> {
    vec![TOOL_WEB_SEARCH.to_string(), TOOL_WEB_VISIT.to_string()]
}

pub fn desktop_built_tools() -> Vec<DesktopToolCapability> {
    crate::cowork::desktop_tools::common_desktop_tool_capabilities()
}

pub fn desktop_runtime_tools() -> Vec<DesktopTool> {
    crate::cowork::desktop_tools::common_desktop_tools()
}

pub fn desktop_built_tool_names() -> Vec<String> {
    crate::cowork::desktop_tools::common_desktop_tool_names()
}

pub fn desktop_built_skills() -> Vec<DesktopSkillCapability> {
    crate::cowork::desktop_skills::common_desktop_skill_capabilities()
}

pub fn desktop_runtime_skills() -> Vec<DesktopSkill> {
    crate::cowork::desktop_skills::common_desktop_skills()
}

pub fn default_runtime_options(agent_name: &str) -> Value {
    Value::Object(Map::from_iter([
        ("name".to_string(), Value::String(agent_name.to_string())),
        ("retries".to_string(), Value::from(0)),
        ("delay_between_retries".to_string(), Value::from(1)),
        ("exponential_backoff".to_string(), Value::Bool(false)),
        ("stream".to_string(), Value::Bool(true)),
        ("stream_events".to_string(), Value::Bool(true)),
        ("store_events".to_string(), Value::Bool(true)),
        ("delegate_to_all_members".to_string(), Value::Bool(false)),
        ("stream_member_events".to_string(), Value::Bool(true)),
        ("store_member_responses".to_string(), Value::Bool(false)),
    ]))
}

pub fn merge_agent_overrides(
    builtin: CoworkAgentOverrides,
    runtime: Option<CoworkAgentOverrides>,
) -> CoworkAgentOverrides {
    let Some(runtime) = runtime else {
        return builtin;
    };

    CoworkAgentOverrides {
        system_prompt: runtime.system_prompt.or(builtin.system_prompt),
        tool_names: runtime.tool_names.or(builtin.tool_names),
        skill_names: runtime.skill_names.or(builtin.skill_names),
        runtime_options: merge_runtime_options(
            builtin.runtime_options,
            runtime.runtime_options,
        ),
    }
}

pub fn apply_tool_settings(
    mut overrides: CoworkAgentOverrides,
    tools: Option<&CoworkChatToolSettings>,
) -> CoworkAgentOverrides {
    let mut tool_names = overrides.tool_names.take().unwrap_or_else(base_tool_names);
    let effective_tools = tools.cloned().unwrap_or(CoworkChatToolSettings {
        web_search: true,
        web_visit: true,
        image_search: false,
        code_interpreter: None,
        generate_image: None,
        generate_video: None,
    });

    set_tool_enabled(&mut tool_names, TOOL_WEB_SEARCH, effective_tools.web_search);
    set_tool_enabled(&mut tool_names, TOOL_WEB_VISIT, effective_tools.web_visit);

    overrides.tool_names = Some(tool_names);
    overrides
}

pub fn lock_tool_names_to_desktop(mut overrides: CoworkAgentOverrides) -> CoworkAgentOverrides {
    let allowed_tool_names = desktop_built_tool_names();
    let requested_tool_names = overrides.tool_names.take();
    let mut filtered_tool_names = Vec::new();

    for requested_tool_name in requested_tool_names.unwrap_or_else(|| allowed_tool_names.clone()) {
        let Some(canonical_tool_name) = resolve_desktop_tool_name(&requested_tool_name) else {
            continue;
        };

        if allowed_tool_names
            .iter()
            .any(|allowed_tool_name| allowed_tool_name == &canonical_tool_name)
            && !filtered_tool_names
                .iter()
                .any(|value| value == &canonical_tool_name)
        {
            filtered_tool_names.push(canonical_tool_name);
        }
    }

    overrides.tool_names = Some(if filtered_tool_names.is_empty() {
        allowed_tool_names
    } else {
        filtered_tool_names
    });
    overrides
}

fn merge_runtime_options(builtin: Option<Value>, runtime: Option<Value>) -> Option<Value> {
    match (builtin, runtime) {
        (None, None) => None,
        (Some(base), None) => Some(base),
        (None, Some(runtime)) => Some(runtime),
        (Some(base), Some(runtime)) => Some(merge_json_values(base, runtime)),
    }
}

fn merge_json_values(base: Value, runtime: Value) -> Value {
    match (base, runtime) {
        (Value::Object(mut base_map), Value::Object(runtime_map)) => {
            for (key, value) in runtime_map {
                let merged_value = match base_map.remove(&key) {
                    Some(existing) => merge_json_values(existing, value),
                    None => value,
                };
                base_map.insert(key, merged_value);
            }
            Value::Object(base_map)
        }
        (_, runtime) => runtime,
    }
}

fn set_tool_enabled(tool_names: &mut Vec<String>, tool_name: &str, enabled: bool) {
    if enabled {
        if !tool_names.iter().any(|value| value == tool_name) {
            tool_names.push(tool_name.to_string());
        }
    } else {
        tool_names.retain(|value| value != tool_name);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cowork::desktop_tools::{TOOL_APPLY_PATCH, TOOL_BASH, TOOL_READ};

    #[test]
    fn lock_tool_names_to_desktop_filters_out_backend_and_web_tools() {
        let overrides = CoworkAgentOverrides {
            system_prompt: None,
            tool_names: Some(vec![
                TOOL_READ.to_string(),
                TOOL_WEB_SEARCH.to_string(),
                "register_port".to_string(),
                TOOL_APPLY_PATCH.to_string(),
            ]),
            skill_names: None,
            runtime_options: None,
        };

        let locked = lock_tool_names_to_desktop(overrides);

        assert_eq!(
            locked.tool_names,
            Some(vec![TOOL_READ.to_string(), TOOL_APPLY_PATCH.to_string()])
        );
    }

    #[test]
    fn lock_tool_names_to_desktop_falls_back_to_desktop_toolset_when_needed() {
        let overrides = CoworkAgentOverrides {
            system_prompt: None,
            tool_names: Some(vec![
                TOOL_WEB_SEARCH.to_string(),
                "unknown_tool".to_string(),
            ]),
            skill_names: None,
            runtime_options: None,
        };

        let locked = lock_tool_names_to_desktop(overrides);

        assert_eq!(locked.tool_names, Some(desktop_built_tool_names()));
    }

    #[test]
    fn lock_tool_names_to_desktop_maps_aliases_to_canonical_names() {
        let overrides = CoworkAgentOverrides {
            system_prompt: None,
            tool_names: Some(vec!["read_file".to_string(), "bash".to_string()]),
            skill_names: None,
            runtime_options: None,
        };

        let locked = lock_tool_names_to_desktop(overrides);

        assert_eq!(
            locked.tool_names,
            Some(vec![TOOL_READ.to_string(), TOOL_BASH.to_string()])
        );
    }
}
