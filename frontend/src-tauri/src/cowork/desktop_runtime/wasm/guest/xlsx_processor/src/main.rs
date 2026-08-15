//! xlsx_processor — WASI preview1 module for the desktop `xlsx` skill.
//!
//! Execution contract (matches `xlsx.skill.md`):
//!
//! * input:
//!   - `/workspace/input.json` — one of:
//!       - `{ "op": "list_sheets" }`
//!       - `{ "op": "read_sheet", "sheet": "<name>" }`
//!       - `{ "op": "read_sheet", "sheet": "<name>", "row_range": [start, end] }`
//!         1-based inclusive row numbers. Out-of-range requests clamp
//!         to the sheet's used range.
//!   - `/workspace/inputs/input.xlsx` — the workbook to process
//! * output:
//!   - `/workspace/output.json`:
//!       list_sheets: `{ "sheets": [{"name": string, "rows": n, "cols": m}] }`
//!       read_sheet:  `{ "sheet": string, "rows": Value[][], "row_offset": n, "total_rows": m }`
//!   - stdout — short "ok" line
//! * exit code 0 on success, 1 on any failure.
//!
//! calamine is a pure-Rust xlsx/xls/ods reader. It compiles cleanly to
//! `wasm32-wasip1` with `default-features = false`. Writing workbooks
//! back is not supported in v1 because it would pull in a separate
//! writer crate; write-back is a future skill op.

use std::io::{Cursor, Write};
use std::{fs, io};

use calamine::{open_workbook_auto_from_rs, Data, Reader};
use serde_json::{json, Value};

const INPUT_JSON: &str = "/workspace/input.json";
const INPUT_XLSX: &str = "/workspace/inputs/input.xlsx";
const OUTPUT_JSON: &str = "/workspace/output.json";

fn main() {
    if let Err(error) = run() {
        let _ = writeln!(io::stderr(), "xlsx_processor error: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let input = read_input()?;
    // calamine's `open_workbook_auto_from_rs` requires `Read + Seek +
    // Clone`. `Cursor<Vec<u8>>` satisfies all three (BufReader does
    // not — BufReader is not Clone), so we pass the cursor directly.
    let bytes = fs::read(INPUT_XLSX)
        .map_err(|error| format!("failed to read {INPUT_XLSX}: {error}"))?;
    let cursor = Cursor::new(bytes);
    let mut workbook = open_workbook_auto_from_rs(cursor)
        .map_err(|error| format!("xlsx open failed: {error}"))?;

    let output = match input.op.as_str() {
        "list_sheets" => list_sheets(&mut workbook)?,
        "read_sheet" => read_sheet(
            &mut workbook,
            input
                .sheet
                .as_deref()
                .ok_or_else(|| "read_sheet requires a 'sheet' name".to_string())?,
            input.row_range.as_ref(),
        )?,
        other => return Err(format!("unknown operation '{other}'")),
    };

    fs::write(OUTPUT_JSON, output.to_string())
        .map_err(|error| format!("failed to write {OUTPUT_JSON}: {error}"))?;
    println!("xlsx_processor: op={} ok", input.op);
    Ok(())
}

struct InputSpec {
    op: String,
    sheet: Option<String>,
    row_range: Option<(u32, u32)>,
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
    let sheet = value
        .get("sheet")
        .and_then(Value::as_str)
        .map(str::to_string);
    let row_range = parse_range(&value, "row_range")?;
    Ok(InputSpec {
        op,
        sheet,
        row_range,
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

type Workbook = calamine::Sheets<Cursor<Vec<u8>>>;

fn list_sheets(workbook: &mut Workbook) -> Result<Value, String> {
    let names: Vec<String> = workbook.sheet_names().to_vec();
    let mut sheets = Vec::with_capacity(names.len());
    for name in names {
        let range = workbook
            .worksheet_range(&name)
            .map_err(|error| format!("worksheet_range({name}) failed: {error}"))?;
        let rows = range.height() as u64;
        let cols = range.width() as u64;
        sheets.push(json!({
            "name": name,
            "rows": rows,
            "cols": cols,
        }));
    }
    Ok(json!({ "sheets": sheets }))
}

fn read_sheet(
    workbook: &mut Workbook,
    sheet_name: &str,
    range_hint: Option<&(u32, u32)>,
) -> Result<Value, String> {
    let range = workbook
        .worksheet_range(sheet_name)
        .map_err(|error| format!("worksheet_range({sheet_name}) failed: {error}"))?;
    let total_rows = range.height() as u32;

    // Materialise the sheet into rows-of-cells.
    let mut rows: Vec<Vec<Value>> = Vec::with_capacity(range.height());
    for row in range.rows() {
        let mut cells = Vec::with_capacity(row.len());
        for cell in row {
            cells.push(cell_to_json(cell));
        }
        rows.push(cells);
    }

    let (slice, offset): (Vec<Vec<Value>>, u32) = if let Some(&(start, end)) = range_hint {
        if start == 0 {
            return Err("row_range start must be 1 or greater".to_string());
        }
        if start > end || start as usize > rows.len() {
            (Vec::new(), start)
        } else {
            let start_idx = (start - 1) as usize;
            let end_idx = (end as usize).min(rows.len());
            (rows[start_idx..end_idx].to_vec(), start)
        }
    } else {
        (rows, 1u32)
    };

    Ok(json!({
        "sheet": sheet_name,
        "rows": slice,
        "row_offset": offset,
        "total_rows": total_rows,
    }))
}

/// Convert a calamine cell into a JSON value. We avoid using
/// `serde_json::to_value(&Data)` because calamine's `Data` enum uses
/// a serde tag format that is unhelpful for the LLM to read; we flatten
/// to plain JSON primitives instead.
fn cell_to_json(cell: &Data) -> Value {
    match cell {
        Data::Empty => Value::Null,
        Data::String(s) => Value::String(s.clone()),
        Data::Float(f) => serde_json::Number::from_f64(*f)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        Data::Int(i) => Value::from(*i),
        Data::Bool(b) => Value::Bool(*b),
        Data::DateTime(dt) => Value::String(dt.as_f64().to_string()),
        Data::Error(e) => Value::String(format!("#ERROR: {e:?}")),
        Data::DurationIso(s) => Value::String(s.clone()),
        Data::DateTimeIso(s) => Value::String(s.clone()),
    }
}

