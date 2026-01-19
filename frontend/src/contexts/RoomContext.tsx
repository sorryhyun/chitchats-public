import { createContext, useContext, useState, ReactNode } from 'react';
import type { ProviderType, RoomSummary, Room } from '../types';
import { useRooms } from '../hooks/useRooms';

interface RoomContextValue {
  // Room data
  rooms: RoomSummary[];
  selectedRoomId: number | null;
  loading: boolean;

  // Room actions
  selectRoom: (roomId: number) => void;
  createRoom: (name: string, provider?: ProviderType) => Promise<Room>;
  deleteRoom: (roomId: number) => Promise<void>;
  renameRoom: (roomId: number, name: string) => Promise<Room>;
  refreshRooms: () => Promise<void>;
  markRoomAsReadOptimistic: (roomId: number) => void;
  clearSelection: () => void;
}

const RoomContext = createContext<RoomContextValue | undefined>(undefined);

export function useRoomContext() {
  const context = useContext(RoomContext);
  if (context === undefined) {
    throw new Error('useRoomContext must be used within a RoomProvider');
  }
  return context;
}

interface RoomProviderProps {
  children: ReactNode;
}

export function RoomProvider({ children }: RoomProviderProps) {
  const {
    rooms,
    loading,
    createRoom: createRoomHook,
    deleteRoom: deleteRoomHook,
    renameRoom: renameRoomHook,
    refreshRooms,
    markRoomAsReadOptimistic
  } = useRooms();

  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);

  const selectRoom = (roomId: number) => {
    setSelectedRoomId(roomId);
  };

  const createRoom = async (name: string, provider?: ProviderType) => {
    return await createRoomHook(name, provider);
  };

  const deleteRoom = async (roomId: number) => {
    await deleteRoomHook(roomId);
    // Clear selection if we deleted the currently selected room
    if (selectedRoomId === roomId) {
      setSelectedRoomId(null);
    }
  };

  const renameRoom = async (roomId: number, name: string) => {
    return await renameRoomHook(roomId, name);
  };

  const clearSelection = () => {
    setSelectedRoomId(null);
  };

  const value: RoomContextValue = {
    rooms,
    selectedRoomId,
    loading,
    selectRoom,
    createRoom,
    deleteRoom,
    renameRoom,
    refreshRooms,
    markRoomAsReadOptimistic,
    clearSelection,
  };

  return (
    <RoomContext.Provider value={value}>
      {children}
    </RoomContext.Provider>
  );
}
