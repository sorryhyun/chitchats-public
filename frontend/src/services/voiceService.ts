import { API_BASE_URL, apiGet, apiPost, getFetchOptions } from './apiClient';

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
   * Download cached voice audio and wrap it in a blob URL for playback.
   *
   * The audio endpoint requires auth, and <audio>/`new Audio(url)` cannot send the
   * X-API-Key header, so the bytes are fetched here instead. Callers own the returned
   * URL and must revoke it with URL.revokeObjectURL when playback finishes.
   */
  async fetchAudioUrl(messageId: number): Promise<string> {
    const response = await fetch(`${API_BASE_URL}/voice/audio/${messageId}`, getFetchOptions());
    if (!response.ok) {
      throw new Error(`Failed to load audio: ${response.status}`);
    }
    return URL.createObjectURL(await response.blob());
  },
};
