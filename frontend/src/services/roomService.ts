import type { ProviderType, ProvidersResponse, Room, RoomSummary, RoomUpdate } from '../types';
import { API_BASE_URL, getFetchOptions } from './apiClient';

export const roomService = {
  async getRooms(): Promise<RoomSummary[]> {
    const response = await fetch(`${API_BASE_URL}/rooms`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch rooms');
    return response.json();
  },

  async getRoom(roomId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch room');
    return response.json();
  },

  async getProviders(): Promise<ProvidersResponse> {
    const response = await fetch(`${API_BASE_URL}/providers`, getFetchOptions());
    if (!response.ok) throw new Error('Failed to fetch providers');
    return response.json();
  },

  async createRoom(name: string, provider?: ProviderType): Promise<Room> {
    const body: { name: string; provider?: ProviderType } = { name };
    if (provider) {
      body.provider = provider;
    }
    const response = await fetch(`${API_BASE_URL}/rooms`, getFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Failed to create room' }));
      throw new Error(errorData.detail || 'Failed to create room');
    }
    return response.json();
  },

  async updateRoom(roomId: number, roomData: RoomUpdate): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}`, getFetchOptions({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(roomData),
    }));
    if (!response.ok) throw new Error('Failed to update room');
    return response.json();
  },

  async pauseRoom(roomId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/pause`, getFetchOptions({
      method: 'POST',
    }));
    if (!response.ok) throw new Error('Failed to pause room');
    return response.json();
  },

  async resumeRoom(roomId: number): Promise<Room> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/resume`, getFetchOptions({
      method: 'POST',
    }));
    if (!response.ok) throw new Error('Failed to resume room');
    return response.json();
  },

  async markRoomAsRead(roomId: number): Promise<{ message: string; last_read_at: string }> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/mark-read`, getFetchOptions({
      method: 'POST',
    }));
    if (!response.ok) throw new Error('Failed to mark room as read');
    return response.json();
  },

  async deleteRoom(roomId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/rooms/${roomId}`, getFetchOptions({
      method: 'DELETE',
    }));
    if (!response.ok) throw new Error('Failed to delete room');
    return response.json();
  },
};
