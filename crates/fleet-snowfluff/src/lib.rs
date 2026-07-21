pub mod animation;
pub mod assets;
pub mod gfx;
pub mod manager;
pub mod pet;
pub mod platform;
pub mod voice;

use std::{sync::Mutex, time::Duration};

use fleet_snowfluff_core::{constants::MOVE_INTERVAL_MS, Config};
use manager::PetManager;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build(),
                )?;
            }

            // Full config-file persistence (reading instance count, scale,
            // etc. from disk) lands with the settings-ui tasks; for now
            // this seeds from Config::default() -- the same typed default
            // the real config will use -- so total_screen is a genuine
            // setting (PetManager::set_total_screen) rather than a bare
            // literal, and toggling it is just one call away for whichever
            // UI surface ends up exposing it first.
            let default_config = Config::default();
            let app_handle = app.handle().clone();
            let mut pet_manager = PetManager::new(app_handle.clone(), default_config.total_screen);
            pet_manager.set_instance_count(1);
            pet_manager.set_voice_enabled(default_config.voice_enabled);
            pet_manager.set_voice_volume_percent(default_config.voice_volume);
            pet_manager.set_display_priority(default_config.display_priority);
            app.manage(Mutex::new(pet_manager));

            // Same background-thread + run_on_main_thread pattern proven
            // in examples/transparent_gif.rs (design.md D14): Tauri's
            // event loop defaults to ControlFlow::Wait, so a continuous
            // tick can't be driven from RunEvent alone.
            let tick_handle = app_handle.clone();
            std::thread::spawn(move || loop {
                std::thread::sleep(Duration::from_millis(MOVE_INTERVAL_MS as u64));
                let handle = tick_handle.clone();
                let result = tick_handle.run_on_main_thread(move || {
                    let state = handle.state::<Mutex<PetManager>>();
                    let mut manager = state.lock().unwrap();
                    manager.tick(MOVE_INTERVAL_MS);
                });
                if result.is_err() {
                    break;
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
