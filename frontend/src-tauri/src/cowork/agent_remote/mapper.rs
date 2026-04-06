use super::prompt::extract_visible_user_content;
use super::socket::normalize_event_name;
use super::types::{RemoteSessionEventRecord, RemoteSessionFile};
use crate::cowork::chat::{
    CoworkAgentRuntimeKind, CoworkChatFile, CoworkChatMessage, CoworkChatMessageRole,
    CoworkChatRunStatus, CoworkChatRuntimeEvent, CoworkChatScope,
};
use crate::cowork::runtime::CoworkRuntimeSessionSnapshot;
use crate::cowork::string_utils::normalize_optional_string;
use crate::cowork::time_utils::{generate_message_id, now_iso};
use reqwest::StatusCode;
use serde_json::Value;

pub fn map_remote_snapshot(
    local_scope: CoworkChatScope,
    local_session_id: &str,
    runtime_session_id: &str,
    updated_at: Option<String>,
    events: &[RemoteSessionEventRecord],
    files: &[RemoteSessionFile],
    run_status: Option<&str>,
) -> CoworkRuntimeSessionSnapshot {
    let effective_updated_at = updated_at
        .or_else(|| {
            events
                .iter()
                .rev()
                .find_map(|event| event.created_at.clone())
        })
        .unwrap_or_else(now_iso);

    CoworkRuntimeSessionSnapshot {
        runtime_kind: CoworkAgentRuntimeKind::Remote,
        runtime_session_id: runtime_session_id.to_string(),
        updated_at: effective_updated_at,
        messages: map_remote_messages(events),
        files: collect_remote_files(files, ""),
        run_status: map_remote_run_status(run_status),
        runtime_events: map_runtime_events(local_scope, local_session_id, events, run_status),
    }
}

fn map_runtime_events(
    local_scope: CoworkChatScope,
    local_session_id: &str,
    events: &[RemoteSessionEventRecord],
    run_status: Option<&str>,
) -> Vec<CoworkChatRuntimeEvent> {
    events
        .iter()
        .map(|event| CoworkChatRuntimeEvent {
            event_type: "runtime.event".to_string(),
            scope: local_scope,
            session_id: local_session_id.to_string(),
            runtime_event_type: normalize_event_name(&event.event_type),
            runtime_event_id: Some(event.id.clone()),
            runtime_created_at: event.created_at.clone(),
            run_status: run_status.map(ToString::to_string),
            emitted_at: event.created_at.clone().unwrap_or_else(now_iso),
            content: event.content.clone(),
        })
        .collect()
}

pub fn extract_error_message(content: &Value) -> String {
    content
        .get("message")
        .and_then(Value::as_str)
        .or_else(|| content.get("error").and_then(Value::as_str))
        .or_else(|| content.get("detail").and_then(Value::as_str))
        .unwrap_or_default()
        .to_string()
}

pub fn build_backend_error_message(status: StatusCode, body: &str, auth_required: &str) -> String {
    match status {
        StatusCode::UNAUTHORIZED => auth_required.to_string(),
        StatusCode::PAYMENT_REQUIRED => {
            "Current user does not have enough credits to run Cowork AI.".to_string()
        }
        StatusCode::NOT_FOUND => extract_error_detail(body)
            .unwrap_or_else(|| format!("Cowork AI backend request failed with status {status}")),
        _ => extract_error_detail(body)
            .unwrap_or_else(|| format!("Cowork AI backend request failed with status {status}")),
    }
}

pub fn is_terminal_run_status(value: &str) -> bool {
    matches!(value, "completed" | "aborted" | "failed" | "error")
}

pub fn is_waiting_run_status(value: &str) -> bool {
    matches!(value, "paused" | "waiting_for_input")
}

fn map_remote_messages(events: &[RemoteSessionEventRecord]) -> Vec<CoworkChatMessage> {
    let mut mapped_messages = Vec::new();
    let mut thinking_buffer = String::new();
    let mut response_buffer = String::new();
    let mut thinking_started_at: Option<String> = None;
    let mut response_started_at: Option<String> = None;
    let mut thinking_anchor: Option<String> = None;
    let mut response_anchor: Option<String> = None;

    let flush_thinking = |messages: &mut Vec<CoworkChatMessage>,
                          buffer: &mut String,
                          started_at: &mut Option<String>,
                          anchor: &mut Option<String>| {
        if let Some(content) = normalize_optional_string(buffer) {
            messages.push(CoworkChatMessage {
                id: anchor
                    .as_deref()
                    .map(|value| build_transcript_message_id("thinking", value))
                    .unwrap_or_else(generate_message_id),
                role: CoworkChatMessageRole::Assistant,
                content,
                created_at: started_at.clone().unwrap_or_else(now_iso),
                is_think_message: Some(true),
            });
        }
        buffer.clear();
        *started_at = None;
        *anchor = None;
    };

    let flush_response = |messages: &mut Vec<CoworkChatMessage>,
                          buffer: &mut String,
                          started_at: &mut Option<String>,
                          anchor: &mut Option<String>| {
        if let Some(content) = normalize_optional_string(buffer) {
            messages.push(CoworkChatMessage {
                id: anchor
                    .as_deref()
                    .map(|value| build_transcript_message_id("response", value))
                    .unwrap_or_else(generate_message_id),
                role: CoworkChatMessageRole::Assistant,
                content,
                created_at: started_at.clone().unwrap_or_else(now_iso),
                is_think_message: None,
            });
        }
        buffer.clear();
        *started_at = None;
        *anchor = None;
    };

    for event in events {
        let normalized_type = normalize_event_name(&event.event_type);
        match normalized_type.as_str() {
            "user_message" | "session_user_message" => {
                flush_thinking(
                    &mut mapped_messages,
                    &mut thinking_buffer,
                    &mut thinking_started_at,
                    &mut thinking_anchor,
                );
                flush_response(
                    &mut mapped_messages,
                    &mut response_buffer,
                    &mut response_started_at,
                    &mut response_anchor,
                );
                let text = extract_event_text(&event.content);
                let visible_text = extract_visible_user_content(&text);
                if !visible_text.is_empty() {
                    mapped_messages.push(CoworkChatMessage {
                        id: event.id.clone(),
                        role: CoworkChatMessageRole::User,
                        content: visible_text,
                        created_at: event.created_at.clone().unwrap_or_else(now_iso),
                        is_think_message: None,
                    });
                }
            }
            "agent_thinking_delta" => {
                if thinking_started_at.is_none() {
                    thinking_started_at = event.created_at.clone();
                    thinking_anchor = Some(event.id.clone());
                }
                thinking_buffer.push_str(&extract_event_text(&event.content));
            }
            "agent_thinking" => {
                if let Some(text) = normalize_optional_string(&extract_event_text(&event.content)) {
                    thinking_buffer.clear();
                    thinking_buffer.push_str(&text);
                    thinking_started_at = event.created_at.clone();
                    thinking_anchor = Some(event.id.clone());
                }
                flush_thinking(
                    &mut mapped_messages,
                    &mut thinking_buffer,
                    &mut thinking_started_at,
                    &mut thinking_anchor,
                );
            }
            "agent_response_delta" => {
                if response_started_at.is_none() {
                    response_started_at = event.created_at.clone();
                    response_anchor = Some(event.id.clone());
                }
                response_buffer.push_str(&extract_event_text(&event.content));
            }
            "agent_response" => {
                if let Some(text) = normalize_optional_string(&extract_event_text(&event.content)) {
                    response_buffer.clear();
                    response_buffer.push_str(&text);
                    response_started_at = event.created_at.clone();
                    response_anchor = Some(event.id.clone());
                }
                flush_response(
                    &mut mapped_messages,
                    &mut response_buffer,
                    &mut response_started_at,
                    &mut response_anchor,
                );
            }
            "complete" | "sub_agent_complete" => {
                if response_buffer.is_empty() {
                    response_buffer.push_str(&extract_event_text(&event.content));
                    response_started_at = event.created_at.clone();
                    response_anchor = Some(event.id.clone());
                }
                flush_response(
                    &mut mapped_messages,
                    &mut response_buffer,
                    &mut response_started_at,
                    &mut response_anchor,
                );
            }
            "error" => {
                flush_thinking(
                    &mut mapped_messages,
                    &mut thinking_buffer,
                    &mut thinking_started_at,
                    &mut thinking_anchor,
                );
                flush_response(
                    &mut mapped_messages,
                    &mut response_buffer,
                    &mut response_started_at,
                    &mut response_anchor,
                );
                let text = extract_error_message(&event.content);
                if !text.is_empty() {
                    mapped_messages.push(CoworkChatMessage {
                        id: event.id.clone(),
                        role: CoworkChatMessageRole::Assistant,
                        content: text,
                        created_at: event.created_at.clone().unwrap_or_else(now_iso),
                        is_think_message: None,
                    });
                }
            }
            _ => {}
        }
    }

    flush_thinking(
        &mut mapped_messages,
        &mut thinking_buffer,
        &mut thinking_started_at,
        &mut thinking_anchor,
    );
    flush_response(
        &mut mapped_messages,
        &mut response_buffer,
        &mut response_started_at,
        &mut response_anchor,
    );

    mapped_messages
}

#[cfg(test)]
mod tests {
    use super::map_remote_snapshot;
    use crate::cowork::chat::CoworkChatScope;
    use serde_json::json;

    use super::super::types::RemoteSessionEventRecord;

    #[test]
    fn snapshot_includes_user_messages_from_session_user_message_events() {
        let snapshot = map_remote_snapshot(
            CoworkChatScope::Homepage,
            "local-session",
            "remote-session",
            Some("2026-04-06T00:00:00Z".to_string()),
            &[RemoteSessionEventRecord {
                id: "evt-1".to_string(),
                event_type: "session.user_message".to_string(),
                content: json!({
                    "text": "Please organize these files"
                }),
                created_at: Some("2026-04-06T00:00:00Z".to_string()),
            }],
            &[],
            Some("completed"),
        );

        assert_eq!(snapshot.messages.len(), 1);
        assert_eq!(snapshot.messages[0].role, crate::cowork::chat::CoworkChatMessageRole::User);
        assert_eq!(snapshot.messages[0].content, "Please organize these files");
    }

    #[test]
    fn snapshot_maps_reasoning_events_to_thinking_messages() {
        let snapshot = map_remote_snapshot(
            CoworkChatScope::Homepage,
            "local-session",
            "remote-session",
            Some("2026-04-06T00:00:00Z".to_string()),
            &[RemoteSessionEventRecord {
                id: "evt-2".to_string(),
                event_type: "agent.reasoning.delta".to_string(),
                content: json!({
                    "text": "Inspecting files..."
                }),
                created_at: Some("2026-04-06T00:00:00Z".to_string()),
            }],
            &[],
            Some("running"),
        );

        assert_eq!(snapshot.messages.len(), 1);
        assert_eq!(
            snapshot.messages[0].role,
            crate::cowork::chat::CoworkChatMessageRole::Assistant
        );
        assert_eq!(snapshot.messages[0].content, "Inspecting files...");
        assert_eq!(snapshot.messages[0].is_think_message, Some(true));
    }
}

fn collect_remote_files(
    files: &[RemoteSessionFile],
    fallback_created_at: &str,
) -> Vec<CoworkChatFile> {
    let created_at = normalize_optional_string(fallback_created_at).unwrap_or_else(now_iso);
    files
        .iter()
        .map(|file| CoworkChatFile {
            id: file.id.clone(),
            file_name: normalize_optional_string(&file.name)
                .or_else(|| {
                    file.url
                        .as_ref()
                        .and_then(|url| normalize_optional_string(url))
                })
                .unwrap_or_else(|| file.id.clone()),
            file_size: file.size,
            content_type: normalize_optional_string(&file.content_type).unwrap_or_default(),
            created_at: created_at.clone(),
        })
        .collect()
}

fn extract_event_text(content: &Value) -> String {
    content
        .get("text")
        .and_then(Value::as_str)
        .or_else(|| content.get("message").and_then(Value::as_str))
        .or_else(|| content.get("content").and_then(Value::as_str))
        .or_else(|| content.get("delta").and_then(Value::as_str))
        .unwrap_or_default()
        .to_string()
}

pub fn map_remote_run_status(run_status: Option<&str>) -> CoworkChatRunStatus {
    match run_status {
        Some("running") => CoworkChatRunStatus::Thinking,
        Some("paused") | Some("waiting_for_input") => CoworkChatRunStatus::WaitingForInput,
        Some("aborted") | Some("cancelled") | Some("failed") | Some("error") => {
            CoworkChatRunStatus::Stopped
        }
        _ => CoworkChatRunStatus::Completed,
    }
}

fn build_transcript_message_id(kind: &str, anchor: &str) -> String {
    let normalized_anchor = anchor.split_whitespace().collect::<Vec<_>>().join("-");
    format!("cowork-transcript:{kind}:{normalized_anchor}")
}

fn extract_error_detail(body: &str) -> Option<String> {
    let parsed = serde_json::from_str::<Value>(body).ok()?;

    parsed
        .get("detail")
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .or_else(|| {
            parsed
                .get("message")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        })
        .or_else(|| {
            parsed
                .get("error")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        })
}
