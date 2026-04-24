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

  // Check if running in bundled mode (frontend served from backend)
  // Dev server runs on 5173/5174, so anything else is bundled mode
  const currentPort = window.location.port;
  const isDevServer = currentPort === '5173' || currentPort === '5174';

  if (!isDevServer) {
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
 * Returns `undefined` for 204 / empty bodies so callers typed as `void` work.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, getFetchOptions(options));

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Request failed: ${response.statusText}` }));
    throw new Error(errorData.detail || `Request failed: ${response.statusText}`);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

interface RequestOpts {
  signal?: AbortSignal;
}

function jsonBodyInit(body: unknown): Pick<RequestInit, 'headers' | 'body'> {
  if (body === undefined) return {};
  return {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export function apiGet<T>(endpoint: string, opts: RequestOpts = {}): Promise<T> {
  return apiRequest<T>(endpoint, { signal: opts.signal });
}

export function apiPost<T>(endpoint: string, body?: unknown, opts: RequestOpts = {}): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'POST', ...jsonBodyInit(body), signal: opts.signal });
}

export function apiPatch<T>(endpoint: string, body: unknown): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'PATCH', ...jsonBodyInit(body) });
}

export function apiDelete<T = void>(endpoint: string): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'DELETE' });
}
