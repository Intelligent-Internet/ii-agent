//! Host-side file splitting for memory-sensitive chunk dispatch.
//!
//! The key problem: guest modules like `pdf_processor` use `lopdf` which
//! calls `Document::load()` on the full file — meaning even if we pass
//! `page_range: [1, 20]`, the guest still loads the full 200 MB into
//! linear memory before extracting the requested pages. This negates
//! the memory benefit of chunking.
//!
//! The fix: split the source file **on the host side** into smaller
//! files (one per chunk), then pass each chunk-file to its own sandbox
//! call. The guest sees a small file and stays within its memory budget.
//!
//! ## Scope
//!
//! v1 supports PDF splitting only. DOCX/XLSX/PPTX are fundamentally
//! different (zipped OOXML containers where you can't extract a subset
//! of pages without rewriting the entire archive), so they skip host-side
//! splitting and continue to pass the full file + range params to the
//! guest. This means large DOCX/XLSX/PPTX may still OOM in the guest,
//! which the skill body documents as a limitation.

use std::fs;
use std::path::{Path, PathBuf};

/// Split a PDF file into multiple smaller PDFs, each containing a
/// contiguous range of pages. Returns a list of `(chunk_file_path,
/// page_start, page_end)` tuples. The chunk files are written to
/// `output_dir` as `chunk_0.pdf`, `chunk_1.pdf`, etc.
///
/// If the file has fewer pages than `pages_per_chunk`, a single chunk
/// containing the entire document is returned.
///
/// This function uses `lopdf` on the host side (native, not sandboxed)
/// because it needs to parse the PDF structure to split pages.
pub fn split_pdf_pages(
    source: &Path,
    output_dir: &Path,
    pages_per_chunk: u32,
) -> Result<Vec<PdfChunkFile>, String> {
    // First pass: count pages without keeping the full doc in memory.
    let page_numbers = {
        let doc = lopdf::Document::load(source)
            .map_err(|e| format!("split_pdf: failed to load {}: {e}", source.display()))?;
        let pages = doc.get_pages();
        let mut nums: Vec<u32> = pages.keys().copied().collect();
        nums.sort_unstable();
        nums
        // `doc` drops here — releases memory before we start splitting.
    };
    let total = page_numbers.len() as u32;

    if total == 0 {
        return Ok(vec![]);
    }

    fs::create_dir_all(output_dir)
        .map_err(|e| format!("split_pdf: mkdir {}: {e}", output_dir.display()))?;

    let mut chunks = Vec::new();
    let mut chunk_idx = 0u32;
    let mut start = 0usize;

    while start < page_numbers.len() {
        let end = (start + pages_per_chunk as usize).min(page_numbers.len());
        let chunk_pages: std::collections::HashSet<u32> =
            page_numbers[start..end].iter().copied().collect();

        // Reload from disk for each chunk so we never hold more than
        // 1 copy of the document in memory at a time. This trades I/O
        // (re-read source N times) for memory (peak = 1× doc size
        // instead of N× doc size from cloning).
        let mut chunk_doc = lopdf::Document::load(source)
            .map_err(|e| format!("split_pdf: reload for chunk {chunk_idx}: {e}"))?;

        let pages_to_remove: Vec<u32> = chunk_doc
            .get_pages()
            .keys()
            .copied()
            .filter(|num| !chunk_pages.contains(num))
            .collect();
        for page_num in pages_to_remove {
            chunk_doc.delete_pages(&[page_num]);
        }

        let chunk_path = output_dir.join(format!("chunk_{chunk_idx}.pdf"));
        chunk_doc
            .save(&chunk_path)
            .map_err(|e| format!("split_pdf: save chunk_{chunk_idx}: {e}"))?;

        chunks.push(PdfChunkFile {
            path: chunk_path,
            page_start: (start as u32) + 1,
            page_end: end as u32,
            total_pages: total,
        });

        start = end;
        chunk_idx += 1;
        // `chunk_doc` drops here — memory freed before next iteration.
    }

    Ok(chunks)
}

/// Metadata about a host-side chunk file produced by [`split_pdf_pages`].
#[derive(Debug, Clone)]
pub struct PdfChunkFile {
    /// Path to the chunk PDF on the host filesystem.
    pub path: PathBuf,
    /// 1-based start page (inclusive) relative to the original document.
    pub page_start: u32,
    /// 1-based end page (inclusive) relative to the original document.
    pub page_end: u32,
    /// Total pages in the original document.
    pub total_pages: u32,
}


/// Count pages in a PDF without extracting content. Cheap compared to
/// full extraction — we only parse the xref table and page tree, never
/// decompress streams. Used by the chunker when it needs an accurate
/// page count rather than the size-based heuristic.
pub fn count_pdf_pages(source: &Path) -> Result<u32, String> {
    let doc = lopdf::Document::load(source)
        .map_err(|e| format!("count_pdf_pages: failed to load {}: {e}", source.display()))?;
    Ok(doc.get_pages().len() as u32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn count_pages_on_fixture() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        let count = count_pdf_pages(&fixture).expect("count ok");
        assert_eq!(count, 1);
    }

    #[test]
    fn split_single_page_produces_one_chunk() {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/hello.pdf");
        let output_dir = std::env::temp_dir().join(format!(
            "split-test-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or_default()
        ));
        let chunks = split_pdf_pages(&fixture, &output_dir, 10).expect("split ok");
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].page_start, 1);
        assert_eq!(chunks[0].page_end, 1);
        assert_eq!(chunks[0].total_pages, 1);
        assert!(chunks[0].path.exists());
        // Verify chunk is a valid PDF by loading it.
        let chunk_doc = lopdf::Document::load(&chunks[0].path).expect("chunk is valid pdf");
        assert_eq!(chunk_doc.get_pages().len(), 1);
        fs::remove_dir_all(&output_dir).ok();
    }
}
