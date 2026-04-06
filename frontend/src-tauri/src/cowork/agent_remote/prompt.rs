use crate::cowork::string_utils::normalize_optional_string;

const USER_REQUEST_MARKER: &str = "\n\n[User request]\n";

pub fn build_remote_content(content: &str, prompt_context: Option<&str>) -> String {
    match prompt_context.and_then(normalize_optional_string) {
        Some(context) => format!("{context}{USER_REQUEST_MARKER}{content}"),
        None => content.to_string(),
    }
}

pub fn extract_visible_user_content(content: &str) -> String {
    content
        .split_once(USER_REQUEST_MARKER)
        .map(|(_, user_request)| user_request.trim().to_string())
        .unwrap_or_else(|| content.trim().to_string())
}
