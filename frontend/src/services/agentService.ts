import type { Agent, AgentCreate, AgentUpdate, AgentConfig, Room } from '../types';
import { API_BASE_URL, getFetchOptions } from './apiClient';

/**
 * Generate the URL for an agent's profile picture.
 * Returns the URL to the profile pic endpoint if the agent has a profile picture.
 */
export function getAgentProfilePicUrl(agent: { name: string; profile_pic?: string | null }): string | null {
  if (!agent.profile_pic) return null;
  return `${API_BASE_URL}/agents/${encodeURIComponent(agent.name)}/profile-pic`;
}

export const agentService = {
  async getAllAgents(): Promise<Agent[]> {
    const response = await fetch(`${API_BASE_URL}/agents`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch agents');
    return response.json();
  },

  async getAgent(agentId: number): Promise<Agent> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch agent');
    return response.json();
  },

  async getRoomAgents(roomId: number): Promise<Agent[]> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/agents`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch room agents');
    return response.json();
  },

  async createAgent(agentData: AgentCreate): Promise<Agent> {
    const response = await fetch(`${API_BASE_URL}/agents`, getFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agentData),
    }));
    if (!response.ok) throw new Error('Failed to create agent');
    return response.json();
  },

  async deleteAgent(agentId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}`, getFetchOptions({
      method: 'DELETE',
    }));
    if (!response.ok) throw new Error('Failed to delete agent');
    return response.json();
  },

  async updateAgent(agentId: number, agentData: AgentUpdate): Promise<Agent> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}`, getFetchOptions({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agentData),
    }));
    if (!response.ok) throw new Error('Failed to update agent');
    return response.json();
  },

  async getAgentConfigs(): Promise<{ configs: AgentConfig }> {
    const response = await fetch(`${API_BASE_URL}/agents/configs`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch agent configs');
    return response.json();
  },

  async getAgentDirectRoom(agentId: number, provider: 'claude' | 'codex' = 'claude'): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}/direct-room?provider=${provider}`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to get agent direct room');
    return response.json();
  },

  async addAgentToRoom(roomId: number, agentId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/agents/${agentId}`, getFetchOptions({
      method: 'POST',
    }));
    if (!response.ok) throw new Error('Failed to add agent to room');
  },

  async removeAgentFromRoom(roomId: number, agentId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/agents/${agentId}`, getFetchOptions({
      method: 'DELETE',
    }));
    if (!response.ok) throw new Error('Failed to remove agent from room');
    return response.json();
  },
};
