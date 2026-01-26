import { useCallback } from 'react';
import { roomService } from '../services';
import { usePollingData, createChangeDetector } from './usePollingData';
import type { ProviderType, RoomSummary, Room } from '../types';

interface UseRoomsReturn {
  rooms: RoomSummary[];
  loading: boolean;
  error: string | null;
  createRoom: (name: string, provider?: ProviderType) => Promise<Room>;
  deleteRoom: (roomId: number) => Promise<void>;
  renameRoom: (roomId: number, name: string) => Promise<Room>;
  refreshRooms: () => Promise<void>;
  markRoomAsReadOptimistic: (roomId: number) => void;
}

const POLL_INTERVAL = 5000; // Poll every 5 seconds

// Compare fields that affect room display
const roomChangeDetector = createChangeDetector<RoomSummary>([
  'name',
  'is_paused',
  'max_interactions',
  'last_activity_at',
  'last_read_at',
  'has_unread',
]);

export const useRooms = (): UseRoomsReturn => {
  const {
    data: rooms,
    setData: setRooms,
    loading,
    error,
    setError,
    refresh: refreshRooms,
  } = usePollingData<RoomSummary>({
    fetchFn: roomService.getRooms,
    pollInterval: POLL_INTERVAL,
    hasChanges: roomChangeDetector,
  });

  const createRoom = useCallback(async (name: string, provider?: ProviderType): Promise<Room> => {
    try {
      const newRoom = await roomService.createRoom(name, provider);
      // Convert Room to RoomSummary for the rooms list
      const roomSummary: RoomSummary = {
        id: newRoom.id,
        name: newRoom.name,
        max_interactions: newRoom.max_interactions,
        is_paused: newRoom.is_paused,
        default_provider: newRoom.default_provider,
        created_at: newRoom.created_at,
        last_activity_at: newRoom.last_activity_at,
        last_read_at: newRoom.last_read_at,
        has_unread: false, // Newly created room has no unread messages
      };
      setRooms((prev) => [...prev, roomSummary]);
      return newRoom;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
      throw err;
    }
  }, [setRooms, setError]);

  const deleteRoom = useCallback(async (roomId: number): Promise<void> => {
    try {
      await roomService.deleteRoom(roomId);
      setRooms((prev) => prev.filter((room) => room.id !== roomId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
      throw err;
    }
  }, [setRooms, setError]);

  const renameRoom = useCallback(async (roomId: number, name: string): Promise<Room> => {
    try {
      const updatedRoom = await roomService.updateRoom(roomId, { name });
      setRooms((prev) => prev.map((room) => (
        room.id === roomId
          ? { ...room, name: updatedRoom.name }
          : room
      )));
      return updatedRoom;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
      throw err;
    }
  }, [setRooms, setError]);

  const markRoomAsReadOptimistic = useCallback((roomId: number) => {
    // Optimistically update the room's has_unread status immediately
    setRooms((prev) => prev.map(room =>
      room.id === roomId
        ? { ...room, has_unread: false, last_read_at: new Date().toISOString() }
        : room
    ));
  }, [setRooms]);

  return { rooms, loading, error, createRoom, deleteRoom, renameRoom, refreshRooms, markRoomAsReadOptimistic };
};
