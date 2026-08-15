//! Host-side file splitting for memory-sensitive chunk dispatch.
//!
//! The key problem: guest modules like `pdf_processor` use `lopdf` which
//! calls `Document::load()` on the full file — meaning even if we pass
//! `page_range: [1, 20]`, the guest still loads the full 200 MB into
//! linear memory before extracting the requested pages. This negates
//! the memory benefit of chunking.
//!
//! The fix: split the source file **on the host side** into smaller
//! files (one per chunk), then pass each chunk-file to its own sandbox
//! call. The guest sees a small file and stays within its memory budget.
//!
//! One subtlety: parsing/splitting a huge PDF with `lopdf` can itself
//! consume a large amount of native heap. If we do that work inside the
//! Tauri process, the OS can kill the entire desktop app before Wasmtime
//! gets a chance to report a sandboxed memory error. To keep the UI
//! alive, production builds run the expensive host-side PDF work in a
//! short-lived helper process spawned from the current executable. If the
//! helper panics, aborts, or is OOM-killed, the parent sees a normal tool
//! error instead of losing the whole app.
//!
//! ## Scope
//!
//! v1 supports PDF splitting only. DOCX/XLSX/PPTX are fundamentally
//! different (zipped OOXML containers where you can't extract a subset
//! of pages without rewriting the entire archive), so they skip host-side
//! splitting and continue to pass the full file + range params to the
//! guest. This means large DOCX/XLSX/PPTX may still OOM in the guest,
//! which the skill body documents as a limitation.

use crate::cowork::desktop_runtime::wasm::WasmRunResult;
use lopdf::Document;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::any::Any;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const PDF_HELPER_FLAG: &str = "--ii-pdf-helper";
const PDF_HELPER_COUNT_PAGES: &str = "count-pages";
const PDF_HELPER_SPLIT_PAGES: &str = "split-pages";
const PDF_HELPER_RUN_PROCESSOR: &str = "run-pdf-processor";

/// Split a PDF file into multiple smaller PDFs, each containing a
/// contiguous range of pages. Returns a list of `(chunk_file_path,
/// page_start, page_end)` tuples. The chunk files are written to
/// `output_dir` as `chunk_0.pdf`, `chunk_1.pdf`, etc.
///
/// If the file has fewer pages than `pages_per_chunk`, a single chunk
/// containing the entire document is returned.
///
/// This function uses `lopdf` on the host side (native, not sandboxed)
/// because it needs to parse the PDF structure to split pages.
pub fn split_pdf_pages(
    source: &Path,
    output_dir: &Path,
    pages_per_chunk: u32,
) -> Result<Vec<PdfChunkFile>, String> {
    if cfg!(test) {
        return split_pdf_pages_in_process(source, output_dir, pages_per_chunk);
    }

    let result_path = helper_result_path("split");
    let output = run_helper_process(&[
        OsString::from(PDF_HELPER_FLAG),
        OsString::from(PDF_HELPER_SPLIT_PAGES),
        source.as_os_str().to_os_string(),
        output_dir.as_os_str().to_os_string(),
        OsString::from(pages_per_chunk.to_string()),
        result_path.as_os_str().to_os_string(),
    ])?;

    if !output.status.success() {
        let _ = fs::remove_file(&result_path);
        return Err(format!(
            "split_pdf: helper process failed{}{}",
            format_exit_status(&output.status),
            format_stderr_suffix(&output.stderr)
        ));
    }

    let parsed: SplitPdfPagesOutput = read_helper_result(&result_path)?;
    let _ = fs::remove_file(&result_path);
    Ok(parsed.chunks)
}

fn split_pdf_pages_in_process(
    source: &Path,
    output_dir: &Path,
    pages_per_chunk: u32,
) -> Result<Vec<PdfChunkFile>, String> {
    run_pdf_host_operation("split_pdf", || {
        if pages_per_chunk == 0 {
            return Err("split_pdf: pages_per_chunk must be greater than 0".to_string());
        }

        // First pass: count pages without keeping the full doc in memory.
        let page_numbers = {
            let doc = lopdf::Document::load(source)
                .map_err(|e| format!("split_pdf: failed to load {}: {e}", source.display()))?;
            let pages = doc.get_pages();
            let mut nums: Vec<u32> = pages.keys().copied().collect();
            nums.sort_unstable();
            nums
            // `doc` drops here — releases memory before we start splitting.
        };
        let total = page_numbers.len() as u32;

        if total == 0 {
            return Ok(vec![]);
        }

        fs::create_dir_all(output_dir)
            .map_err(|e| format!("split_pdf: mkdir {}: {e}", output_dir.display()))?;

        let mut chunks = Vec::new();
        let mut chunk_idx = 0u32;
        let mut start = 0usize;

        while start < page_numbers.len() {
            let end = (start + pages_per_chunk as usize).min(page_numbers.len());
            let chunk_pages: std::collections::HashSet<u32> =
                page_numbers[start..end].iter().copied().collect();

            // Reload from disk for each chunk so we never hold more than
            // 1 copy of the document in memory at a time. This trades I/O
            // (re-read source N times) for memory (peak = 1× doc size
            // instead of N× doc size from cloning).
            let mut chunk_doc = lopdf::Document::load(source)
                .map_err(|e| format!("split_pdf: reload for chunk {chunk_idx}: {e}"))?;

            let pages_to_remove: Vec<u32> = chunk_doc
                .get_pages()
                .keys()
                .copied()
                .filter(|num| !chunk_pages.contains(num))
                .collect();
            for page_num in pages_to_remove {
                chunk_doc.delete_pages(&[page_num]);
            }

            let chunk_path = output_dir.join(format!("chunk_{chunk_idx}.pdf"));
            chunk_doc
                .save(&chunk_path)
                .map_err(|e| format!("split_pdf: save chunk_{chunk_idx}: {e}"))?;

            chunks.push(PdfChunkFile {
                path: chunk_path,
                page_start: (start as u32) + 1,
                page_end: end as u32,
                total_pages: total,
            });

            start = end;
            chunk_idx += 1;
            // `chunk_doc` drops here — memory freed before next iteration.
        }

        Ok(chunks)
    })
}

/// Metadata about a host-side chunk file produced by [`split_pdf_pages`].
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PdfChunkFile {
    /// Path to the chunk PDF on the host filesystem.
    pub path: PathBuf,
    /// 1-based start page (inclusive) relative to the original document.
    pub page_start: u32,
    /// 1-based end page (inclusive) relative to the original document.
    pub page_end: u32,
    /// Total pages in the original document.
    pub total_pages: u32,
}

/// Count pages in a PDF without extracting content. Cheap compared to
/// full extraction — we only parse the xref table and page tree, never
/// decompress streams. Used by the chunker when it needs an accurate
/// page count rather than the size-based heuristic.
pub fn count_pdf_pages(source: &Path) -> Result<u32, String> {
    if cfg!(test) {
        return count_pdf_pages_in_process(source);
    }

    let result_path = helper_result_path("count");
    let output = run_helper_process(&[
        OsString::from(PDF_HELPER_FLAG),
        OsString::from(PDF_HELPER_COUNT_PAGES),
        source.as_os_str().to_os_string(),
        result_path.as_os_str().to_os_string(),
    ])?;

    if !output.status.success() {
        let _ = fs::remove_file(&result_path);
        return Err(format!(
            "count_pdf_pages: helper process failed{}{}",
            format_exit_status(&output.status),
            format_stderr_suffix(&output.stderr)
        ));
    }

    let parsed: CountPdfPagesOutput = read_helper_result(&result_path)?;
    let _ = fs::remove_file(&result_path);
    Ok(parsed.page_count)
}

pub fn run_pdf_processor_in_helper(
    input_file: &Path,
    input_json: Option<Value>,
) -> Result<WasmRunResult, String> {
    let request_path = helper_result_path("run-pdf-processor-request");
    let result_path = helper_result_path("run-pdf-processor-result");

    let request = PdfProcessorRunRequest {
        input_file: input_file.to_path_buf(),
        input_json,
    };
    write_helper_result(&request_path, &request)?;

    let output = run_helper_process(&[
        OsString::from(PDF_HELPER_FLAG),
        OsString::from(PDF_HELPER_RUN_PROCESSOR),
        request_path.as_os_str().to_os_string(),
        result_path.as_os_str().to_os_string(),
    ])?;

    let _ = fs::remove_file(&request_path);

    if !output.status.success() {
        let _ = fs::remove_file(&result_path);
        return Err(format!(
            "run_pdf_processor: helper process failed{}{}",
            format_exit_status(&output.status),
            format_stderr_suffix(&output.stderr)
        ));
    }

    let parsed: PdfProcessorRunOutput = read_helper_result(&result_path)?;
    let _ = fs::remove_file(&result_path);
    Ok(parsed.result)
}

fn count_pdf_pages_in_process(source: &Path) -> Result<u32, String> {
    run_pdf_host_operation("count_pdf_pages", || {
        let doc = lopdf::Document::load(source)
            .map_err(|e| format!("count_pdf_pages: failed to load {}: {e}", source.display()))?;
        Ok(doc.get_pages().len() as u32)
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CountPdfPagesOutput {
    page_count: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SplitPdfPagesOutput {
    chunks: Vec<PdfChunkFile>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PdfProcessorRunRequest {
    input_file: PathBuf,
    input_json: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PdfProcessorRunOutput {
    result: WasmRunResult,
}

#[derive(Debug)]
struct PdfProcessorInput {
    op: String,
    page_range: Option<(u32, u32)>,
}

#[derive(Debug)]
enum PdfHelperCommand {
    CountPages {
        source: PathBuf,
        result_path: PathBuf,
    },
    SplitPages {
        source: PathBuf,
        output_dir: PathBuf,
        pages_per_chunk: u32,
        result_path: PathBuf,
    },
    RunPdfProcessor {
        request_path: PathBuf,
        result_path: PathBuf,
    },
}

pub fn maybe_run_pdf_helper_from_env_args() -> Option<i32> {
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    let command = match parse_pdf_helper_args(args) {
        Ok(Some(command)) => command,
        Ok(None) => return None,
        Err(error) => {
            eprintln!("ii pdf helper: {error}");
            return Some(2);
        }
    };

    let outcome = match command {
        PdfHelperCommand::CountPages {
            source,
            result_path,
        } => count_pdf_pages_in_process(&source).and_then(|page_count| {
            write_helper_result(&result_path, &CountPdfPagesOutput { page_count })
        }),
        PdfHelperCommand::SplitPages {
            source,
            output_dir,
            pages_per_chunk,
            result_path,
        } => split_pdf_pages_in_process(&source, &output_dir, pages_per_chunk)
            .and_then(|chunks| write_helper_result(&result_path, &SplitPdfPagesOutput { chunks })),
        PdfHelperCommand::RunPdfProcessor {
            request_path,
            result_path,
        } => read_helper_result::<PdfProcessorRunRequest>(&request_path)
            .and_then(run_pdf_processor_in_process)
            .and_then(|result| {
                write_helper_result(&result_path, &PdfProcessorRunOutput { result })
            }),
    };

    match outcome {
        Ok(()) => Some(0),
        Err(error) => {
            eprintln!("ii pdf helper: {error}");
            Some(1)
        }
    }
}

fn parse_pdf_helper_args(
    args: impl IntoIterator<Item = OsString>,
) -> Result<Option<PdfHelperCommand>, String> {
    let mut args = args.into_iter();
    loop {
        let Some(flag) = args.next() else {
            return Ok(None);
        };
        if flag == OsStr::new(PDF_HELPER_FLAG) {
            break;
        }
    }

    let Some(command) = args.next() else {
        return Err("missing helper command".to_string());
    };

    match command.to_string_lossy().as_ref() {
        PDF_HELPER_COUNT_PAGES => {
            let source = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "count-pages requires <source>".to_string())?;
            let result_path = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "count-pages requires <result_path>".to_string())?;
            if args.next().is_some() {
                return Err("count-pages received unexpected extra arguments".to_string());
            }
            Ok(Some(PdfHelperCommand::CountPages {
                source,
                result_path,
            }))
        }
        PDF_HELPER_SPLIT_PAGES => {
            let source = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "split-pages requires <source>".to_string())?;
            let output_dir = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "split-pages requires <output_dir>".to_string())?;
            let pages_per_chunk = args
                .next()
                .ok_or_else(|| "split-pages requires <pages_per_chunk>".to_string())?
                .to_string_lossy()
                .parse::<u32>()
                .map_err(|error| format!("split-pages invalid pages_per_chunk: {error}"))?;
            if pages_per_chunk == 0 {
                return Err("split-pages requires pages_per_chunk > 0".to_string());
            }
            let result_path = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "split-pages requires <result_path>".to_string())?;
            if args.next().is_some() {
                return Err("split-pages received unexpected extra arguments".to_string());
            }
            Ok(Some(PdfHelperCommand::SplitPages {
                source,
                output_dir,
                pages_per_chunk,
                result_path,
            }))
        }
        PDF_HELPER_RUN_PROCESSOR => {
            let request_path = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "run-pdf-processor requires <request_path>".to_string())?;
            let result_path = args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "run-pdf-processor requires <result_path>".to_string())?;
            if args.next().is_some() {
                return Err("run-pdf-processor received unexpected extra arguments".to_string());
            }
            Ok(Some(PdfHelperCommand::RunPdfProcessor {
                request_path,
                result_path,
            }))
        }
        other => Err(format!("unknown helper command '{other}'")),
    }
}

fn helper_result_path(label: &str) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    std::env::temp_dir().join(format!("ii-pdf-helper-{label}-{nanos}.json"))
}

fn run_helper_process(args: &[OsString]) -> Result<std::process::Output, String> {
    let current_exe = std::env::current_exe()
        .map_err(|error| format!("cannot locate current executable: {error}"))?;
    Command::new(current_exe)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .output()
        .map_err(|error| format!("failed to spawn pdf helper process: {error}"))
}

fn write_helper_result<T: Serialize>(result_path: &Path, value: &T) -> Result<(), String> {
    if let Some(parent) = result_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("helper: mkdir {}: {error}", parent.display()))?;
    }
    let bytes =
        serde_json::to_vec(value).map_err(|error| format!("helper: serialize result: {error}"))?;
    fs::write(result_path, bytes)
        .map_err(|error| format!("helper: write {}: {error}", result_path.display()))
}

fn read_helper_result<T: for<'de> Deserialize<'de>>(result_path: &Path) -> Result<T, String> {
    let bytes = fs::read(result_path).map_err(|error| {
        format!(
            "helper result missing at {}: {error}",
            result_path.display()
        )
    })?;
    serde_json::from_slice(&bytes).map_err(|error| {
        format!(
            "helper result parse failed at {}: {error}",
            result_path.display()
        )
    })
}

fn format_exit_status(status: &std::process::ExitStatus) -> String {
    match status.code() {
        Some(code) => format!(" (exit code {code})"),
        None => " (terminated by signal)".to_string(),
    }
}

fn format_stderr_suffix(stderr: &[u8]) -> String {
    let text = String::from_utf8_lossy(stderr);
    let trimmed = text.trim();
    if trimmed.is_empty() {
        String::new()
    } else {
        format!(": {trimmed}")
    }
}

fn run_pdf_host_operation<T, F>(operation: &str, work: F) -> Result<T, String>
where
    F: FnOnce() -> Result<T, String>,
{
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(work)) {
        Ok(result) => result,
        Err(payload) => Err(format!(
            "{operation}: host PDF processing panicked: {}",
            panic_payload_message(payload.as_ref())
        )),
    }
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

fn run_pdf_processor_in_process(request: PdfProcessorRunRequest) -> Result<WasmRunResult, String> {
    run_pdf_host_operation("run_pdf_processor", || {
        let started_at = std::time::Instant::now();
        let input = parse_pdf_processor_input(request.input_json.as_ref())?;
        let document = Document::load(&request.input_file)
            .map_err(|error| format!("failed to load {}: {error}", request.input_file.display()))?;

        let output_json = match input.op.as_str() {
            "extract_text" => pdf_processor_extract_text(&document, input.page_range.as_ref())?,
            "metadata" => pdf_processor_metadata(&document)?,
            other => return Err(format!("unknown operation '{other}'")),
        };

        Ok(WasmRunResult {
            module: "pdf_processor".to_string(),
            stdout: format!("pdf_processor: op={} ok\n", input.op),
            stderr: String::new(),
            duration_ms: started_at.elapsed().as_millis(),
            output_json: Some(output_json),
            output_files: Vec::new(),
            scratch_dir: None,
        })
    })
}

fn parse_pdf_processor_input(input_json: Option<&Value>) -> Result<PdfProcessorInput, String> {
    let value = input_json
        .cloned()
        .ok_or_else(|| "failed to read /workspace/input.json: not provided".to_string())?;
    let op = value
        .get("op")
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| "input.json is missing the 'op' field".to_string())?;

    let page_range = match value.get("page_range") {
        Some(Value::Null) | None => None,
        Some(Value::Array(items)) => {
            if items.len() != 2 {
                return Err(format!(
                    "page_range must be a 2-element array [start, end], got {} elements",
                    items.len()
                ));
            }
            let start = items[0]
                .as_u64()
                .ok_or_else(|| "page_range[0] must be a non-negative integer".to_string())?;
            let end = items[1]
                .as_u64()
                .ok_or_else(|| "page_range[1] must be a non-negative integer".to_string())?;
            Some((start as u32, end as u32))
        }
        Some(other) => {
            return Err(format!(
                "page_range must be an array or null, got {}",
                json_kind(other)
            ));
        }
    };

    Ok(PdfProcessorInput { op, page_range })
}

fn json_kind(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn pdf_processor_extract_text(
    document: &Document,
    page_range: Option<&(u32, u32)>,
) -> Result<Value, String> {
    let pages = document.get_pages();
    let mut ordered: Vec<u32> = pages.keys().copied().collect();
    ordered.sort_unstable();
    let total_pages = ordered.len() as u32;

    let (slice, page_offset) = if let Some(&(start, end)) = page_range {
        if start == 0 {
            return Err("page_range start must be 1 or greater".to_string());
        }
        if start > end {
            return Ok(serde_json::json!({
                "pages": Vec::<String>::new(),
                "page_offset": start,
                "total_pages": total_pages,
            }));
        }

        let start_idx = (start - 1) as usize;
        if start_idx >= ordered.len() {
            return Ok(serde_json::json!({
                "pages": Vec::<String>::new(),
                "page_offset": start,
                "total_pages": total_pages,
            }));
        }

        let end_idx = (end as usize).min(ordered.len());
        (&ordered[start_idx..end_idx], start)
    } else {
        (&ordered[..], 1u32)
    };

    let mut pages_out = Vec::with_capacity(slice.len());
    for &page_num in slice {
        let text = document
            .extract_text(&[page_num])
            .map_err(|error| format!("page {page_num} extraction failed: {error}"))?;
        pages_out.push(text);
    }

    Ok(serde_json::json!({
        "pages": pages_out,
        "page_offset": page_offset,
        "total_pages": total_pages,
    }))
}

fn pdf_processor_metadata(document: &Document) -> Result<Value, String> {
    let page_count = document.get_pages().len();
    let info = document.trailer.get(b"Info").ok();
    let mut title: Option<String> = None;
    let mut author: Option<String> = None;

    if let Some(info_ref) = info {
        if let Ok(object_id) = info_ref.as_reference() {
            if let Ok(info_dict) = document
                .get_object(object_id)
                .and_then(|object| object.as_dict())
            {
                title = read_pdf_text_field(info_dict, b"Title");
                author = read_pdf_text_field(info_dict, b"Author");
            }
        }
    }

    Ok(serde_json::json!({
        "title": title,
        "author": author,
        "page_count": page_count,
    }))
}

fn read_pdf_text_field(dict: &lopdf::Dictionary, key: &[u8]) -> Option<String> {
    let object = dict.get(key).ok()?;
    let bytes = object.as_str().ok()?;
    Some(String::from_utf8_lossy(bytes).into_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn count_pages_on_fixture() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        let count = count_pdf_pages(&fixture).expect("count ok");
        assert_eq!(count, 1);
    }

    #[test]
    fn split_single_page_produces_one_chunk() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        let output_dir = std::env::temp_dir().join(format!(
            "split-test-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        ));
        let chunks = split_pdf_pages(&fixture, &output_dir, 10).expect("split ok");
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].page_start, 1);
        assert_eq!(chunks[0].page_end, 1);
        assert_eq!(chunks[0].total_pages, 1);
        assert!(chunks[0].path.exists());
        // Verify chunk is a valid PDF by loading it.
        let chunk_doc = lopdf::Document::load(&chunks[0].path).expect("chunk is valid pdf");
        assert_eq!(chunk_doc.get_pages().len(), 1);
        fs::remove_dir_all(&output_dir).ok();
    }

    #[test]
    fn helper_args_ignore_normal_app_launch() {
        let parsed = parse_pdf_helper_args(Vec::<OsString>::new()).expect("parse ok");
        assert!(parsed.is_none());
    }

    #[test]
    fn helper_args_parse_count_pages() {
        let parsed = parse_pdf_helper_args([
            OsString::from(PDF_HELPER_FLAG),
            OsString::from(PDF_HELPER_COUNT_PAGES),
            OsString::from("/tmp/input.pdf"),
            OsString::from("/tmp/result.json"),
        ])
        .expect("parse ok");

        match parsed {
            Some(PdfHelperCommand::CountPages {
                source,
                result_path,
            }) => {
                assert_eq!(source, PathBuf::from("/tmp/input.pdf"));
                assert_eq!(result_path, PathBuf::from("/tmp/result.json"));
            }
            other => panic!("expected CountPages, got {other:?}"),
        }
    }

    #[test]
    fn helper_args_find_flag_after_prefix_args() {
        let parsed = parse_pdf_helper_args([
            OsString::from("--tauri-dev"),
            OsString::from(PDF_HELPER_FLAG),
            OsString::from(PDF_HELPER_COUNT_PAGES),
            OsString::from("/tmp/input.pdf"),
            OsString::from("/tmp/result.json"),
        ])
        .expect("parse ok");

        match parsed {
            Some(PdfHelperCommand::CountPages {
                source,
                result_path,
            }) => {
                assert_eq!(source, PathBuf::from("/tmp/input.pdf"));
                assert_eq!(result_path, PathBuf::from("/tmp/result.json"));
            }
            other => panic!("expected CountPages, got {other:?}"),
        }
    }

    #[test]
    fn helper_args_parse_split_pages() {
        let parsed = parse_pdf_helper_args([
            OsString::from(PDF_HELPER_FLAG),
            OsString::from(PDF_HELPER_SPLIT_PAGES),
            OsString::from("/tmp/input.pdf"),
            OsString::from("/tmp/chunks"),
            OsString::from("20"),
            OsString::from("/tmp/result.json"),
        ])
        .expect("parse ok");

        match parsed {
            Some(PdfHelperCommand::SplitPages {
                source,
                output_dir,
                pages_per_chunk,
                result_path,
            }) => {
                assert_eq!(source, PathBuf::from("/tmp/input.pdf"));
                assert_eq!(output_dir, PathBuf::from("/tmp/chunks"));
                assert_eq!(pages_per_chunk, 20);
                assert_eq!(result_path, PathBuf::from("/tmp/result.json"));
            }
            other => panic!("expected SplitPages, got {other:?}"),
        }
    }

    #[test]
    fn pdf_processor_in_process_extracts_text_without_wasm() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        let result = run_pdf_processor_in_process(PdfWasmRunRequest {
            input_file: fixture,
            input_json: Some(serde_json::json!({ "op": "extract_text" })),
            session_id: "test-session".to_string(),
            wall_timeout_secs: 30,
            max_memory_bytes: 256 * 1024 * 1024,
            max_fuel: 1_000_000,
        })
        .expect("native pdf processor runs");

        assert_eq!(result.module, "pdf_processor");
        assert!(result.stdout.contains("pdf_processor: op=extract_text ok"));
        let output = result.output_json.expect("output json");
        let pages = output
            .get("pages")
            .and_then(Value::as_array)
            .expect("pages array");
        assert_eq!(pages.len(), 1);
    }

    #[test]
    fn pdf_processor_in_process_handles_page_range_contract() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        let result = run_pdf_processor_in_process(PdfWasmRunRequest {
            input_file: fixture,
            input_json: Some(serde_json::json!({
                "op": "extract_text",
                "page_range": [10, 20]
            })),
            session_id: "test-session".to_string(),
            wall_timeout_secs: 30,
            max_memory_bytes: 256 * 1024 * 1024,
            max_fuel: 1_000_000,
        })
        .expect("native pdf processor runs");

        let output = result.output_json.expect("output json");
        let pages = output
            .get("pages")
            .and_then(Value::as_array)
            .expect("pages array");
        assert!(pages.is_empty());
        assert_eq!(output.get("page_offset").and_then(Value::as_u64), Some(10));
        assert_eq!(output.get("total_pages").and_then(Value::as_u64), Some(1));
    }
}
