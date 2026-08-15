//! Module freshness check utilities.
//!
//! At compile time, `include_bytes!` embeds the `.wasm` file bytes into
//! the binary. But there's no mechanism to detect if the `.wasm` file
//! is stale (older than the guest source code). This module provides a
//! runtime check that can log a warning if the compiled module timestamp
//! is older than expected. This is purely a dev-experience helper and
//! does not affect production behavior.
//!
//! ## Usage
//!
//! Call `check_module_freshness()` during runtime startup (e.g., inside
//! `register_builtin_modules`). It compares the mtime of source files
//! against the mtime of the compiled .wasm artifact. If the source is
//! newer, it can print a warning to stderr when explicitly enabled.
//!
//! In release builds (production), this is a no-op because the paths
//! are relative to the source tree which doesn't exist on end-user
//! machines.
//!
//! To avoid noisy logs during normal desktop development, warnings are
//! disabled by default. Set `II_AGENT_WASM_FRESHNESS_WARN=1` (or `true`,
//! `yes`, `on`) to enable them.

use std::path::Path;

/// Check whether a compiled `.wasm` module is fresh relative to its
/// guest source. Returns `true` if fresh or if the check cannot be
/// performed (missing files, release build, etc.).
///
/// Logs a warning to stderr when stale if
/// `II_AGENT_WASM_FRESHNESS_WARN` is enabled.
pub fn check_freshness(module_name: &str, wasm_path: &str, source_dir: &str) -> bool {
    let wasm = Path::new(wasm_path);
    let source = Path::new(source_dir);

    if !wasm.exists() || !source.exists() {
        return true; // can't check — assume fresh
    }

    let wasm_mtime = match wasm.metadata().and_then(|m| m.modified()) {
        Ok(t) => t,
        Err(_) => return true,
    };

    // Walk source dir and find the newest .rs file.
    let newest_source = match find_newest_rs(source) {
        Some(t) => t,
        None => return true,
    };

    if newest_source > wasm_mtime {
        if !warnings_enabled() {
            return false;
        }
        eprintln!(
            "[warn] desktop_runtime: module '{module_name}' may be stale. \
            Source in {source_dir} is newer than {wasm_path}. \
            Rebuild with: cd {source_dir} && cargo build --target wasm32-wasip1 --release && cp target/wasm32-wasip1/release/{module_name}.wasm {wasm_path}"
        );
        return false;
    }
    true
}

fn warnings_enabled() -> bool {
    std::env::var("II_AGENT_WASM_FRESHNESS_WARN")
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(false)
}

fn find_newest_rs(dir: &Path) -> Option<std::time::SystemTime> {
    let mut newest: Option<std::time::SystemTime> = None;
    let entries = std::fs::read_dir(dir).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if let Some(t) = find_newest_rs(&path) {
                newest = Some(newest.map_or(t, |cur| cur.max(t)));
            }
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            if let Ok(mtime) = path.metadata().and_then(|m| m.modified()) {
                newest = Some(newest.map_or(mtime, |cur| cur.max(mtime)));
            }
        }
    }
    newest
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_freshness_returns_true_for_missing_paths() {
        assert!(check_freshness("foo", "/nonexistent/foo.wasm", "/nonexistent/src"));
    }
}
