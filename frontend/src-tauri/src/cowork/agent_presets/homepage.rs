use super::shared;
use crate::cowork::chat::CoworkAgentOverrides;

pub fn homepage_builtin_agent_overrides(_prompt_context: Option<&str>) -> CoworkAgentOverrides {
    CoworkAgentOverrides {
        system_prompt: Some(
            "You are the Cowork homepage agent inside II Agent desktop. Help the user reason over local cowork context, use tools deliberately, and keep responses concise and actionable."
                .to_string(),
        ),
        tool_names: Some(shared::base_tool_names()),
        skill_names: None,
        runtime_options: Some(shared::default_runtime_options("homepage_cowork_agent")),
    }
}
