// Prevents an additional console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// No `invoke_handler` is registered and no plugin is added. The native bridge
// exposes nothing to the frontend at Layer 0, and no arbitrary local command
// path may ever be introduced through it (00-charter.md invariant 8).
fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("failed to start the Val desktop shell");
}
