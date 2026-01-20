mod setup;
mod sidecar;
mod window_state;

use tauri::{
    image::Image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};
use std::sync::atomic::{AtomicBool, Ordering};

static SETUP_COMPLETE: AtomicBool = AtomicBool::new(false);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .invoke_handler(tauri::generate_handler![
            setup::check_setup_needed,
            setup::create_env_file,
            setup::get_app_data_dir,
            sidecar::start_backend,
            sidecar::stop_backend,
            sidecar::check_backend_health,
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();

            // Create tray menu
            let show_item = MenuItem::with_id(app, "show", "Show ChitChats", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Exit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &quit_item])?;

            // Create tray icon
            let _tray = TrayIconBuilder::new()
                .icon(Image::from_path("icons/icon.png").unwrap_or_else(|_| {
                    // Fallback to embedded icon if file not found
                    Image::from_bytes(include_bytes!("../icons/icon.png"))
                        .expect("Failed to load embedded tray icon")
                }))
                .menu(&menu)
                .tooltip("ChitChats")
                .on_menu_event(move |app, event| {
                    match event.id.as_ref() {
                        "show" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        "quit" => {
                            // Stop backend before quitting
                            let handle = app.clone();
                            tauri::async_runtime::spawn(async move {
                                let _ = sidecar::stop_backend_internal(&handle).await;
                            });
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Check if setup is needed
            let setup_needed = setup::is_setup_needed(&app_handle);

            if !setup_needed {
                // Start backend sidecar
                let handle = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    match sidecar::start_backend_internal(&handle).await {
                        Ok(_) => {
                            log::info!("Backend started successfully");
                            // Wait for backend to be healthy, then show window
                            for _ in 0..30 {
                                if sidecar::check_health().await {
                                    SETUP_COMPLETE.store(true, Ordering::SeqCst);
                                    if let Some(window) = handle.get_webview_window("main") {
                                        // Restore window state if available
                                        window_state::restore_window_state(&window);
                                        let _ = window.show();
                                        let _ = window.set_focus();
                                    }
                                    return;
                                }
                                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                            }
                            log::error!("Backend health check timed out");
                        }
                        Err(e) => {
                            log::error!("Failed to start backend: {}", e);
                        }
                    }
                });
            } else {
                // Show window immediately for setup
                if let Some(window) = app_handle.get_webview_window("main") {
                    // Restore window state if available
                    window_state::restore_window_state(&window);
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                WindowEvent::CloseRequested { api, .. } => {
                    // Save window state before hiding
                    window_state::save_window_state(window);
                    // Hide window instead of closing (minimize to tray)
                    let _ = window.hide();
                    api.prevent_close();
                }
                WindowEvent::Resized(_) | WindowEvent::Moved(_) => {
                    // Save window state on resize/move
                    window_state::save_window_state(window);
                }
                _ => {}
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
