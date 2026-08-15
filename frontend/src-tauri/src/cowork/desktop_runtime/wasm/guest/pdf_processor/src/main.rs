//! pdf_processor — WASI preview1 module for the desktop `pdf` skill.
//!
//! Execution contract (matches `pdf.skill.md`):
//!
//! * input:
//!   - `/workspace/input.json` — one of:
//!       - `{ "op": "extract_text" }`
//!       - `{ "op": "extract_text", "page_range": [start, end] }`
//!         where `start` and `end` are 1-based **inclusive** page
//!         numbers. If the range extends past the document, the module
//!         clamps to the last page. If `start > end` or the range is
//!         empty, the module returns `{"pages": []}` without error.
//!       - `{ "op": "metadata" }`
//!   - `/workspace/inputs/input.pdf` — the PDF to process
//! * output:
//!   - `/workspace/output.json` —
//!       - extract_text: `{ "pages": string[], "page_offset": n, "total_pages": m }`
//!         `page_offset` is the 1-based page number of the first entry
//!         in `pages`. `total_pages` is the document's full length.
//!         Host-side chunking relies on both fields to merge chunks back
//!         into document order.
//!       - metadata: `{ "title": ..., "author": ..., "page_count": n }`
//!   - stdout — a short human-readable line so the wasm_run tool result
//!     has something useful even when output.json is also present.
//! * exit code 0 on success, 1 on any failure.
//!
//! The module is compiled for `wasm32-wasip1` and loaded by the cowork
//! desktop WASM runtime. It deliberately depends only on `lopdf` + the
//! standard library so the binary stays small.

use std::fs;
use std::io::Write;

use lopdf::Document;
use serde_json::{json, Value};

const INPUT_JSON: &str = "/workspace/input.json";
const INPUT_PDF: &str = "/workspace/inputs/input.pdf";
const OUTPUT_JSON: &str = "/workspace/output.json";

fn main() {
    if let Err(error) = run() {
        let _ = writeln!(std::io::stderr(), "pdf_processor error: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let input = read_input()?;
    let document = Document::load(INPUT_PDF)
        .map_err(|error| format!("failed to load {INPUT_PDF}: {error}"))?;

    let output = match input.op.as_str() {
        "extract_text" => extract_text(&document, input.page_range.as_ref())?,
        "metadata" => metadata(&document)?,
        other => return Err(format!("unknown operation '{other}'")),
    };

    fs::write(OUTPUT_JSON, output.to_string())
        .map_err(|error| format!("failed to write {OUTPUT_JSON}: {error}"))?;

    println!("pdf_processor: op={} ok", input.op);
    Ok(())
}

struct InputSpec {
    op: String,
    /// Optional 1-based inclusive page range. `None` means "all pages".
    page_range: Option<(u32, u32)>,
}

fn read_input() -> Result<InputSpec, String> {
    let bytes = fs::read(INPUT_JSON)
        .map_err(|error| format!("failed to read {INPUT_JSON}: {error}"))?;
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|error| format!("failed to parse {INPUT_JSON}: {error}"))?;
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
                kind_of(other)
            ));
        }
    };
    Ok(InputSpec { op, page_range })
}

fn kind_of(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn extract_text(document: &Document, page_range: Option<&(u32, u32)>) -> Result<Value, String> {
    let pages = document.get_pages();
    let mut ordered: Vec<u32> = pages.keys().copied().collect();
    ordered.sort_unstable();
    let total_pages = ordered.len() as u32;

    // Determine the slice of `ordered` to extract.
    //
    // The range is 1-based inclusive on both ends to match the contract
    // in `pdf.skill.md`. We clamp both ends so the host-side chunker
    // does not need to know the document length up front: it can fire
    // [1, 50], [51, 100], ... and the last chunk will simply return
    // fewer pages than requested when it runs off the end.
    let (slice, page_offset) = if let Some(&(start, end)) = page_range {
        if start == 0 {
            return Err("page_range start must be 1 or greater".to_string());
        }
        if start > end {
            return Ok(json!({
                "pages": Vec::<String>::new(),
                "page_offset": start,
                "total_pages": total_pages,
            }));
        }
        let start_idx = (start - 1) as usize;
        if start_idx >= ordered.len() {
            return Ok(json!({
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

    let mut pages_out: Vec<String> = Vec::with_capacity(slice.len());
    for &page_num in slice {
        let text = document
            .extract_text(&[page_num])
            .map_err(|error| format!("page {page_num} extraction failed: {error}"))?;
        pages_out.push(text);
    }
    Ok(json!({
        "pages": pages_out,
        "page_offset": page_offset,
        "total_pages": total_pages,
    }))
}

fn metadata(document: &Document) -> Result<Value, String> {
    let page_count = document.get_pages().len();
    let info = document.trailer.get(b"Info").ok();
    let mut title: Option<String> = None;
    let mut author: Option<String> = None;
    if let Some(info_ref) = info {
        if let Ok(object_id) = info_ref.as_reference() {
            if let Ok(info_dict) = document.get_object(object_id).and_then(|o| o.as_dict()) {
                title = read_text_field(info_dict, b"Title");
                author = read_text_field(info_dict, b"Author");
            }
        }
    }
    Ok(json!({
        "title": title,
        "author": author,
        "page_count": page_count,
    }))
}

fn read_text_field(dict: &lopdf::Dictionary, key: &[u8]) -> Option<String> {
    let object = dict.get(key).ok()?;
    if let Ok(bytes) = object.as_str() {
        return Some(String::from_utf8_lossy(bytes).into_owned());
    }
    None
}
