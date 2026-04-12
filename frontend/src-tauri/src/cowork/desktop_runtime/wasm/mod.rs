//! Isolated WASM runtime backend.
//!
//! This module owns the sandboxed execution path used by skill-driven
//! processing tasks that should not run directly on the host. It is the
//! single place where the wasmtime engine, WASI preview1 linker, resource
//! limits, temporary workspace layout, and the input/output contract with
//! callers are defined.
//!
//! ## Execution contract
//!
//! A caller supplies:
//!
//! 1. A WASM module name. The runtime resolves the module via
//!    [`ModuleRegistry`] (either an embedded module shipped with the
//!    desktop app or, for tests, a raw byte buffer).
//! 2. A JSON input payload. The runtime serialises this to a temp file
//!    inside a per-call scratch directory and exposes the scratch directory
//!    to the guest as its preopened `/workspace` directory via WASI.
//! 3. Optional host files to mirror into the scratch `/workspace/inputs`
//!    directory.
//! 4. A [`RuntimeLimits`] override. Defaults come from
//!    [`RuntimeLimits::defaults`].
//!
//! The runtime returns a [`WasmRunResult`] containing stdout, stderr,
//! structured JSON output read from `/workspace/output.json` if the guest
//! produced one, a list of output artifact paths copied back from
//! `/workspace/outputs`, and the wall-clock duration. Errors are returned
//! as [`WasmRunError`] variants.
//!
//! ## Sandboxing
//!
//! * A fresh `wasmtime::Store` is created per call (no state bleeding).
//! * Fuel is metered; the store traps when `RuntimeLimits::max_fuel` is
//!   consumed.
//! * Epoch-based deadlines enforce `wall_timeout` even when the guest is
//!   stuck in non-fuel-accounted code.
//! * Linear memory is capped by [`wasmtime::ResourceLimiter`].
//! * File access is restricted to the preopened scratch directory via
//!   WASI. The guest cannot touch the host filesystem outside of it.
//!
//! ## Temp workspace layout
//!
//! Every call creates a scratch directory like:
//!
//! ```text
//! {root}/wasm-{session_id}/{call_id}/
//!   input.json         (caller payload)
//!   inputs/            (mirrored host files — optional)
//!   outputs/           (populated by the guest)
//!   output.json        (optional structured guest response)
//! ```
//!
//! The caller is responsible for providing `root`. The scratch directory
//! is removed when the [`WasmRuntimeCall`] guard is dropped, unless the
//! caller asks the runtime to keep it for debugging.

#![allow(dead_code)]

pub mod chunking;
pub mod freshness;
pub mod lifecycle;

pub use lifecycle::acquire_runtime;

use super::{RuntimeKind, RuntimeLimits};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use std::{io, thread};
use wasmtime::{Config, Engine, Linker, Module, Store, StoreLimits, StoreLimitsBuilder};
use wasmtime_wasi::preview1::{self as wasi_preview1, WasiP1Ctx};
use wasmtime_wasi::{DirPerms, FilePerms, WasiCtxBuilder};

/// Registry of WASM modules known to the desktop runtime.
///
/// Modules can be registered ahead of time (application-owned assets) or
/// at runtime (for tests and experimental skills). Lookup by name is
/// case-sensitive.
#[derive(Default)]
pub struct ModuleRegistry {
    entries: Mutex<HashMap<String, ModuleEntry>>,
}

#[derive(Clone)]
struct ModuleEntry {
    source: ModuleSource,
}

#[derive(Clone)]
enum ModuleSource {
    Bytes(Arc<Vec<u8>>),
    Wat(Arc<String>),
    Path(PathBuf),
}

impl ModuleRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a module by its raw WASM bytes. The byte buffer is stored
    /// behind an `Arc` so repeated lookups are cheap.
    pub fn register_bytes(&self, name: impl Into<String>, bytes: Vec<u8>) {
        self.entries.lock().expect("module registry poisoned").insert(
            name.into(),
            ModuleEntry {
                source: ModuleSource::Bytes(Arc::new(bytes)),
            },
        );
    }

    /// Register a module by its WAT (text format) source. Useful for
    /// bundling small helpers without having to ship pre-compiled bytes.
    pub fn register_wat(&self, name: impl Into<String>, wat: impl Into<String>) {
        self.entries.lock().expect("module registry poisoned").insert(
            name.into(),
            ModuleEntry {
                source: ModuleSource::Wat(Arc::new(wat.into())),
            },
        );
    }

    /// Register a module that lives on disk. The path is resolved lazily,
    /// so it is safe to register modules that will only become available
    /// at runtime.
    pub fn register_path(&self, name: impl Into<String>, path: PathBuf) {
        self.entries.lock().expect("module registry poisoned").insert(
            name.into(),
            ModuleEntry {
                source: ModuleSource::Path(path),
            },
        );
    }

    pub fn has(&self, name: &str) -> bool {
        self.entries
            .lock()
            .expect("module registry poisoned")
            .contains_key(name)
    }

    pub fn names(&self) -> Vec<String> {
        let mut names: Vec<String> = self
            .entries
            .lock()
            .expect("module registry poisoned")
            .keys()
            .cloned()
            .collect();
        names.sort();
        names
    }

    fn lookup(&self, name: &str) -> Option<ModuleEntry> {
        self.entries
            .lock()
            .expect("module registry poisoned")
            .get(name)
            .cloned()
        }

    fn load_module(&self, engine: &Engine, name: &str) -> Result<Module, WasmRunError> {
        let entry = self
            .lookup(name)
            .ok_or_else(|| WasmRunError::UnknownModule(name.to_string()))?;
        match entry.source {
            ModuleSource::Bytes(bytes) => Module::new(engine, bytes.as_slice())
                .map_err(|error| WasmRunError::ModuleLoad(error.to_string())),
            ModuleSource::Wat(wat) => {
                let bytes = wat::parse_str(wat.as_str())
                    .map_err(|error| WasmRunError::ModuleLoad(error.to_string()))?;
                Module::new(engine, bytes.as_slice())
                    .map_err(|error| WasmRunError::ModuleLoad(error.to_string()))
            }
            ModuleSource::Path(path) => {
                let bytes = fs::read(&path).map_err(|error| {
                    WasmRunError::ModuleLoad(format!(
                        "failed to read WASM module at {}: {}",
                        path.display(),
                        error
                    ))
                })?;
                Module::new(engine, bytes.as_slice())
                    .map_err(|error| WasmRunError::ModuleLoad(error.to_string()))
            }
        }
    }
}

/// Input passed to a single [`WasmRuntime::run`] call.
#[derive(Debug, Clone)]
pub struct WasmRunRequest {
    pub module_name: String,
    /// Optional JSON payload written to `input.json` in the scratch
    /// directory before the guest runs.
    pub input_json: Option<Value>,
    /// Optional host files mirrored into `inputs/` (source path → logical
    /// filename inside `inputs/`).
    pub input_files: Vec<(PathBuf, String)>,
    /// Optional resource limit overrides. Missing fields fall back to
    /// [`RuntimeLimits::defaults`].
    pub limits: Option<RuntimeLimits>,
    /// Keep the scratch workspace on disk after the call returns. Useful
    /// for debugging; defaults to `false` so artifacts are cleaned up.
    pub keep_workspace: bool,
    /// Optional entrypoint function to invoke. Defaults to calling the
    /// module's `_start` (WASI command) export.
    pub entrypoint: WasmEntrypoint,
    /// Optional cowork session identifier. When set, the runtime scopes
    /// the scratch directory under `{scratch_root}/{session_id}/` so
    /// session cleanup can sweep only the directories belonging to a
    /// given session.
    pub session_id: Option<String>,
}

impl WasmRunRequest {
    pub fn new(module_name: impl Into<String>) -> Self {
        Self {
            module_name: module_name.into(),
            input_json: None,
            input_files: Vec::new(),
            limits: None,
            keep_workspace: false,
            entrypoint: WasmEntrypoint::Start,
            session_id: None,
        }
    }

    pub fn with_input_json(mut self, value: Value) -> Self {
        self.input_json = Some(value);
        self
    }

    pub fn with_session_id(mut self, session_id: impl Into<String>) -> Self {
        self.session_id = Some(session_id.into());
        self
    }
}

/// Guest entrypoint strategy.
#[derive(Debug, Clone)]
pub enum WasmEntrypoint {
    /// Call the module's `_start` export (standard WASI command).
    Start,
    /// Call a named exported function that takes and returns no
    /// parameters. Used by simple utility modules that are not full WASI
    /// commands.
    NamedVoid(String),
}

/// Structured result produced by a WASM call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WasmRunResult {
    pub module: String,
    pub stdout: String,
    pub stderr: String,
    pub duration_ms: u128,
    pub output_json: Option<Value>,
    pub output_files: Vec<WasmOutputArtifact>,
    /// If `keep_workspace` was set, this is the scratch directory on the
    /// host. Otherwise `None`.
    pub scratch_dir: Option<PathBuf>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WasmOutputArtifact {
    pub name: String,
    pub bytes: usize,
}

/// Typed errors returned by the WASM runtime.
#[derive(Debug)]
pub enum WasmRunError {
    /// The module name did not resolve in the registry.
    UnknownModule(String),
    /// Compilation or bytecode loading failed.
    ModuleLoad(String),
    /// Host-side I/O error preparing or tearing down the scratch dir.
    Io(String),
    /// Guest execution trapped or exceeded a limit.
    Execution(String),
    /// Wall-clock deadline exceeded before the guest returned.
    Timeout(Duration),
    /// Fuel limit exhausted before the guest returned.
    OutOfFuel,
    /// Linear memory limit exceeded.
    MemoryLimit(usize),
}

impl std::fmt::Display for WasmRunError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            WasmRunError::UnknownModule(name) => {
                write!(f, "unknown WASM module '{}'", name)
            }
            WasmRunError::ModuleLoad(detail) => {
                write!(f, "failed to load WASM module: {}", detail)
            }
            WasmRunError::Io(detail) => write!(f, "WASM runtime I/O error: {}", detail),
            WasmRunError::Execution(detail) => {
                write!(f, "WASM guest execution failed: {}", detail)
            }
            WasmRunError::Timeout(duration) => {
                write!(f, "WASM call exceeded wall timeout {:?}", duration)
            }
            WasmRunError::OutOfFuel => write!(f, "WASM call exhausted fuel budget"),
            WasmRunError::MemoryLimit(limit) => {
                write!(f, "WASM call exceeded memory limit {} bytes", limit)
            }
        }
    }
}

impl std::error::Error for WasmRunError {}

impl From<io::Error> for WasmRunError {
    fn from(error: io::Error) -> Self {
        WasmRunError::Io(error.to_string())
    }
}

/// The desktop WASM runtime. A single instance owns a shared wasmtime
/// engine and the module registry; it is cheap to clone via `Arc`.
pub struct WasmRuntime {
    engine: Engine,
    registry: ModuleRegistry,
    scratch_root: Mutex<Option<PathBuf>>,
}

impl WasmRuntime {
    /// Construct a new runtime with sensible defaults and register the
    /// built-in WASM modules that ship with the desktop app.
    pub fn new() -> Result<Self, WasmRunError> {
        let mut config = Config::new();
        config.consume_fuel(true);
        config.epoch_interruption(true);
        config.wasm_backtrace(true);
        config.wasm_bulk_memory(true);
        config.wasm_multi_value(true);
        let engine = Engine::new(&config)
            .map_err(|error| WasmRunError::ModuleLoad(error.to_string()))?;
        let runtime = Self {
            engine,
            registry: ModuleRegistry::new(),
            scratch_root: Mutex::new(None),
        };
        runtime.register_builtin_modules();
        Ok(runtime)
    }

    /// Register every WASM module that is bundled into the desktop
    /// binary via `include_bytes!`. Called from [`Self::new`]; callers
    /// should not need to invoke this directly.
    ///
    /// Built-in modules are keyed by their skill-contract name (the same
    /// string that appears in each skill's frontmatter `wasm_module`
    /// field). Skills look up their module by this name when dispatching
    /// a call through `desktop_skill_run`.
    fn register_builtin_modules(&self) {
        const PDF_PROCESSOR: &[u8] = include_bytes!("modules/pdf_processor.wasm");
        const DOCX_PROCESSOR: &[u8] = include_bytes!("modules/docx_processor.wasm");
        const XLSX_PROCESSOR: &[u8] = include_bytes!("modules/xlsx_processor.wasm");
        const PPTX_PROCESSOR: &[u8] = include_bytes!("modules/pptx_processor.wasm");
        self.registry
            .register_bytes("pdf_processor", PDF_PROCESSOR.to_vec());
        self.registry
            .register_bytes("docx_processor", DOCX_PROCESSOR.to_vec());
        self.registry
            .register_bytes("xlsx_processor", XLSX_PROCESSOR.to_vec());
        self.registry
            .register_bytes("pptx_processor", PPTX_PROCESSOR.to_vec());

        // Dev-only freshness checks. Warning output is opt-in via
        // II_AGENT_WASM_FRESHNESS_WARN to avoid noisy logs during normal
        // desktop development.
        #[cfg(debug_assertions)]
        {
            let base = concat!(env!("CARGO_MANIFEST_DIR"), "/src/cowork/desktop_runtime/wasm");
            freshness::check_freshness(
                "pdf_processor",
                &format!("{base}/modules/pdf_processor.wasm"),
                &format!("{base}/guest/pdf_processor/src"),
            );
            freshness::check_freshness(
                "docx_processor",
                &format!("{base}/modules/docx_processor.wasm"),
                &format!("{base}/guest/docx_processor/src"),
            );
            freshness::check_freshness(
                "xlsx_processor",
                &format!("{base}/modules/xlsx_processor.wasm"),
                &format!("{base}/guest/xlsx_processor/src"),
            );
            freshness::check_freshness(
                "pptx_processor",
                &format!("{base}/modules/pptx_processor.wasm"),
                &format!("{base}/guest/pptx_processor/src"),
            );
        }
    }

    pub const KIND: RuntimeKind = RuntimeKind::Wasm;

    /// Borrow the module registry so callers can register application
    /// assets at startup.
    pub fn registry(&self) -> &ModuleRegistry {
        &self.registry
    }

    /// Configure the root directory used to create per-call scratch
    /// workspaces. Typically `{app_data}/cowork/wasm-scratch`.
    pub fn set_scratch_root(&self, root: PathBuf) {
        *self.scratch_root.lock().expect("scratch root poisoned") = Some(root);
    }

    /// Execute a single WASM call and return a structured result.
    pub fn run(&self, request: WasmRunRequest) -> Result<WasmRunResult, WasmRunError> {
        let limits = request.limits.unwrap_or_else(RuntimeLimits::defaults);

        // --- Prepare scratch workspace ---
        let scratch_dir = self.build_scratch_dir(request.session_id.as_deref())?;
        let inputs_dir = scratch_dir.join("inputs");
        let outputs_dir = scratch_dir.join("outputs");
        fs::create_dir_all(&inputs_dir)?;
        fs::create_dir_all(&outputs_dir)?;

        if let Some(input_json) = request.input_json.as_ref() {
            let serialised = serde_json::to_vec_pretty(input_json)
                .map_err(|error| WasmRunError::Io(error.to_string()))?;
            fs::write(scratch_dir.join("input.json"), serialised)?;
        }

        for (source_path, logical_name) in &request.input_files {
            // Resolve symlinks before copying so a symlink pointing
            // outside the desktop scope cannot smuggle host files into
            // the sandbox.
            let canonical = fs::canonicalize(source_path).map_err(|error| {
                WasmRunError::Io(format!(
                    "failed to resolve input file {}: {}",
                    source_path.display(),
                    error
                ))
            })?;
            let destination = inputs_dir.join(logical_name);
            if let Some(parent) = destination.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(&canonical, &destination).map_err(|error| {
                WasmRunError::Io(format!(
                    "failed to copy input file {} to scratch: {}",
                    canonical.display(),
                    error
                ))
            })?;
        }

        // --- Load module ---
        let module = self.registry.load_module(&self.engine, &request.module_name)?;

        // --- Build WASI context ---
        let stdout_pipe = wasmtime_wasi::pipe::MemoryOutputPipe::new(256 * 1024);
        let stderr_pipe = wasmtime_wasi::pipe::MemoryOutputPipe::new(256 * 1024);

        let wasi = WasiCtxBuilder::new()
            .stdout(stdout_pipe.clone())
            .stderr(stderr_pipe.clone())
            .preopened_dir(
                &scratch_dir,
                "/workspace",
                DirPerms::all(),
                FilePerms::all(),
            )
            .map_err(|error| WasmRunError::Io(error.to_string()))?
            .build_p1();

        let store_limits = StoreLimitsBuilder::new()
            .memory_size(limits.max_memory_bytes)
            .build();

        let host_state = HostState {
            wasi,
            limits: store_limits,
            memory_tripped: false,
        };

        let mut store = Store::new(&self.engine, host_state);
        store
            .set_fuel(limits.max_fuel)
            .map_err(|error| WasmRunError::Execution(error.to_string()))?;
        store.limiter(|state| &mut state.limits);
        store.set_epoch_deadline(1);

        // --- Instantiate + link WASI ---
        let mut linker: Linker<HostState> = Linker::new(&self.engine);
        wasi_preview1::add_to_linker_sync(&mut linker, |state| &mut state.wasi)
            .map_err(|error| WasmRunError::Execution(error.to_string()))?;

        let start_time = Instant::now();
        let epoch_handle = EpochDeadlineHandle::new(&self.engine, limits.wall_timeout);

        let run_outcome: Result<(), wasmtime::Error> = (|| {
            let instance = linker.instantiate(&mut store, &module)?;
            match &request.entrypoint {
                WasmEntrypoint::Start => {
                    if let Some(start) = instance.get_func(&mut store, "_start") {
                        let typed = start.typed::<(), ()>(&store)?;
                        typed.call(&mut store, ())?;
                    } else {
                        return Err(wasmtime::Error::msg(
                            "module has no '_start' export; set a NamedVoid entrypoint",
                        ));
                    }
                }
                WasmEntrypoint::NamedVoid(name) => {
                    let func = instance
                        .get_func(&mut store, name.as_str())
                        .ok_or_else(|| {
                            wasmtime::Error::msg(format!(
                                "module has no exported function '{}'",
                                name
                            ))
                        })?;
                    let typed = func.typed::<(), ()>(&store)?;
                    typed.call(&mut store, ())?;
                }
            }
            Ok(())
        })();

        drop(epoch_handle);

        let duration = start_time.elapsed();

        if let Err(error) = run_outcome {
            let message = format!("{error:?}");
            // Classify the error into a friendlier variant when possible.
            if message.contains("epoch deadline") {
                return Err(WasmRunError::Timeout(limits.wall_timeout));
            }
            if message.contains("all fuel consumed") {
                return Err(WasmRunError::OutOfFuel);
            }
            if store.data().memory_tripped {
                return Err(WasmRunError::MemoryLimit(limits.max_memory_bytes));
            }
            // Graceful WASI exit(0) also surfaces as an error here.
            if message.contains("Exited with i32 exit status 0") {
                // fall through to success path below
            } else if !message.contains("Exited with i32 exit status 0") {
                return Err(WasmRunError::Execution(message));
            }
        }

        // --- Collect outputs ---
        let stdout_bytes = stdout_pipe.contents();
        let stderr_bytes = stderr_pipe.contents();
        let stdout_text = String::from_utf8_lossy(&stdout_bytes).into_owned();
        let stderr_text = String::from_utf8_lossy(&stderr_bytes).into_owned();

        let output_json = {
            let output_path = scratch_dir.join("output.json");
            if output_path.exists() {
                let bytes = fs::read(&output_path)?;
                match serde_json::from_slice::<Value>(&bytes) {
                    Ok(value) => Some(value),
                    Err(_) => None,
                }
            } else {
                None
            }
        };

        let output_files = collect_output_artifacts(&outputs_dir)?;

        let result = WasmRunResult {
            module: request.module_name.clone(),
            stdout: stdout_text,
            stderr: stderr_text,
            duration_ms: duration.as_millis(),
            output_json,
            output_files,
            scratch_dir: if request.keep_workspace {
                Some(scratch_dir.clone())
            } else {
                None
            },
        };

        if !request.keep_workspace {
            let _ = fs::remove_dir_all(&scratch_dir);
        }

        Ok(result)
    }

    fn build_scratch_dir(&self, session_id: Option<&str>) -> Result<PathBuf, WasmRunError> {
        let base = match self.scratch_root.lock().expect("scratch root poisoned").clone() {
            Some(root) => root,
            None => std::env::temp_dir().join("ii-cowork-wasm"),
        };
        let scoped = match session_id {
            Some(session_id) => base.join(sanitize_session_segment(session_id)),
            None => base,
        };
        fs::create_dir_all(&scoped)?;
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or_default();
        // Random suffix prevents collision when two calls happen in
        // the same nanosecond (unlikely but possible under load).
        let rand_suffix: u32 = (nanos as u32).wrapping_mul(2654435761);
        let subdir = scoped.join(format!("call-{nanos}-{rand_suffix:08x}"));
        fs::create_dir_all(&subdir)?;
        Ok(subdir)
    }

    /// Remove every scratch directory belonging to a given session.
    ///
    /// Called by the cowork session gateway when a session is closed or
    /// deleted. Silently succeeds if the session has no scratch state.
    pub fn sweep_session(&self, session_id: &str) -> Result<(), WasmRunError> {
        let Some(base) = self.scratch_root.lock().expect("scratch root poisoned").clone() else {
            return Ok(());
        };
        let scoped = base.join(sanitize_session_segment(session_id));
        if scoped.exists() {
            fs::remove_dir_all(&scoped)?;
        }
        Ok(())
    }

    /// Remove the entire scratch root. Called at desktop app startup so
    /// leftover artifacts from previous runs do not accumulate.
    pub fn sweep_all(&self) -> Result<(), WasmRunError> {
        let Some(base) = self.scratch_root.lock().expect("scratch root poisoned").clone() else {
            return Ok(());
        };
        if base.exists() {
            fs::remove_dir_all(&base)?;
        }
        fs::create_dir_all(&base)?;
        Ok(())
    }
}

/// Sanitise a cowork session identifier so it is safe to use as a
/// directory name. Anything that is not alphanumeric, `-`, `_`, or `.` is
/// replaced with `_`.
fn sanitize_session_segment(session_id: &str) -> String {
    session_id
        .chars()
        .map(|c| match c {
            'a'..='z' | 'A'..='Z' | '0'..='9' | '-' | '_' | '.' => c,
            _ => '_',
        })
        .collect()
}

/// Shared host state available to wasmtime callbacks.
struct HostState {
    wasi: WasiP1Ctx,
    limits: StoreLimits,
    memory_tripped: bool,
}

fn collect_output_artifacts(outputs_dir: &Path) -> Result<Vec<WasmOutputArtifact>, WasmRunError> {
    if !outputs_dir.exists() {
        return Ok(Vec::new());
    }
    let mut artifacts = Vec::new();
    for entry in fs::read_dir(outputs_dir)? {
        let entry = entry?;
        let metadata = entry.metadata()?;
        if metadata.is_file() {
            artifacts.push(WasmOutputArtifact {
                name: entry.file_name().to_string_lossy().into_owned(),
                bytes: metadata.len() as usize,
            });
        }
    }
    artifacts.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(artifacts)
}

/// Background thread that bumps the wasmtime engine epoch after the wall
/// deadline so the guest is interrupted even when fuel is not being
/// consumed.
struct EpochDeadlineHandle {
    shutdown: Arc<Mutex<bool>>,
    thread: Option<thread::JoinHandle<()>>,
}

impl EpochDeadlineHandle {
    fn new(engine: &Engine, deadline: Duration) -> Self {
        let shutdown = Arc::new(Mutex::new(false));
        let shutdown_clone = Arc::clone(&shutdown);
        let engine = engine.clone();
        let thread = thread::spawn(move || {
            let start = Instant::now();
            while start.elapsed() < deadline {
                if *shutdown_clone.lock().expect("shutdown poisoned") {
                    return;
                }
                thread::sleep(Duration::from_millis(25));
            }
            engine.increment_epoch();
        });
        Self {
            shutdown,
            thread: Some(thread),
        }
    }
}

impl Drop for EpochDeadlineHandle {
    fn drop(&mut self) {
        *self.shutdown.lock().expect("shutdown poisoned") = true;
        if let Some(handle) = self.thread.take() {
            let _ = handle.join();
        }
    }
}

// Global runtime access is provided by [`lifecycle::acquire_runtime`].
// It replaces an earlier `global()` helper that held the engine alive
// forever. The lifecycle module manages lazy creation, in-flight
// counting, and idle drop.

#[cfg(test)]
mod tests {
    use super::*;

    const HELLO_WAT: &str = r#"
        (module
          (import "wasi_snapshot_preview1" "fd_write"
            (func $fd_write (param i32 i32 i32 i32) (result i32)))
          (memory (export "memory") 1)
          (data (i32.const 8) "hello wasm\n")
          (func $main (export "_start")
            (i32.store (i32.const 0) (i32.const 8))
            (i32.store (i32.const 4) (i32.const 11))
            (call $fd_write (i32.const 1) (i32.const 0) (i32.const 1) (i32.const 20))
            drop)
        )
    "#;

    #[test]
    fn runtime_runs_embedded_wat_module() {
        let runtime = WasmRuntime::new().expect("runtime construction");
        runtime.registry().register_wat("hello", HELLO_WAT);
        assert!(runtime.registry().has("hello"));

        let request = WasmRunRequest::new("hello");
        let result = runtime.run(request).expect("hello module runs");
        assert_eq!(result.module, "hello");
        assert!(
            result.stdout.contains("hello wasm"),
            "expected hello wasm in stdout, got {:?}",
            result.stdout
        );
        assert!(result.scratch_dir.is_none());
    }

    #[test]
    fn runtime_reports_unknown_module() {
        let runtime = WasmRuntime::new().expect("runtime construction");
        let err = runtime
            .run(WasmRunRequest::new("does-not-exist"))
            .unwrap_err();
        match err {
            WasmRunError::UnknownModule(name) => assert_eq!(name, "does-not-exist"),
            other => panic!("expected UnknownModule, got {other:?}"),
        }
    }

    #[test]
    fn runtime_reports_module_list() {
        let runtime = WasmRuntime::new().expect("runtime construction");
        runtime.registry().register_wat("test_b", HELLO_WAT);
        runtime.registry().register_wat("test_a", HELLO_WAT);
        let names = runtime.registry().names();
        assert!(names.contains(&"test_a".to_string()));
        assert!(names.contains(&"test_b".to_string()));
        // Built-in modules like pdf_processor are registered by
        // `WasmRuntime::new()` via `include_bytes!`, so the list
        // contains them too. We only assert the test-registered names
        // made it in, not the exact shape of the list.
    }

    #[test]
    fn session_id_scopes_scratch_dir() {
        let runtime = WasmRuntime::new().expect("runtime construction");
        runtime.registry().register_wat("hello", HELLO_WAT);

        let root = std::env::temp_dir().join(format!(
            "ii-cowork-wasm-lifecycle-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        ));
        runtime.set_scratch_root(root.clone());

        let request = WasmRunRequest::new("hello")
            .with_session_id("session-xyz")
            .with_input_json(serde_json::json!({"hello": "world"}));
        let result = runtime
            .run(WasmRunRequest {
                keep_workspace: true,
                ..request
            })
            .expect("runs");

        let scratch = result.scratch_dir.expect("kept scratch");
        assert!(
            scratch.starts_with(root.join("session-xyz")),
            "scratch dir {:?} should live under the session-scoped root",
            scratch
        );

        runtime
            .sweep_session("session-xyz")
            .expect("session sweep succeeds");
        assert!(!root.join("session-xyz").exists());

        runtime.sweep_all().expect("sweep all succeeds");
        assert!(root.exists(), "sweep_all recreates the empty root");

        let _ = std::fs::remove_dir_all(&root);
    }

    /// End-to-end: boot the real runtime (which auto-registers
    /// pdf_processor.wasm via `include_bytes!`), prepare a real PDF input,
    /// run the module, and assert the guest produced a structured
    /// `output.json` with extracted text.
    ///
    /// This is the canonical proof that the full sandbox pipeline works:
    /// Rust→wasm32-wasip1 module loaded → WASI preopen → guest reads
    /// `/workspace/inputs/input.pdf` → lopdf parses → writes
    /// `/workspace/output.json` → host reads and returns structured
    /// result.
    #[test]
    fn pdf_processor_extract_text_end_to_end() {
        const HELLO_PDF: &[u8] = include_bytes!("../../../../tests/fixtures/hello.pdf");

        let runtime = WasmRuntime::new().expect("runtime construction");
        assert!(
            runtime.registry().has("pdf_processor"),
            "pdf_processor module should be auto-registered via include_bytes!"
        );

        // Stage the input PDF on the host side so we can pass it as an
        // input file to the runtime (the runtime copies it into the
        // sandbox's /workspace/inputs/ dir).
        let stage_dir = std::env::temp_dir().join(format!(
            "pdf-extract-stage-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        ));
        std::fs::create_dir_all(&stage_dir).unwrap();
        let pdf_path = stage_dir.join("hello.pdf");
        std::fs::write(&pdf_path, HELLO_PDF).unwrap();

        let request = WasmRunRequest::new("pdf_processor")
            .with_session_id("pdf-e2e-test")
            .with_input_json(serde_json::json!({ "op": "extract_text" }));
        let request = WasmRunRequest {
            input_files: vec![(pdf_path.clone(), "input.pdf".to_string())],
            ..request
        };

        let result = runtime.run(request).expect("pdf_processor runs");

        assert_eq!(result.module, "pdf_processor");
        assert!(
            result.stdout.contains("pdf_processor: op=extract_text ok"),
            "expected stdout success line, got: {:?}",
            result.stdout
        );

        let output = result
            .output_json
            .as_ref()
            .expect("pdf_processor should write /workspace/output.json");
        let pages = output
            .get("pages")
            .and_then(|value| value.as_array())
            .expect("output.json.pages must be an array");
        assert!(!pages.is_empty(), "pages must not be empty");
        let joined: String = pages
            .iter()
            .filter_map(|page| page.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        assert!(
            joined.contains("Hello Desktop Skill"),
            "extracted text should contain the fixture phrase, got: {joined:?}"
        );

        std::fs::remove_dir_all(&stage_dir).ok();
    }

    /// End-to-end with `page_range`: we hand the guest a 1-page fixture
    /// PDF but ask for `[1, 1]` explicitly, and verify it honours the
    /// range plus reports `page_offset`/`total_pages`. This is the
    /// smoking gun that our rebuilt `pdf_processor.wasm` picks up the
    /// new input contract — the chunking dispatcher relies on this
    /// contract for correctness.
    #[test]
    fn pdf_processor_respects_page_range() {
        const HELLO_PDF: &[u8] = include_bytes!("../../../../tests/fixtures/hello.pdf");

        let runtime = WasmRuntime::new().expect("runtime construction");
        let stage_dir = std::env::temp_dir().join(format!(
            "pdf-page-range-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        ));
        std::fs::create_dir_all(&stage_dir).unwrap();
        let pdf_path = stage_dir.join("hello.pdf");
        std::fs::write(&pdf_path, HELLO_PDF).unwrap();

        // In-range: ask for pages 1-1, expect 1 page with the fixture text.
        let in_range = WasmRunRequest {
            input_files: vec![(pdf_path.clone(), "input.pdf".to_string())],
            ..WasmRunRequest::new("pdf_processor")
                .with_session_id("pdf-range-in")
                .with_input_json(serde_json::json!({
                    "op": "extract_text",
                    "page_range": [1, 1]
                }))
        };
        let result = runtime.run(in_range).expect("pdf_processor runs");
        let output = result.output_json.expect("output.json");
        let pages = output
            .get("pages")
            .and_then(|v| v.as_array())
            .expect("pages array");
        assert_eq!(pages.len(), 1, "expected exactly 1 page in slice");
        assert_eq!(output.get("page_offset").and_then(|v| v.as_u64()), Some(1));
        assert_eq!(output.get("total_pages").and_then(|v| v.as_u64()), Some(1));

        // Out-of-range: ask for pages 10-20 on a 1-page doc, expect
        // empty pages array and no error (guest clamps).
        let out_of_range = WasmRunRequest {
            input_files: vec![(pdf_path.clone(), "input.pdf".to_string())],
            ..WasmRunRequest::new("pdf_processor")
                .with_session_id("pdf-range-out")
                .with_input_json(serde_json::json!({
                    "op": "extract_text",
                    "page_range": [10, 20]
                }))
        };
        let result2 = runtime.run(out_of_range).expect("pdf_processor runs out-of-range");
        let output2 = result2.output_json.expect("output.json");
        let pages2 = output2
            .get("pages")
            .and_then(|v| v.as_array())
            .expect("pages array");
        assert!(
            pages2.is_empty(),
            "out-of-range should produce empty pages, got {} pages",
            pages2.len()
        );

        std::fs::remove_dir_all(&stage_dir).ok();
    }

    #[test]
    fn docx_processor_extract_text_end_to_end() {
        const HELLO_DOCX: &[u8] = include_bytes!("../../../../tests/fixtures/hello.docx");
        let runtime = WasmRuntime::new().expect("runtime");
        let stage = stage_file(HELLO_DOCX, "hello.docx");
        let request = WasmRunRequest {
            input_files: vec![(stage.join("hello.docx"), "input.docx".to_string())],
            ..WasmRunRequest::new("docx_processor")
                .with_session_id("docx-e2e")
                .with_input_json(serde_json::json!({"op": "extract_text"}))
        };
        let result = runtime.run(request).expect("docx_processor runs");
        let output = result.output_json.expect("output.json");
        let paragraphs = output.get("paragraphs").and_then(|v| v.as_array()).expect("paragraphs");
        assert!(!paragraphs.is_empty());
        let joined: String = paragraphs.iter().filter_map(|p| p.as_str()).collect::<Vec<_>>().join(" ");
        assert!(joined.contains("Hello Desktop Skill Docx"), "got: {joined:?}");
        std::fs::remove_dir_all(&stage).ok();
    }

    #[test]
    fn xlsx_processor_list_sheets_end_to_end() {
        const HELLO_XLSX: &[u8] = include_bytes!("../../../../tests/fixtures/hello.xlsx");
        let runtime = WasmRuntime::new().expect("runtime");
        let stage = stage_file(HELLO_XLSX, "hello.xlsx");
        let request = WasmRunRequest {
            input_files: vec![(stage.join("hello.xlsx"), "input.xlsx".to_string())],
            ..WasmRunRequest::new("xlsx_processor")
                .with_session_id("xlsx-e2e")
                .with_input_json(serde_json::json!({"op": "list_sheets"}))
        };
        let result = runtime.run(request).expect("xlsx_processor runs");
        let output = result.output_json.expect("output.json");
        let sheets = output.get("sheets").and_then(|v| v.as_array()).expect("sheets");
        assert!(!sheets.is_empty());
        let first_name = sheets[0].get("name").and_then(|v| v.as_str()).unwrap_or("");
        assert_eq!(first_name, "TestSheet");
        std::fs::remove_dir_all(&stage).ok();
    }

    #[test]
    fn xlsx_processor_read_sheet_end_to_end() {
        const HELLO_XLSX: &[u8] = include_bytes!("../../../../tests/fixtures/hello.xlsx");
        let runtime = WasmRuntime::new().expect("runtime");
        let stage = stage_file(HELLO_XLSX, "hello.xlsx");
        let request = WasmRunRequest {
            input_files: vec![(stage.join("hello.xlsx"), "input.xlsx".to_string())],
            ..WasmRunRequest::new("xlsx_processor")
                .with_session_id("xlsx-read-e2e")
                .with_input_json(serde_json::json!({"op": "read_sheet", "sheet": "TestSheet"}))
        };
        let result = runtime.run(request).expect("xlsx_processor runs");
        let output = result.output_json.expect("output.json");
        let rows = output.get("rows").and_then(|v| v.as_array()).expect("rows");
        assert_eq!(rows.len(), 2);
        // Row 1: ["Hello", "Desktop"]
        let row1 = rows[0].as_array().expect("row1");
        assert_eq!(row1[0].as_str(), Some("Hello"));
        assert_eq!(row1[1].as_str(), Some("Desktop"));
        std::fs::remove_dir_all(&stage).ok();
    }

    #[test]
    fn pptx_processor_extract_text_end_to_end() {
        const HELLO_PPTX: &[u8] = include_bytes!("../../../../tests/fixtures/hello.pptx");
        let runtime = WasmRuntime::new().expect("runtime");
        let stage = stage_file(HELLO_PPTX, "hello.pptx");
        let request = WasmRunRequest {
            input_files: vec![(stage.join("hello.pptx"), "input.pptx".to_string())],
            ..WasmRunRequest::new("pptx_processor")
                .with_session_id("pptx-e2e")
                .with_input_json(serde_json::json!({"op": "extract_text"}))
        };
        let result = runtime.run(request).expect("pptx_processor runs");
        let output = result.output_json.expect("output.json");
        let slides = output.get("slides").and_then(|v| v.as_array()).expect("slides");
        assert!(!slides.is_empty());
        let text = slides[0].get("text").and_then(|v| v.as_str()).unwrap_or("");
        assert!(text.contains("Hello Desktop Skill Pptx"), "got: {text:?}");
        std::fs::remove_dir_all(&stage).ok();
    }

    /// Helper: write fixture bytes to a temp dir so tests can pass them
    /// as input_files to the runtime.
    fn stage_file(bytes: &[u8], filename: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "e2e-{}-{}",
            filename,
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join(filename), bytes).unwrap();
        dir
    }

    /// Verifies that the skill registry resolves the pdf skill to the
    /// pdf_processor module name, and that the runtime registry agrees.
    /// This is the "match" step desktop_skill_run performs before
    /// calling into the runtime.
    #[test]
    fn pdf_skill_resolves_to_registered_module() {
        use crate::cowork::desktop_skills::find_builtin_skill;

        let skill = find_builtin_skill("pdf").expect("pdf skill registered");
        let module_name = skill.wasm_module().expect("pdf skill declares wasm_module");
        assert_eq!(module_name, "pdf_processor");

        let runtime = WasmRuntime::new().expect("runtime construction");
        assert!(
            runtime.registry().has(module_name),
            "pdf skill's wasm_module should be registered in the runtime"
        );
    }

    #[test]
    fn sanitise_session_segment_is_filesystem_safe() {
        // `.`, `-`, `_`, and alphanumerics pass through unchanged.
        assert_eq!(sanitize_session_segment("abc_123-x.y"), "abc_123-x.y");
        // Path separators and backslashes collapse to `_`. Parent-dir
        // dots are preserved as dots (they are harmless inside a single
        // segment).
        assert_eq!(
            sanitize_session_segment("../../etc/passwd"),
            ".._.._etc_passwd"
        );
        assert_eq!(sanitize_session_segment("a/b\\c"), "a_b_c");
    }
}
