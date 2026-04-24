import { API_BASE_URL, apiGet, apiPost } from './apiClient';

export interface VoiceStatus {
  enabled: boolean;
  server_available: boolean;
  server_url: string;
}

export interface VoiceGenerateResult {
  status: 'success' | 'exists' | 'error';
  file_path?: string;
  error?: string;
  duration_ms?: number;
}

export interface VoiceExistsResult {
  exists: boolean;
  file_path?: string;
}

export const voiceService = {
  /**
   * Check voice server status and availability.
   */
  getStatus(): Promise<VoiceStatus> {
    return apiGet('/voice/status');
  },

  /**
   * Generate voice audio for a message.
   */
  generate(messageId: number, roomId: number): Promise<VoiceGenerateResult> {
    return apiPost('/voice/generate', { message_id: messageId, room_id: roomId });
  },

  /**
   * Check if voice audio exists for a message.
   */
  exists(messageId: number): Promise<VoiceExistsResult> {
    return apiGet(`/voice/exists/${messageId}`);
  },

  /**
   * Get the URL for playing cached voice audio.
   */
  getAudioUrl(messageId: number): string {
    return `${API_BASE_URL}/voice/audio/${messageId}`;
  },
};
