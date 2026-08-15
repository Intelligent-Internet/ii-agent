//! Host-side chunking policy for desktop WASM calls.
//!
//! Large input documents can exhaust the 256 MB per-Store memory limit
//! if processed in a single `wasm_run` call. This module owns the
//! decision of "does this call need to be split, and if so how?" so
//! the `wasm_run` tool can stay agnostic about individual file formats.
//!
//! ## Concepts
//!
//! * [`ChunkPlan`] — the decision returned by a planner. Either
//!   [`ChunkPlan::Single`] (run one WASM call as-is) or
//!   [`ChunkPlan::Multi`] (run several WASM calls in sequence and
//!   merge the results).
//! * [`ChunkPlanner`] — a format-specific strategy that inspects a
//!   host-side file and produces a [`ChunkPlan`]. Each supported format
//!   gets its own planner implementation; [`pdf::PdfChunker`] is the
//!   first.
//! * [`classify_and_plan`] — the entry point the `wasm_run` tool calls.
//!   Picks the right planner for the target module, runs it, and falls
//!   back to a single-call plan when no planner exists for the module.
//!
//! ## Why not inside the guest?
//!
//! The obvious alternative is to let each guest module detect its own
//! memory pressure and stream. Two reasons the decision lives in the
//! host instead:
//!
//! 1. Guest modules run with a hard memory ceiling that the host
//!    cannot raise mid-call. Splitting the work across Stores is the
//!    only way to keep individual peak memory bounded.
//! 2. The host can run chunks in parallel later (each chunk gets its
//!    own Store). Inside one guest, parallelism requires WASI threads,
//!    which are not part of the `wasm32-wasip1` target we ship.
//!
//! ## Current scope
//!
//! v1 is size-based only: the planner classifies by file size on disk
//! and picks a fixed chunk granularity. It does not parse the document
//! to count pages — that would require pulling `lopdf` into the host
//! binary, which we want to avoid. The granularity heuristic is tuned
//! so the guest, once given a page_range, never tries to load more
//! than ~100 MB of PDF into memory at once.

pub mod docx;
pub mod pdf;
pub mod pptx;
pub mod splitter;
pub mod xlsx;

use crate::cowork::desktop_runtime::RuntimeLimits;
use serde_json::Value;
use std::path::Path;

/// Result of planning a `wasm_run` call against a specific input file.
///
/// A plan is always safe to ignore: if the caller does not know how to
/// execute multi-chunk plans it can treat [`ChunkPlan::Multi`] as if it
/// were a single call and accept the memory risk. That keeps the plan
/// structure additive — callers adopt chunking at their own pace.
#[derive(Debug, Clone)]
pub enum ChunkPlan {
    /// Run the call as-is, optionally with overridden limits (e.g. a
    /// larger memory ceiling for borderline inputs that do not need
    /// splitting but do need headroom).
    Single { limits: RuntimeLimits },
    /// Run several calls in order, each with its own input_json
    /// override and limits. The caller merges the structured results
    /// back together via [`MergeStrategy`].
    Multi {
        chunks: Vec<Chunk>,
        merge: MergeStrategy,
        /// When `true`, the dispatcher should use host-side file
        /// splitting (via [`splitter::split_pdf_pages`]) to produce
        /// per-chunk input files instead of passing the full file with
        /// a range overlay. This eliminates guest-side full-file memory
        /// pressure for formats where host splitting is implemented
        /// (currently: PDF only).
        use_host_split: bool,
    },
}

impl ChunkPlan {
    pub fn single_default() -> Self {
        Self::Single {
            limits: RuntimeLimits::defaults(),
        }
    }

    pub fn is_multi(&self) -> bool {
        matches!(self, Self::Multi { .. })
    }

    pub fn uses_host_split(&self) -> bool {
        matches!(self, Self::Multi { use_host_split: true, .. })
    }

    pub fn chunk_count(&self) -> usize {
        match self {
            Self::Single { .. } => 1,
            Self::Multi { chunks, .. } => chunks.len(),
        }
    }
}

/// One unit of work in a multi-chunk plan.
#[derive(Debug, Clone)]
pub struct Chunk {
    /// Zero-based chunk index, used for ordering merged results.
    pub index: usize,
    /// Human-readable label for logging and error reporting, for
    /// example `"pages 1-50"`.
    pub label: String,
    /// Fields to merge into `input_json` before dispatching the call.
    /// The chunker produces this from its own heuristics (for example,
    /// a PDF chunker inserts `{"page_range": [1, 50]}`).
    pub input_json_overlay: Value,
    /// Resource limits for this specific chunk. Usually the same for
    /// every chunk in a plan, but kept per-chunk so unusual cases can
    /// bump limits on the last chunk if needed.
    pub limits: RuntimeLimits,
}

/// Strategy the caller uses to merge the output of a multi-chunk plan
/// back into a single structured result.
///
/// Each variant corresponds to a specific `(module, op)` pair. Adding a
/// new chunkable operation means adding a variant here and a matching
/// implementation in [`merge_chunk_outputs`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MergeStrategy {
    /// Concatenate `output.json.pages[]` across chunks, ordered by
    /// chunk `index`. The merged result uses the first chunk's
    /// `total_pages` value.
    PdfExtractTextPages,
    /// Concatenate `output.json.paragraphs[]` across chunks for the
    /// docx `extract_text` op.
    DocxExtractTextParagraphs,
    /// Concatenate `output.json.rows[]` across chunks for the xlsx
    /// `read_sheet` op.
    XlsxReadSheetRows,
    /// Concatenate `output.json.slides[]` across chunks for the pptx
    /// `extract_text` op.
    PptxExtractTextSlides,
}

/// A format-specific strategy for deciding whether a call needs to be
/// chunked and, if so, how.
///
/// Implementations should be pure functions of `(file_path, op,
/// base_input_json)` so the planner can be unit tested without
/// touching the WASM runtime.
pub trait ChunkPlanner {
    /// Plan a call for `file_path` with the given base `input_json`.
    ///
    /// Returns `Ok(None)` when the planner does not know how to handle
    /// the call — the caller should fall through to another planner or
    /// the default single-call plan. Returns `Err(_)` only for hard
    /// I/O errors that should abort the whole tool call.
    fn plan(
        &self,
        file_path: &Path,
        op: &str,
        base_input_json: &Value,
    ) -> Result<Option<ChunkPlan>, String>;
}

/// Top-level entry point used by `wasm_run`.
///
/// The `module` parameter lets the dispatcher pick the right planner
/// without having to know which format the file is. Today only
/// `pdf_processor` has a planner; other modules fall through to the
/// default single-call plan.
pub fn classify_and_plan(
    module: &str,
    file_path: Option<&Path>,
    op: Option<&str>,
    base_input_json: &Value,
) -> Result<ChunkPlan, String> {
    let Some(file_path) = file_path else {
        return Ok(ChunkPlan::single_default());
    };
    let Some(op) = op else {
        return Ok(ChunkPlan::single_default());
    };

    let planner: Option<Box<dyn ChunkPlanner>> = match module {
        "pdf_processor" => Some(Box::new(pdf::PdfChunker::default())),
        "docx_processor" => Some(Box::new(docx::DocxChunker::default())),
        "xlsx_processor" => Some(Box::new(xlsx::XlsxChunker::default())),
        "pptx_processor" => Some(Box::new(pptx::PptxChunker::default())),
        _ => None,
    };

    let Some(planner) = planner else {
        return Ok(ChunkPlan::single_default());
    };

    match planner.plan(file_path, op, base_input_json)? {
        Some(plan) => Ok(plan),
        None => Ok(ChunkPlan::single_default()),
    }
}

/// Merge structured outputs of multi-chunk plans back into one
/// `output.json`-style value.
///
/// The caller hands in the chunk outputs in chunk-index order (the
/// sequential dispatcher in `wasm_run` owns ordering). This function
/// knows the merge shape for each [`MergeStrategy`] variant and
/// produces the final `Value` that gets formatted into the tool
/// result.
pub fn merge_chunk_outputs(
    strategy: MergeStrategy,
    chunk_outputs: &[Value],
) -> Result<Value, String> {
    match strategy {
        MergeStrategy::PdfExtractTextPages => {
            merge_array_field(chunk_outputs, "pages", "total_pages", "pdf_processor")
        }
        MergeStrategy::DocxExtractTextParagraphs => merge_array_field(
            chunk_outputs,
            "paragraphs",
            "total_paragraphs",
            "docx_processor",
        ),
        MergeStrategy::XlsxReadSheetRows => {
            merge_array_field(chunk_outputs, "rows", "total_rows", "xlsx_processor")
        }
        MergeStrategy::PptxExtractTextSlides => {
            merge_array_field(chunk_outputs, "slides", "total_slides", "pptx_processor")
        }
    }
}

/// Generic merge: concatenate `array_field` across all chunk outputs in
/// order, then copy `total_field` from the first chunk. Shared by every
/// merge strategy since they all produce the same shape.
fn merge_array_field(
    chunk_outputs: &[Value],
    array_field: &str,
    total_field: &str,
    module_label: &str,
) -> Result<Value, String> {
    let mut merged_items: Vec<Value> = Vec::new();
    let mut total_value: Option<u64> = None;
    for (index, chunk) in chunk_outputs.iter().enumerate() {
        let items = chunk
            .get(array_field)
            .and_then(Value::as_array)
            .ok_or_else(|| {
                format!(
                    "{module_label} chunk {index}: output.json has no '{array_field}' array"
                )
            })?;
        merged_items.extend(items.iter().cloned());
        if total_value.is_none() {
            total_value = chunk.get(total_field).and_then(Value::as_u64);
        }
    }
    let mut merged = serde_json::Map::new();
    merged.insert(array_field.to_string(), Value::Array(merged_items));
    if let Some(total) = total_value {
        merged.insert(total_field.to_string(), Value::from(total));
    }
    Ok(Value::Object(merged))
}


#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn classify_and_plan_falls_back_for_unknown_module() {
        let plan =
            classify_and_plan("no_such_module", None, Some("extract_text"), &Value::Null).unwrap();
        assert!(matches!(plan, ChunkPlan::Single { .. }));
    }

    #[test]
    fn classify_and_plan_falls_back_when_no_file_path() {
        let plan =
            classify_and_plan("pdf_processor", None, Some("extract_text"), &Value::Null).unwrap();
        assert!(matches!(plan, ChunkPlan::Single { .. }));
    }

    #[test]
    fn merge_pdf_extract_text_concatenates_in_order() {
        let outputs = vec![
            json!({
                "pages": ["p1", "p2", "p3"],
                "page_offset": 1,
                "total_pages": 7,
            }),
            json!({
                "pages": ["p4", "p5"],
                "page_offset": 4,
                "total_pages": 7,
            }),
            json!({
                "pages": ["p6", "p7"],
                "page_offset": 6,
                "total_pages": 7,
            }),
        ];
        let merged = merge_chunk_outputs(MergeStrategy::PdfExtractTextPages, &outputs).unwrap();
        let pages = merged
            .get("pages")
            .and_then(Value::as_array)
            .expect("pages");
        assert_eq!(pages.len(), 7);
        assert_eq!(pages[0].as_str(), Some("p1"));
        assert_eq!(pages[6].as_str(), Some("p7"));
        assert_eq!(merged.get("total_pages").and_then(Value::as_u64), Some(7));
    }

    #[test]
    fn merge_pdf_extract_text_rejects_missing_pages_array() {
        let outputs = vec![json!({ "oops": true })];
        let err = merge_chunk_outputs(MergeStrategy::PdfExtractTextPages, &outputs).unwrap_err();
        assert!(err.contains("no 'pages' array"));
    }
}
