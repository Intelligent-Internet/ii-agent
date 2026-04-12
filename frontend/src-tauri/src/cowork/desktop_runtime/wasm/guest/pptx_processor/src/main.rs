//! pptx_processor — WASI preview1 module for the desktop `pptx` skill.
//!
//! Execution contract (matches `pptx.skill.md`):
//!
//! * input:
//!   - `/workspace/input.json` — one of:
//!       - `{ "op": "extract_text" }`
//!       - `{ "op": "extract_text", "slide_range": [start, end] }`
//!       - `{ "op": "count_slides" }`
//!   - `/workspace/inputs/input.pptx` — the presentation to process
//! * output:
//!   - `/workspace/output.json`:
//!       extract_text: `{ "slides": [{"index": n, "text": string}], "slide_offset": n, "total_slides": m }`
//!       count_slides: `{ "total_slides": n }`
//!   - stdout — short "ok" line
//! * exit code 0 on success, 1 on any failure.
//!
//! pptx is an OOXML zip container. Slide text lives in
//! `ppt/slides/slideN.xml` where N is a 1-based index. For v1 we:
//!
//! 1. Enumerate every `ppt/slides/slide*.xml` entry in the zip.
//! 2. Sort them by numeric index (slide1, slide2, ... slide10).
//! 3. For each slide in scope, parse the XML and concatenate every
//!    `<a:t>` text run into a single string.
//!
//! This is the minimum viable slide text extraction. It intentionally
//! ignores speaker notes (`ppt/notesSlides/...`), comments, and layout
//! metadata — those are future ops.

use std::fs;
use std::io::{Cursor, Write};

use quick_xml::events::Event;
use quick_xml::reader::Reader;
use serde_json::{json, Value};
use zip::ZipArchive;

const INPUT_JSON: &str = "/workspace/input.json";
const INPUT_PPTX: &str = "/workspace/inputs/input.pptx";
const OUTPUT_JSON: &str = "/workspace/output.json";

fn main() {
    if let Err(error) = run() {
        let _ = writeln!(std::io::stderr(), "pptx_processor error: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let input = read_input()?;
    let bytes = fs::read(INPUT_PPTX)
        .map_err(|error| format!("failed to read {INPUT_PPTX}: {error}"))?;
    let mut archive = ZipArchive::new(Cursor::new(bytes))
        .map_err(|error| format!("pptx zip open failed: {error}"))?;

    let slides = collect_slide_entries(&mut archive)?;

    let output = match input.op.as_str() {
        "extract_text" => extract_text(&mut archive, &slides, input.slide_range.as_ref())?,
        "count_slides" => json!({ "total_slides": slides.len() as u64 }),
        other => return Err(format!("unknown operation '{other}'")),
    };

    fs::write(OUTPUT_JSON, output.to_string())
        .map_err(|error| format!("failed to write {OUTPUT_JSON}: {error}"))?;
    println!("pptx_processor: op={} ok", input.op);
    Ok(())
}

struct InputSpec {
    op: String,
    slide_range: Option<(u32, u32)>,
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
    let slide_range = parse_range(&value, "slide_range")?;
    Ok(InputSpec { op, slide_range })
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

/// One zip entry representing a slide, pre-sorted by 1-based slide
/// number.
struct SlideEntry {
    /// 1-based slide index (`ppt/slides/slide1.xml` → 1).
    index: u32,
    /// Path inside the archive, used to `by_name` lookup the raw bytes
    /// at extraction time.
    path: String,
}

fn collect_slide_entries<R: std::io::Read + std::io::Seek>(
    archive: &mut ZipArchive<R>,
) -> Result<Vec<SlideEntry>, String> {
    let mut entries: Vec<SlideEntry> = Vec::new();
    for index in 0..archive.len() {
        let file = archive
            .by_index(index)
            .map_err(|error| format!("pptx archive read failed: {error}"))?;
        let name = file.name().to_string();
        if let Some(slide_index) = parse_slide_path(&name) {
            entries.push(SlideEntry {
                index: slide_index,
                path: name,
            });
        }
    }
    entries.sort_by_key(|entry| entry.index);
    Ok(entries)
}

/// Match `ppt/slides/slideN.xml` (case-sensitive, the OOXML spec fixes
/// the casing). Returns the 1-based slide number on match.
fn parse_slide_path(path: &str) -> Option<u32> {
    let file_name = path.strip_prefix("ppt/slides/")?;
    if !file_name.ends_with(".xml") {
        return None;
    }
    let stem = &file_name[..file_name.len() - 4];
    let number = stem.strip_prefix("slide")?;
    // Reject `slideLayoutN.xml`, `slideMasterN.xml`, etc.
    if !number.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    number.parse().ok()
}

fn extract_text<R: std::io::Read + std::io::Seek>(
    archive: &mut ZipArchive<R>,
    entries: &[SlideEntry],
    range: Option<&(u32, u32)>,
) -> Result<Value, String> {
    let total = entries.len() as u32;
    let (slice, offset) = if let Some(&(start, end)) = range {
        if start == 0 {
            return Err("slide_range start must be 1 or greater".to_string());
        }
        if start > end {
            return Ok(json!({
                "slides": Vec::<Value>::new(),
                "slide_offset": start,
                "total_slides": total,
            }));
        }
        let start_idx = (start - 1) as usize;
        if start_idx >= entries.len() {
            return Ok(json!({
                "slides": Vec::<Value>::new(),
                "slide_offset": start,
                "total_slides": total,
            }));
        }
        let end_idx = (end as usize).min(entries.len());
        (&entries[start_idx..end_idx], start)
    } else {
        (entries, 1u32)
    };

    let mut slides_out: Vec<Value> = Vec::with_capacity(slice.len());
    for entry in slice {
        let mut zip_file = archive
            .by_name(&entry.path)
            .map_err(|error| format!("pptx: cannot read {}: {}", entry.path, error))?;
        let mut xml_bytes = Vec::new();
        std::io::copy(&mut zip_file, &mut xml_bytes)
            .map_err(|error| format!("pptx: zip read failed: {error}"))?;
        let text = extract_slide_text(&xml_bytes)?;
        slides_out.push(json!({
            "index": entry.index,
            "text": text,
        }));
    }

    Ok(json!({
        "slides": slides_out,
        "slide_offset": offset,
        "total_slides": total,
    }))
}

/// Walk a slide XML document and return every `<a:t>` run concatenated.
/// Text inside different paragraphs is joined with a single newline so
/// the agent can reconstruct reading order without parsing structure.
fn extract_slide_text(xml_bytes: &[u8]) -> Result<String, String> {
    let mut reader = Reader::from_reader(xml_bytes);
    reader.config_mut().trim_text(true);
    let mut in_text = false;
    let mut in_paragraph = false;
    let mut current_paragraph = String::new();
    let mut paragraphs: Vec<String> = Vec::new();
    let mut buf = Vec::new();

    loop {
        match reader
            .read_event_into(&mut buf)
            .map_err(|error| format!("pptx xml parse error: {error}"))?
        {
            Event::Start(e) => {
                let name = e.name();
                let local = name.as_ref();
                if local.ends_with(b":t") || local == b"t" {
                    in_text = true;
                } else if local.ends_with(b":p") || local == b"p" {
                    in_paragraph = true;
                    current_paragraph.clear();
                }
            }
            Event::End(e) => {
                let name = e.name();
                let local = name.as_ref();
                if local.ends_with(b":t") || local == b"t" {
                    in_text = false;
                } else if local.ends_with(b":p") || local == b"p" {
                    in_paragraph = false;
                    if !current_paragraph.is_empty() {
                        paragraphs.push(current_paragraph.clone());
                    }
                }
            }
            Event::Text(t) if in_text && in_paragraph => {
                let decoded = t
                    .unescape()
                    .map_err(|error| format!("pptx xml unescape error: {error}"))?;
                current_paragraph.push_str(&decoded);
            }
            Event::Eof => break,
            _ => {}
        }
        buf.clear();
    }

    Ok(paragraphs.join("\n"))
}
