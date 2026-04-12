//! Desktop execution runtimes for cowork desktop tools and skills.
//!
//! The desktop runtime owns execution policy: resource limits, scratch
//! workspace layout, and cleanup semantics for skill-driven processing.
//! Tools plug into a runtime by asking the runtime to execute something —
//! they never spawn isolated work directly.
//!
//! Two backends are currently defined:
//!
//! * [`host`] — the existing native execution backend used by normal local
//!   file and shell tools. It is declared here only so that runtime policy
//!   lives in one place; the tool modules continue to run on the host
//!   directly.
//! * [`wasm`] — the isolated backend used by skill-driven processing tasks
//!   that should not run as native host code. Modules are sandboxed by a
//!   wasmtime engine with memory and fuel limits.

pub mod host;
pub mod wasm;

use std::time::Duration;

/// Resource limits shared between desktop runtimes.
///
/// These limits are expressed once so both the host and the WASM backend
/// can enforce a common policy. Individual backends may ignore a limit
/// that does not apply to them (for example, the host backend only enforces
/// `wall_timeout`, while the WASM backend enforces all three).
#[derive(Debug, Clone, Copy)]
pub struct RuntimeLimits {
    /// Maximum wall-clock duration of a single runtime call.
    pub wall_timeout: Duration,
    /// Maximum linear memory (in bytes) a WASM module may allocate.
    pub max_memory_bytes: usize,
    /// Maximum number of WASM instructions (fuel units) per call.
    pub max_fuel: u64,
}

impl RuntimeLimits {
    /// Default limits used when a skill or tool does not override them.
    pub const fn defaults() -> Self {
        Self {
            wall_timeout: Duration::from_secs(30),
            max_memory_bytes: 256 * 1024 * 1024, // 256 MiB
            max_fuel: 1_000_000_000,
        }
    }
}

impl Default for RuntimeLimits {
    fn default() -> Self {
        Self::defaults()
    }
}

/// Identifier for a desktop runtime backend.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeKind {
    Host,
    Wasm,
}
