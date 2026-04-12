//! `wasm_run` desktop tool.
//!
//! This tool exposes the isolated desktop WASM runtime to the agent. It is
//! deliberately scoped as the **isolation path** for processing tasks —
//! not as a replacement for normal file tools. The agent should prefer
//! `Read`, `Write`, `Edit`, `Bash`, etc. for everyday local work and only
//! reach for `wasm_run` when a skill explicitly asks for isolated
//! processing (for example, extracting text from a PDF with tight memory
//! and timeout limits).
//!
//! ## Chunking
//!
//! Before running the guest, the tool asks
//! [`crate::cowork::desktop_runtime::wasm::chunking::classify_and_plan`]
//! whether the call needs to be split. For small inputs the answer is
//! always `ChunkPlan::Single` and the tool runs a single WASM call.
//! For large inputs where a format-specific planner exists, the plan
//! is [`ChunkPlan::Multi`] and the tool dispatches several sequential
//! calls, merges their structured outputs, and returns a combined
//! result. Chunking is transparent to the LLM: it sees one tool call,
//! one tool result.
//!
//! ## Input contract
//!
//! The tool accepts a module name and an optional JSON payload. Input
//! files selected from the current desktop scope are mirrored into the
//! guest's preopened `/workspace/inputs` directory before the module
//! runs. The guest may write outputs to `/workspace/outputs` and/or a
//! structured `/workspace/output.json`; the tool reports back both.
//!
//! The set of modules the agent can invoke is defined by the desktop
//! runtime's [`ModuleRegistry`](crate::cowork::desktop_runtime::wasm::ModuleRegistry).
//! Unknown module names return an error without touching the filesystem.

use super::{DesktopTool, DesktopToolContext, TOOL_WASM_RUN};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use crate::cowork::desktop_runtime::wasm::chunking::{
    self, splitter, Chunk, ChunkPlan, MergeStrategy,
};
use crate::cowork::desktop_runtime::wasm::{
    acquire_runtime, WasmEntrypoint, WasmRunRequest, WasmRunResult,
};
use crate::cowork::desktop_runtime::RuntimeLimits;
use serde_json::Value;
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_WASM_RUN.to_string(),
            aliases: Vec::new(),
            display_name: "Run an isolated WASM processing module".to_string(),
            description: "Invoke a desktop-owned WebAssembly module inside an isolated sandbox with memory, fuel, and wall-clock limits. Use this when a skill explicitly requires isolated processing (for example, parsing a user document into structured data). Do NOT use it for normal file reading, editing, or shell work — use the Read, Write, Edit, and Bash tools for those. The module must be registered in the desktop WASM runtime. Optional input_files are copied into the guest's /workspace/inputs directory. Optional input_json is written to /workspace/input.json. The guest may return stdout/stderr, a structured /workspace/output.json, and files in /workspace/outputs. Large inputs (for example PDFs over 100 MB) may be transparently split by the host into several sequential sandbox calls whose structured outputs are merged back into one tool result.".to_string(),
            input_schema: serde_json::json!({
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "Name of the WASM module to run. The module must be pre-registered in the desktop runtime."
                    },
                    "entrypoint": {
                        "type": "string",
                        "description": "Optional exported function name to call instead of the default `_start`. Leave unset for standard WASI command modules."
                    },
                    "input_json": {
                        "type": "object",
                        "description": "Optional JSON payload written to /workspace/input.json before the module runs. Use this to pass structured arguments to the module."
                    },
                    "input_files": {
                        "type": "array",
                        "description": "Optional list of host files (relative or absolute within the desktop scope) to mirror into /workspace/inputs inside the sandbox.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Source path, absolute or relative to the current desktop scope."
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Optional logical filename to expose inside /workspace/inputs. Defaults to the source filename."
                                }
                            },
                            "required": ["path"]
                        }
                    },
                    "keep_workspace": {
                        "type": "boolean",
                        "description": "Keep the scratch workspace on disk after the call for debugging. Defaults to false."
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Optional wall-clock timeout in seconds. Defaults to the runtime default. Applied per chunk when the host splits the call."
                    }
                },
                "required": ["module"]
            }),
        },
        execute,
        false,
    )
}

/// Maximum total wall-clock time a multi-chunk run may spend before
/// aborting mid-sequence. Prevents pathological PDF causing indefinite
/// blocking.
const MAX_MULTI_CHUNK_TOTAL_TIMEOUT: Duration = Duration::from_secs(600); // 10 minutes

/// Holds everything the tool parsed from the LLM's input block, so the
/// single-call and multi-call dispatch paths can share code.
struct ParsedInput {
    module_name: String,
    /// Local cowork session id captured at parse time. Used as the
    /// scratch-dir scope for every chunk in a multi-chunk plan so the
    /// runtime's session sweeper can reclaim them together.
    session_id: String,
    base_input_json: Option<Value>,
    input_files: Vec<(PathBuf, String)>,
    entrypoint: WasmEntrypoint,
    keep_workspace: bool,
    /// When set by the user, this is the **total** timeout for the entire
    /// call. For multi-chunk plans, each chunk gets `total / chunk_count`
    /// as its per-chunk wall deadline (never less than 10 s).
    user_timeout_override: Option<Duration>,
    /// Tauri app handle for emitting progress events during multi-chunk
    /// dispatch. If absent (unit test context), progress events are skipped.
    app_handle: Option<AppHandle>,
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let parsed = parse_input(ctx, tool_input)?;
    let module_name = parsed.module_name.clone();

    // Emit start event so the desktop UI can show a spinner.
    emit_lifecycle_event(&parsed, "wasm_run:started");

    // Lease the shared desktop WASM runtime. This lazily creates the
    // wasmtime engine on first use and keeps it alive for the duration
    // of the lease so the idle reaper cannot tear it down mid-call.
    let lease = acquire_runtime()
        .map_err(|error| format!("wasm_run: failed to acquire runtime: {error}"))?;
    if !lease.registry().has(&module_name) {
        let available = lease.registry().names().join(", ");
        return Err(format!(
            "wasm_run: module '{}' is not registered. Available modules: [{}]",
            module_name, available
        ));
    }

    // Classify the call. This is the only place that knows about
    // chunking policy — the rest of the dispatch path treats plan
    // variants uniformly.
    let op_name = parsed
        .base_input_json
        .as_ref()
        .and_then(|value| value.get("op"))
        .and_then(Value::as_str);
    let primary_file = parsed.input_files.first().map(|(path, _)| path.as_path());
    let plan = chunking::classify_and_plan(
        &module_name,
        primary_file,
        op_name,
        parsed
            .base_input_json
            .as_ref()
            .unwrap_or(&Value::Null),
    )?;

    // Fix #21: multi-file + chunkable plan is ambiguous — which file do
    // we chunk? Error early so the LLM knows to split its call.
    if plan.is_multi() && parsed.input_files.len() > 1 {
        return Err(
            "wasm_run: cannot chunk a call with multiple input_files. \
            Split into one call per file so each can be chunked independently."
                .to_string(),
        );
    }

    let outcome = match plan {
        ChunkPlan::Single { limits } => run_single(&lease, &parsed, limits, None),
        ChunkPlan::Multi {
            chunks,
            merge,
            use_host_split,
        } => {
            if use_host_split {
                run_multi_with_host_split(&lease, &parsed, chunks, merge)
            } else {
                run_multi(&lease, &parsed, chunks, merge)
            }
        }
    };

    drop(lease);
    emit_lifecycle_event(&parsed, "wasm_run:completed");
    outcome
}

fn parse_input(
    ctx: &mut DesktopToolContext<'_>,
    tool_input: &Value,
) -> Result<ParsedInput, String> {
    let module_name = tool_input
        .get("module")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "wasm_run requires a 'module' name".to_string())?
        .to_string();

    let base_input_json = tool_input
        .get("input_json")
        .filter(|v| !v.is_null())
        .cloned();

    let entrypoint = tool_input
        .get("entrypoint")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| WasmEntrypoint::NamedVoid(value.to_string()))
        .unwrap_or(WasmEntrypoint::Start);

    let keep_workspace = tool_input
        .get("keep_workspace")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    let user_timeout_override = tool_input
        .get("timeout_seconds")
        .and_then(Value::as_u64)
        .map(|secs| std::time::Duration::from_secs(secs.min(120)));

    let mut input_files = Vec::new();
    if let Some(entries) = tool_input.get("input_files").and_then(Value::as_array) {
        for entry in entries {
            let Some(spec) = entry.as_object() else {
                return Err("wasm_run: input_files entries must be objects".to_string());
            };
            let raw_path = spec
                .get("path")
                .and_then(Value::as_str)
                .ok_or_else(|| "wasm_run: input_files entry requires a 'path'".to_string())?;
            let resolved = ctx.resolve_scoped_path(raw_path, false)?;
            let logical_name = spec
                .get("name")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| {
                    PathBuf::from(raw_path)
                        .file_name()
                        .map(|name| name.to_string_lossy().into_owned())
                        .unwrap_or_else(|| "input.bin".to_string())
                });
            input_files.push((resolved, logical_name));
        }
    }

    Ok(ParsedInput {
        module_name,
        session_id: ctx.local_session_id().to_string(),
        base_input_json,
        input_files,
        entrypoint,
        keep_workspace,
        user_timeout_override,
        app_handle: Some(ctx.app_handle().clone()),
    })
}

fn build_request(
    parsed: &ParsedInput,
    session_id: &str,
    limits: RuntimeLimits,
    input_json_overlay: Option<&Value>,
) -> WasmRunRequest {
    let input_json = match (parsed.base_input_json.as_ref(), input_json_overlay) {
        (None, None) => None,
        (Some(base), None) => Some(base.clone()),
        (None, Some(overlay)) => Some(overlay.clone()),
        (Some(base), Some(overlay)) => Some(merge_json_objects(base.clone(), overlay)),
    };

    let mut request = WasmRunRequest::new(parsed.module_name.clone())
        .with_session_id(session_id.to_string());
    request.input_json = input_json;
    request.entrypoint = parsed.entrypoint.clone();
    request.keep_workspace = parsed.keep_workspace;
    request.input_files = parsed.input_files.clone();

    let mut effective_limits = limits;
    if let Some(user_timeout) = parsed.user_timeout_override {
        effective_limits.wall_timeout = user_timeout;
    }
    request.limits = Some(effective_limits);
    request
}

/// Shallow merge two JSON values, preferring keys from `overlay`. Both
/// must be objects; if either is not, `overlay` wins outright.
fn merge_json_objects(base: Value, overlay: &Value) -> Value {
    let (Value::Object(mut base_map), Value::Object(overlay_map)) = (base, overlay) else {
        return overlay.clone();
    };
    for (key, value) in overlay_map.iter() {
        base_map.insert(key.clone(), value.clone());
    }
    Value::Object(base_map)
}

fn run_single(
    lease: &crate::cowork::desktop_runtime::wasm::lifecycle::RuntimeLease,
    parsed: &ParsedInput,
    limits: RuntimeLimits,
    overlay: Option<&Value>,
) -> Result<String, String> {
    let request = build_request(parsed, &parsed.session_id, limits, overlay);
    let result = lease.run(request);
    match result {
        Ok(result) => Ok(super::format_wasm_result(&result)),
        Err(error) => Err(super::format_wasm_error(
            "wasm_run",
            &parsed.module_name,
            error,
        )),
    }
}

fn run_multi(
    lease: &crate::cowork::desktop_runtime::wasm::lifecycle::RuntimeLease,
    parsed: &ParsedInput,
    mut chunks: Vec<chunking::Chunk>,
    merge: MergeStrategy,
) -> Result<String, String> {
    if chunks.is_empty() {
        return Err("wasm_run: chunking planner returned an empty chunk list".to_string());
    }
    let chunk_count = chunks.len();

    // Fix #14 + #23: compute per-chunk timeout from user total override.
    // If user set `timeout_seconds`, that's the TOTAL budget across all
    // chunks. Each chunk gets total/chunks (min 10 s per chunk). If no
    // user override, use planner-assigned limits as-is but enforce
    // MAX_MULTI_CHUNK_TOTAL_TIMEOUT as a hard ceiling.
    let total_deadline = parsed
        .user_timeout_override
        .unwrap_or(MAX_MULTI_CHUNK_TOTAL_TIMEOUT);
    let per_chunk_timeout = Duration::from_secs(
        (total_deadline.as_secs() / chunk_count as u64).max(10),
    );

    // Override per-chunk limits with the computed timeout.
    for chunk in &mut chunks {
        chunk.limits.wall_timeout = per_chunk_timeout;
    }

    let global_start = Instant::now();
    let mut chunk_outputs: Vec<Value> = Vec::with_capacity(chunk_count);
    let mut combined_stdout = String::new();
    let mut combined_stderr = String::new();
    let mut total_duration_ms: u128 = 0;
    let mut chunk_summaries: Vec<String> = Vec::with_capacity(chunk_count);

    for (i, chunk) in chunks.iter().enumerate() {
        // Fix #14: check global timeout before starting next chunk.
        if global_start.elapsed() > total_deadline {
            return Err(format!(
                "wasm_run: multi-chunk run exceeded total timeout ({} s) after completing {}/{} chunks",
                total_deadline.as_secs(),
                i,
                chunk_count
            ));
        }

        let request = build_request(
            parsed,
            &parsed.session_id,
            chunk.limits,
            Some(&chunk.input_json_overlay),
        );
        let label = chunk.label.clone();
        let result: Result<WasmRunResult, _> = lease.run(request);
        match result {
            Ok(chunk_result) => {
                total_duration_ms += chunk_result.duration_ms;
                if !chunk_result.stdout.trim().is_empty() {
                    combined_stdout.push_str(&format!(
                        "[{}]\n{}\n",
                        label,
                        chunk_result.stdout.trim_end()
                    ));
                }
                if !chunk_result.stderr.trim().is_empty() {
                    combined_stderr.push_str(&format!(
                        "[{}]\n{}\n",
                        label,
                        chunk_result.stderr.trim_end()
                    ));
                }
                let Some(output_json) = chunk_result.output_json else {
                    return Err(format!(
                        "wasm_run: chunk {label} produced no output.json; cannot merge"
                    ));
                };
                chunk_summaries.push(format!(
                    "- [{label}] duration_ms={}, items_in_chunk={}",
                    chunk_result.duration_ms,
                    first_array_len(&output_json)
                ));
                chunk_outputs.push(output_json);

                // Fix #19: emit progress event so the UI can show a
                // progress bar between chunks.
                emit_chunk_progress(parsed, i + 1, chunk_count, &label);
            }
            Err(error) => {
                let error_msg = super::format_wasm_error(
                    "wasm_run",
                    &parsed.module_name,
                    error,
                );
                // Return partial results if we have any, instead of
                // losing all completed work.
                return format_multi_result(
                    parsed,
                    &global_start,
                    total_duration_ms,
                    chunk_count,
                    &chunk_outputs,
                    &chunk_summaries,
                    &combined_stdout,
                    &combined_stderr,
                    merge,
                    Some(&error_msg),
                );
            }
        }
    }

    format_multi_result(
        parsed,
        &global_start,
        total_duration_ms,
        chunk_count,
        &chunk_outputs,
        &chunk_summaries,
        &combined_stdout,
        &combined_stderr,
        merge,
        None,
    )
}

/// Format the result of a multi-chunk run, optionally with a partial-failure error.
fn format_multi_result(
    parsed: &ParsedInput,
    global_start: &Instant,
    total_duration_ms: u128,
    chunk_count: usize,
    chunk_outputs: &[Value],
    chunk_summaries: &[String],
    combined_stdout: &str,
    combined_stderr: &str,
    merge: MergeStrategy,
    error: Option<&str>,
) -> Result<String, String> {
    let wall_ms = global_start.elapsed().as_millis();
    let completed = chunk_outputs.len();
    let status = if error.is_some() {
        format!("PARTIAL ({completed}/{chunk_count} chunks succeeded)")
    } else {
        format!("{chunk_count} (sequential)")
    };

    let mut sections: Vec<String> = Vec::new();
    sections.push(format!(
        "module: {}\nwall_time_ms: {wall_ms}\ncpu_time_ms: {total_duration_ms}\nchunks: {status}",
        parsed.module_name
    ));

    if !chunk_summaries.is_empty() {
        sections.push(format!("chunk_summary:\n{}", chunk_summaries.join("\n")));
    }
    if !combined_stdout.trim().is_empty() {
        sections.push(format!("stdout (merged):\n{}", combined_stdout.trim_end()));
    }
    if !combined_stderr.trim().is_empty() {
        sections.push(format!("stderr (merged):\n{}", combined_stderr.trim_end()));
    }

    if !chunk_outputs.is_empty() {
        match chunking::merge_chunk_outputs(merge, chunk_outputs) {
            Ok(merged) => {
                if let Ok(pretty) = serde_json::to_string_pretty(&merged) {
                    sections.push(format!("output.json (merged):\n{pretty}"));
                }
            }
            Err(merge_err) => {
                sections.push(format!("merge_error: {merge_err}"));
            }
        }
    }

    if let Some(err) = error {
        sections.push(format!("error:\n{err}"));
    }

    // If we have at least some output, return Ok (partial success)
    // even if a chunk failed, so the LLM can use what was extracted.
    // Only return Err if zero chunks succeeded.
    if chunk_outputs.is_empty() && error.is_some() {
        Err(error.unwrap().to_string())
    } else {
        Ok(sections.join("\n\n"))
    }
}

/// Multi-chunk dispatch with host-side file splitting (Fix #7).
///
/// Instead of passing the full source file + `page_range` overlay to
/// each chunk, this path uses [`splitter::split_pdf_pages`] to produce
/// N smaller PDFs on the host. Each guest call then receives a small
/// file that fits within its 256–512 MB memory budget without loading
/// the entire original document.
///
/// The chunk plan's `input_json_overlay` (which would contain
/// `page_range`) is **ignored** here because the guest file already
/// contains only the relevant pages. The guest is called without a
/// `page_range` param — it extracts the entire (small) file.
fn run_multi_with_host_split(
    lease: &crate::cowork::desktop_runtime::wasm::lifecycle::RuntimeLease,
    parsed: &ParsedInput,
    chunks: Vec<Chunk>,
    merge: MergeStrategy,
) -> Result<String, String> {
    if chunks.is_empty() {
        return Err("wasm_run: host-split: empty chunk list".to_string());
    }

    // We need the primary input file to split.
    let (source_path, _logical_name) = parsed
        .input_files
        .first()
        .ok_or_else(|| "wasm_run: host-split requires at least one input file".to_string())?;

    // Determine pages_per_chunk from the first chunk's overlay.
    let pages_per_chunk = chunks
        .first()
        .and_then(|c| c.input_json_overlay.get("page_range"))
        .and_then(|r| r.as_array())
        .and_then(|arr| {
            let start = arr.first()?.as_u64()?;
            let end = arr.get(1)?.as_u64()?;
            Some((end - start + 1) as u32)
        })
        .unwrap_or(20);

    // Split the PDF on the host side into chunk files.
    let split_dir = std::env::temp_dir().join(format!(
        "ii-wasm-split-{}-{}",
        parsed.session_id,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or_default()
    ));
    let chunk_files =
        splitter::split_pdf_pages(source_path, &split_dir, pages_per_chunk)
            .map_err(|e| format!("wasm_run: host-split failed: {e}"))?;

    if chunk_files.is_empty() {
        let _ = std::fs::remove_dir_all(&split_dir);
        return Err("wasm_run: host-split produced 0 chunk files (empty PDF?)".to_string());
    }

    // Compute timeout.
    let total_deadline = parsed
        .user_timeout_override
        .unwrap_or(MAX_MULTI_CHUNK_TOTAL_TIMEOUT);
    let per_chunk_timeout = Duration::from_secs(
        (total_deadline.as_secs() / chunk_files.len() as u64).max(10),
    );

    let global_start = Instant::now();
    let mut chunk_outputs: Vec<Value> = Vec::with_capacity(chunk_files.len());
    let mut combined_stdout = String::new();
    let mut combined_stderr = String::new();
    let mut total_duration_ms: u128 = 0;
    let mut chunk_summaries: Vec<String> = Vec::new();
    let actual_chunk_count = chunk_files.len();

    for (i, chunk_file) in chunk_files.iter().enumerate() {
        if global_start.elapsed() > total_deadline {
            let _ = std::fs::remove_dir_all(&split_dir);
            return Err(format!(
                "wasm_run: host-split exceeded total timeout ({} s) after {}/{} chunks",
                total_deadline.as_secs(),
                i,
                actual_chunk_count
            ));
        }

        // Build a request that uses the chunk file instead of the original.
        let mut limits = RuntimeLimits::defaults();
        limits.wall_timeout = per_chunk_timeout;
        limits.max_memory_bytes = 512 * 1024 * 1024;

        // base input_json without page_range (guest extracts entire chunk file).
        let chunk_input_json = parsed
            .base_input_json
            .as_ref()
            .and_then(|v| v.as_object())
            .map(|obj| {
                let mut filtered = obj.clone();
                filtered.remove("page_range");
                Value::Object(filtered)
            })
            .or_else(|| parsed.base_input_json.clone());

        let mut request = WasmRunRequest::new(parsed.module_name.clone())
            .with_session_id(parsed.session_id.clone());
        request.input_json = chunk_input_json;
        request.entrypoint = parsed.entrypoint.clone();
        request.keep_workspace = parsed.keep_workspace;
        request.input_files = vec![(chunk_file.path.clone(), "input.pdf".to_string())];
        request.limits = Some(limits);

        let label = format!("pages {}-{}", chunk_file.page_start, chunk_file.page_end);
        let result = lease.run(request);

        match result {
            Ok(chunk_result) => {
                total_duration_ms += chunk_result.duration_ms;
                if !chunk_result.stdout.trim().is_empty() {
                    combined_stdout.push_str(&format!("[{label}]\n{}\n", chunk_result.stdout.trim_end()));
                }
                if !chunk_result.stderr.trim().is_empty() {
                    combined_stderr.push_str(&format!("[{label}]\n{}\n", chunk_result.stderr.trim_end()));
                }
                let Some(mut output_json) = chunk_result.output_json else {
                    let _ = std::fs::remove_dir_all(&split_dir);
                    return Err(format!("wasm_run: host-split chunk {label} produced no output.json"));
                };
                // Patch page_offset to reflect position in the original doc.
                if let Some(obj) = output_json.as_object_mut() {
                    obj.insert(
                        "page_offset".to_string(),
                        Value::from(chunk_file.page_start as u64),
                    );
                    obj.insert(
                        "total_pages".to_string(),
                        Value::from(chunk_file.total_pages as u64),
                    );
                }
                chunk_summaries.push(format!(
                    "- [{label}] duration_ms={}, items={}",
                    chunk_result.duration_ms,
                    first_array_len(&output_json)
                ));
                chunk_outputs.push(output_json);
                emit_chunk_progress(parsed, i + 1, actual_chunk_count, &label);
            }
            Err(error) => {
                let error_msg = super::format_wasm_error(
                    "wasm_run",
                    &parsed.module_name,
                    error,
                );
                let _ = std::fs::remove_dir_all(&split_dir);
                return format_multi_result(
                    parsed,
                    &global_start,
                    total_duration_ms,
                    actual_chunk_count,
                    &chunk_outputs,
                    &chunk_summaries,
                    &combined_stdout,
                    &combined_stderr,
                    merge,
                    Some(&error_msg),
                );
            }
        }
    }

    let _ = std::fs::remove_dir_all(&split_dir);
    format_multi_result(
        parsed,
        &global_start,
        total_duration_ms,
        actual_chunk_count,
        &chunk_outputs,
        &chunk_summaries,
        &combined_stdout,
        &combined_stderr,
        merge,
        None,
    )
}

/// Emit a lifecycle event (started/completed) for UI feedback on single calls.
fn emit_lifecycle_event(parsed: &ParsedInput, event_name: &str) {
    let Some(app) = &parsed.app_handle else {
        return;
    };
    let payload = serde_json::json!({
        "module": parsed.module_name,
        "session_id": parsed.session_id,
    });
    let _ = app.emit(event_name, payload);
}

/// Emit a progress event after each chunk completes so the desktop
/// UI can render a progress indicator. No-op if app handle is absent
/// (unit tests) or if emit fails (best-effort).
fn emit_chunk_progress(parsed: &ParsedInput, done: usize, total: usize, label: &str) {
    let Some(app) = &parsed.app_handle else {
        return;
    };
    let payload = serde_json::json!({
        "module": parsed.module_name,
        "session_id": parsed.session_id,
        "chunk_done": done,
        "chunk_total": total,
        "chunk_label": label,
    });
    let _ = app.emit("wasm_run:chunk_progress", payload);
}

/// Get the length of the first array-valued field in a JSON object.
/// Used for chunk summary (pages, paragraphs, rows, slides — we don't
/// need to know which field it is, just how many items came back).
fn first_array_len(value: &Value) -> usize {
    let Some(obj) = value.as_object() else {
        return 0;
    };
    for val in obj.values() {
        if let Some(arr) = val.as_array() {
            return arr.len();
        }
    }
    0
}

