use super::{DesktopBashSession, DesktopTool, DesktopToolContext, TOOL_BASH};
use crate::cowork::agent_presets::shared::DesktopToolCapability;
use serde_json::{json, Value};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const DEFAULT_BASH_TIMEOUT_SECS: u64 = 60;
const MAX_BASH_TIMEOUT_SECS: u64 = 180;

pub fn desktop_tool() -> DesktopTool {
    DesktopTool::new(
        DesktopToolCapability {
            name: TOOL_BASH.to_string(),
            aliases: Vec::new(),
            display_name: "Run or inspect desktop shell sessions".to_string(),
            description: "Run a local shell command or inspect saved shell session output inside the selected desktop folder. Use action='run' to execute commands, action='view' to inspect saved sessions, or action='list_sessions' to list available sessions. This tool runs on the desktop app, not on the Python backend.".to_string(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["run", "view", "list_sessions"],
                        "description": "The Bash action to perform. Defaults to 'run'."
                    },
                    "session_name": {
                        "type": "string",
                        "description": "Logical shell session name used to store or inspect command output. Defaults to 'default'."
                    },
                    "session_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Session names to inspect when action='view'."
                    },
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute when action='run'."
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory for action='run' within the selected desktop scope. It may be absolute or relative to the scope root."
                    },
                    "shell": {
                        "type": "string",
                        "description": "Optional shell executable for action='run'. Supported values include powershell, pwsh, cmd, sh, bash, and zsh. Defaults to powershell on Windows and sh on other systems."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional short description of what the command does when action='run'."
                    },
                    "wait_for_output": {
                        "type": "boolean",
                        "description": "Whether to wait for command completion when action='run'. Defaults to true. Background execution is not supported yet."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in seconds for action='run'. Defaults to 60 and is capped at 180."
                    }
                },
                "required": []
            }),
        },
        execute,
        true,
    )
    .with_aliases(&["bash"])
}

fn execute(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let action = tool_input
        .get("action")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("run");

    match action {
        "run" => execute_run(ctx, tool_input),
        "view" => execute_view(ctx, tool_input),
        "list_sessions" => execute_list_sessions(ctx),
        other => Err(format!(
            "Unsupported Bash action '{}'. Supported actions: run, view, list_sessions",
            other
        )),
    }
}

fn execute_run(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let session_name = tool_input
        .get("session_name")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("default")
        .to_string();
    let command = tool_input
        .get("command")
        .and_then(Value::as_str)
        .ok_or_else(|| "Bash action='run' requires command".to_string())?;
    let wait_for_output = tool_input
        .get("wait_for_output")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    if !wait_for_output {
        return Err(
            "Background Bash execution is not supported in desktop cowork mode yet".to_string(),
        );
    }

    let timeout_secs = tool_input
        .get("timeout")
        .and_then(Value::as_u64)
        .unwrap_or(DEFAULT_BASH_TIMEOUT_SECS)
        .min(MAX_BASH_TIMEOUT_SECS);
    let working_directory = tool_input
        .get("cwd")
        .and_then(Value::as_str)
        .map(|value| ctx.resolve_scoped_path(value, false))
        .transpose()?
        .unwrap_or_else(|| ctx.working_directory().to_path_buf());
    let requested_shell = tool_input
        .get("shell")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty());

    let mut process = build_command_process(requested_shell, command, &working_directory)?;
    process.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = process
        .spawn()
        .map_err(|error| format!("Failed to start Bash command: {error}"))?;
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);

    loop {
        if child
            .try_wait()
            .map_err(|error| format!("Failed to poll Bash command: {error}"))?
            .is_some()
        {
            let output = child
                .wait_with_output()
                .map_err(|error| format!("Failed to collect Bash output: {error}"))?;
            let stdout = String::from_utf8_lossy(&output.stdout);
            let stderr = String::from_utf8_lossy(&output.stderr);
            let combined = format_output(stdout.as_ref(), stderr.as_ref(), output.status.code());
            ctx.bash_sessions_mut().insert(
                session_name,
                DesktopBashSession {
                    last_output: combined.clone(),
                    last_exit_code: output.status.code(),
                },
            );
            if output.status.success() {
                return Ok(combined);
            }
            return Err(combined);
        }

        if Instant::now() >= deadline {
            let _ = child.kill();
            let output = child
                .wait_with_output()
                .map_err(|error| format!("Failed to collect timed out Bash output: {error}"))?;
            let stdout = String::from_utf8_lossy(&output.stdout);
            let stderr = String::from_utf8_lossy(&output.stderr);
            let combined = format!(
                "{}\nTimed out after {} seconds",
                format_output(stdout.as_ref(), stderr.as_ref(), output.status.code()),
                timeout_secs
            );
            ctx.bash_sessions_mut().insert(
                session_name,
                DesktopBashSession {
                    last_output: combined.clone(),
                    last_exit_code: output.status.code(),
                },
            );
            return Err(combined);
        }

        thread::sleep(Duration::from_millis(100));
    }
}

fn execute_view(ctx: &mut DesktopToolContext<'_>, tool_input: &Value) -> Result<String, String> {
    let session_names = tool_input
        .get("session_names")
        .and_then(Value::as_array)
        .ok_or_else(|| "Bash action='view' requires session_names".to_string())?;
    let mut results = Vec::new();
    for session_name in session_names {
        let Some(session_name) = session_name.as_str() else {
            continue;
        };
        if let Some(state) = ctx.bash_sessions().get(session_name) {
            results.push(format!(
                "[{}] exit_code={:?}\n{}",
                session_name, state.last_exit_code, state.last_output
            ));
        } else {
            results.push(format!(
                "[{}] No desktop bash session output available",
                session_name
            ));
        }
    }
    Ok(results.join("\n\n"))
}

fn execute_list_sessions(ctx: &mut DesktopToolContext<'_>) -> Result<String, String> {
    let session_names = ctx.bash_sessions().keys().cloned().collect::<Vec<_>>();
    serde_json::to_string_pretty(&session_names)
        .map_err(|error| format!("Failed to encode bash session list: {error}"))
}

fn format_output(stdout: &str, stderr: &str, exit_code: Option<i32>) -> String {
    let mut sections = Vec::new();
    if !stdout.trim().is_empty() {
        sections.push(format!("stdout:\n{}", stdout.trim_end()));
    }
    if !stderr.trim().is_empty() {
        sections.push(format!("stderr:\n{}", stderr.trim_end()));
    }
    sections.push(format!("exit_code: {:?}", exit_code));
    sections.join("\n\n")
}

fn build_command_process(
    requested_shell: Option<&str>,
    command: &str,
    working_directory: &PathBuf,
) -> Result<Command, String> {
    let shell = requested_shell.unwrap_or(default_shell_name());
    let mut process = match shell {
        "powershell" => {
            let mut command_builder = Command::new("powershell");
            command_builder
                .arg("-NoProfile")
                .arg("-Command")
                .arg(command);
            command_builder
        }
        "pwsh" => {
            let mut command_builder = Command::new("pwsh");
            command_builder
                .arg("-NoProfile")
                .arg("-Command")
                .arg(command);
            command_builder
        }
        "cmd" => {
            let mut command_builder = Command::new("cmd");
            command_builder.arg("/C").arg(command);
            command_builder
        }
        "sh" | "bash" | "zsh" => {
            let mut command_builder = Command::new(shell);
            command_builder.arg("-lc").arg(command);
            command_builder
        }
        _ => {
            return Err(format!(
                "Unsupported shell '{}'. Supported shells: powershell, pwsh, cmd, sh, bash, zsh",
                shell
            ))
        }
    };

    process.current_dir(working_directory);
    #[cfg(target_os = "windows")]
    {
        // Keep shell execution headless in desktop mode to avoid flashing terminal windows.
        process.creation_flags(CREATE_NO_WINDOW);
    }

    Ok(process)
}

fn default_shell_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "powershell"
    } else {
        "sh"
    }
}
