---
name: pptx
description: Desktop presentation handling via an isolated WebAssembly module. Supports slide text extraction and slide counting.
version: 0.1.0
runtime: wasm
wasm_module: pptx_processor
---

You are about to work with PowerPoint files inside the selected desktop
folder. Read this body, then pick the operation that matches the task.

# When to use this skill

Use when the task requires reading slide text from a `.pptx` file.
Do NOT use for plain text/md/txt files (use `Read` directly) or for
tasks that only care about filenames (use `glob`/`list_dir`).

# Host first, sandbox second

1. Use `glob` / `list_dir` to find `.pptx` files.
2. If the task only needs filenames → answer from host tools.
3. If you need slide content → call `wasm_run` below.
4. Never `Read` or `Edit` a `.pptx` file — it is a zip container.

# Operations

## extract_text

Extract all slide text in slide order.

```
wasm_run({
  "module": "pptx_processor",
  "input_json": { "op": "extract_text" },
  "input_files": [{ "path": "<path to .pptx>", "name": "input.pptx" }]
})
```

Response `output.json`:
```
{
  "slides": [{"index": 1, "text": "..."}, {"index": 2, "text": "..."}, ...],
  "slide_offset": 1,
  "total_slides": N
}
```

### Optional slide_range

```
wasm_run({
  "module": "pptx_processor",
  "input_json": { "op": "extract_text", "slide_range": [1, 10] },
  "input_files": [{ "path": "<path>", "name": "input.pptx" }]
})
```

Out-of-range requests are clamped. Large files are automatically chunked
by the host.

## count_slides

```
wasm_run({
  "module": "pptx_processor",
  "input_json": { "op": "count_slides" },
  "input_files": [{ "path": "<path>", "name": "input.pptx" }]
})
```

Response: `{ "total_slides": N }`

# Error handling

- Memory limit error → file too large, report to user.
- `pptx zip open failed` → corrupt file, do not retry.
- Never try to edit a `.pptx` with `Edit`.

# What to return to the user

- Files inspected and operations run.
- Per-slide text summaries when applicable.
- Any errors encountered with file paths.
