// Prevents an additional console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// Owner execution order, 24 September 2026 (Voice work package 3 §8). Exactly one
// plugin is registered, and it does exactly one thing: it lets Lord Armand mute and
// unmute his own microphone with Command+Shift+M while another application is in
// front. Nothing else is exposed through the native bridge — no filesystem, no
// shell, no process, no HTTP — and no arbitrary local command path is introduced by
// it (00-charter.md invariant 8).
//
// The shortcut is **registered from the frontend, while a Voice session is active,
// and unregistered when it ends** (§8's privacy rule). It cannot start Voice: the
// handler it reaches toggles mute on an already-active session and is a hard no-op
// otherwise. A plugin that could acquire a device is not what this is; the device is
// acquired only by the owner's own gesture in the window.
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .run(tauri::generate_context!())
        .expect("failed to start the Val desktop shell");
}
