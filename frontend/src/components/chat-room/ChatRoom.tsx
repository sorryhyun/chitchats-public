import { useState, useEffect, useRef, DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { usePolling } from '../../hooks/usePolling';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { MessageList } from './message-list/MessageList';
import { AgentManager } from '../AgentManager';
import { ChatHeader } from './ChatHeader';
import { MessageInput, MessageInputHandle } from './MessageInput';
import { api } from '../../services';
import type { Room, ParticipantType } from '../../types';
import { useToast } from '../../contexts/ToastContext';

interface ChatRoomProps {
  roomId: number | null;
  onRoomRead?: () => void;
  onMarkRoomAsRead?: (roomId: number) => void;
  onRenameRoom: (roomId: number, name: string) => Promise<Room>;
  isSidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
}

export const ChatRoom = ({ roomId, onRoomRead, onMarkRoomAsRead, onRenameRoom, isSidebarCollapsed, onToggleSidebar }: ChatRoomProps) => {
  const { t } = useTranslation('chat');
  const { t: tCommon } = useTranslation('common');
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
  const [isDragging, setIsDragging] = useState(false);
  const messageInputRef = useRef<MessageInputHandle>(null);
  const dragCounterRef = useRef(0);

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

  // Track the last message count to detect new messages
  const lastMessageCountRef = useRef<number>(0);

  useEffect(() => {
    if (roomId) {
      fetchRoomDetails();

      // Mark as read when switching rooms
      if (lastMarkedRoomRef.current !== roomId) {
        lastMarkedRoomRef.current = roomId;
        lastMessageCountRef.current = messages.length;

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

  // Mark as read when new messages arrive while viewing the room
  useEffect(() => {
    if (roomId && messages.length > lastMessageCountRef.current) {
      lastMessageCountRef.current = messages.length;

      // Optimistically update UI immediately
      onMarkRoomAsReadRef.current?.(roomId);

      // Then make the API call in the background
      api.markRoomAsRead(roomId)
        .catch(err => {
          console.error('Failed to mark room as read:', err);
        });
    }
  }, [roomId, messages.length]);

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

  // Handle F5 key to reset conversation
  useEffect(() => {
    const handleF5 = (e: KeyboardEvent) => {
      if (e.key === 'F5' && roomId) {
        e.preventDefault(); // Prevent browser refresh
        setShowClearConfirm(true);
      }
    };
    window.addEventListener('keydown', handleF5);
    return () => window.removeEventListener('keydown', handleF5);
  }, [roomId]);

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
      addToast(t('conversationReset'), 'success');
    } catch (err) {
      console.error('Failed to reset conversation:', err);
      setClearError(t('failedToResetRetry'));
      addToast(t('failedToReset'), 'error');
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
      addToast(t('messagesRefreshed'), 'success');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSendMessage = (message: string, participantType: ParticipantType, characterName?: string, imageData?: string, imageMediaType?: string, mentionedAgentIds?: number[]) => {
    sendMessage(message, participantType, characterName, imageData, imageMediaType, mentionedAgentIds);
  };

  // Drag-and-drop handlers for the entire chatroom
  const handleDragEnter = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      messageInputRef.current?.handleFileSelect(file);
    }
  };

  // Track last mark-as-read call to throttle
  const lastMarkAsReadRef = useRef<number>(0);

  // Mark room as read when user clicks anywhere in the chatroom
  const handleChatRoomClick = () => {
    if (roomId) {
      const now = Date.now();
      // Throttle API calls to once per second
      if (now - lastMarkAsReadRef.current > 1000) {
        lastMarkAsReadRef.current = now;
        onMarkRoomAsReadRef.current?.(roomId);
        api.markRoomAsRead(roomId).catch(err => {
          console.error('Failed to mark room as read:', err);
        });
      }
    }
  };

  if (!roomId) {
    return (
      <div className="flex-1 flex items-center justify-center p-4 bg-white">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 mx-auto mb-4 bg-slate-100 rounded-full flex items-center justify-center">
            <svg className="w-10 h-10 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-slate-700 mb-3">{t('welcomeTitle')}</h3>
          <p className="text-slate-600 mb-6 text-sm">{t('welcomeSubtitle')}</p>

          {/* Action buttons */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center items-center">
            <button
              onClick={() => {
                if (isSidebarCollapsed && onToggleSidebar) {
                  onToggleSidebar();
                }
              }}
              className="w-full sm:w-auto px-6 py-3 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 shadow-sm"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              {t('createChatroom')}
            </button>
            <button
              onClick={() => {
                if (isSidebarCollapsed && onToggleSidebar) {
                  onToggleSidebar();
                }
              }}
              className="w-full sm:w-auto px-6 py-3 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 shadow-sm border border-slate-300"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              {t('browseAgents')}
            </button>
          </div>

          <p className="text-slate-500 text-xs mt-6">{t('clickAgentHint')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex bg-white relative overflow-hidden min-w-0" onClick={handleChatRoomClick}>
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
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleSidebar={onToggleSidebar}
        />

        {/* Message content area - drag-and-drop zone for images */}
        <div
          className="flex-1 flex flex-col min-h-0 relative"
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          {/* Drag overlay */}
          {isDragging && (
            <div className="absolute inset-0 bg-blue-100/90 backdrop-blur-sm flex items-center justify-center z-40 pointer-events-none">
              <div className="text-blue-600 font-medium flex flex-col items-center gap-3">
                <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span className="text-lg">{t('dropImageHere')}</span>
              </div>
            </div>
          )}

          {/* Messages */}
          <MessageList messages={messages} />

          {/* Input Area */}
          <MessageInput
            ref={messageInputRef}
            isConnected={isConnected}
            onSendMessage={handleSendMessage}
            roomAgents={roomData?.agents ?? []}
          />
        </div>
      </div>

      {/* Right Sidebar - Agent Manager (Desktop: collapsible, Mobile/Tablet: modal) */}
      <div
        ref={agentManagerRef}
        className={`
          ${isAgentManagerCollapsed ? 'lg:w-0 lg:border-0' : 'lg:w-96 lg:border-l lg:border-slate-200'}
          lg:bg-slate-50 lg:overflow-y-auto lg:static lg:block lg:h-full
          fixed inset-y-0 right-0 z-30 w-80 sm:w-96 bg-white border-l border-slate-200 overflow-y-auto
          transform transition-all duration-300 ease-in-out
          ${showAgentManager ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'}
        `}
      >
        <div className="lg:hidden flex justify-between items-center p-4 border-b border-slate-200 bg-white sticky top-0 z-10">
          <h3 className="font-bold text-lg text-slate-800">{t('roomAgents')}</h3>
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
          className="lg:hidden fixed inset-0 bg-black/40 z-20 transition-opacity duration-300 ease-in-out"
          onClick={() => setShowAgentManager(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setShowAgentManager(false);
            }
          }}
        />
      )}

      {/* Reset Messages Confirmation Modal */}
      {showClearConfirm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-800">{t('resetConversation')}</h3>
                <p className="text-sm text-slate-500">{t('resetWarning')}</p>
              </div>
            </div>
            <p className="text-slate-600 mb-6">
              {t('resetConfirmMessage')}
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
                {tCommon('cancel')}
              </button>
              <button
                onClick={handleClearMessages}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 active:bg-red-800 font-medium transition-colors"
              >
                {t('reset')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
