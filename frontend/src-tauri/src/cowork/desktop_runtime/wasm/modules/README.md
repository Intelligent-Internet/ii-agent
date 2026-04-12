# Desktop WASM guest modules

This directory holds the compiled `.wasm` artifacts that are bundled into
the desktop binary at compile time via `include_bytes!` in
[`../mod.rs`](../mod.rs).

Each file here is produced by building a crate under [`../guest/`](../guest/)
for the `wasm32-wasip1` target. The bytes are then copied into this
directory and registered with the runtime's `ModuleRegistry` when
`WasmRuntime::new()` runs.

## Rebuilding a module

After editing any guest crate (for example, `../guest/pdf_processor/`):

```bash
cd src/cowork/desktop_runtime/wasm/guest/pdf_processor
rustup target add wasm32-wasip1    # only needed once
cargo build --target wasm32-wasip1 --release

# Copy the compiled artifact into this modules/ directory so
# include_bytes! picks up the new bytes on the next cargo check.
cp target/wasm32-wasip1/release/pdf_processor.wasm ../../modules/pdf_processor.wasm
```

Then run `cargo check` on the top-level `src-tauri` crate — it will
recompile the host binary with the new guest bytes embedded.

## Freshness warnings

The desktop runtime can detect when a guest module's source is newer than
the compiled `.wasm` artifact, but that warning is disabled by default to
avoid noisy local logs.

If you want to see the warning while debugging, start the desktop app with
`II_AGENT_WASM_FRESHNESS_WARN=1`.

## Why separate `guest/` and `modules/`?

- `guest/` holds *source code* for the WASM programs. Each guest is its
  own cargo crate with its own dependency tree and its own target
  triple (`wasm32-wasip1`). These crates are **not** part of the main
  `src-tauri` workspace — cargo does not walk into them during normal
  host builds.
- `modules/` holds the *compiled bytes* that the host embeds at
  compile time. These bytes are the only thing the running desktop app
  sees; the guest source code is only needed when you want to change
  what a skill does inside the sandbox.

Keeping the source and the artifact separate means the host crate
(`src-tauri`) depends on exactly one file per module — the
`.wasm` artifact — instead of triggering a `wasm32-wasip1` toolchain
build on every `cargo check`.

## Current modules

| File | Built from | Used by skill |
|------|------------|----------------|
| `pdf_processor.wasm` | `../guest/pdf_processor/` | `pdf` (extract_text, metadata) |

`docx`, `xlsx`, and `pptx` are registered as skills but do not yet have
corresponding WASM modules. Calls targeting those modules will return a
clear "module not registered" error until their guest crates are added
here.
