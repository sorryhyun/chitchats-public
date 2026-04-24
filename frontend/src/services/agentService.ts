import type { Agent, AgentCreate, AgentUpdate, AgentConfig, Room } from '../types';
import { API_BASE_URL, apiDelete, apiGet, apiPatch, apiPost } from './apiClient';

/**
 * Generate the URL for an agent's profile picture.
 * Returns the URL to the profile pic endpoint if the agent has a profile picture.
 *
 * @param agent - Agent object with name and optional profile_pic
 * @param size - Optional target size in pixels. If provided, returns a resized image.
 *               For best quality on Retina displays, pass 2x the display size.
 */
export function getAgentProfilePicUrl(
  agent: { name: string; profile_pic?: string | null },
  size?: number
): string | null {
  if (!agent.profile_pic) return null;
  const baseUrl = `${API_BASE_URL}/agents/${encodeURIComponent(agent.name)}/profile-pic`;
  if (size) {
    return `${baseUrl}?size=${size}`;
  }
  return baseUrl;
}

export const agentService = {
  getAllAgents(): Promise<Agent[]> {
    return apiGet('/agents');
  },

  getAgent(agentId: number): Promise<Agent> {
    return apiGet(`/agents/${agentId}`);
  },

  getRoomAgents(roomId: number): Promise<Agent[]> {
    return apiGet(`/rooms/${roomId}/agents`);
  },

  createAgent(agentData: AgentCreate): Promise<Agent> {
    return apiPost('/agents', agentData);
  },

  deleteAgent(agentId: number): Promise<void> {
    return apiDelete(`/agents/${agentId}`);
  },

  updateAgent(agentId: number, agentData: AgentUpdate): Promise<Agent> {
    return apiPatch(`/agents/${agentId}`, agentData);
  },

  getAgentConfigs(): Promise<{ configs: AgentConfig }> {
    return apiGet('/agents/configs');
  },

  getAgentDirectRoom(agentId: number, provider: 'claude' | 'codex' = 'claude', model?: string): Promise<Room> {
    const params = new URLSearchParams({ provider });
    if (model) params.set('model', model);
    return apiGet(`/agents/${agentId}/direct-room?${params}`);
  },

  addAgentToRoom(roomId: number, agentId: number): Promise<void> {
    return apiPost(`/rooms/${roomId}/agents/${agentId}`);
  },

  removeAgentFromRoom(roomId: number, agentId: number): Promise<void> {
    return apiDelete(`/rooms/${roomId}/agents/${agentId}`);
  },
};
