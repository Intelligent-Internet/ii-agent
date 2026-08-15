//! docx_processor — WASI preview1 module for the desktop `docx` skill.
//!
//! Execution contract (matches `docx.skill.md`):
//!
//! * input:
//!   - `/workspace/input.json` — one of:
//!       - `{ "op": "extract_text" }`
//!       - `{ "op": "extract_text", "paragraph_range": [start, end] }`
//!         1-based inclusive paragraph numbers. Out-of-range requests
//!         are clamped to the document length.
//!       - `{ "op": "count_paragraphs" }`
//!   - `/workspace/inputs/input.docx` — the Word document to process
//! * output:
//!   - `/workspace/output.json` — for extract_text:
//!       `{ "paragraphs": string[], "paragraph_offset": n, "total_paragraphs": m }`
//!     for count_paragraphs:
//!       `{ "total_paragraphs": n }`
//!   - stdout — short "ok" line for human debugging
//! * exit code 0 on success, 1 on any failure.
//!
//! docx-rs is a pure-Rust DOCX reader/writer; it compiles cleanly to
//! `wasm32-wasip1` with `default-features = false`. The module stays
//! small because it only uses the reader path.

use std::fs;
use std::io::Write;

use docx_rs::*;
use serde_json::{json, Value};

const INPUT_JSON: &str = "/workspace/input.json";
const INPUT_DOCX: &str = "/workspace/inputs/input.docx";
const OUTPUT_JSON: &str = "/workspace/output.json";

fn main() {
    if let Err(error) = run() {
        let _ = writeln!(std::io::stderr(), "docx_processor error: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let input = read_input()?;
    let bytes = fs::read(INPUT_DOCX)
        .map_err(|error| format!("failed to read {INPUT_DOCX}: {error}"))?;
    let doc = read_docx(&bytes).map_err(|error| format!("docx parse failed: {error:?}"))?;

    let paragraphs = collect_paragraphs(&doc);

    let output = match input.op.as_str() {
        "extract_text" => extract_text(&paragraphs, input.paragraph_range.as_ref())?,
        "count_paragraphs" => json!({ "total_paragraphs": paragraphs.len() as u64 }),
        other => return Err(format!("unknown operation '{other}'")),
    };

    fs::write(OUTPUT_JSON, output.to_string())
        .map_err(|error| format!("failed to write {OUTPUT_JSON}: {error}"))?;
    println!("docx_processor: op={} ok", input.op);
    Ok(())
}

struct InputSpec {
    op: String,
    paragraph_range: Option<(u32, u32)>,
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
        .ok_or_else(|| "input.json is missing 'op'".to_string())?;
    let paragraph_range = parse_range(&value, "paragraph_range")?;
    Ok(InputSpec {
        op,
        paragraph_range,
    })
}

fn parse_range(value: &Value, key: &str) -> Result<Option<(u32, u32)>, String> {
    match value.get(key) {
        Some(Value::Null) | None => Ok(None),
        Some(Value::Array(items)) => {
            if items.len() != 2 {
                return Err(format!(
                    "{key} must be a 2-element array, got {}",
                    items.len()
                ));
            }
            let start = items[0]
                .as_u64()
                .ok_or_else(|| format!("{key}[0] must be a non-negative integer"))?;
            let end = items[1]
                .as_u64()
                .ok_or_else(|| format!("{key}[1] must be a non-negative integer"))?;
            Ok(Some((start as u32, end as u32)))
        }
        Some(other) => Err(format!("{key} must be array or null, got {other:?}")),
    }
}

/// Walk the docx document tree and collect every paragraph's plain
/// text in reading order. We intentionally flatten away run styling,
/// tables, headers, footers — v1 only cares about body text. Future
/// ops can walk the tree more carefully.
fn collect_paragraphs(doc: &Docx) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for child in &doc.document.children {
        if let DocumentChild::Paragraph(p) = child {
            out.push(paragraph_text(p));
        }
    }
    out
}

fn paragraph_text(paragraph: &Paragraph) -> String {
    let mut text = String::new();
    for child in &paragraph.children {
        if let ParagraphChild::Run(run) = child {
            for run_child in &run.children {
                if let RunChild::Text(t) = run_child {
                    text.push_str(&t.text);
                }
            }
        }
    }
    text
}

fn extract_text(paragraphs: &[String], range: Option<&(u32, u32)>) -> Result<Value, String> {
    let total = paragraphs.len() as u32;
    let (slice, offset) = if let Some(&(start, end)) = range {
        if start == 0 {
            return Err("paragraph_range start must be 1 or greater".to_string());
        }
        if start > end {
            return Ok(json!({
                "paragraphs": Vec::<String>::new(),
                "paragraph_offset": start,
                "total_paragraphs": total,
            }));
        }
        let start_idx = (start - 1) as usize;
        if start_idx >= paragraphs.len() {
            return Ok(json!({
                "paragraphs": Vec::<String>::new(),
                "paragraph_offset": start,
                "total_paragraphs": total,
            }));
        }
        let end_idx = (end as usize).min(paragraphs.len());
        (&paragraphs[start_idx..end_idx], start)
    } else {
        (&paragraphs[..], 1u32)
    };

    Ok(json!({
        "paragraphs": slice,
        "paragraph_offset": offset,
        "total_paragraphs": total,
    }))
}
