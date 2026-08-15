---
name: xlsx
description: Desktop spreadsheet handling. CSV/TSV tasks use host tools directly. XLSX tasks use the isolated xlsx_processor WebAssembly module.
version: 0.1.0
runtime: mixed
wasm_module: xlsx_processor
---

You are about to work with spreadsheet files inside the selected desktop
folder. Read this body carefully — this skill splits cleanly between a
host path (CSV/TSV) and a sandbox path (XLSX) and the two should never
be confused.

# Decision tree

1. Is the file `.csv` or `.tsv`?
   → Use `Read` and `Edit` directly. These are plain text files. Do
     **not** call `wasm_run`.
2. Is the file `.xlsx` or `.xlsm`?
   → Content operations need the `xlsx_processor` WebAssembly module.
     That module is **not shipped** in this build (see below).
3. Is the task only filename-level?
   → Use `glob` / `list_dir` / `Bash` for both csv and xlsx.

# CSV / TSV — host path (works today)

Treat these as plain text. Typical tasks:

- `Read` a csv to show the first few rows
- `Edit` or `Write` to modify cells
- `grep` for a column value across many csv files
- `Bash` for batch rename or move

Never try to run a csv through `wasm_run` — there is no value in
isolating plain text parsing.

# XLSX / XLSM — sandbox path (shipped)

## list_sheets

Get an inventory of all sheets in the workbook with row/col counts.

```
wasm_run({
  "module": "xlsx_processor",
  "input_json": { "op": "list_sheets" },
  "input_files": [{ "path": "<path to .xlsx>", "name": "input.xlsx" }]
})
```

Response: `{ "sheets": [{"name": "Sheet1", "rows": 500, "cols": 12}, ...] }`

## read_sheet

Read all cell values from a named sheet.

```
wasm_run({
  "module": "xlsx_processor",
  "input_json": { "op": "read_sheet", "sheet": "<sheet name>" },
  "input_files": [{ "path": "<path>", "name": "input.xlsx" }]
})
```

Response: `{ "sheet": "...", "rows": [[cell, ...], ...], "row_offset": 1, "total_rows": N }`

### Optional row_range

```
wasm_run({
  "module": "xlsx_processor",
  "input_json": { "op": "read_sheet", "sheet": "Data", "row_range": [1, 100] },
  "input_files": [{ "path": "<path>", "name": "input.xlsx" }]
})
```

Out-of-range requests are clamped. Large files are automatically chunked
by the host and merged.

Do not try to open an `.xlsx` file with `Read` — it is a zipped OOXML
container. Do not try to `Edit` it — you will corrupt the zip.

# Formula safety (when the module ships)

When writing back cell values via `update_cells`, always:

1. `read_sheet` first to see whether the target cell already holds a
   formula.
2. If it does, ask the user before overwriting it with a plain value.
3. Never silently "fix" `#REF!`, `#N/A`, or `#VALUE!` — surface them in
   your summary.

# What to return to the user

- The list of spreadsheet files you inspected.
- Which path you took (host-csv vs sandbox-xlsx).
- Any operations that were gated on the missing xlsx module.
- Paths of any files you wrote back.
