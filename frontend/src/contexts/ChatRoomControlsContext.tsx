import { createContext, useContext, type ReactNode } from 'react';
import type { Room, Message } from '../types';

export interface ChatRoomControls {
  roomData: Room | null;
  messages: Message[];
  isConnected: boolean;
  isRefreshing: boolean;
  isAgentManagerCollapsed: boolean;
  onRefreshMessages: () => Promise<void>;
  onPauseToggle: () => void;
  onLimitUpdate: (limit: number | null) => void;
  onClearMessages: () => void;
  onRenameRoom: (name: string) => Promise<void>;
  onShowAgentManager: () => void;
  onToggleAgentManagerCollapse: () => void;
}

const ChatRoomControlsContext = createContext<ChatRoomControls | null>(null);

export const ChatRoomControlsProvider = ({
  value,
  children,
}: {
  value: ChatRoomControls;
  children: ReactNode;
}) => (
  <ChatRoomControlsContext.Provider value={value}>{children}</ChatRoomControlsContext.Provider>
);

export const useChatRoomControls = (): ChatRoomControls => {
  const ctx = useContext(ChatRoomControlsContext);
  if (!ctx) {
    throw new Error('useChatRoomControls must be used within ChatRoomControlsProvider');
  }
  return ctx;
};
