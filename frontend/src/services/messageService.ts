import type { Message, ImageItem } from '../types';
import { API_BASE_URL, getFetchOptions } from './apiClient';

export const messageService = {
  async getMessages(roomId: number): Promise<Message[]> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch messages');
    return response.json();
  },

  async pollMessages(roomId: number, sinceId?: number): Promise<Message[]> {
    const url = sinceId && sinceId > 0
      ? `${API_BASE_URL}/rooms/${roomId}/messages/poll?since_id=${sinceId}`
      : `${API_BASE_URL}/rooms/${roomId}/messages/poll`;
    const response = await fetch(url, getFetchOptions());
    if (!response.ok) throw new Error('Failed to poll messages');
    return response.json();
  },

  async sendMessage(roomId: number, data: {
    content: string;
    participant_type?: string;
    participant_name?: string;
    images?: ImageItem[];
    mentioned_agent_ids?: number[];
  }): Promise<void> {
    const body: Record<string, unknown> = { content: data.content, role: 'user' };
    if (data.participant_type) body.participant_type = data.participant_type;
    if (data.participant_name) body.participant_name = data.participant_name;
    if (data.images && data.images.length > 0) body.images = data.images;
    if (data.mentioned_agent_ids && data.mentioned_agent_ids.length > 0) body.mentioned_agent_ids = data.mentioned_agent_ids;

    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages/send`, getFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
    if (!response.ok) throw new Error('Failed to send message');
  },

  async getChattingAgents(roomId: number): Promise<{ chatting_agents: any[] }> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/chatting-agents`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch chatting agents');
    return response.json();
  },

  async clearRoomMessages(roomId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages`, getFetchOptions({
      method: 'DELETE',
    }));
    if (!response.ok) throw new Error('Failed to clear messages');
    return response.json();
  },
};
