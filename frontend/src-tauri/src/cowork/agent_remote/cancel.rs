//! Fire-and-forget cancel dispatch for cowork remote runs.
//!
//! When the user presses Pause in the cowork chat box, the local
//! `stop_cowork_chat_session` command updates UI state immediately, but the
//! Python backend is still running the agent loop. This module opens a
//! short-lived, independent socket.io connection to Python, emits a single
//! `chat_message` event with `{command: "cancel"}`, and disconnects.
//!
//! Python's `CancelHandler` (see `src/ii_agent/realtime/handlers/cancel.py`)
//! then transitions the running task to ABORTING and sets a Redis cancel
//! flag; the agent's execution loop picks that up on its next poll and
//! throws `RunCancelledException`, which the backend translates into a
//! terminal socket event. The original `run_remote_agent_request` worker
//! (still blocked in `wait_for_remote_run_completion`) receives that event
//! via its OWN long-lived socket and exits cleanly via its existing
//! terminal branches.
//!
//! This is deliberately kept separate from `socket.rs::run_remote_agent_request`
//! because the cancel flow has very different semantics: no event loop, no
//! tool confirmation / continue-run, and errors are best-effort (logged and
//! dropped, never propagated — local stop must not fail because of a network
//! hiccup).
//!
//! ## Why no `join_session`?
//!
//! The Python `chat_message` handler
//! (`src/ii_agent/realtime/manager.py::chat_message`) resolves the session
//! directly from `request.session_uuid` via `_require_session` (DB lookup).
//! It does NOT require the socket to have previously called `join_session`.
//!
//! Emitting `join_session` from this short-lived cancel socket triggered a
//! race: the `join_session` handler performs `enter_room` +
//! `add_sid_to_session` async operations, and if Rust disconnected the
//! socket before those finished, python-socketio's internal sid→session map
//! raised `KeyError: 'Session not found'` during cleanup. Since `chat_message`
//! doesn't need the join, we skip it entirely and avoid the race.
//!
//! We also do NOT pass `session_uuid` in the connect-auth payload — the only
//! required auth field is `token`. Passing `session_uuid` would cause Python
//! to store it on the sid's session data, but since we never emit
//! `join_session`, it goes unused and could mislead future maintainers.

use rust_socketio::{ClientBuilder as SocketClientBuilder, TransportType};
use serde_json::json;
use std::thread;
use std::time::Duration;
use tauri::async_runtime::spawn_blocking;

/// Grace period between emitting the cancel `chat_message` and disconnecting
/// the short-lived cancel socket. Gives Python's async event loop enough time
/// to fully dispatch the incoming event into `CancelHandler` before the socket
/// tears down. 250ms is plenty for an in-process event-loop dispatch and
/// cheap enough that the stop button still feels instant.
const CANCEL_EMIT_GRACE_MS: u64 = 250;

/// Dispatch a `{command: "cancel"}` event to the Python backend for the given
/// remote session. Fire-and-forget: the returned `Result` is for logging only
/// and should never be used to block the caller's local stop flow.
pub async fn emit_cancel_signal(
    api_base_url: String,
    access_token: String,
    remote_session_id: String,
) -> Result<(), String> {
    spawn_blocking(move || -> Result<(), String> {
        // Auth payload: ONLY token. See the module-level comment for why we
        // deliberately omit session_uuid here.
        let auth_payload = json!({ "token": access_token });

        // Build a standalone socket.io client. We intentionally do NOT
        // register any `on("chat_event", …)` listeners — we don't care about
        // responses; the original run worker is still subscribed on ITS own
        // long-lived socket and will receive the terminal event organically
        // once Python marks the run as cancelled.
        let socket = SocketClientBuilder::new(api_base_url.as_str())
            .transport_type(TransportType::Websocket)
            .auth(auth_payload)
            .connect()
            .map_err(|error| {
                format!("Cowork cancel dispatch: connect failed: {error}")
            })?;

        // Emit the cancel command directly. Python's `chat_message` handler
        // (`src/ii_agent/realtime/manager.py`) calls `_require_session` on
        // `request.session_uuid`, so the session is resolved from the
        // payload — no prior `join_session` emit is required. `CancelContent`
        // extends `EmptyContent` with `extra="allow"`, so a bare
        // `{command: "cancel"}` parses cleanly via the discriminated union.
        socket
            .emit(
                "chat_message",
                json!({
                    "session_uuid": remote_session_id,
                    "content": { "command": "cancel" },
                }),
            )
            .map_err(|error| {
                format!("Cowork cancel dispatch: chat_message emit failed: {error}")
            })?;

        // Give Python's event loop a moment to dispatch the cancel into
        // CancelHandler before we tear down the socket. Without this sleep,
        // a premature disconnect can race the server's async handler and
        // cause spurious cleanup errors in python-socketio's internal state.
        thread::sleep(Duration::from_millis(CANCEL_EMIT_GRACE_MS));

        // Best-effort disconnect — ignore errors. We've already delivered the
        // cancel signal.
        let _ = socket.disconnect();

        Ok(())
    })
    .await
    .map_err(|error| format!("Cowork cancel dispatch worker join failed: {error}"))?
}
