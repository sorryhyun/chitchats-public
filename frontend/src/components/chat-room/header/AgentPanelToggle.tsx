import { Button } from '@/components/ui/button';
import { useAuth } from '../../../contexts/AuthContext';
import { useChatRoomControls } from '../../../contexts/ChatRoomControlsContext';

export const AgentPanelToggle = () => {
  const { isAdmin } = useAuth();
  const {
    isAgentManagerCollapsed,
    onShowAgentManager,
    onToggleAgentManagerCollapse,
    onClearMessages,
  } = useChatRoomControls();

  // Handle click based on screen size
  const handleAgentButtonClick = () => {
    // lg breakpoint is 1024px
    if (window.innerWidth >= 1024) {
      onToggleAgentManagerCollapse();
    } else {
      onShowAgentManager();
    }
  };

  return (
    <div className="flex items-center gap-1 sm:gap-mobile">
      {/* Unified Agents Button */}
      <button
        onClick={handleAgentButtonClick}
        className="btn-icon-mobile text-slate-600 hover:bg-slate-100 rounded-full transition-colors sm:p-2 sm:min-w-[44px] sm:min-h-[44px] lg:p-2"
        title={isAgentManagerCollapsed ? 'Show agents' : 'Hide agents'}
      >
        <svg className="icon-mobile sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      </button>

      {/* Reset History Button - Hidden on mobile, visible on tablet+ */}
      {isAdmin && (
        <Button
          onClick={onClearMessages}
          variant="destructive"
          size="sm"
          className="hidden sm:flex rounded-full h-8 sm:h-9 px-2 sm:px-3 text-white"
          title="Reset conversation history"
        >
          <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          <span className="hidden sm:inline ml-1">Reset</span>
        </Button>
      )}
    </div>
  );
};
