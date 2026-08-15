---
name: pdf
description: Desktop PDF processing via an isolated WebAssembly module. Supports plain text extraction and basic metadata.
version: 0.1.0
runtime: wasm
wasm_module: pdf_processor
---

You are about to work with a PDF file inside the selected desktop folder.
Read this entire body, then pick the section that matches the user's
request and copy the `wasm_run` call shape exactly.

# When to use this skill

Use it when the task requires reading text, metadata, or structural
information from a `.pdf` file. Do not use it for:

- plain text, markdown, code, or csv files — use `Read` directly
- moving or renaming pdf files by filename — use `Bash` or `glob`
- tasks where only the filename matters — stay on the host

# Host first, sandbox second

Always do cheap host work first and only reach into the sandbox when you
actually need the pdf content:

1. Use `list_dir` / `glob` to find the pdf files you care about.
2. If the user only cares about filenames or folder structure, answer
   from host tools and stop.
3. If you need the pdf's content (to summarise, translate, classify,
   extract fields, answer questions about it) call `wasm_run` with one
   of the shapes below.
4. Read the result from `output.json` and continue reasoning in the
   agent turn.

The isolated runtime enforces memory, fuel, and wall-clock limits for
you. Trust them — do not try to pre-chunk unless a previous call came
back with an out-of-memory error.

# Operations

## extract_text

Extract one string per page in reading order. Use this for
summarisation, content search, translation, or any task that needs the
raw text of the document.

Call it with:

```
wasm_run({
  "module": "pdf_processor",
  "input_json": { "op": "extract_text" },
  "input_files": [
    { "path": "<relative or absolute path to the pdf>", "name": "input.pdf" }
  ]
})
```

The `name` field must be `"input.pdf"` — the pdf_processor module only
reads `/workspace/inputs/input.pdf`.

On success the tool result contains an `output.json` block of the form:

```
{
  "pages": ["page 1 text", "page 2 text", ...],
  "page_offset": 1,
  "total_pages": <number>
}
```

`page_offset` is the 1-based page number of the first entry in `pages`;
when you did not pass a `page_range` it will always be `1`. `total_pages`
is the document's full page count. Join the pages yourself if you need a
single flat string — each page already ends with a newline.

### Optional page_range

You may pass `page_range: [start, end]` (1-based, inclusive) inside
`input_json` to extract a subset. Out-of-range requests are clamped: if
a document has 180 pages and you ask for `[201, 250]`, the guest returns
`{"pages": [], "page_offset": 201, "total_pages": 180}` without error.

Use this only when the user explicitly asks for a specific slice — you
do **not** need to chunk large PDFs by hand. The host automatically
splits very large files into sequential chunks and merges the results
back before returning to you, so you always see a single combined
`pages` array in the tool result (plus a `chunk_summary` section
reporting how many chunks were run).

```
wasm_run({
  "module": "pdf_processor",
  "input_json": { "op": "extract_text", "page_range": [1, 5] },
  "input_files": [
    { "path": "<path to the pdf>", "name": "input.pdf" }
  ]
})
```

## metadata

Get the document's title, author, and page count. Use this for
inventory reports, sorting, or to decide whether a document is worth
extracting fully.

```
wasm_run({
  "module": "pdf_processor",
  "input_json": { "op": "metadata" },
  "input_files": [
    { "path": "<path to the pdf>", "name": "input.pdf" }
  ]
})
```

`output.json` will look like:

```
{ "title": "<string or null>", "author": "<string or null>", "page_count": <number> }
```

# Error handling

- If `wasm_run` reports `unknown module 'pdf_processor'`, the pdf
  runtime has not been shipped with this build. Tell the user that pdf
  content extraction is unavailable in this version and offer
  filename-level operations instead.
- If `wasm_run` reports a memory limit error, the pdf is too large to
  process in a single call. Tell the user the file is oversized and
  suggest splitting it manually. Page-range chunking is not yet
  supported by the module.
- If `wasm_run` reports an execution error mentioning `load failed` or
  `invalid file trailer`, the file is corrupt or not a real pdf. Do not
  retry — report the file path and move on.
- Never try to "fix" a pdf by using `Edit` or `Write` on it. pdf is a
  binary format and any byte-level edit will corrupt it.

# Multi-file workflow

For batch jobs (for example "summarise every pdf in this folder"):

1. `glob` pattern `**/*.pdf` to list the files.
2. Call `wasm_run` with `op: extract_text` once per file.
3. Between calls, keep per-file results in your reasoning — do not try
   to pass multiple pdfs into a single wasm_run call.
4. When you have all the text, compose the final answer.

# What to return to the user

Always tell the user:

- how many files you inspected
- which operation(s) you ran against each
- a short summary of the extracted content, grouped by file path
- any files that failed, with the exact error message
