//! PDF-specific chunk planner.
//!
//! Classifies a PDF file by **file size on disk** (no parsing) and
//! picks a page-range chunk granularity that keeps individual guest
//! Store memory usage within the 256 MB ceiling. This is a heuristic —
//! it does not know the actual page count of the document, it only
//! knows the file size. The guest module clamps out-of-range chunk
//! requests gracefully, so overshoot is safe: if we ask for pages
//! `[201, 250]` on a 180-page document, the guest returns an empty
//! `pages` array for that chunk rather than erroring out.
//!
//! ## Heuristic
//!
//! | File size | Plan | Pages per chunk |
//! |---|---|---|
//! | ≤ 20 MB  | Single (default limits) | — |
//! | 20–100 MB | Single (larger memory ceiling) | — |
//! | > 100 MB | Multi, sequential | 20 |
//!
//! The chunk count for the "Multi" bucket is hard-capped at
//! [`MAX_CHUNKS`] so a pathologically large file cannot generate
//! thousands of wasm calls. In practice this means the host gives up
//! on documents larger than ~6 GB and falls back to a single
//! best-effort call with raised limits.
//!
//! Only `extract_text` is chunkable in v1. Any other op routes through
//! the default single-call plan.

use super::splitter;
use super::{Chunk, ChunkPlan, ChunkPlanner, MergeStrategy};
use crate::cowork::desktop_runtime::RuntimeLimits;
use serde_json::{json, Value};
use std::path::Path;
use std::time::Duration;

/// Upper bound on the number of chunks the planner will emit for a
/// single call. Prevents runaway multi-call dispatch on pathologically
/// large files.
pub const MAX_CHUNKS: usize = 256;

/// Page count per chunk in the "large file" bucket. Tuned so the
/// guest-side `lopdf` parser can process the slice comfortably inside
/// the 256 MB Store limit for typical PDFs.
pub const LARGE_FILE_CHUNK_PAGES: u32 = 20;

/// Very rough per-page PDF size estimate used to turn "how big is the
/// file" into "how many pages does this cover, roughly". 50 KB per
/// page is pessimistic enough that the last chunk usually overshoots
/// the real document — and the guest clamps overshoot to an empty
/// `pages` array, so we are always safe to ask for more than the
/// document holds.
const BYTES_PER_PAGE_ESTIMATE: u64 = 50 * 1024;

/// File size threshold at which the plan stops using default limits
/// and starts either bumping memory or splitting the call.
const SMALL_FILE_THRESHOLD: u64 = 20 * 1024 * 1024;

/// File size threshold at which the plan switches from "single call
/// with larger memory" to "multi chunk".
const LARGE_FILE_THRESHOLD: u64 = 100 * 1024 * 1024;

/// Memory ceiling for the medium bucket. 768 MB gives lopdf room to
/// parse mid-size PDFs without forcing a multi-call dispatch.
const MEDIUM_MEMORY_BYTES: usize = 768 * 1024 * 1024;

/// Memory ceiling for chunked calls. Kept at 512 MB because the chunk
/// size is already small (20 pages) so we rarely need more.
const CHUNKED_MEMORY_BYTES: usize = 512 * 1024 * 1024;

/// Wall-clock deadline for a single chunked call. Chunked calls are
/// each smaller than a full extraction, so they finish faster; 60 s is
/// generous.
const CHUNK_WALL_TIMEOUT_SECS: u64 = 60;

#[derive(Debug, Default, Clone, Copy)]
pub struct PdfChunker;

impl ChunkPlanner for PdfChunker {
    fn plan(
        &self,
        file_path: &Path,
        op: &str,
        _base_input_json: &Value,
    ) -> Result<Option<ChunkPlan>, String> {
        // Only extract_text benefits from chunking — metadata is a
        // constant-time read that already fits in any memory budget.
        if op != "extract_text" {
            return Ok(None);
        }

        let metadata = std::fs::metadata(file_path).map_err(|error| {
            format!(
                "pdf chunker: cannot stat {} for chunk planning: {}",
                file_path.display(),
                error
            )
        })?;
        let size = metadata.len();

        // For large files, use the real page count from `lopdf` on the
        // host side so chunk boundaries are accurate. For small/medium
        // files where memory is not at risk, skip the extra parse.
        if size > LARGE_FILE_THRESHOLD {
            return Ok(Some(plan_large_file(
                file_path,
                size,
                splitter::count_pdf_pages(file_path),
            )?));
        }

        Ok(Some(plan_from_size(size)))
    }
}

fn plan_large_file(
    file_path: &Path,
    size: u64,
    page_count: Result<u32, String>,
) -> Result<ChunkPlan, String> {
    let real_page_count = page_count.map_err(|error| {
        format!(
            "pdf chunker: failed to count pages for large PDF {}: {error}",
            file_path.display()
        )
    })?;
    Ok(plan_from_page_count(real_page_count, size))
}

/// Plan using the real page count (available for large PDFs parsed on
/// the host side via [`splitter::count_pdf_pages`]).
pub fn plan_from_page_count(page_count: u32, _file_size: u64) -> ChunkPlan {
    if page_count == 0 {
        return ChunkPlan::single_default();
    }

    let chunk_pages = LARGE_FILE_CHUNK_PAGES;
    let ideal_chunks = page_count.div_ceil(chunk_pages).max(1) as usize;

    if ideal_chunks <= 1 {
        // Small number of pages — even though the file is large (heavy
        // images), a single call should be fine with raised memory.
        let mut limits = RuntimeLimits::defaults();
        limits.max_memory_bytes = MEDIUM_MEMORY_BYTES;
        limits.wall_timeout = Duration::from_secs(120);
        return ChunkPlan::Single { limits };
    }

    if ideal_chunks > MAX_CHUNKS {
        let mut limits = RuntimeLimits::defaults();
        limits.max_memory_bytes = MEDIUM_MEMORY_BYTES;
        limits.wall_timeout = Duration::from_secs(180);
        return ChunkPlan::Single { limits };
    }

    let mut chunks = Vec::with_capacity(ideal_chunks);
    let mut chunk_limits = RuntimeLimits::defaults();
    chunk_limits.max_memory_bytes = CHUNKED_MEMORY_BYTES;
    chunk_limits.wall_timeout = Duration::from_secs(CHUNK_WALL_TIMEOUT_SECS);

    // For accurate chunking, use the `split_source` flag that tells
    // the wasm_run dispatcher to call the host-side splitter instead
    // of passing a page_range param to the guest with the full file.
    // This is handled externally by checking whether the chunk plan
    // was built with real page counts; see `plan.uses_host_splitting`.
    for index in 0..ideal_chunks {
        let start = (index as u32) * chunk_pages + 1;
        let end = (start + chunk_pages - 1).min(page_count);
        chunks.push(Chunk {
            index,
            label: format!("pages {start}-{end}"),
            input_json_overlay: json!({
                "page_range": [start, end]
            }),
            limits: chunk_limits,
        });
    }

    ChunkPlan::Multi {
        chunks,
        merge: MergeStrategy::PdfExtractTextPages,
        use_host_split: true, // accurate page count → host can split
    }
}

/// Pure decision function — extracted so tests can drive the heuristic
/// with synthetic sizes without touching the filesystem.
pub fn plan_from_size(size: u64) -> ChunkPlan {
    if size <= SMALL_FILE_THRESHOLD {
        return ChunkPlan::Single {
            limits: RuntimeLimits::defaults(),
        };
    }

    if size <= LARGE_FILE_THRESHOLD {
        let mut limits = RuntimeLimits::defaults();
        limits.max_memory_bytes = MEDIUM_MEMORY_BYTES;
        return ChunkPlan::Single { limits };
    }

    // Large file: multi-chunk plan.
    //
    // Estimate the page count from the file size, then split into
    // `LARGE_FILE_CHUNK_PAGES` page chunks. Cap at MAX_CHUNKS so a
    // 100 GB corrupted input cannot generate 2 million wasm_run calls.
    let estimated_pages = ((size + BYTES_PER_PAGE_ESTIMATE - 1) / BYTES_PER_PAGE_ESTIMATE) as u32;
    let chunk_pages = LARGE_FILE_CHUNK_PAGES;
    let ideal_chunks = estimated_pages.div_ceil(chunk_pages).max(1) as usize;

    if ideal_chunks > MAX_CHUNKS {
        // Fall back to a single oversized call rather than spawning
        // thousands of wasm invocations. The user will see a memory
        // error if this fails — at that point the right answer is
        // "too big, split manually", which the skill body documents.
        let mut limits = RuntimeLimits::defaults();
        limits.max_memory_bytes = MEDIUM_MEMORY_BYTES;
        limits.wall_timeout = Duration::from_secs(180);
        return ChunkPlan::Single { limits };
    }

    let mut chunks = Vec::with_capacity(ideal_chunks);
    let mut chunk_limits = RuntimeLimits::defaults();
    chunk_limits.max_memory_bytes = CHUNKED_MEMORY_BYTES;
    chunk_limits.wall_timeout = Duration::from_secs(CHUNK_WALL_TIMEOUT_SECS);

    for index in 0..ideal_chunks {
        let start = (index as u32) * chunk_pages + 1;
        let end = start + chunk_pages - 1;
        chunks.push(Chunk {
            index,
            label: format!("pages {start}-{end}"),
            input_json_overlay: json!({
                "page_range": [start, end]
            }),
            limits: chunk_limits,
        });
    }

    ChunkPlan::Multi {
        chunks,
        merge: MergeStrategy::PdfExtractTextPages,
        use_host_split: false, // size-only heuristic → no real page count
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn small_file_is_single_with_default_limits() {
        let plan = plan_from_size(5 * 1024 * 1024); // 5 MB
        match plan {
            ChunkPlan::Single { limits } => {
                assert_eq!(
                    limits.max_memory_bytes,
                    RuntimeLimits::defaults().max_memory_bytes
                );
            }
            other => panic!("expected Single, got {:?}", other),
        }
    }

    #[test]
    fn medium_file_is_single_with_raised_memory() {
        let plan = plan_from_size(50 * 1024 * 1024); // 50 MB
        match plan {
            ChunkPlan::Single { limits } => {
                assert_eq!(limits.max_memory_bytes, MEDIUM_MEMORY_BYTES);
            }
            other => panic!("expected Single, got {:?}", other),
        }
    }

    #[test]
    fn large_file_is_multi_with_page_ranges() {
        let plan = plan_from_size(200 * 1024 * 1024); // 200 MB
        match plan {
            ChunkPlan::Multi { chunks, merge, .. } => {
                assert_eq!(merge, MergeStrategy::PdfExtractTextPages);
                assert!(
                    !chunks.is_empty() && chunks.len() <= MAX_CHUNKS,
                    "chunk count {} should be reasonable",
                    chunks.len()
                );
                // Verify chunks form contiguous, non-overlapping ranges starting at 1.
                let first = chunks.first().unwrap();
                let overlay = first.input_json_overlay.as_object().expect("overlay obj");
                let range = overlay
                    .get("page_range")
                    .and_then(|v| v.as_array())
                    .expect("page_range array");
                assert_eq!(range[0].as_u64(), Some(1));
                assert_eq!(range[1].as_u64(), Some(LARGE_FILE_CHUNK_PAGES as u64));
                // Second chunk starts right after the first.
                let second = &chunks[1];
                let overlay2 = second.input_json_overlay.as_object().expect("overlay obj");
                let range2 = overlay2
                    .get("page_range")
                    .and_then(|v| v.as_array())
                    .expect("page_range array");
                assert_eq!(range2[0].as_u64(), Some(LARGE_FILE_CHUNK_PAGES as u64 + 1));
            }
            other => panic!("expected Multi, got {:?}", other),
        }
    }

    #[test]
    fn pathologically_large_file_falls_back_to_single() {
        // 100 GB — far above the MAX_CHUNKS threshold at 20 pages ×
        // 50 KB per page = 1 MB per chunk. 100 GB / 1 MB = 100_000
        // chunks >> MAX_CHUNKS. The planner should refuse to generate
        // that many and fall back to a single oversized call.
        let plan = plan_from_size(100 * 1024 * 1024 * 1024);
        assert!(
            matches!(plan, ChunkPlan::Single { .. }),
            "expected Single fallback, got {:?}",
            plan
        );
    }

    #[test]
    fn large_file_page_count_failure_does_not_fall_back_to_heuristic() {
        let err = plan_large_file(
            Path::new("/tmp/heavy.pdf"),
            LARGE_FILE_THRESHOLD + 1,
            Err("helper crashed".to_string()),
        )
        .expect_err("large-file helper failure should be surfaced");

        assert!(err.contains("failed to count pages for large PDF /tmp/heavy.pdf"));
        assert!(err.contains("helper crashed"));
    }

    #[test]
    fn non_extract_text_op_is_none() {
        let chunker = PdfChunker::default();
        // Even if we point at a real file that exists, metadata op
        // should bypass chunking.
        let tempdir = std::env::temp_dir();
        let result = chunker.plan(&tempdir, "metadata", &Value::Null).unwrap();
        assert!(result.is_none());
    }

    /// End-to-end wiring: hand the real planner the small fixture PDF
    /// from `tests/fixtures/`. It is well under 20 MB so the plan must
    /// be a Single with default limits. This proves that the I/O path
    /// works (stat the file, size bucket, return plan).
    #[test]
    fn small_fixture_pdf_is_single_plan() {
        let fixture =
            std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        assert!(fixture.exists(), "fixture missing: {}", fixture.display());
        let chunker = PdfChunker::default();
        let plan = chunker
            .plan(&fixture, "extract_text", &Value::Null)
            .expect("plan ok");
        match plan {
            Some(ChunkPlan::Single { limits }) => {
                assert_eq!(
                    limits.max_memory_bytes,
                    RuntimeLimits::defaults().max_memory_bytes
                );
            }
            other => panic!("expected Single, got {:?}", other),
        }
    }
}
