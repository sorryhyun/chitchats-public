import type { Room, Message } from '../../types';
import { useAuth } from '../../contexts/AuthContext';
import { RoomTitleEditor } from './header/RoomTitleEditor';
import { ConversationCopyButton } from './header/ConversationCopyButton';
import { ConnectionStatus } from './header/ConnectionStatus';
import { RoomBadges } from './header/RoomBadges';
import { AgentPanelToggle } from './header/AgentPanelToggle';
import { RoomControls } from './header/RoomControls';

interface ChatHeaderProps {
  roomName: string;
  roomData: Room | null;
  isConnected: boolean;
  messages: Message[];
  onRefreshMessages: () => Promise<void>;
  isRefreshing: boolean;
  onPauseToggle: () => void;
  onLimitUpdate: (limit: number | null) => void;
  onClearMessages: () => void;
  onRenameRoom: (name: string) => Promise<void>;
  onShowAgentManager: () => void;
  isAgentManagerCollapsed: boolean;
  onToggleAgentManagerCollapse: () => void;
  isSidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
}

export const ChatHeader = ({
  roomName,
  roomData,
  isConnected,
  messages,
  onRefreshMessages,
  isRefreshing,
  onPauseToggle,
  onLimitUpdate,
  onClearMessages,
  onRenameRoom,
  onShowAgentManager,
  isAgentManagerCollapsed,
  onToggleAgentManagerCollapse,
  isSidebarCollapsed,
  onToggleSidebar,
}: ChatHeaderProps) => {
  const { isAdmin } = useAuth();

  // Add left padding on desktop when sidebar is collapsed to avoid hamburger overlap
  // Use ! modifier to override header-padding-mobile which sets pl-4 at lg breakpoint
  const sidebarCollapsedPadding = isSidebarCollapsed ? 'lg:!pl-16' : '';

  return (
    <div className={`sticky top-0 z-10 bg-white/80 backdrop-blur-md supports-[backdrop-filter]:bg-white/60 header-padding-mobile shadow-sm pt-12 lg:pt-2 border-b border-slate-300/50 overflow-hidden select-none ${sidebarCollapsedPadding}`}>
      <div className="flex items-center justify-between gap-1 sm:gap-2 pb-2 min-w-0">
        {/* Room Title - Truncate on mobile */}
        <div className="min-w-0 flex-1">
          <RoomTitleEditor
            roomName={roomName}
            isAdmin={isAdmin}
            onRenameRoom={onRenameRoom}
          />

          {/* Info Row - Only show on larger screens */}
          <div className="hidden sm:flex items-center gap-mobile mt-1 flex-wrap">
            <ConnectionStatus isConnected={isConnected} />
            <RoomBadges roomName={roomName} isPaused={roomData?.is_paused || false} provider={roomData?.default_provider} />
            <ConversationCopyButton roomName={roomName} messages={messages} />
          </div>
        </div>

        {/* Right Controls - Single row on mobile, stacked on larger screens */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {/* Mobile: Show only essential controls */}
          <div className="flex sm:hidden items-center gap-1">
            <button
              onClick={onShowAgentManager}
              className="btn-icon-mobile text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              title="Show agents"
            >
              <svg className="icon-mobile" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </button>
            <button
              onClick={onClearMessages}
              className="btn-icon-mobile text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              title="Reset conversation"
            >
              <svg className="icon-mobile" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
            <button
              onClick={onPauseToggle}
              className={`btn-icon-mobile rounded-lg transition-colors ${
                roomData?.is_paused
                  ? 'bg-green-50 hover:bg-green-100 text-green-600'
                  : 'bg-orange-50 hover:bg-orange-100 text-orange-600'
              }`}
              title={roomData?.is_paused ? 'Resume' : 'Pause'}
            >
              {roomData?.is_paused ? (
                <svg className="icon-mobile" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              ) : (
                <svg className="icon-mobile" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                </svg>
              )}
            </button>
          </div>

          {/* Desktop: Show all controls in columns */}
          <div className="hidden sm:flex flex-col items-end gap-1">
            <AgentPanelToggle
              isAgentManagerCollapsed={isAgentManagerCollapsed}
              onShowAgentManager={onShowAgentManager}
              onToggleAgentManagerCollapse={onToggleAgentManagerCollapse}
              onClearMessages={onClearMessages}
            />
            <RoomControls
              roomData={roomData}
              isRefreshing={isRefreshing}
              onRefreshMessages={onRefreshMessages}
              onPauseToggle={onPauseToggle}
              onLimitUpdate={onLimitUpdate}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
