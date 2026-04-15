// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// Learn more about Tauri commands at https://tauri.app/v1/guides/features/command
mod cowork;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn main() {
    cowork::bootstrap::install_panic_diagnostics();

    if let Some(exit_code) = cowork::bootstrap::maybe_startup_exit_code_from_env_args() {
        std::process::exit(exit_code);
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .manage(cowork::agent_remote::auth::RemoteAuthState::default())
        .invoke_handler(tauri::generate_handler![
            greet,
            cowork::agent_remote::auth::sync_cowork_auth_context,
            cowork::runtime::send_cowork_chat_message,
            cowork::chat_commands::stop_cowork_chat_session,
            cowork::homepage::chat_sessions::list_homepage_chat_sessions,
            cowork::homepage::chat_sessions::get_homepage_chat_session,
            cowork::homepage::chat_sessions::create_homepage_chat_session,
            cowork::homepage::chat_sessions::update_homepage_chat_session,
            cowork::homepage::chat_sessions::rename_homepage_chat_session,
            cowork::homepage::chat_sessions::delete_homepage_chat_session,
            cowork::intelligent_folder::file_tree::read_path_tree,
            cowork::intelligent_folder::sessions::list_folder_sessions,
            cowork::intelligent_folder::sessions::get_folder_session,
            cowork::intelligent_folder::sessions::create_folder_session,
            cowork::intelligent_folder::sessions::update_folder_session,
            cowork::intelligent_folder::sessions::rename_folder_session,
            cowork::intelligent_folder::sessions::delete_folder_session,
            cowork::intelligent_folder::undo_commands::undo_cowork_folder,
            cowork::intelligent_folder::undo_commands::redo_cowork_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
