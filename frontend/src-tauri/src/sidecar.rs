//! Sidecar module for managing the backend process
//!
//! Handles starting, stopping, and health checking the Python backend.

use std::sync::Mutex;
use tauri::AppHandle;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

// Global state for the backend process
static BACKEND_PROCESS: Mutex<Option<CommandChild>> = Mutex::new(None);

/// Start the backend sidecar (internal function)
pub async fn start_backend_internal(app: &AppHandle) -> Result<(), String> {
    // Check if already running
    {
        let process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;
        if process.is_some() {
            return Ok(()); // Already running
        }
    }

    log::info!("Starting backend sidecar...");

    // Spawn the sidecar
    let sidecar_command = app
        .shell()
        .sidecar("chitchats-backend")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?;

    let (mut rx, child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    // Store the process handle
    {
        let mut process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;
        *process = Some(child);
    }

    // Spawn a task to handle sidecar output
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_shell::process::CommandEvent;

        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    log::info!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    log::warn!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(err) => {
                    log::error!("[backend] Error: {}", err);
                }
                CommandEvent::Terminated(payload) => {
                    log::info!(
                        "[backend] Terminated with code: {:?}, signal: {:?}",
                        payload.code,
                        payload.signal
                    );
                    // Clear the process handle
                    if let Ok(mut process) = BACKEND_PROCESS.lock() {
                        *process = None;
                    }
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(())
}

/// Stop the backend sidecar (internal function)
pub async fn stop_backend_internal(_app: &AppHandle) -> Result<(), String> {
    let mut process = BACKEND_PROCESS.lock().map_err(|e| e.to_string())?;

    if let Some(child) = process.take() {
        log::info!("Stopping backend sidecar...");
        child.kill().map_err(|e| format!("Failed to kill sidecar: {}", e))?;
    }

    Ok(())
}

/// Check if backend is healthy
pub async fn check_health() -> bool {
    let client = reqwest::Client::new();
    let response = client
        .get("http://localhost:8000/health")
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await;

    match response {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
}

/// Tauri command: Start the backend sidecar
#[tauri::command]
pub async fn start_backend(app: AppHandle) -> Result<(), String> {
    start_backend_internal(&app).await
}

/// Tauri command: Stop the backend sidecar
#[tauri::command]
pub async fn stop_backend(app: AppHandle) -> Result<(), String> {
    stop_backend_internal(&app).await
}

/// Tauri command: Check if backend is healthy
#[tauri::command]
pub async fn check_backend_health() -> bool {
    check_health().await
}
