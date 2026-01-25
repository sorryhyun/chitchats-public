import { API_BASE_URL, getFetchOptions } from './apiClient';

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
  async getStatus(): Promise<VoiceStatus> {
    const response = await fetch(
      `${API_BASE_URL}/voice/status`,
      getFetchOptions()
    );
    if (!response.ok) {
      throw new Error('Failed to get voice status');
    }
    return response.json();
  },

  /**
   * Generate voice audio for a message.
   */
  async generate(messageId: number, roomId: number): Promise<VoiceGenerateResult> {
    const response = await fetch(
      `${API_BASE_URL}/voice/generate`,
      getFetchOptions({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message_id: messageId,
          room_id: roomId,
        }),
      })
    );
    if (!response.ok) {
      throw new Error('Failed to generate voice');
    }
    return response.json();
  },

  /**
   * Check if voice audio exists for a message.
   */
  async exists(messageId: number): Promise<VoiceExistsResult> {
    const response = await fetch(
      `${API_BASE_URL}/voice/exists/${messageId}`,
      getFetchOptions()
    );
    if (!response.ok) {
      throw new Error('Failed to check voice exists');
    }
    return response.json();
  },

  /**
   * Get the URL for playing cached voice audio.
   */
  getAudioUrl(messageId: number): string {
    return `${API_BASE_URL}/voice/audio/${messageId}`;
  },
};
