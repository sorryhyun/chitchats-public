/**
 * Tauri utility functions
 *
 * Provides detection and interaction with Tauri runtime
 */

/**
 * Check if running inside Tauri desktop app
 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI__' in window;
}

/**
 * Check if setup wizard is needed (Tauri only)
 */
export async function checkSetupNeeded(): Promise<boolean> {
  if (!isTauri()) {
    return false;
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<boolean>('check_setup_needed');
  } catch {
    return false;
  }
}

/**
 * Start the backend sidecar (Tauri only)
 */
export async function startBackend(): Promise<void> {
  if (!isTauri()) {
    return;
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('start_backend');
  } catch (e) {
    console.error('Failed to start backend:', e);
    throw e;
  }
}

/**
 * Check if backend is healthy
 */
export async function checkBackendHealth(): Promise<boolean> {
  if (!isTauri()) {
    // In browser mode, check via fetch
    try {
      const response = await fetch('http://localhost:8000/health');
      return response.ok;
    } catch {
      return false;
    }
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<boolean>('check_backend_health');
  } catch {
    return false;
  }
}
