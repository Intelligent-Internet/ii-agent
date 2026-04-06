use crate::cowork::organize::sessions::CoworkChatSessionDetail;

pub fn build_organize_prompt_context(session: &CoworkChatSessionDetail) -> String {
    format!(
        "You are assisting in II Cowork organize-file-folder mode.\n\
You are working on the user's real local desktop folder.\n\
Your job is to inspect, understand, clean up, and reorganize files inside that folder based on the user's request.\n\n\
[Operating rules]\n\
- Work only inside the selected local folder.\n\
- Understand the current structure before changing it.\n\
- Always read relevant files before modifying them when the decision depends on file content, meaning, or purpose.\n\
- Do not reorganize semantic content based only on filenames when content inspection is needed.\n\
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
- `TodoWrite` - Keep a short task checklist during the run\n\n\
[Local organize scope and context]\n\
Mode scope: organize-file-folder\n\
Input folder path: {}\n",
        session.organize_tree_pair.source_root,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cowork::organize::file_tree::{FileTreeNode, FileTreeNodeKind};

    fn sample_folder(name: &str) -> FileTreeNode {
        FileTreeNode {
            id: format!("folder::{name}"),
            name: name.to_string(),
            kind: FileTreeNodeKind::Folder,
            extension: None,
            size: None,
            children: Some(Vec::new()),
        }
    }

    fn sample_session() -> CoworkChatSessionDetail {
        CoworkChatSessionDetail {
            base: crate::cowork::chat::CoworkChatSessionDetail {
                id: "cowork-organize-1".to_string(),
                scope: crate::cowork::chat::CoworkChatScope::OrganizeFileFolder,
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
            organize_tree_pair: crate::cowork::organize::sessions::CoworkOrganizeTreePair {
                source_root: "C:/demo".to_string(),
                result_root: "C:/demo".to_string(),
                source_tree: sample_folder("demo"),
                result_tree: None,
            },
        }
    }

    #[test]
    fn build_organize_prompt_context_includes_scope_and_tool_guidance() {
        let prompt = build_organize_prompt_context(&sample_session());

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
}
