//! Pptx-specific chunk planner.
//!
//! Like docx, pptx cannot be host-side split. For files > 100 MB the
//! planner raises memory to 1 GB and runs a single call.

use super::{ChunkPlan, ChunkPlanner};
use crate::cowork::desktop_runtime::RuntimeLimits;
use serde_json::Value;
use std::path::Path;
use std::time::Duration;

const SMALL_THRESHOLD: u64 = 20 * 1024 * 1024;
const LARGE_THRESHOLD: u64 = 100 * 1024 * 1024;
const MEDIUM_MEMORY: usize = 768 * 1024 * 1024;
const LARGE_MEMORY: usize = 1024 * 1024 * 1024;

#[derive(Debug, Default, Clone, Copy)]
pub struct PptxChunker;

impl ChunkPlanner for PptxChunker {
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
            .map_err(|e| format!("pptx chunker: stat {}: {e}", file_path.display()))?
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
    let mut limits = RuntimeLimits::defaults();
    limits.max_memory_bytes = LARGE_MEMORY;
    limits.wall_timeout = Duration::from_secs(120);
    ChunkPlan::Single { limits }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_file_single() {
        let plan = plan_from_size(5 * 1024 * 1024);
        assert!(matches!(plan, ChunkPlan::Single { .. }));
    }

    #[test]
    fn large_file_single_1gb() {
        let plan = plan_from_size(200 * 1024 * 1024);
        match plan {
            ChunkPlan::Single { limits } => {
                assert_eq!(limits.max_memory_bytes, LARGE_MEMORY);
            }
            _ => panic!("expected Single with 1GB"),
        }
    }
}
