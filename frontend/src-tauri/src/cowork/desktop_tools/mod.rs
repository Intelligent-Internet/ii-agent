mod apply_patch;
mod bash;
mod edit;
mod glob;
mod grep;
mod list_dir;
mod read;
mod todo_write;
mod wasm_run;
mod write;

use crate::cowork::agent_presets::shared::DesktopToolCapability;
use crate::cowork::desktop_runtime::wasm::{WasmRunError, WasmRunResult};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::AppHandle;

pub const TOOL_BASH: &str = "Bash";
pub const TOOL_READ: &str = "Read";
pub const TOOL_WRITE: &str = "Write";
pub const TOOL_EDIT: &str = "Edit";
pub const TOOL_APPLY_PATCH: &str = "apply_patch";
pub const TOOL_TODO_WRITE: &str = "TodoWrite";
pub const TOOL_GLOB: &str = "glob";
pub const TOOL_GREP: &str = "grep";
pub const TOOL_LIST_DIR: &str = "list_dir";
pub const TOOL_WASM_RUN: &str = "wasm_run";

pub type DesktopToolExecuteFn =
    for<'a> fn(&mut DesktopToolContext<'a>, &Value) -> Result<String, String>;
pub type DesktopExecutionScopeLoaderFn =
    fn(&AppHandle, &str) -> Result<DesktopExecutionScope, String>;
pub type DesktopExecutionScopeRefreshFn =
    fn(&AppHandle, &str, &DesktopExecutionScope) -> Result<(), String>;

#[derive(Clone)]
pub struct DesktopTool {
    capability: DesktopToolCapability,
    execute: DesktopToolExecuteFn,
    refreshes_scope: bool,
}

impl DesktopTool {
    pub fn new(
        capability: DesktopToolCapability,
        execute: DesktopToolExecuteFn,
        refreshes_scope: bool,
    ) -> Self {
        Self {
            capability,
            execute,
            refreshes_scope,
        }
    }

    pub fn name(&self) -> &str {
        self.capability.name.as_str()
    }

    pub fn display_name(&self) -> &str {
        self.capability.display_name.as_str()
    }

    pub fn aliases(&self) -> &[String] {
        self.capability.aliases.as_slice()
    }

    pub fn into_capability(self) -> DesktopToolCapability {
        self.capability
    }

    pub fn refreshes_scope(&self) -> bool {
        self.refreshes_scope
    }

    pub fn execute(
        &self,
        ctx: &mut DesktopToolContext<'_>,
        input: &Value,
    ) -> Result<String, String> {
        (self.execute)(ctx, input)
    }

    pub fn with_aliases(mut self, aliases: &[&str]) -> Self {
        self.capability.aliases = aliases.iter().map(|value| value.to_string()).collect();
        self
    }
}

#[derive(Default)]
pub struct DesktopToolRuntime {
    bash_sessions: HashMap<String, DesktopBashSession>,
    todos: Option<Value>,
}

#[derive(Clone, Default)]
pub(crate) struct DesktopBashSession {
    pub(crate) last_output: String,
    pub(crate) last_exit_code: Option<i32>,
}

pub struct DesktopExecutionScope {
    canonical_root: PathBuf,
}

pub struct DesktopToolContext<'a> {
    app: &'a AppHandle,
    local_session_id: &'a str,
    execution_scope: &'a DesktopExecutionScope,
    runtime: &'a mut DesktopToolRuntime,
    refresh_scope: Option<DesktopExecutionScopeRefreshFn>,
}

impl<'a> DesktopToolContext<'a> {
    pub fn new(
        app: &'a AppHandle,
        local_session_id: &'a str,
        execution_scope: &'a DesktopExecutionScope,
        runtime: &'a mut DesktopToolRuntime,
        refresh_scope: Option<DesktopExecutionScopeRefreshFn>,
    ) -> Self {
        Self {
            app,
            local_session_id,
            execution_scope,
            runtime,
            refresh_scope,
        }
    }

    pub fn working_directory(&self) -> &Path {
        &self.execution_scope.canonical_root
    }

    pub fn local_session_id(&self) -> &str {
        self.local_session_id
    }

    pub fn app_handle(&self) -> &AppHandle {
        self.app
    }

    pub fn resolve_scoped_path(
        &self,
        file_path: &str,
        allow_missing: bool,
    ) -> Result<PathBuf, String> {
        resolve_scoped_path(self.execution_scope, file_path, allow_missing)
    }

    pub fn refresh_scope_snapshot(&self) -> Result<(), String> {
        match self.refresh_scope {
            Some(refresh_scope) => {
                refresh_scope(self.app, self.local_session_id, self.execution_scope)
            }
            None => Ok(()),
        }
    }

    pub(crate) fn bash_sessions(&self) -> &HashMap<String, DesktopBashSession> {
        &self.runtime.bash_sessions
    }

    pub(crate) fn bash_sessions_mut(&mut self) -> &mut HashMap<String, DesktopBashSession> {
        &mut self.runtime.bash_sessions
    }

    pub(crate) fn set_todos(&mut self, todos: Value) {
        self.runtime.todos = Some(todos);
    }
}

impl DesktopExecutionScope {
    pub fn new(canonical_root: PathBuf) -> Self {
        Self { canonical_root }
    }
}

pub fn common_desktop_tools() -> Vec<DesktopTool> {
    vec![
        bash::desktop_tool(),
        list_dir::desktop_tool(),
        glob::desktop_tool(),
        grep::desktop_tool(),
        read::desktop_tool(),
        write::desktop_tool(),
        edit::desktop_tool(),
        apply_patch::desktop_tool(),
        todo_write::desktop_tool(),
        // desktop_skill_run lives under desktop_skills/ because its job is
        // to surface skill guidance, not to drive the host filesystem.
        // It still appears in the common tool list so every cowork mode
        // that ships desktop tools automatically advertises it.
        crate::cowork::desktop_skills::desktop_skill_run::desktop_tool(),
        wasm_run::desktop_tool(),
    ]
}

pub fn common_desktop_tool_capabilities() -> Vec<DesktopToolCapability> {
    common_desktop_tools()
        .into_iter()
        .map(DesktopTool::into_capability)
        .collect()
}

pub fn common_desktop_tool_names() -> Vec<String> {
    common_desktop_tool_capabilities()
        .into_iter()
        .map(|tool| tool.name)
        .collect()
}

pub fn find_desktop_tool<'a>(tools: &'a [DesktopTool], tool_name: &str) -> Option<&'a DesktopTool> {
    let normalized = tool_name.trim().to_lowercase();
    tools.iter().find(|tool| {
        tool.name().eq_ignore_ascii_case(&normalized)
            || tool
                .aliases()
                .iter()
                .any(|alias| alias.eq_ignore_ascii_case(&normalized))
    })
}

pub fn resolve_desktop_tool_name(tool_name: &str) -> Option<String> {
    let normalized = tool_name.trim().to_lowercase();
    if normalized.is_empty() {
        return None;
    }

    common_desktop_tools().into_iter().find_map(|tool| {
        if tool.name().eq_ignore_ascii_case(&normalized)
            || tool
                .aliases()
                .iter()
                .any(|alias| alias.eq_ignore_ascii_case(&normalized))
        {
            Some(tool.name().to_string())
        } else {
            None
        }
    })
}

/// Shared formatter for desktop tools that invoke the WASM runtime.
///
/// This stays in the desktop tool layer because it renders the
/// user-facing tool result string, not the runtime's execution contract.
pub(super) fn format_wasm_result(result: &WasmRunResult) -> String {
    let mut sections = Vec::new();
    sections.push(format!(
        "module: {}\nduration_ms: {}",
        result.module, result.duration_ms
    ));
    if !result.stdout.trim().is_empty() {
        sections.push(format!("stdout:\n{}", result.stdout.trim_end()));
    }
    if !result.stderr.trim().is_empty() {
        sections.push(format!("stderr:\n{}", result.stderr.trim_end()));
    }
    if let Some(output_json) = &result.output_json {
        if let Ok(pretty) = serde_json::to_string_pretty(output_json) {
            sections.push(format!("output.json:\n{}", pretty));
        }
    }
    if !result.output_files.is_empty() {
        let listing = result
            .output_files
            .iter()
            .map(|file| format!("- {} ({} bytes)", file.name, file.bytes))
            .collect::<Vec<_>>()
            .join("\n");
        sections.push(format!("output_files:\n{}", listing));
    }
    if let Some(scratch) = &result.scratch_dir {
        sections.push(format!("scratch_dir: {}", scratch.display()));
    }
    sections.join("\n\n")
}

/// Shared formatter for human-readable WASM tool errors.
pub(super) fn format_wasm_error(tool: &str, module: &str, error: WasmRunError) -> String {
    let (message, hint) = match &error {
        WasmRunError::UnknownModule(name) => (
            format!("{tool}: unknown module '{name}'"),
            "Check that the skill body references a registered module name.".to_string(),
        ),
        WasmRunError::Timeout(duration) => (
            format!("{tool}: module '{module}' timed out after {duration:?}"),
            "The file may be too complex. Try a smaller file or a subset (e.g., specific page range).".to_string(),
        ),
        WasmRunError::OutOfFuel => (
            format!("{tool}: module '{module}' exhausted its instruction budget"),
            "The file requires more processing than the budget allows. Try a smaller file.".to_string(),
        ),
        WasmRunError::MemoryLimit(limit) => (
            format!("{tool}: module '{module}' exceeded memory limit {limit} bytes"),
            "The file is too large for the current memory budget. For PDF, the host auto-splits large files. For docx/xlsx/pptx, try a smaller file or extract a subset.".to_string(),
        ),
        WasmRunError::Io(detail) => (
            format!("{tool}: I/O error preparing sandbox: {detail}"),
            "Check that the input file exists and is readable.".to_string(),
        ),
        WasmRunError::ModuleLoad(detail) => (
            format!("{tool}: failed to load module: {detail}"),
            "The WebAssembly module may be corrupt. This is an internal error.".to_string(),
        ),
        WasmRunError::Execution(detail) => (
            format!("{tool}: module '{module}' failed during execution: {detail}"),
            "The file may be corrupt or in an unsupported format. Do not retry with the same file.".to_string(),
        ),
    };
    format!("{message}\n\nHint: {hint}")
}

fn resolve_scoped_path(
    execution_scope: &DesktopExecutionScope,
    file_path: &str,
    allow_missing: bool,
) -> Result<PathBuf, String> {
    let raw_path = PathBuf::from(file_path);
    let scoped_path = if raw_path.is_absolute() {
        raw_path
    } else {
        execution_scope.canonical_root.join(raw_path)
    };

    if scoped_path.exists() {
        let canonical = fs::canonicalize(&scoped_path)
            .map_err(|error| format!("Failed to resolve {}: {}", scoped_path.display(), error))?;
        ensure_within_scope(execution_scope, &canonical)?;
        return Ok(canonical);
    }

    if !allow_missing {
        return Err(format!("Path does not exist: {}", scoped_path.display()));
    }

    let (existing_ancestor, relative_suffix) = split_existing_ancestor(&scoped_path)?;
    if relative_suffix
        .components()
        .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(format!(
            "Desktop tool path cannot escape desktop scope: {}",
            scoped_path.display()
        ));
    }
    let canonical_ancestor = fs::canonicalize(&existing_ancestor).map_err(|error| {
        format!(
            "Failed to resolve ancestor {}: {}",
            existing_ancestor.display(),
            error
        )
    })?;
    ensure_within_scope(execution_scope, &canonical_ancestor)?;
    Ok(canonical_ancestor.join(relative_suffix))
}

fn split_existing_ancestor(path: &Path) -> Result<(PathBuf, PathBuf), String> {
    let mut current = path.to_path_buf();
    let mut suffix = PathBuf::new();

    while !current.exists() {
        let file_name = current
            .file_name()
            .map(PathBuf::from)
            .ok_or_else(|| format!("Unable to resolve path ancestor for {}", path.display()))?;
        suffix = if suffix.as_os_str().is_empty() {
            file_name
        } else {
            PathBuf::from(file_name).join(suffix)
        };
        current = current
            .parent()
            .map(PathBuf::from)
            .ok_or_else(|| format!("Unable to resolve path ancestor for {}", path.display()))?;
    }

    Ok((current, suffix))
}

fn ensure_within_scope(execution_scope: &DesktopExecutionScope, path: &Path) -> Result<(), String> {
    if path.starts_with(&execution_scope.canonical_root) {
        Ok(())
    } else {
        Err(format!(
            "Desktop tool path {} is outside desktop scope {}",
            path.display(),
            execution_scope.canonical_root.display()
        ))
    }
}
