---
name: docx
description: Desktop Word document handling via an isolated WebAssembly module. Supports text extraction and paragraph counting.
version: 0.1.0
runtime: wasm
wasm_module: docx_processor
---

You are about to work with a Word document inside the selected desktop
folder. Read this body, then pick the operation that matches the task.

# When to use this skill

Use when the task requires reading the body text of a `.docx` file.
Do NOT use for plain text/md/txt files (use `Read` directly), or for
tasks that only care about filenames (use `glob`/`list_dir`).

# Host first, sandbox second

1. Use `glob` / `list_dir` to find the `.docx` files.
2. If the task only needs filenames or folder structure, answer from
   host tools and stop.
3. If you need the document content, call `wasm_run` below.
4. Never try to `Read` or `Edit` a `.docx` file directly — it is a
   zipped OOXML container and any byte-level operation will corrupt it
   or produce gibberish.

# Operations

## extract_text

Extract all paragraph text in reading order.

```
wasm_run({
  "module": "docx_processor",
  "input_json": { "op": "extract_text" },
  "input_files": [{ "path": "<path to .docx>", "name": "input.docx" }]
})
```

Response `output.json`:
```
{ "paragraphs": ["...", "..."], "paragraph_offset": 1, "total_paragraphs": N }
```

### Optional paragraph_range

```
wasm_run({
  "module": "docx_processor",
  "input_json": { "op": "extract_text", "paragraph_range": [1, 100] },
  "input_files": [{ "path": "<path>", "name": "input.docx" }]
})
```

Out-of-range requests are clamped. The host automatically chunks large
files and merges results — you always see one combined array.

## count_paragraphs

```
wasm_run({
  "module": "docx_processor",
  "input_json": { "op": "count_paragraphs" },
  "input_files": [{ "path": "<path>", "name": "input.docx" }]
})
```

Response: `{ "total_paragraphs": N }`

# Error handling

- If `wasm_run` reports a memory limit error, the docx is too large.
  Report this to the user.
- If `wasm_run` reports `docx parse failed`, the file is corrupt.
- Never try to "fix" a .docx file with `Edit` — you will corrupt it.

# What to return to the user

- Files inspected and operations run.
- Relevant paragraph text or summaries.
- Any errors encountered with file paths.
