use crate::cowork::intelligent_folder::sessions::CoworkChatSessionDetail;

pub fn build_folder_prompt_context(session: &CoworkChatSessionDetail) -> String {
    format!(
        "You are assisting in II Cowork intelligent-folder mode.\n\
You are working on the user's real local desktop folder.\n\
Your job is to inspect, understand, clean up, and refolder files inside that folder based on the user's request.\n\n\
[Operating rules]\n\
- Work only inside the selected local folder.\n\
- Understand the current structure before changing it.\n\
- Always read relevant files before modifying them when the decision depends on file content, meaning, or purpose.\n\
- Do not refolder semantic content based only on filenames when content inspection is needed.\n\
- For purely structural tasks such as grouping by extension, renaming obvious folders, or moving generated files, you may act from directory structure alone when that is sufficient.\n\
- Keep changes scoped, intentional, and easy to explain.\n\
- Preserve user content unless the request clearly asks for renaming, regrouping, cleanup, or rewrites.\n\
- If no file changes are needed, explain that clearly instead of forcing edits.\n\
- When you do make changes, summarize the affected paths and the reason for each group of changes.\n\n\
[Recommended approach]\n\
1. Start with `list_dir` to inspect the current folder layout.\n\
2. Use `glob` and `grep` to narrow down relevant files.\n\
3. Use `Read` on files that matter before making content-aware decisions.\n\
4. Form a short plan.\n\
5. Make only the necessary changes.\n\
6. Summarize what changed and why.\n\n\
[Desktop tools available]\n\
- `list_dir` - List directories and files inside the selected folder\n\
- `glob` - Find files by path patterns or extensions\n\
- `grep` - Search file contents by text pattern\n\
- `Read` - Read local text files\n\
- `Write` - Create or overwrite local files\n\
- `Edit` - Make exact text replacements in local files\n\
- `apply_patch` - Apply structured multi-file edits\n\
- `Bash` - Execute shell commands inside the selected folder\n\
- `TodoWrite` - Keep a short task checklist during the run\n\
- `desktop_skill_run` - Load the full body of a desktop skill by name. Call this first whenever you plan to process a complex document format (pdf, docx, xlsx, pptx). It returns markdown instructions and the exact `wasm_run` shape you should use next. It does NOT execute anything itself.\n\
- `wasm_run` - Execute a WebAssembly module inside the isolated desktop runtime. Only call this after you have read the relevant skill body via `desktop_skill_run` and know the exact module name, input_json, and input_files shape to use. You may also call it directly when debugging a specific module.\n\n\
[Desktop skills available]\n\
Skills are packaged guidance backed by the desktop WebAssembly runtime. To use a skill, follow the two-step flow:\n\
1. Call `desktop_skill_run(skill_name=<name>)` to load the skill's body and operation contracts into context.\n\
2. Follow the body: usually it tells you to call `wasm_run` with a specific module and shape. Copy that shape exactly.\n\
Built-in skills:\n\
- `pdf` - PDF text extraction and metadata via the `pdf_processor` isolated runtime.\n\
- `docx` - Word document text extraction via the `docx_processor` isolated runtime.\n\
- `xlsx` - Spreadsheet reading via the `xlsx_processor` isolated runtime (csv/tsv use host tools directly).\n\
- `pptx` - Presentation slide text extraction via the `pptx_processor` isolated runtime.\n\
Decision rule:\n\
- Plain text, markdown, code, or csv/tsv files: use `Read`, `Write`, `Edit`, `grep` directly. Do not touch skills.\n\
- `.pdf`, `.docx`, `.xlsx`, `.pptx`: call `desktop_skill_run` first to read instructions, then follow them.\n\
- If a skill body reports that its WebAssembly module is not shipped yet, tell the user what is unavailable and offer filename-level operations instead. Never try to edit a binary container (.docx, .xlsx, .pptx are all zipped OOXML) with `Edit` or `Write` — you will corrupt the file.\n\n\
[Local folder scope and context]\n\
Mode scope: intelligent-folder\n\
Input folder path: {}\n",
        session.folder_tree_pair.source_root,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cowork::intelligent_folder::file_tree::{FileTreeNode, FileTreeNodeKind};

    fn sample_folder(name: &str) -> FileTreeNode {
        FileTreeNode {
            id: format!("folder::{name}"),
            name: name.to_string(),
            kind: FileTreeNodeKind::Folder,
            extension: None,
            size: None,
            last_modified: None,
            children: Some(Vec::new()),
        }
    }

    fn sample_session() -> CoworkChatSessionDetail {
        CoworkChatSessionDetail {
            base: crate::cowork::chat::CoworkChatSessionDetail {
                id: "cowork-folder-1".to_string(),
                scope: crate::cowork::chat::CoworkChatScope::IntelligentFolder,
                title: "demo".to_string(),
                preview: "demo".to_string(),
                updated_at: "2026-04-04T00:00:00.000Z".to_string(),
                message_count: 0,
                runtime_kind: None,
                runtime_session_id: None,
                messages: Vec::new(),
                runtime_events: Vec::new(),
                files: Vec::new(),
                run_status: crate::cowork::chat::CoworkChatRunStatus::Idle,
            },
            folder_tree_pair: crate::cowork::intelligent_folder::sessions::CoworkFolderTreePair {
                source_root: "C:/demo".to_string(),
                result_root: "C:/demo".to_string(),
                source_tree: sample_folder("demo"),
                result_tree: None,
            },
            undo_state: crate::cowork::intelligent_folder::sessions::FolderUndoState::default(),
        }
    }

    #[test]
    fn build_folder_prompt_context_includes_scope_and_tool_guidance() {
        let prompt = build_folder_prompt_context(&sample_session());

        assert!(prompt.contains("[Operating rules]"));
        assert!(prompt.contains("[Recommended approach]"));
        assert!(prompt.contains("[Desktop tools available]"));
        assert!(prompt.contains("Input folder path: C:/demo"));
        assert!(prompt.contains("Always read relevant files before modifying them"));
        assert!(prompt.contains("Start with `list_dir` to inspect the current folder layout"));
        assert!(
            prompt.contains("- `list_dir` - List directories and files inside the selected folder")
        );
        assert!(prompt.contains("- `Read` - Read local text files"));
        assert!(prompt.contains("- `Edit` - Make exact text replacements in local files"));
        assert!(prompt.contains("- `Bash` - Execute shell commands inside the selected folder"));
    }

    #[test]
    fn build_folder_prompt_context_advertises_two_step_flow() {
        let prompt = build_folder_prompt_context(&sample_session());
        assert!(prompt.contains("- `desktop_skill_run`"));
        assert!(prompt.contains("- `wasm_run`"));
        assert!(prompt.contains("[Desktop skills available]"));
        assert!(prompt.contains("- `pdf`"));
        assert!(prompt.contains("- `docx`"));
        assert!(prompt.contains("- `xlsx`"));
        assert!(prompt.contains("- `pptx`"));
        assert!(prompt.contains("Decision rule:"));
        // Two-step flow must be spelled out explicitly.
        assert!(prompt.contains("two-step flow"));
        assert!(prompt.contains("desktop_skill_run(skill_name="));
        assert!(prompt.contains("Follow the body"));
        // The prompt must tell the LLM not to edit binary containers.
        assert!(prompt.contains("corrupt the file"));
    }
}
