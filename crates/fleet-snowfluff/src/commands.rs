//! Tauri commands invoked from webviews (settings window). One module
//! for all of them since they're all thin wrappers over `PetManager`
//! state behind the same `Mutex`.

use std::sync::Mutex;

use crate::manager::PetManager;

/// Returns the active UI language's locale dictionary as raw JSON
/// (task 11.2) for the settings webview to `JSON.parse` and read
/// strings from directly.
#[tauri::command]
pub fn locale_dictionary(state: tauri::State<Mutex<PetManager>>) -> String {
    state.lock().unwrap().locale_dictionary_json().to_string()
}
