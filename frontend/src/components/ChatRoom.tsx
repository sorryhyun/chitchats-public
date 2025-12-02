import { useState, useEffect, useRef, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { MessageList } from './MessageList';
import { AgentManager } from './AgentManager';
import { ChatHeader } from './chat-room/ChatHeader';
import { MessageInput } from './chat-room/MessageInput';
import { api } from '../utils/api';
import type { Room, ParticipantType, ImageAttachment } from '../types';
import { useToast } from '../contexts/ToastContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { MessageSquare, X, AlertTriangle, Plus, Users, BookOpen } from 'lucide-react';

interface ChatRoomProps {
  roomId: number | null;
  onRoomRead?: () => void;
  onMarkRoomAsRead?: (roomId: number) => void;
  onRenameRoom: (roomId: number, name: string) => Promise<Room>;
  onCreateRoom?: () => void;
  onOpenSidebar?: () => void;
  onShowHowToUse?: () => void;
}

export const ChatRoom = ({ roomId, onRoomRead, onMarkRoomAsRead, onRenameRoom, onCreateRoom, onOpenSidebar, onShowHowToUse }: ChatRoomProps) => {
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

  const fetchRoomDetails = useCallback(async () => {
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
  }, [roomId]);

  const handlePauseToggle = useCallback(async () => {
    if (!roomId || !roomData) return;

    try {
      const updatedRoom = roomData.is_paused
        ? await api.resumeRoom(roomId)
        : await api.pauseRoom(roomId);
      setRoomData(updatedRoom);
    } catch (err) {
      console.error('Failed to toggle pause:', err);
    }
  }, [roomId, roomData]);

  const handleLimitUpdate = useCallback(async (limit: number | null) => {
    if (!roomId) return;

    try {
      const updatedRoom = await api.updateRoom(roomId, { max_interactions: limit });
      setRoomData(updatedRoom);
    } catch (err) {
      console.error('Failed to update interaction limit:', err);
    }
  }, [roomId]);

  const handleClearMessages = useCallback(async () => {
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
  }, [roomId, resetMessages, addToast]);

  const handleRenameRoom = useCallback(async (name: string) => {
    if (!roomId) return;

    try {
      const updatedRoom = await onRenameRoom(roomId, name);
      setRoomName(updatedRoom.name);
      setRoomData((prev) => (prev ? { ...prev, name: updatedRoom.name } : updatedRoom));
    } catch (err) {
      console.error('Failed to rename room:', err);
      throw err;
    }
  }, [roomId, onRenameRoom]);

  const handleRefreshMessages = useCallback(async () => {
    if (!roomId || isRefreshing) return;

    try {
      setIsRefreshing(true);
      setMessages([]);
      await resetMessages();
      addToast('Messages refreshed', 'success');
    } finally {
      setIsRefreshing(false);
    }
  }, [roomId, isRefreshing, setMessages, resetMessages, addToast]);

  const handleSendMessage = useCallback((message: string, participantType: ParticipantType, characterName?: string, imageData?: ImageAttachment) => {
    sendMessage(message, participantType, characterName, imageData);
  }, [sendMessage]);

  if (!roomId) {
    return (
      <div className="flex-1 flex items-center justify-center p-4 bg-background">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 sm:w-24 sm:h-24 mx-auto mb-4 sm:mb-6 bg-accent rounded-full flex items-center justify-center shadow-lg">
            <MessageSquare className="w-10 h-10 sm:w-12 sm:h-12 text-accent-foreground" />
          </div>
          <h3 className="text-xl sm:text-2xl font-bold text-foreground mb-3 sm:mb-4">Welcome to Claude Code RP</h3>
          <p className="text-muted-foreground mb-2 text-sm sm:text-base">Select a chatroom or agent from the sidebar</p>
          <p className="text-muted-foreground/70 text-xs sm:text-sm mb-6">Click an agent to start a direct chat, or create a new chatroom for multiple agents</p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            {onCreateRoom && (
              <Button
                onClick={onCreateRoom}
                className="gap-2"
                size="lg"
              >
                <Plus className="w-5 h-5" />
                Create Room
              </Button>
            )}
            {onOpenSidebar && (
              <Button
                onClick={onOpenSidebar}
                variant="outline"
                className="gap-2 lg:hidden"
                size="lg"
              >
                <Users className="w-5 h-5" />
                View Agents
              </Button>
            )}
          </div>

          {onShowHowToUse && (
            <button
              onClick={onShowHowToUse}
              className="mt-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <BookOpen className="w-4 h-4" />
              How to Use
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex bg-background relative">
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
        className={cn(
          isAgentManagerCollapsed ? 'xl:w-0 xl:border-0' : 'xl:w-96 xl:border-l xl:border-border',
          'xl:bg-secondary xl:overflow-y-auto xl:static xl:block',
          'fixed inset-y-0 right-0 z-30 w-80 sm:w-96 bg-secondary border-l border-border overflow-y-auto',
          'transform transition-all duration-300 ease-in-out',
          showAgentManager ? 'translate-x-0' : 'translate-x-full xl:translate-x-0'
        )}
      >
        <div className="xl:hidden flex justify-between items-center p-4 border-b border-border bg-card sticky top-0 z-10">
          <h3 className="font-bold text-lg text-foreground">Room Agents</h3>
          <Button
            onClick={() => setShowAgentManager(false)}
            variant="ghost"
            size="icon"
            className="h-11 w-11"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>
        <AgentManager roomId={roomId} />
      </div>

      {/* Mobile Overlay for Agent Manager */}
      {showAgentManager && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Close agent manager"
          className="xl:hidden fixed inset-0 bg-black/60 z-20 transition-opacity duration-300 ease-in-out"
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
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-card rounded-xl shadow-2xl max-w-md w-full p-6 border border-border">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-6 h-6 text-destructive" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-foreground">Clear Conversation History?</h3>
                <p className="text-sm text-muted-foreground">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-muted-foreground mb-6">
              Are you sure you want to delete all messages in this room? This will permanently remove the entire conversation history.
            </p>
            {clearError && (
              <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
                <p className="text-sm text-destructive">{clearError}</p>
              </div>
            )}
            <div className="flex gap-3 justify-end">
              <Button
                onClick={() => {
                  setShowClearConfirm(false);
                  setClearError(null);
                }}
                variant="outline"
              >
                Cancel
              </Button>
              <Button
                onClick={handleClearMessages}
                variant="destructive"
              >
                Clear Messages
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
