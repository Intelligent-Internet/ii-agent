use super::desktop_dispatcher::auto_execute_external_tools;
use super::mapper::{
    extract_error_message, is_terminal_run_status, is_waiting_run_status, map_remote_run_status,
};
use super::types::{
    RemoteAgentRunOutcome, RemoteSocketChatEvent, RemoteSocketSignal, REMOTE_SOCKET_MESSAGE_TYPE,
    SOCKET_EVENT_TIMEOUT_SECS,
};
use crate::cowork::agent_presets::DesktopRuntimePreset;
use crate::cowork::chat::{
    emit_cowork_stream_event, CoworkChatEvent, CoworkChatRunStatus, CoworkChatRuntimeEvent,
    CoworkChatScope,
};
use crate::cowork::desktop_tools::DesktopToolRuntime;
use crate::cowork::session_gateway;
use crate::cowork::string_utils::normalize_optional_string;
use crate::cowork::time_utils::now_iso;
use rust_socketio::{ClientBuilder as SocketClientBuilder, Payload, TransportType};
use serde_json::{json, Value};
use std::any::Any;
use std::sync::mpsc;
use std::time::{Duration, Instant};
use tauri::async_runtime::spawn_blocking;
use tauri::AppHandle;

pub async fn run_remote_agent_request(
    api_base_url: &str,
    access_token: &str,
    remote_session_id: Option<String>,
    command_payload: Value,
    app: AppHandle,
    scope: CoworkChatScope,
    desktop_runtime_preset: Option<DesktopRuntimePreset>,
    local_session_id: String,
) -> Result<RemoteAgentRunOutcome, String> {
    let api_base_url = api_base_url.to_string();
    let access_token = access_token.to_string();
    let remote_session_id_for_auth = remote_session_id.clone();
    let stream_context = RemoteStreamContext {
        app,
        scope,
        local_session_id,
    };

    spawn_blocking(move || {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(
            || -> Result<RemoteAgentRunOutcome, String> {
                let (tx, rx) = mpsc::channel::<RemoteSocketSignal>();
                let tx_chat = tx.clone();
                let tx_error = tx.clone();
                let mut last_status = Some(CoworkChatRunStatus::Thinking);
                let mut desktop_runtime = DesktopToolRuntime::default();

                let auth_payload = if let Some(session_id) = remote_session_id_for_auth.clone() {
                    json!({
                        "token": access_token,
                        "session_uuid": session_id,
                    })
                } else {
                    json!({
                        "token": access_token,
                    })
                };

                let socket = SocketClientBuilder::new(api_base_url.as_str())
                    .transport_type(TransportType::Websocket)
                    .auth(auth_payload)
                    .on("chat_event", move |payload, _socket| {
                        if let Err(payload) =
                            std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                if let Some(event) =
                                    parse_socket_payload(payload).and_then(parse_socket_chat_event)
                                {
                                    let _ = tx_chat.send(RemoteSocketSignal::ChatEvent(event));
                                }
                            }))
                        {
                            eprintln!(
                                "[cowork] chat_event callback panicked: {}",
                                panic_payload_message(payload.as_ref())
                            );
                        }
                    })
                    .on("error", move |payload, _socket| {
                        if let Err(payload) =
                            std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                let message = parse_socket_payload(payload)
                                    .and_then(|value| {
                                        let extracted = extract_error_message(&value);
                                        if extracted.is_empty() {
                                            None
                                        } else {
                                            Some(extracted)
                                        }
                                    })
                                    .unwrap_or_else(|| {
                                        "Cowork agent socket returned an unknown error".to_string()
                                    });
                                let _ = tx_error.send(RemoteSocketSignal::ClientError(message));
                            }))
                        {
                            eprintln!(
                                "[cowork] socket error callback panicked: {}",
                                panic_payload_message(payload.as_ref())
                            );
                        }
                    })
                    .connect()
                    .map_err(|error| format!("Failed to connect Cowork agent socket: {error}"))?;

                let join_payload = if let Some(session_id) = remote_session_id.clone() {
                    json!({ "session_uuid": session_id })
                } else {
                    json!({})
                };

                socket
                    .emit("join_session", join_payload)
                    .map_err(|error| format!("Failed to join Cowork agent session: {error}"))?;

                let active_session_id = wait_for_socket_session(
                    &rx,
                    remote_session_id.clone(),
                    &stream_context,
                    &mut last_status,
                )?;

                // Inject "command" into content so the backend discriminated union can resolve it.
                let mut enriched_content = command_payload.clone();
                if let Some(obj) = enriched_content.as_object_mut() {
                    obj.insert(
                        "command".to_string(),
                        Value::String(REMOTE_SOCKET_MESSAGE_TYPE.to_string()),
                    );
                }

                socket
                    .emit(
                        "chat_message",
                        json!({
                            "session_uuid": active_session_id,
                            "content": enriched_content,
                        }),
                    )
                    .map_err(|error| format!("Failed to send Cowork agent message: {error}"))?;

                let continue_session_id = active_session_id.clone();
                let mut continue_run = |run_id: &str,
                                        external_tool_results: Vec<Value>|
                 -> Result<(), String> {
                    socket
                        .emit(
                            "chat_message",
                            json!({
                                "session_uuid": continue_session_id,
                                "content": {
                                    "command": "cowork_continue_run",
                                    "run_id": run_id,
                                    "confirmed": true,
                                    "external_tool_results": external_tool_results,
                                }
                            }),
                        )
                        .map_err(|error| format!("Failed to continue Cowork agent run: {error}"))
                };

                wait_for_remote_run_completion(
                    &rx,
                    &stream_context,
                    &mut last_status,
                    desktop_runtime_preset.as_ref(),
                    &mut desktop_runtime,
                    &mut continue_run,
                )?;
                let _ = socket.disconnect();

                Ok(RemoteAgentRunOutcome {
                    runtime_session_id: active_session_id,
                })
            },
        ))
        .map_err(|payload| {
            format!(
                "Cowork agent worker panicked: {}",
                panic_payload_message(payload.as_ref())
            )
        })?
    })
    .await
    .map_err(|error| format!("Cowork agent worker failed: {error}"))?
}

fn panic_payload_message(payload: &(dyn Any + Send)) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        (*message).to_string()
    } else if let Some(message) = payload.downcast_ref::<String>() {
        message.clone()
    } else {
        "non-string panic payload".to_string()
    }
}

fn wait_for_socket_session(
    receiver: &mpsc::Receiver<RemoteSocketSignal>,
    fallback_session_id: Option<String>,
    stream_context: &RemoteStreamContext,
    last_status: &mut Option<CoworkChatRunStatus>,
) -> Result<String, String> {
    if let Some(session_id) = fallback_session_id {
        return Ok(session_id);
    }

    let started_at = Instant::now();
    let timeout = Duration::from_secs(SOCKET_EVENT_TIMEOUT_SECS);

    while started_at.elapsed() < timeout {
        match receiver.recv_timeout(Duration::from_millis(250)) {
            Ok(RemoteSocketSignal::ChatEvent(event)) => {
                emit_remote_socket_event(stream_context, &event, last_status);
                if event.event_type == "system" {
                    if let Some(session_id) = event
                        .content
                        .get("session_id")
                        .and_then(Value::as_str)
                        .and_then(normalize_optional_string)
                    {
                        return Ok(session_id);
                    }
                } else if event.event_type == "error" {
                    let message = extract_error_message(&event.content);
                    if !message.is_empty() {
                        return Err(message);
                    }
                }
            }
            Ok(RemoteSocketSignal::ClientError(message)) => return Err(message),
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err(
                    "Cowork agent socket disconnected before session initialization".to_string(),
                );
            }
        }
    }

    Err("Timed out while waiting for Cowork agent session initialization".to_string())
}

fn wait_for_remote_run_completion(
    receiver: &mpsc::Receiver<RemoteSocketSignal>,
    stream_context: &RemoteStreamContext,
    last_status: &mut Option<CoworkChatRunStatus>,
    desktop_runtime_preset: Option<&DesktopRuntimePreset>,
    desktop_runtime: &mut DesktopToolRuntime,
    continue_run: &mut dyn FnMut(&str, Vec<Value>) -> Result<(), String>,
) -> Result<(), String> {
    let started_at = Instant::now();
    let timeout = Duration::from_secs(SOCKET_EVENT_TIMEOUT_SECS);
    let mut pending_continue_run_id: Option<String> = None;

    while started_at.elapsed() < timeout {
        match receiver.recv_timeout(Duration::from_millis(250)) {
            Ok(RemoteSocketSignal::ChatEvent(event)) => {
                emit_remote_socket_event(stream_context, &event, last_status);
                if event.event_type == "error" {
                    let message = extract_error_message(&event.content);
                    if !message.is_empty() {
                        return Err(message);
                    }
                }

                if event.event_type == "tool_confirmation" {
                    if let Some(run_id) = event.run_id.as_deref() {
                        if let Some(external_tool_results) = auto_execute_external_tools(
                            &stream_context.app,
                            stream_context.scope,
                            desktop_runtime_preset,
                            &stream_context.local_session_id,
                            &event.content,
                            desktop_runtime,
                        )? {
                            continue_run(run_id, external_tool_results)?;
                            pending_continue_run_id = Some(run_id.to_string());
                            continue;
                        }
                    }
                }

                if should_ignore_terminal_after_continue(&event, pending_continue_run_id.as_deref())
                {
                    continue;
                }
                if should_clear_pending_continue(&event, pending_continue_run_id.as_deref()) {
                    pending_continue_run_id = None;
                }

                if let Some(run_status) = event.run_status.as_deref() {
                    if is_terminal_run_status(run_status) || is_waiting_run_status(run_status) {
                        return Ok(());
                    }
                }

                match event.event_type.as_str() {
                    "stream_complete"
                    | "complete"
                    | "agent_response_interrupted"
                    | "tool_confirmation" => {
                        return Ok(());
                    }
                    _ => {}
                }
            }
            Ok(RemoteSocketSignal::ClientError(message)) => return Err(message),
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err("Cowork agent socket disconnected before the run completed".to_string());
            }
        }
    }

    Err("Timed out while waiting for Cowork agent run completion".to_string())
}

fn should_ignore_terminal_after_continue(
    event: &RemoteSocketChatEvent,
    pending_continue_run_id: Option<&str>,
) -> bool {
    let Some(pending_run_id) = pending_continue_run_id else {
        return false;
    };
    if event.run_id.as_deref() != Some(pending_run_id) {
        return false;
    }

    matches!(event.event_type.as_str(), "stream_complete" | "complete")
        || matches!(
            event.run_status.as_deref(),
            Some(run_status) if is_terminal_run_status(run_status)
        )
}

fn should_clear_pending_continue(
    event: &RemoteSocketChatEvent,
    pending_continue_run_id: Option<&str>,
) -> bool {
    let Some(pending_run_id) = pending_continue_run_id else {
        return false;
    };
    if event.run_id.as_deref() != Some(pending_run_id) {
        return false;
    }

    matches!(
        event.event_type.as_str(),
        "agent_continue"
            | "processing"
            | "agent_thinking_start"
            | "tool_call"
            | "tool_result"
            | "agent_thinking_delta"
            | "agent_thinking"
            | "agent_response_delta"
            | "agent_response"
            | "tool_confirmation"
    ) || matches!(event.run_status.as_deref(), Some("running"))
}

fn parse_socket_payload(payload: Payload) -> Option<Value> {
    #[allow(deprecated)]
    match payload {
        Payload::Text(values) => values.into_iter().next(),
        Payload::String(text) => serde_json::from_str::<Value>(&text).ok(),
        Payload::Binary(_) => None,
    }
}

/// Map backend dotted event names (e.g. "agent.stream.complete") to the short
/// names the Cowork runtime uses for status derivation and terminal detection.
pub fn normalize_event_name(raw: &str) -> String {
    match raw {
        // System / connection events
        "connection.established" => "system".to_string(),
        "system.error" => "error".to_string(),
        "system.pong" => "pong".to_string(),

        // Agent lifecycle
        "agent.processing" => "processing".to_string(),
        "agent.reasoning.start" => "agent_thinking_start".to_string(),
        "agent.reasoning.delta" => "agent_thinking_delta".to_string(),
        "agent.reasoning" => "agent_thinking".to_string(),
        "agent.thinking.delta" => "agent_thinking_delta".to_string(),
        "agent.thinking" => "agent_thinking".to_string(),
        "agent.response.delta" => "agent_response_delta".to_string(),
        "agent.response" => "agent_response".to_string(),
        "agent.response.interrupted" => "agent_response_interrupted".to_string(),
        "agent.continue" => "agent_continue".to_string(),
        "agent.stream.complete" => "stream_complete".to_string(),
        "agent.complete" => "complete".to_string(),
        "agent.error" => "error".to_string(),

        // Tool events
        "tool.call" => "tool_call".to_string(),
        "tool.result" => "tool_result".to_string(),
        "tool.confirmation" => "tool_confirmation".to_string(),
        "tool.user_input" => "waiting_for_user_input".to_string(),

        // Metrics / user message
        "metrics.updated" => "metrics_update".to_string(),
        "session.user_message" => "user_message".to_string(),
        "user.message" => "user_message".to_string(),

        // Fallback: strip "agent." / "system." prefix and replace dots with underscores
        other => {
            let stripped = other
                .strip_prefix("agent.")
                .or_else(|| other.strip_prefix("system."))
                .or_else(|| other.strip_prefix("tool."))
                .unwrap_or(other);
            stripped.replace('.', "_")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::types::RemoteSocketChatEvent;
    use super::{
        normalize_event_name, parse_socket_chat_event, should_clear_pending_continue,
        should_ignore_terminal_after_continue,
    };
    use serde_json::json;

    #[test]
    fn normalizes_session_user_message_to_user_message() {
        assert_eq!(normalize_event_name("session.user_message"), "user_message");
    }

    #[test]
    fn normalizes_legacy_user_message_to_user_message() {
        assert_eq!(normalize_event_name("user.message"), "user_message");
    }

    #[test]
    fn normalizes_reasoning_events_to_thinking_events() {
        assert_eq!(
            normalize_event_name("agent.reasoning.start"),
            "agent_thinking_start"
        );
        assert_eq!(
            normalize_event_name("agent.reasoning.delta"),
            "agent_thinking_delta"
        );
        assert_eq!(normalize_event_name("agent.reasoning"), "agent_thinking");
    }

    #[test]
    fn ignores_stale_stream_complete_after_auto_continue() {
        let event = RemoteSocketChatEvent {
            event_id: Some("evt-1".to_string()),
            event_type: "stream_complete".to_string(),
            content: json!({}),
            created_at: Some("2026-04-06T00:00:00Z".to_string()),
            run_status: None,
            run_id: Some("run-1".to_string()),
        };

        assert!(should_ignore_terminal_after_continue(&event, Some("run-1")));
        assert!(!should_ignore_terminal_after_continue(
            &event,
            Some("run-2")
        ));
    }

    #[test]
    fn clears_pending_continue_once_resumed_events_arrive() {
        let event = RemoteSocketChatEvent {
            event_id: Some("evt-2".to_string()),
            event_type: "agent_continue".to_string(),
            content: json!({}),
            created_at: Some("2026-04-06T00:00:01Z".to_string()),
            run_status: Some("running".to_string()),
            run_id: Some("run-1".to_string()),
        };

        assert!(should_clear_pending_continue(&event, Some("run-1")));
        assert!(!should_clear_pending_continue(&event, Some("run-2")));
    }

    #[test]
    fn parses_run_id_from_content_when_top_level_run_id_is_missing() {
        let event = parse_socket_chat_event(json!({
            "id": "evt-3",
            "name": "agent.tool.confirmation",
            "content": {
                "run_id": "run-1",
                "tools": []
            }
        }))
        .expect("socket event should parse");

        assert_eq!(event.run_id.as_deref(), Some("run-1"));
        assert_eq!(event.event_type, "tool_confirmation");
    }
}

fn parse_socket_chat_event(value: Value) -> Option<RemoteSocketChatEvent> {
    let record = value.as_object()?;
    let event_id = record
        .get("id")
        .and_then(Value::as_str)
        .and_then(normalize_optional_string);

    // Backend sends "name" (e.g. "agent.stream.complete"), fall back to "type"
    let raw_event_type = record
        .get("name")
        .and_then(Value::as_str)
        .or_else(|| record.get("type").and_then(Value::as_str))?;
    let event_type = normalize_event_name(raw_event_type);

    let content = record.get("content").cloned().unwrap_or(Value::Null);

    // Backend sends "timestamp" as a float (epoch seconds), convert to ISO string
    let created_at = record
        .get("created_at")
        .and_then(Value::as_str)
        .and_then(normalize_optional_string)
        .or_else(|| {
            record
                .get("timestamp")
                .and_then(Value::as_str)
                .and_then(normalize_optional_string)
        })
        .or_else(|| {
            // timestamp may be a numeric epoch — just stringify it
            record.get("timestamp").and_then(|v| {
                if v.is_f64() || v.is_i64() || v.is_u64() {
                    Some(v.to_string())
                } else {
                    None
                }
            })
        });

    // run_status may be top-level or inside content
    let run_status = record
        .get("run_status")
        .and_then(Value::as_str)
        .and_then(normalize_optional_string)
        .or_else(|| {
            content
                .get("run_status")
                .and_then(Value::as_str)
                .and_then(normalize_optional_string)
        });

    let run_id = record
        .get("run_id")
        .and_then(Value::as_str)
        .and_then(normalize_optional_string)
        .or_else(|| {
            content
                .get("run_id")
                .and_then(Value::as_str)
                .and_then(normalize_optional_string)
        });

    Some(RemoteSocketChatEvent {
        event_id,
        event_type,
        content,
        created_at,
        run_status,
        run_id,
    })
}

#[derive(Clone)]
struct RemoteStreamContext {
    app: AppHandle,
    scope: CoworkChatScope,
    local_session_id: String,
}

fn emit_remote_socket_event(
    stream_context: &RemoteStreamContext,
    event: &RemoteSocketChatEvent,
    last_status: &mut Option<CoworkChatRunStatus>,
) {
    let derived_status = derive_status_from_remote_event(event);
    let runtime_event = CoworkChatEvent::Runtime(CoworkChatRuntimeEvent {
        event_type: "runtime.event".to_string(),
        scope: stream_context.scope,
        session_id: stream_context.local_session_id.clone(),
        runtime_event_type: event.event_type.clone(),
        runtime_event_id: event.event_id.clone(),
        runtime_created_at: event.created_at.clone(),
        run_status: event.run_status.clone(),
        emitted_at: now_iso(),
        content: event.content.clone(),
    });

    if let CoworkChatEvent::Runtime(runtime_event_payload) = &runtime_event {
        let _ = session_gateway::persist_stream_runtime_event(
            &stream_context.app,
            runtime_event_payload,
            derived_status,
        );
    }
    let _ = emit_cowork_stream_event(&stream_context.app, &runtime_event);

    if let Some(status) = derived_status {
        if last_status.as_ref() == Some(&status) {
            return;
        }

        *last_status = Some(status);
        let status_event = session_gateway::build_status_updated_event(
            stream_context.scope,
            stream_context.local_session_id.clone(),
            status,
        );
        let _ = emit_cowork_stream_event(&stream_context.app, &status_event);
    }
}

fn derive_status_from_remote_event(event: &RemoteSocketChatEvent) -> Option<CoworkChatRunStatus> {
    if let Some(run_status) = event.run_status.as_deref() {
        return Some(map_remote_run_status(Some(run_status)));
    }

    match event.event_type.as_str() {
        "processing"
        | "agent_thinking_start"
        | "agent_thinking_delta"
        | "agent_thinking"
        | "agent_response_delta"
        | "agent_response"
        | "agent_continue"
        | "tool_call"
        | "tool_result"
        | "system" => Some(CoworkChatRunStatus::Thinking),
        "tool_confirmation" | "waiting_for_user_input" => {
            Some(CoworkChatRunStatus::WaitingForInput)
        }
        "complete" | "stream_complete" => Some(CoworkChatRunStatus::Completed),
        "error" | "agent_response_interrupted" => Some(CoworkChatRunStatus::Stopped),
        _ => None,
    }
}
