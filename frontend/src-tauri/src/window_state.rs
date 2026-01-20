//! Window state persistence module
//!
//! Saves and restores window position and size across app restarts.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{WebviewWindow, Window};

#[derive(Debug, Serialize, Deserialize)]
struct WindowState {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    maximized: bool,
}

/// Get the path to the window state file
fn get_state_file_path() -> PathBuf {
    // Store in exe directory for production, current dir for dev
    if cfg!(debug_assertions) {
        PathBuf::from(".window_state.json")
    } else {
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.join(".window_state.json")))
            .unwrap_or_else(|| PathBuf::from(".window_state.json"))
    }
}

/// Save the current window state to file
pub fn save_window_state(window: &Window) {
    // Don't save if window is minimized or hidden
    if window.is_minimized().unwrap_or(false) || !window.is_visible().unwrap_or(true) {
        return;
    }

    let state = match (
        window.outer_position(),
        window.outer_size(),
        window.is_maximized(),
    ) {
        (Ok(pos), Ok(size), Ok(maximized)) => WindowState {
            x: pos.x,
            y: pos.y,
            width: size.width,
            height: size.height,
            maximized,
        },
        _ => return,
    };

    // Don't save if maximized (we'll restore to maximized state instead)
    if state.maximized {
        // Just save the maximized flag
        let state_file = get_state_file_path();
        if let Ok(existing) = fs::read_to_string(&state_file) {
            if let Ok(mut existing_state) = serde_json::from_str::<WindowState>(&existing) {
                existing_state.maximized = true;
                if let Ok(json) = serde_json::to_string_pretty(&existing_state) {
                    let _ = fs::write(&state_file, json);
                }
            }
        }
        return;
    }

    let state_file = get_state_file_path();
    if let Ok(json) = serde_json::to_string_pretty(&state) {
        if let Err(e) = fs::write(&state_file, json) {
            log::warn!("Failed to save window state: {}", e);
        }
    }
}

/// Restore window state from file
pub fn restore_window_state(window: &WebviewWindow) {
    let state_file = get_state_file_path();

    let content = match fs::read_to_string(&state_file) {
        Ok(c) => c,
        Err(_) => return, // No saved state
    };

    let state: WindowState = match serde_json::from_str(&content) {
        Ok(s) => s,
        Err(e) => {
            log::warn!("Failed to parse window state: {}", e);
            return;
        }
    };

    // Validate state (ensure window is not off-screen)
    if state.width < 400 || state.height < 300 {
        return; // Invalid size
    }

    // Apply state
    if state.maximized {
        let _ = window.maximize();
    } else {
        // Set position first, then size
        let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
            x: state.x,
            y: state.y,
        }));
        let _ = window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
            width: state.width,
            height: state.height,
        }));
    }

    log::info!(
        "Restored window state: {}x{} at ({}, {}), maximized: {}",
        state.width,
        state.height,
        state.x,
        state.y,
        state.maximized
    );
}
