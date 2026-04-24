import type { Message, ImageItem } from '../types';
import { apiDelete, apiGet, apiPost } from './apiClient';

export interface ChattingAgent {
  id: number;
  name: string;
  profile_pic?: string | null;
  response_text?: string;
  thinking_text?: string;
}

export const messageService = {
  getMessages(roomId: number, signal?: AbortSignal): Promise<Message[]> {
    return apiGet(`/rooms/${roomId}/messages`, { signal });
  },

  pollMessages(roomId: number, sinceId?: number, signal?: AbortSignal): Promise<Message[]> {
    const endpoint = sinceId && sinceId > 0
      ? `/rooms/${roomId}/messages/poll?since_id=${sinceId}`
      : `/rooms/${roomId}/messages/poll`;
    return apiGet(endpoint, { signal });
  },

  sendMessage(roomId: number, data: {
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
    return apiPost(`/rooms/${roomId}/messages/send`, body);
  },

  getChattingAgents(roomId: number): Promise<{ chatting_agents: ChattingAgent[] }> {
    return apiGet(`/rooms/${roomId}/chatting-agents`);
  },

  clearRoomMessages(roomId: number): Promise<void> {
    return apiDelete(`/rooms/${roomId}/messages`);
  },
};
