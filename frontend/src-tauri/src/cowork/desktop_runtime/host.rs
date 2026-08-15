//! Host runtime backend.
//!
//! This backend is a thin policy layer over the existing native tool
//! execution path. The actual tools (bash, read, write, edit, apply_patch,
//! list_dir, glob, grep, todo_write) still own their execution. This module
//! centralises the documentation of what "host execution" means so that
//! tools and skills can reason about it uniformly alongside the WASM
//! backend.
//!
//! The host backend is appropriate for:
//!
//! * file discovery, reading, and structural edits
//! * regex / glob search
//! * shell-based local development tasks
//! * any task that already depends on the user's native environment
//!
//! It is **not** appropriate for isolated processing of user documents
//! with tight resource limits — use [`super::wasm`] for that.

#![allow(dead_code)]

use super::{RuntimeKind, RuntimeLimits};

/// Marker type for the host runtime. Kept separate from [`super::wasm`] so
/// downstream modules can branch on backend kind without touching tool
/// implementations.
#[derive(Debug, Clone, Copy, Default)]
pub struct HostRuntime;

impl HostRuntime {
    pub const KIND: RuntimeKind = RuntimeKind::Host;

    /// Default resource policy for host execution. The host backend only
    /// enforces the wall timeout; memory/fuel limits are advisory and are
    /// exposed so that host-side tools which want to match WASM policy can
    /// read the same values.
    pub fn default_limits() -> RuntimeLimits {
        RuntimeLimits::defaults()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn host_runtime_reports_host_kind() {
        assert_eq!(HostRuntime::KIND, RuntimeKind::Host);
    }

    #[test]
    fn host_runtime_exposes_default_limits() {
        let limits = HostRuntime::default_limits();
        assert!(limits.wall_timeout.as_secs() > 0);
        assert!(limits.max_memory_bytes > 0);
        assert!(limits.max_fuel > 0);
    }
}
