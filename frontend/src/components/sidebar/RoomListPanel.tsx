import { useState } from 'react';
import type { RoomSummary } from '../../types';
import { useAuth } from '../../contexts/AuthContext';

interface RoomListPanelProps {
  rooms: RoomSummary[];
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  onDeleteRoom: (roomId: number) => Promise<void>;
}

// Determine the display key based on provider + model
const getRoomDisplayKey = (provider: string, model: string | null): string => {
  if (provider === 'codex') return 'codex';
  if (provider === 'custom') return 'custom';
  if (model === 'claude-sonnet-4-6') return 'sonnet';
  return 'opus'; // default claude = opus
};

// Get room icon based on display key
const getProviderIcon = (key: string): string => {
  switch (key) {
    case 'opus': return 'O';
    case 'sonnet': return 'S';
    case 'codex': return 'X';
    case 'custom': return '★';
    default: return '#';
  }
};

// Get room badge background color
const getProviderBgColor = (key: string, isSelected: boolean): string => {
  if (isSelected) {
    switch (key) {
      case 'opus': return 'bg-[#D97757]';
      case 'sonnet': return 'bg-[#B8860B]';
      case 'codex': return 'bg-[#10A37F]';
      case 'custom': return 'bg-[#F59E0B]';
      default: return 'bg-slate-700';
    }
  }
  switch (key) {
    case 'opus': return 'bg-[#D97757]/20 group-hover:bg-[#D97757]/30';
    case 'sonnet': return 'bg-[#B8860B]/20 group-hover:bg-[#B8860B]/30';
    case 'codex': return 'bg-[#10A37F]/20 group-hover:bg-[#10A37F]/30';
    case 'custom': return 'bg-[#F59E0B]/20 group-hover:bg-[#F59E0B]/30';
    default: return 'bg-slate-200 group-hover:bg-slate-300';
  }
};

// Get room badge text color
const getProviderTextColor = (key: string, isSelected: boolean): string => {
  if (isSelected) return 'text-white';
  switch (key) {
    case 'opus': return 'text-[#D97757]';
    case 'sonnet': return 'text-[#B8860B]';
    case 'codex': return 'text-[#10A37F]';
    case 'custom': return 'text-[#F59E0B]';
    default: return 'text-slate-600';
  }
};

export const RoomListPanel = ({
  rooms,
  selectedRoomId,
  onSelectRoom,
  onDeleteRoom,
}: RoomListPanelProps) => {
  const { isAdmin } = useAuth();
  const [deletingRoomId, setDeletingRoomId] = useState<number | null>(null);

  return (
    <div className="absolute inset-0 overflow-y-auto p-2 sm:p-3 divide-y divide-slate-300">
      {rooms.length === 0 ? (
        <div className="text-center text-slate-500 mt-8 px-4">
          <p className="text-xs sm:text-sm">No rooms yet</p>
          <p className="text-xs mt-1">Create one or select an agent!</p>
        </div>
      ) : (
        rooms.map((room) => {
          const displayKey = getRoomDisplayKey(room.default_provider, room.default_model);
          return (
          <div
            key={room.id}
            onClick={() => onSelectRoom(room.id)}
            className={`group relative flex items-center justify-between p-2.5 sm:p-3 rounded-lg cursor-pointer transition-all min-h-[48px] touch-manipulation ${
              selectedRoomId === room.id
                ? 'bg-slate-100 border border-slate-300'
                : 'hover:bg-slate-50 active:bg-slate-100'
            }`}
          >
            <div className="flex items-center gap-2.5 sm:gap-3 flex-1 min-w-0">
              <div className={`relative w-9 h-9 sm:w-10 sm:h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                getProviderBgColor(displayKey, selectedRoomId === room.id)
              }`}>
                <span className={`text-base sm:text-lg font-semibold ${getProviderTextColor(displayKey, selectedRoomId === room.id)}`}>
                  {getProviderIcon(displayKey)}
                </span>
                {room.has_unread && (
                  <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 border-2 border-white rounded-full"></span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <span className={`font-medium truncate text-sm sm:text-base ${
                  selectedRoomId === room.id ? 'text-slate-800' : 'text-slate-700'
                } ${room.has_unread ? 'font-bold' : ''}`}>
                  {room.name}
                </span>
                {room.has_unread && (
                  <span className="flex-shrink-0 px-1.5 py-0.5 bg-red-500 text-white text-xs font-semibold rounded">
                    NEW
                  </span>
                )}
              </div>
            </div>
            {isAdmin && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  if (confirm(`Delete room "${room.name}"?`)) {
                    setDeletingRoomId(room.id);
                    try {
                      await onDeleteRoom(room.id);
                    } catch (err) {
                      alert(`Failed to delete room: ${err instanceof Error ? err.message : 'Unknown error'}`);
                    } finally {
                      setDeletingRoomId(null);
                    }
                  }
                }}
                disabled={deletingRoomId === room.id}
                className="opacity-40 hover:opacity-100 transition-opacity p-2 hover:bg-red-100 active:bg-red-200 rounded text-red-500 hover:text-red-700 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation disabled:opacity-50 disabled:cursor-not-allowed"
                title="Delete room"
              >
                {deletingRoomId === room.id ? (
                  <svg className="w-4 h-4 sm:w-5 sm:h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
              </button>
            )}
          </div>
          );
        })
      )}
    </div>
  );
};
