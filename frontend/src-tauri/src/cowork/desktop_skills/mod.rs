//! Desktop skills: first-class local capabilities the agent can reason about.
//!
//! A *skill* is a packaged piece of guidance that tells the agent how to
//! approach a class of tasks (for example, "process a PDF file"). Unlike a
//! tool, a skill is not invoked directly by the model — it surfaces to the
//! agent as a descriptor (name + short description) that the backend
//! agent reads before planning, and the full body is available for the
//! agent to pull in when it decides the skill is relevant.
//!
//! ## Package layout
//!
//! The desktop app owns skill storage. Built-in skills live as Markdown
//! files in `assets/desktop_skills/` and are bundled into the binary via
//! [`include_str!`]. Each skill file has YAML-like frontmatter and a
//! Markdown body:
//!
//! ```markdown
//! ---
//! name: pdf
//! description: Isolated PDF processing on the desktop runtime.
//! version: 0.1.0
//! triggers: pdf document processing, pdf text extraction
//! runtime: wasm
//! wasm_module: pdf_processor
//! tools: Read, wasm_run
//! ---
//!
//! # PDF Skill
//!
//! ...
//! ```
//!
//! All frontmatter fields except `name` and `description` are optional.
//! `runtime` picks between `host` (the skill is host-tool driven) and
//! `wasm` (the skill expects an isolated runtime call through
//! `wasm_run`).
//!
//! ## Registry
//!
//! [`common_desktop_skills`] returns the canonical set of built-in
//! skills. Callers that want mode-specific additions merge their own
//! lists, just like the desktop tool layer does. Skill discovery and
//! metadata parsing happen at this layer — downstream code should never
//! parse the raw Markdown directly.
//!
//! ## Tool surface
//!
//! The desktop skill module also owns the `desktop_skill_run` tool
//! (see [`desktop_skill_run`]). That tool lives here — not in the
//! generic `desktop_tools/` folder — because its only job is to load a
//! skill body into the agent's context. Execution of the isolated
//! runtime stays in [`crate::cowork::desktop_tools::wasm_run`].

#![allow(dead_code)]

pub mod desktop_skill_run;

use crate::cowork::agent_presets::shared::DesktopSkillCapability;

/// Target runtime for a desktop skill. Guides the agent on when to reach
/// for isolated execution versus normal host tools.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SkillRuntime {
    /// The skill expects to drive the host tools (Read/Write/Edit/Bash).
    Host,
    /// The skill expects to call into the WASM runtime via `wasm_run`.
    Wasm,
    /// The skill may use either runtime depending on the task.
    Mixed,
}

impl SkillRuntime {
    fn parse(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "host" => Some(Self::Host),
            "wasm" => Some(Self::Wasm),
            "mixed" | "host+wasm" | "wasm+host" => Some(Self::Mixed),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            SkillRuntime::Host => "host",
            SkillRuntime::Wasm => "wasm",
            SkillRuntime::Mixed => "mixed",
        }
    }
}

/// Parsed skill frontmatter. All optional fields are surfaced so tests
/// can inspect them directly.
#[derive(Debug, Clone)]
pub struct SkillFrontmatter {
    pub name: String,
    pub description: String,
    pub version: Option<String>,
    pub triggers: Vec<String>,
    pub runtime: SkillRuntime,
    pub wasm_module: Option<String>,
    pub tools: Vec<String>,
}

/// A fully loaded desktop skill: frontmatter + Markdown body.
#[derive(Debug, Clone)]
pub struct DesktopSkill {
    pub frontmatter: SkillFrontmatter,
    pub body: String,
}

impl DesktopSkill {
    pub fn name(&self) -> &str {
        self.frontmatter.name.as_str()
    }

    pub fn description(&self) -> &str {
        self.frontmatter.description.as_str()
    }

    pub fn runtime(&self) -> SkillRuntime {
        self.frontmatter.runtime
    }

    pub fn wasm_module(&self) -> Option<&str> {
        self.frontmatter.wasm_module.as_deref()
    }

    pub fn tools(&self) -> &[String] {
        &self.frontmatter.tools
    }

    pub fn body(&self) -> &str {
        self.body.as_str()
    }

    /// Consume the skill and return only its capability descriptor (the
    /// part that is sent to the backend agent).
    pub fn into_capability(self) -> DesktopSkillCapability {
        DesktopSkillCapability {
            name: self.frontmatter.name,
            description: self.frontmatter.description,
        }
    }
}

/// Parse a Markdown document with YAML-like frontmatter into a skill.
///
/// The parser accepts the minimal subset of frontmatter used by desktop
/// skills:
///
/// * A document beginning with `---\n`.
/// * `key: value` pairs until the next `---` line.
/// * Comma-separated values for `triggers` and `tools`.
/// * A Markdown body after the closing `---`.
pub fn parse_skill_document(source: &str) -> Result<DesktopSkill, String> {
    let mut lines = source.lines();
    let first = lines
        .next()
        .ok_or_else(|| "skill document is empty".to_string())?;
    if first.trim() != "---" {
        return Err("skill document must start with '---' frontmatter".to_string());
    }

    let mut frontmatter_lines: Vec<&str> = Vec::new();
    let mut closed = false;
    for line in lines.by_ref() {
        if line.trim() == "---" {
            closed = true;
            break;
        }
        frontmatter_lines.push(line);
    }
    if !closed {
        return Err("skill document is missing a closing '---'".to_string());
    }

    let mut name: Option<String> = None;
    let mut description: Option<String> = None;
    let mut version: Option<String> = None;
    let mut triggers: Vec<String> = Vec::new();
    let mut runtime: SkillRuntime = SkillRuntime::Host;
    let mut wasm_module: Option<String> = None;
    let mut tools: Vec<String> = Vec::new();

    for raw in frontmatter_lines {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let (key, value) = line
            .split_once(':')
            .ok_or_else(|| format!("invalid frontmatter line '{}'", raw))?;
        let key = key.trim().to_ascii_lowercase();
        let value = strip_quotes(value.trim());
        match key.as_str() {
            "name" => name = Some(value.to_string()),
            "description" => description = Some(value.to_string()),
            "version" => version = Some(value.to_string()),
            "triggers" => triggers = split_list(value),
            "runtime" => {
                runtime = SkillRuntime::parse(value).ok_or_else(|| {
                    format!(
                        "unknown runtime '{}'. Expected host, wasm, or mixed",
                        value
                    )
                })?;
            }
            "wasm_module" => wasm_module = Some(value.to_string()),
            "tools" => tools = split_list(value),
            "license" => { /* ignored but accepted for backward compatibility */ }
            other => {
                return Err(format!("unknown frontmatter key '{}'", other));
            }
        }
    }

    let name = name.ok_or_else(|| "skill frontmatter is missing 'name'".to_string())?;
    let description = description
        .ok_or_else(|| "skill frontmatter is missing 'description'".to_string())?;

    let body: String = lines.collect::<Vec<_>>().join("\n");

    Ok(DesktopSkill {
        frontmatter: SkillFrontmatter {
            name,
            description,
            version,
            triggers,
            runtime,
            wasm_module,
            tools,
        },
        body: body.trim_start_matches('\n').to_string(),
    })
}

fn strip_quotes(value: &str) -> &str {
    let value = value.trim();
    if value.len() >= 2 {
        let bytes = value.as_bytes();
        let first = bytes[0];
        let last = bytes[value.len() - 1];
        if (first == b'"' && last == b'"') || (first == b'\'' && last == b'\'') {
            return &value[1..value.len() - 1];
        }
    }
    value
}

fn split_list(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(|piece| piece.trim().to_string())
        .filter(|piece| !piece.is_empty())
        .collect()
}

// -----------------------------------------------------------------------
// Built-in skill registry
// -----------------------------------------------------------------------

/// Raw Markdown source for the built-in skills. Bundled into the binary
/// at compile time so the desktop app does not depend on any runtime
/// filesystem layout. Skill files live in
/// `src-tauri/assets/desktop_skills/` and are edited as plain Markdown.
const BUILTIN_PDF_SKILL: &str = include_str!("pdf.skill.md");
const BUILTIN_DOCX_SKILL: &str = include_str!("docx.skill.md");
const BUILTIN_XLSX_SKILL: &str = include_str!("xlsx.skill.md");
const BUILTIN_PPTX_SKILL: &str = include_str!("pptx.skill.md");

/// Canonical set of built-in desktop skills.
pub fn common_desktop_skills() -> Vec<DesktopSkill> {
    [
        BUILTIN_PDF_SKILL,
        BUILTIN_DOCX_SKILL,
        BUILTIN_XLSX_SKILL,
        BUILTIN_PPTX_SKILL,
    ]
    .into_iter()
    .map(|source| {
        parse_skill_document(source)
            .unwrap_or_else(|error| panic!("built-in skill failed to parse: {error}"))
    })
    .collect()
}

/// Descriptors for all built-in desktop skills (the lightweight shape
/// that gets shipped to the backend agent).
pub fn common_desktop_skill_capabilities() -> Vec<DesktopSkillCapability> {
    common_desktop_skills()
        .into_iter()
        .map(DesktopSkill::into_capability)
        .collect()
}

/// Look up a built-in desktop skill by name. Returns `None` if the name
/// does not match any registered skill. Used when the agent asks for the
/// body of a skill by name.
pub fn find_builtin_skill(name: &str) -> Option<DesktopSkill> {
    let normalized = name.trim().to_ascii_lowercase();
    common_desktop_skills()
        .into_iter()
        .find(|skill| skill.name().eq_ignore_ascii_case(&normalized))
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "---\n\
name: sample\n\
description: A sample skill used only in tests.\n\
version: 0.1.0\n\
triggers: foo, bar, baz\n\
runtime: wasm\n\
wasm_module: sample_module\n\
tools: Read, wasm_run\n\
---\n\
\n\
# Sample\n\
\n\
Body text.\n";

    #[test]
    fn parses_frontmatter_and_body() {
        let skill = parse_skill_document(SAMPLE).expect("parses");
        assert_eq!(skill.name(), "sample");
        assert_eq!(skill.description(), "A sample skill used only in tests.");
        assert_eq!(skill.runtime(), SkillRuntime::Wasm);
        assert_eq!(skill.wasm_module(), Some("sample_module"));
        assert_eq!(skill.tools(), &["Read".to_string(), "wasm_run".to_string()]);
        assert_eq!(
            skill.frontmatter.triggers,
            vec!["foo".to_string(), "bar".to_string(), "baz".to_string()]
        );
        assert_eq!(skill.frontmatter.version.as_deref(), Some("0.1.0"));
        assert!(skill.body().contains("Body text."));
    }

    #[test]
    fn rejects_missing_name() {
        let source = "---\ndescription: nope\n---\nBody\n";
        let error = parse_skill_document(source).unwrap_err();
        assert!(error.contains("missing 'name'"), "got: {}", error);
    }

    #[test]
    fn rejects_bad_runtime() {
        let source = "---\nname: x\ndescription: y\nruntime: lua\n---\nBody\n";
        let error = parse_skill_document(source).unwrap_err();
        assert!(error.contains("unknown runtime"), "got: {}", error);
    }

    #[test]
    fn builtin_skills_parse() {
        let skills = common_desktop_skills();
        let names: Vec<_> = skills.iter().map(|s| s.name().to_string()).collect();
        assert_eq!(names, vec!["pdf", "docx", "xlsx", "pptx"]);
        for skill in &skills {
            assert!(!skill.description().is_empty());
            assert!(!skill.body().is_empty());
        }
    }

    #[test]
    fn builtin_skills_expose_capabilities() {
        let caps = common_desktop_skill_capabilities();
        assert_eq!(caps.len(), 4);
        for cap in &caps {
            assert!(!cap.name.is_empty());
            assert!(!cap.description.is_empty());
        }
    }

    #[test]
    fn find_builtin_skill_is_case_insensitive() {
        assert!(find_builtin_skill("PDF").is_some());
        assert!(find_builtin_skill("pdf").is_some());
        assert!(find_builtin_skill("nope").is_none());
    }
}
