//! Docx-specific chunk planner.
//!
//! OOXML containers (docx) cannot be host-side split like PDF because
//! they share internal resources (styles, relationships, numbering).
//! For files > 100 MB the planner raises the memory ceiling to 1 GB
//! and lets the guest parse the full file in a single call.

use super::{ChunkPlan, ChunkPlanner};
use crate::cowork::desktop_runtime::RuntimeLimits;
use serde_json::Value;
use std::path::Path;
use std::time::Duration;

const SMALL_THRESHOLD: u64 = 20 * 1024 * 1024;
const LARGE_THRESHOLD: u64 = 100 * 1024 * 1024;
const MEDIUM_MEMORY: usize = 768 * 1024 * 1024;
const LARGE_MEMORY: usize = 1024 * 1024 * 1024; // 1 GB

#[derive(Debug, Default, Clone, Copy)]
pub struct DocxChunker;

impl ChunkPlanner for DocxChunker {
    fn plan(
        &self,
        file_path: &Path,
        op: &str,
        _base: &Value,
    ) -> Result<Option<ChunkPlan>, String> {
        if op != "extract_text" {
            return Ok(None);
        }
        let size = std::fs::metadata(file_path)
            .map_err(|e| format!("docx chunker: stat {}: {e}", file_path.display()))?
            .len();
        Ok(Some(plan_from_size(size)))
    }
}

pub fn plan_from_size(size: u64) -> ChunkPlan {
    if size <= SMALL_THRESHOLD {
        return ChunkPlan::single_default();
    }
    if size <= LARGE_THRESHOLD {
        let mut limits = RuntimeLimits::defaults();
        limits.max_memory_bytes = MEDIUM_MEMORY;
        return ChunkPlan::Single { limits };
    }
    // > 100 MB: single call with raised memory (1 GB) and extended
    // timeout. Multi-chunk is pointless because the guest (docx-rs)
    // loads the full zip container before slicing by paragraph range.
    let mut limits = RuntimeLimits::defaults();
    limits.max_memory_bytes = LARGE_MEMORY;
    limits.wall_timeout = Duration::from_secs(120);
    ChunkPlan::Single { limits }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_file_single_default_limits() {
        let plan = plan_from_size(5 * 1024 * 1024);
        match plan {
            ChunkPlan::Single { limits } => {
                assert_eq!(limits.max_memory_bytes, RuntimeLimits::defaults().max_memory_bytes);
            }
            _ => panic!("expected Single"),
        }
    }

    #[test]
    fn medium_file_single_raised_memory() {
        let plan = plan_from_size(50 * 1024 * 1024);
        match plan {
            ChunkPlan::Single { limits } => {
                assert_eq!(limits.max_memory_bytes, MEDIUM_MEMORY);
            }
            _ => panic!("expected Single"),
        }
    }

    #[test]
    fn large_file_single_1gb_memory() {
        let plan = plan_from_size(200 * 1024 * 1024);
        match plan {
            ChunkPlan::Single { limits } => {
                assert_eq!(limits.max_memory_bytes, LARGE_MEMORY);
                assert_eq!(limits.wall_timeout, Duration::from_secs(120));
            }
            _ => panic!("expected Single with 1GB, got Multi"),
        }
    }
}
