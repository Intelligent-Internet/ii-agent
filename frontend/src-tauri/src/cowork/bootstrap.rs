use std::any::Any;
use std::backtrace::Backtrace;
use std::io::Write;

pub fn install_panic_diagnostics() {
    std::panic::set_hook(Box::new(|panic_info| {
        let location = panic_info
            .location()
            .map(|loc| format!("{}:{}:{}", loc.file(), loc.line(), loc.column()))
            .unwrap_or_else(|| "<unknown>".to_string());
        let thread = std::thread::current();
        let thread_name = thread.name().unwrap_or("<unnamed>");
        let payload = panic_payload_message(panic_info.payload());
        let backtrace = Backtrace::force_capture();
        let message = format!(
            "[ii-agent panic] thread={thread_name} location={location}\nmessage: {payload}\nbacktrace:\n{backtrace}\n"
        );

        eprintln!("{message}");

        let log_path = std::env::temp_dir().join("ii-agent-panic.log");
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
        {
            let _ = writeln!(file, "{message}");
        }
    }));
}

pub fn maybe_startup_exit_code_from_env_args() -> Option<i32> {
    crate::cowork::desktop_runtime::wasm::chunking::splitter::maybe_run_pdf_helper_from_env_args()
}

fn panic_payload_message(payload: &(dyn Any + Send)) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        (*message).to_string()
    } else if let Some(message) = payload.downcast_ref::<String>() {
        message.clone()
    } else {
        "non-string panic payload".to_string()
    }
}
