import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../services';
import { useAuth } from '../contexts/AuthContext';
import type { RoomSummary, Room, RoomCreate } from '../types';

interface UseRoomsReturn {
  rooms: RoomSummary[];
  loading: boolean;
  error: string | null;
  createRoom: (data: RoomCreate) => Promise<Room>;
  deleteRoom: (roomId: number) => Promise<void>;
  renameRoom: (roomId: number, name: string) => Promise<Room>;
  refreshRooms: () => Promise<void>;
  markRoomAsReadOptimistic: (roomId: number) => void;
}

const POLL_INTERVAL = 5000; // Poll every 5 seconds

export const useRooms = (): UseRoomsReturn => {
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { apiKey } = useAuth();

  const fetchRooms = useCallback(async (isInitial = false) => {
    try {
      if (isInitial) {
        setLoading(true);
      }
      const data = await api.getRooms();

      // Only update state if rooms have actually changed
      setRooms((prevRooms) => {
        // Check if data is different
        if (prevRooms.length !== data.length) {
          return data;
        }

        // Check if any room has changed
        const hasChanges = data.some((newRoom) => {
          const prevRoom = prevRooms.find(r => r.id === newRoom.id);
          if (!prevRoom) return true;

          // Compare relevant properties
          return (
            prevRoom.name !== newRoom.name ||
            prevRoom.is_paused !== newRoom.is_paused ||
            prevRoom.max_interactions !== newRoom.max_interactions ||
            prevRoom.last_activity_at !== newRoom.last_activity_at ||
            prevRoom.last_read_at !== newRoom.last_read_at ||
            prevRoom.has_unread !== newRoom.has_unread
          );
        });

        return hasChanges ? data : prevRooms;
      });

      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      if (isInitial) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    // Only fetch if API key is available
    if (!apiKey) {
      setLoading(false);
      return;
    }

    let isActive = true;

    const doFetch = async (isInitial = false) => {
      try {
        if (isInitial) {
          setLoading(true);
        }
        const data = await api.getRooms();

        // Only update state if rooms have actually changed
        setRooms((prevRooms) => {
          // Check if data is different
          if (prevRooms.length !== data.length) {
            return data;
          }

          // Check if any room has changed
          const hasChanges = data.some((newRoom) => {
            const prevRoom = prevRooms.find(r => r.id === newRoom.id);
            if (!prevRoom) return true;

            // Compare relevant properties
            return (
              prevRoom.name !== newRoom.name ||
              prevRoom.is_paused !== newRoom.is_paused ||
              prevRoom.max_interactions !== newRoom.max_interactions ||
              prevRoom.last_activity_at !== newRoom.last_activity_at ||
              prevRoom.last_read_at !== newRoom.last_read_at ||
              prevRoom.has_unread !== newRoom.has_unread
            );
          });

          return hasChanges ? data : prevRooms;
        });

        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        if (isInitial) {
          setLoading(false);
        }
      }
    };

    // Initial fetch
    doFetch(true);

    // Setup polling using setTimeout to prevent stacking
    const scheduleNextPoll = () => {
      if (!isActive) return;

      pollIntervalRef.current = setTimeout(async () => {
        await doFetch(false);
        scheduleNextPoll(); // Schedule next poll after this one completes
      }, POLL_INTERVAL);
    };

    // Start polling
    scheduleNextPoll();

    return () => {
      isActive = false;
      if (pollIntervalRef.current) {
        clearTimeout(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [apiKey]);

  const createRoom = async (data: RoomCreate): Promise<Room> => {
    try {
      const newRoom = await api.createRoom(data);
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
  };

  const deleteRoom = async (roomId: number): Promise<void> => {
    try {
      await api.deleteRoom(roomId);
      setRooms((prev) => prev.filter((room) => room.id !== roomId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
      throw err;
    }
  };

  const renameRoom = async (roomId: number, name: string): Promise<Room> => {
    try {
      const updatedRoom = await api.updateRoom(roomId, { name });
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
  };

  const markRoomAsReadOptimistic = useCallback((roomId: number) => {
    // Optimistically update the room's has_unread status immediately
    setRooms((prev) => prev.map(room =>
      room.id === roomId
        ? { ...room, has_unread: false, last_read_at: new Date().toISOString() }
        : room
    ));
  }, []);

  return { rooms, loading, error, createRoom, deleteRoom, renameRoom, refreshRooms: fetchRooms, markRoomAsReadOptimistic };
};
