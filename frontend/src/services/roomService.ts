import type { ProviderType, ProvidersResponse, Room, RoomSummary, RoomUpdate } from '../types';
import { apiDelete, apiGet, apiPatch, apiPost } from './apiClient';

export const roomService = {
  getRooms(): Promise<RoomSummary[]> {
    return apiGet('/rooms');
  },

  getRoom(roomId: number): Promise<Room> {
    return apiGet(`/rooms/${roomId}`);
  },

  getProviders(): Promise<ProvidersResponse> {
    return apiGet('/providers');
  },

  createRoom(name: string, provider?: ProviderType, model?: string): Promise<Room> {
    const body: { name: string; provider?: ProviderType; model?: string } = { name };
    if (provider) body.provider = provider;
    if (model) body.model = model;
    return apiPost('/rooms', body);
  },

  updateRoom(roomId: number, roomData: RoomUpdate): Promise<Room> {
    return apiPatch(`/rooms/${roomId}`, roomData);
  },

  pauseRoom(roomId: number): Promise<Room> {
    return apiPost(`/rooms/${roomId}/pause`);
  },

  resumeRoom(roomId: number): Promise<Room> {
    return apiPost(`/rooms/${roomId}/resume`);
  },

  markRoomAsRead(roomId: number): Promise<{ message: string; last_read_at: string }> {
    return apiPost(`/rooms/${roomId}/mark-read`);
  },

  deleteRoom(roomId: number): Promise<void> {
    return apiDelete(`/rooms/${roomId}`);
  },
};
