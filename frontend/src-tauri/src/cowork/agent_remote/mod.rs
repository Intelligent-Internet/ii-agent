pub mod auth;
pub mod cancel;
mod desktop_dispatcher;
mod mapper;
mod payload;
mod prompt;
pub mod service;
mod session_api;
mod socket;
mod types;

pub(super) use payload::build_remote_command;
pub(super) use prompt::build_remote_content;
pub(super) use session_api::{
    ensure_remote_session_uses_v1, fetch_remote_session_info, fetch_remote_session_snapshot,
    resolve_remote_model_selection, should_recreate_remote_session,
};
pub(super) use socket::run_remote_agent_request;
pub(super) use types::{V1_BACKEND_REQUIRED_MESSAGE, V1_REQUIRED_MESSAGE};
