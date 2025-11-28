import { useState, useEffect, useRef } from 'react';
import { usePolling } from '../hooks/usePolling';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { MessageList } from './MessageList';
import { AgentManager } from './AgentManager';
import { ChatHeader } from './chat-room/ChatHeader';
import { MessageInput } from './chat-room/MessageInput';
import { api } from '../utils/api';
import type { Room, ParticipantType, ImageAttachment } from '../types';
import { useToast } from '../contexts/ToastContext';

interface ChatRoomProps {
  roomId: number | null;
  onRoomRead?: () => void;
  onMarkRoomAsRead?: (roomId: number) => void;
  onRenameRoom: (roomId: number, name: string) => Promise<Room>;
}

export const ChatRoom = ({ roomId, onRoomRead, onMarkRoomAsRead, onRenameRoom }: ChatRoomProps) => {
  const [roomName, setRoomName] = useState('');
  const [roomData, setRoomData] = useState<Room | null>(null);
  const [showAgentManager, setShowAgentManager] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);
  const { addToast } = useToast();
  // Desktop collapse state with localStorage persistence
  const [isAgentManagerCollapsed, setIsAgentManagerCollapsed] = useState(() => {
    const saved = localStorage.getItem('agentManagerCollapsed');
    return saved === 'true';
  });
  const { messages, sendMessage, isConnected, setMessages, resetMessages } = usePolling(roomId);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Focus trap for agent manager drawer
  const agentManagerRef = useFocusTrap<HTMLDivElement>(showAgentManager);

  // Track the last room we marked as read to avoid duplicate calls
  const lastMarkedRoomRef = useRef<number | null>(null);
  // Keep stable references to callbacks
  const onRoomReadRef = useRef(onRoomRead);
  const onMarkRoomAsReadRef = useRef(onMarkRoomAsRead);
  useEffect(() => {
    onRoomReadRef.current = onRoomRead;
    onMarkRoomAsReadRef.current = onMarkRoomAsRead;
  }, [onRoomRead, onMarkRoomAsRead]);

  useEffect(() => {
    if (roomId) {
      fetchRoomDetails();

      // Only mark as read if we haven't marked this room yet
      if (lastMarkedRoomRef.current !== roomId) {
        lastMarkedRoomRef.current = roomId;

        // Optimistically update UI immediately
        onMarkRoomAsReadRef.current?.(roomId);

        // Then make the API call in the background
        api.markRoomAsRead(roomId)
          .catch(err => {
            console.error('Failed to mark room as read:', err);
            // On error, refresh to get the actual state from backend
            onRoomReadRef.current?.();
          });
      }
    }
  }, [roomId]);

  // Persist collapse state to localStorage
  useEffect(() => {
    localStorage.setItem('agentManagerCollapsed', String(isAgentManagerCollapsed));
  }, [isAgentManagerCollapsed]);

  // Handle Escape key to close agent manager drawer
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showAgentManager) {
        setShowAgentManager(false);
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [showAgentManager]);

  const fetchRoomDetails = async () => {
    if (!roomId) return;

    try {
      const room = await api.getRoom(roomId);
      setRoomName(room.name);
      setRoomData(room);
      // Note: Messages are now handled entirely by usePolling hook
      // No need to set messages here as it would conflict with polling
    } catch (err) {
      console.error('Failed to fetch room details:', err);
    }
  };

  const handlePauseToggle = async () => {
    if (!roomId || !roomData) return;

    try {
      const updatedRoom = roomData.is_paused
        ? await api.resumeRoom(roomId)
        : await api.pauseRoom(roomId);
      setRoomData(updatedRoom);
    } catch (err) {
      console.error('Failed to toggle pause:', err);
    }
  };

  const handleLimitUpdate = async (limit: number | null) => {
    if (!roomId) return;

    try {
      const updatedRoom = await api.updateRoom(roomId, { max_interactions: limit });
      setRoomData(updatedRoom);
    } catch (err) {
      console.error('Failed to update interaction limit:', err);
    }
  };

  const handleClearMessages = async () => {
    if (!roomId) return;

    setClearError(null);
    try {
      await api.clearRoomMessages(roomId);
      // Manually clear messages and reset polling state
      // Wait for reset to complete to avoid race conditions with polling
      await resetMessages();
      setShowClearConfirm(false);
      addToast('Messages cleared', 'success');
    } catch (err) {
      console.error('Failed to clear messages:', err);
      setClearError('Failed to clear messages. Please try again.');
      addToast('Failed to clear messages', 'error');
    }
  };

  const handleRenameRoom = async (name: string) => {
    if (!roomId) return;

    try {
      const updatedRoom = await onRenameRoom(roomId, name);
      setRoomName(updatedRoom.name);
      setRoomData((prev) => (prev ? { ...prev, name: updatedRoom.name } : updatedRoom));
    } catch (err) {
      console.error('Failed to rename room:', err);
      throw err;
    }
  };

  const handleRefreshMessages = async () => {
    if (!roomId || isRefreshing) return;

    try {
      setIsRefreshing(true);
      setMessages([]);
      await resetMessages();
      addToast('Messages refreshed', 'success');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSendMessage = (message: string, participantType: ParticipantType, characterName?: string, imageData?: ImageAttachment) => {
    sendMessage(message, participantType, characterName, imageData);
  };

  if (!roomId) {
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 sm:w-24 sm:h-24 mx-auto mb-4 sm:mb-6 bg-gradient-to-br from-emerald-400 to-cyan-500 rounded-full flex items-center justify-center shadow-lg">
            <svg className="w-10 h-10 sm:w-12 sm:h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <h3 className="text-xl sm:text-2xl font-bold text-slate-700 mb-3 sm:mb-4">Welcome to Claude Code RP</h3>
          <p className="text-slate-500 mb-2 text-sm sm:text-base">Select a chatroom or agent from the sidebar</p>
          <p className="text-slate-400 text-xs sm:text-sm">Click an agent to start a direct chat, or create a new chatroom for multiple agents</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex bg-white relative">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <ChatHeader
          roomName={roomName}
          roomData={roomData}
          isConnected={isConnected}
          messages={messages}
          onRefreshMessages={handleRefreshMessages}
          isRefreshing={isRefreshing}
          onPauseToggle={handlePauseToggle}
          onLimitUpdate={handleLimitUpdate}
          onClearMessages={() => setShowClearConfirm(true)}
          onRenameRoom={handleRenameRoom}
          onShowAgentManager={() => setShowAgentManager(!showAgentManager)}
          isAgentManagerCollapsed={isAgentManagerCollapsed}
          onToggleAgentManagerCollapse={() => setIsAgentManagerCollapsed(!isAgentManagerCollapsed)}
        />

        {/* Messages */}
        <MessageList messages={messages} />

        {/* Input Area */}
        <MessageInput
          isConnected={isConnected}
          onSendMessage={handleSendMessage}
        />
      </div>

      {/* Right Sidebar - Agent Manager (Desktop: collapsible, Mobile/Tablet: modal) */}
      <div
        ref={agentManagerRef}
        className={`
          ${isAgentManagerCollapsed ? 'xl:w-0 xl:border-0' : 'xl:w-96 xl:border-l xl:border-slate-200'}
          xl:bg-slate-50 xl:overflow-y-auto xl:static xl:block
          fixed inset-y-0 right-0 z-30 w-80 sm:w-96 bg-slate-50 border-l border-slate-200 overflow-y-auto
          transform transition-all duration-300 ease-in-out
          ${showAgentManager ? 'translate-x-0' : 'translate-x-full xl:translate-x-0'}
        `}
      >
        <div className="xl:hidden flex justify-between items-center p-4 border-b border-slate-200 bg-white sticky top-0 z-10">
          <h3 className="font-bold text-lg text-slate-800">Room Agents</h3>
          <button
            onClick={() => setShowAgentManager(false)}
            className="p-2 hover:bg-slate-100 active:bg-slate-200 rounded-lg transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation"
          >
            <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <AgentManager roomId={roomId} />
      </div>

      {/* Mobile Overlay for Agent Manager */}
      {showAgentManager && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Close agent manager"
          className="xl:hidden fixed inset-0 bg-black bg-opacity-50 z-20 transition-opacity duration-300 ease-in-out"
          onClick={() => setShowAgentManager(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setShowAgentManager(false);
            }
          }}
        />
      )}

      {/* Clear Messages Confirmation Modal */}
      {showClearConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-800">Clear Conversation History?</h3>
                <p className="text-sm text-slate-500">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-slate-600 mb-6">
              Are you sure you want to delete all messages in this room? This will permanently remove the entire conversation history.
            </p>
            {clearError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{clearError}</p>
              </div>
            )}
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowClearConfirm(false);
                  setClearError(null);
                }}
                className="px-4 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 active:bg-slate-400 font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleClearMessages}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 active:bg-red-800 font-medium transition-colors"
              >
                Clear Messages
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
