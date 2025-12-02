import type { Room, RoomSummary, RoomUpdate, Agent, AgentCreate, AgentUpdate, AgentConfig, Message } from '../types';

/**
 * Typed API error class for better error handling
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Request deduplication - prevents duplicate simultaneous requests
 */
const pendingRequests = new Map<string, Promise<unknown>>();

function deduplicatedFetch<T>(key: string, fetchFn: () => Promise<T>): Promise<T> {
  const existing = pendingRequests.get(key);
  if (existing) {
    return existing as Promise<T>;
  }

  const promise = fetchFn().finally(() => {
    pendingRequests.delete(key);
  });

  pendingRequests.set(key, promise);
  return promise;
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

  // Auto-detect based on current window location
  // If accessing via network IP, use network IP for backend too
  const currentHost = window.location.hostname;
  if (currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
    return `http://${currentHost}:8000`;
  }

  // Default to localhost
  return 'http://localhost:8000';
}

export const API_BASE_URL = getApiUrl();

/**
 * Generate the URL for an agent's profile picture.
 * Returns the URL to the profile pic endpoint if the agent has a profile picture.
 */
export function getAgentProfilePicUrl(agent: { name: string; profile_pic?: string | null }): string | null {
  if (!agent.profile_pic) return null;
  return `${API_BASE_URL}/agents/${encodeURIComponent(agent.name)}/profile-pic`;
}

// Global API key storage for the API module
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
 * Helper to handle API response errors
 */
async function handleResponse<T>(response: Response, errorMessage: string): Promise<T> {
  if (!response.ok) {
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      // Response body is not JSON
    }
    throw new ApiError(errorMessage, response.status, data);
  }
  return response.json();
}

// Helper to create fetch options with API key
function getFetchOptions(options: RequestInit = {}): RequestInit {
  // Properly merge headers: user headers first, then add API key
  // This ensures API key is always included and not overwritten by user headers
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

export const api = {
  // Rooms
  async getRooms(): Promise<RoomSummary[]> {
    return deduplicatedFetch('getRooms', async () => {
      const response = await fetch(`${API_BASE_URL}/rooms`, getFetchOptions());
      return handleResponse<RoomSummary[]>(response, 'Failed to fetch rooms');
    });
  },

  async getRoom(roomId: number): Promise<Room> {
    return deduplicatedFetch(`getRoom:${roomId}`, async () => {
      const response = await fetch(`${API_BASE_URL}/rooms/${roomId}`, getFetchOptions());
      return handleResponse<Room>(response, 'Failed to fetch room');
    });
  },

  async createRoom(name: string): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms`, getFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }));
    return handleResponse<Room>(response, 'Failed to create room');
  },

  async updateRoom(roomId: number, roomData: RoomUpdate): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}`, getFetchOptions({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(roomData),
    }));
    return handleResponse<Room>(response, 'Failed to update room');
  },

  async pauseRoom(roomId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/pause`, getFetchOptions({
      method: 'POST',
    }));
    return handleResponse<Room>(response, 'Failed to pause room');
  },

  async resumeRoom(roomId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/resume`, getFetchOptions({
      method: 'POST',
    }));
    return handleResponse<Room>(response, 'Failed to resume room');
  },

  async markRoomAsRead(roomId: number): Promise<{ message: string; last_read_at: string }> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/mark-read`, getFetchOptions({
      method: 'POST',
    }));
    return handleResponse<{ message: string; last_read_at: string }>(response, 'Failed to mark room as read');
  },

  async deleteRoom(roomId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}`, getFetchOptions({
      method: 'DELETE',
    }));
    return handleResponse<void>(response, 'Failed to delete room');
  },

  // Agents
  async getAllAgents(): Promise<Agent[]> {
    return deduplicatedFetch('getAllAgents', async () => {
      const response = await fetch(`${API_BASE_URL}/agents`, getFetchOptions());
      return handleResponse<Agent[]>(response, 'Failed to fetch agents');
    });
  },

  async getAgent(agentId: number): Promise<Agent> {
    return deduplicatedFetch(`getAgent:${agentId}`, async () => {
      const response = await fetch(`${API_BASE_URL}/agents/${agentId}`, getFetchOptions());
      return handleResponse<Agent>(response, 'Failed to fetch agent');
    });
  },

  async getRoomAgents(roomId: number): Promise<Agent[]> {
    return deduplicatedFetch(`getRoomAgents:${roomId}`, async () => {
      const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/agents`, getFetchOptions());
      return handleResponse<Agent[]>(response, 'Failed to fetch room agents');
    });
  },

  async createAgent(agentData: AgentCreate): Promise<Agent> {
    const response = await fetch(`${API_BASE_URL}/agents`, getFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agentData),
    }));
    return handleResponse<Agent>(response, 'Failed to create agent');
  },

  async deleteAgent(agentId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}`, getFetchOptions({
      method: 'DELETE',
    }));
    return handleResponse<void>(response, 'Failed to delete agent');
  },

  async addAgentToRoom(roomId: number, agentId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/agents/${agentId}`, getFetchOptions({
      method: 'POST',
    }));
    return handleResponse<Room>(response, 'Failed to add agent to room');
  },

  async removeAgentFromRoom(roomId: number, agentId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/agents/${agentId}`, getFetchOptions({
      method: 'DELETE',
    }));
    return handleResponse<void>(response, 'Failed to remove agent from room');
  },

  async updateAgent(agentId: number, agentData: AgentUpdate): Promise<Agent> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}`, getFetchOptions({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agentData),
    }));
    return handleResponse<Agent>(response, 'Failed to update agent');
  },

  async getAgentConfigs(): Promise<{ configs: AgentConfig }> {
    return deduplicatedFetch('getAgentConfigs', async () => {
      const response = await fetch(`${API_BASE_URL}/agent-configs`, getFetchOptions());
      return handleResponse<{ configs: AgentConfig }>(response, 'Failed to fetch agent configs');
    });
  },

  async getAgentDirectRoom(agentId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}/direct-room`, getFetchOptions());
    return handleResponse<Room>(response, 'Failed to get agent direct room');
  },

  // Messages
  async getMessages(roomId: number): Promise<Message[]> {
    return deduplicatedFetch(`getMessages:${roomId}`, async () => {
      const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages`, getFetchOptions());
      return handleResponse<Message[]>(response, 'Failed to fetch messages');
    });
  },

  async clearRoomMessages(roomId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages`, getFetchOptions({
      method: 'DELETE',
    }));
    return handleResponse<void>(response, 'Failed to clear messages');
  },
};
