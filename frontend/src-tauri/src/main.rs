// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// Learn more about Tauri commands at https://tauri.app/v1/guides/features/command
mod cowork;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn main() {
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
            cowork::organize::file_tree::read_path_tree,
            cowork::organize::sessions::list_organize_sessions,
            cowork::organize::sessions::get_organize_session,
            cowork::organize::sessions::create_organize_session,
            cowork::organize::sessions::update_organize_session,
            cowork::organize::sessions::rename_organize_session,
            cowork::organize::sessions::delete_organize_session
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
