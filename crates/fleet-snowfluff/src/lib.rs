pub mod animation;
pub mod assets;
pub mod commands;
pub mod config_store;
pub mod gfx;
pub mod manager;
pub mod pet;
pub mod platform;
pub mod quick_menu;
pub mod settings_window;
pub mod tray;
pub mod voice;

use std::{sync::Mutex, time::Duration};

use fleet_snowfluff_core::{constants::MOVE_INTERVAL_MS, Config, WanderStayMode};
use manager::PetManager;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            commands::locale_dictionary,
            commands::get_personalization,
            commands::set_scale_index,
            commands::set_opacity_index,
            commands::set_display_priority,
            commands::set_wander_stay_mode,
            commands::set_total_screen,
            commands::set_monitor_index,
            commands::set_window_snap,
            commands::set_instance_count,
            commands::set_ui_language,
            commands::set_voice_enabled,
            commands::set_voice_volume,
            commands::set_voice_language,
            commands::set_auto_startup,
            commands::set_skip_updates,
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build(),
                )?;
            }

            // Bootstrap with typed defaults first (total_screen needs to
            // be known before PetManager can compute initial bounds);
            // the real persisted config -- which may override every one
            // of these -- loads right after and every field is
            // reconciled via the matching setter.
            let default_config = Config::default();
            let app_handle = app.handle().clone();
            let mut pet_manager = PetManager::new(app_handle.clone(), default_config.total_screen);
            pet_manager.set_instance_count(1);

            let config = config_store::load(&app_handle, pet_manager.voice_languages_with_clips());
            pet_manager
                .set_scale(fleet_snowfluff_core::constants::scale_options()[config.scale_index]);
            pet_manager.set_opacity(
                fleet_snowfluff_core::constants::transparency_options()[config.transparency_index]
                    as f32,
            );
            pet_manager.set_total_screen(config.total_screen);
            pet_manager.set_monitor_index(config.screen_index);
            pet_manager.set_window_snap(config.window_snap);
            pet_manager.set_click_through(config.click_through);
            pet_manager.settings.follow_mouse = config.follow_mouse;
            pet_manager.settings.wander_idle_stay_mode =
                WanderStayMode::from_legacy_mode(config.wander_idle_stay_mode as i32);
            pet_manager.set_display_priority(config.display_priority);
            pet_manager.set_instance_count(config.instance_count);
            pet_manager.set_voice_enabled(config.voice_enabled);
            pet_manager.set_voice_volume_percent(config.voice_volume);
            pet_manager.set_voice_language(config.voice_language);
            pet_manager.set_ui_language(config.ui_language);
            // Persist immediately so sanitize-on-load corrections (or a
            // fresh default on first run) are on disk right away, not
            // only after the first setting the user happens to change.
            config_store::save(&app_handle, &config);

            app.manage(Mutex::new(pet_manager));
            app.manage(Mutex::new(config));
            tray::build(&app_handle)?;

            // Same background-thread + run_on_main_thread pattern proven
            // in examples/transparent_gif.rs (design.md D14): Tauri's
            // event loop defaults to ControlFlow::Wait, so a continuous
            // tick can't be driven from RunEvent alone.
            let tick_handle = app_handle.clone();
            std::thread::spawn(move || loop {
                std::thread::sleep(Duration::from_millis(MOVE_INTERVAL_MS as u64));
                let handle = tick_handle.clone();
                let result = tick_handle.run_on_main_thread(move || {
                    let pending_quick_menu = {
                        let state = handle.state::<Mutex<PetManager>>();
                        let mut manager = state.lock().unwrap();
                        manager.tick(MOVE_INTERVAL_MS)
                        // lock released at the end of this block --
                        // quick_menu::popup below needs to read
                        // PetManager state itself (see tick's doc
                        // comment), which would deadlock if it ran
                        // while still holding this same lock.
                    };
                    if let Some(window) = pending_quick_menu {
                        quick_menu::popup(&handle, &window);
                    }
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
