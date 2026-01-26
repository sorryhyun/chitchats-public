// Check if running inside Tauri desktop app
function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI__' in window;
}

// Get clean API URL without credentials
function getApiUrl(): string {
  // If VITE_API_BASE_URL is explicitly set, use it
  if (import.meta.env.VITE_API_BASE_URL) {
    const urlString = import.meta.env.VITE_API_BASE_URL;
    try {
      const parsed = new URL(urlString);
      // Remove credentials if present (they're handled by API key now)
      parsed.username = '';
      parsed.password = '';
      // Remove trailing slash to avoid double slashes in API calls
      return parsed.toString().replace(/\/$/, '');
    } catch {
      return urlString;
    }
  }

  // Tauri desktop app: sidecar runs on port 8000
  if (isTauri()) {
    return 'http://localhost:8000';
  }

  // Check if running in bundled mode (frontend served from backend on port 8000)
  // In this case, use the same origin for API calls
  const currentPort = window.location.port;
  if (currentPort === '8000') {
    // Bundled mode: frontend and backend on same origin
    return window.location.origin;
  }

  // Auto-detect based on current window location
  // If accessing via network IP, use network IP for backend too
  const currentHost = window.location.hostname;
  if (currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
    return `http://${currentHost}:8001`;
  }

  // Default to localhost (development mode with separate frontend server)
  return 'http://localhost:8001';
}

export const API_BASE_URL = getApiUrl();

// Global API key storage
let globalApiKey: string | null = null;

/**
 * Set the API key to be used for all API requests.
 * This should be called by the AuthContext when the user logs in.
 */
export function setApiKey(key: string | null) {
  globalApiKey = key;
}

/**
 * Get the current API key.
 */
export function getApiKey(): string | null {
  return globalApiKey;
}

/**
 * Get authentication headers for API requests.
 * This is useful when you need just the headers (e.g., for fetch with streaming).
 */
export function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'ngrok-skip-browser-warning': 'true',
  };

  if (globalApiKey) {
    headers['X-API-Key'] = globalApiKey;
  }

  return headers;
}

/**
 * Helper to create fetch options with API key and common headers.
 */
export function getFetchOptions(options: RequestInit = {}): RequestInit {
  const headers: Record<string, string> = {
    ...options.headers as Record<string, string>,
  };

  // Add API key header if available
  if (globalApiKey) {
    headers['X-API-Key'] = globalApiKey;
  }

  // Add ngrok header to skip browser warning page
  headers['ngrok-skip-browser-warning'] = 'true';

  return {
    ...options,
    headers,
  };
}

/**
 * Generic API request helper that handles common patterns.
 * Use this for simple fetch operations that don't need streaming.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, getFetchOptions(options));

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(errorData.detail || `Request failed: ${response.statusText}`);
  }

  return response.json();
}
