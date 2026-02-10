import { useState, useEffect } from 'react';
import { useFocusTrap } from './hooks/useFocusTrap';
import { useAuth } from './contexts/AuthContext';
import { RoomProvider, useRoomContext } from './contexts/RoomContext';
import { AgentProvider, useAgentContext } from './contexts/AgentContext';
import { VoiceProvider } from './contexts/VoiceContext';
import { MainSidebar } from './components/sidebar/MainSidebar';
import { ChatRoom } from './components/chat-room/ChatRoom';
import { AgentProfileModal } from './components/AgentProfileModal';
import { HowToDocsModal } from './components/HowToDocsModal';
import { SettingsModal } from './components/sidebar/SettingsModal';
import { ExportModal } from './components/sidebar/ExportModal';
import { Login } from './components/Login';
import { ErrorBoundary } from './components/ErrorBoundary';
import { BREAKPOINTS } from './config/breakpoints';

function AppContent() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const roomContext = useRoomContext();
  const agentContext = useAgentContext();

  // Mobile viewport height fix - sets CSS variable to actual window height
  useEffect(() => {
    const setAppHeight = () => {
      const doc = document.documentElement;
      doc.style.setProperty('--app-height', `${window.innerHeight}px`);
    };

    // Debounce resize events to avoid excessive updates
    let timeoutId: number | undefined;
    const debouncedSetAppHeight = () => {
      clearTimeout(timeoutId);
      timeoutId = window.setTimeout(setAppHeight, 100);
    };

    // Set immediately on mount
    setAppHeight();
    window.addEventListener('resize', debouncedSetAppHeight);

    // Keep orientationchange immediate for better mobile UX
    window.addEventListener('orientationchange', setAppHeight);

    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener('resize', debouncedSetAppHeight);
      window.removeEventListener('orientationchange', setAppHeight);
    };
  }, []);

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  // Desktop sidebar collapse state with localStorage persistence
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved === 'true';
  });
  const [isMobile, setIsMobile] = useState(window.innerWidth < BREAKPOINTS.lg);
  const [showDocsModal, setShowDocsModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);

  // Track window size for responsive behavior
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < BREAKPOINTS.lg);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Focus trap for mobile sidebar drawer
  const sidebarRef = useFocusTrap<HTMLDivElement>(isSidebarOpen);

  // Close sidebar when a room/agent is selected on mobile
  useEffect(() => {
    if (roomContext.selectedRoomId !== null || agentContext.selectedAgentId !== null) {
      setIsSidebarOpen(false);
    }
  }, [roomContext.selectedRoomId, agentContext.selectedAgentId]);

  // Handle Escape key to close sidebar
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isSidebarOpen) {
        setIsSidebarOpen(false);
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isSidebarOpen]);

  // Persist desktop sidebar collapse state
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', String(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  const handleSelectAgent = async (agentId: number, provider: 'claude' | 'codex') => {
    await agentContext.selectAgent(agentId, provider);
  };

  const handleSelectRoom = (roomId: number) => {
    agentContext.clearSelection();
    roomContext.selectRoom(roomId);
  };

  // Show login screen if not authenticated
  if (authLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-lg sm:text-xl text-gray-600">Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  if (agentContext.loading || roomContext.loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-lg sm:text-xl text-gray-600">Loading...</p>
      </div>
    );
  }

  const handleToggleSidebar = () => {
    // On mobile: toggle drawer (isSidebarOpen)
    // On desktop: toggle collapse (isSidebarCollapsed)
    if (isMobile) {
      setIsSidebarOpen(!isSidebarOpen);
    } else {
      setIsSidebarCollapsed(!isSidebarCollapsed);
    }
  };

  return (
    <div className="h-full flex bg-white relative overflow-hidden">
      {/* Hamburger Menu Button - Always visible, fixed position */}
      <button
        onClick={handleToggleSidebar}
        className="fixed top-2 left-2 z-50 p-2.5 min-w-[44px] min-h-[44px] bg-slate-700 text-white rounded-lg shadow-lg hover:bg-slate-600 active:bg-slate-500 transition-colors flex items-center justify-center"
        aria-label="Toggle menu"
      >
        {isMobile ? (
          isSidebarOpen ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )
        ) : (
          isSidebarCollapsed ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          )
        )}
      </button>

      {/* Mobile Overlay */}
      {isSidebarOpen && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Close menu"
          className="lg:hidden fixed inset-0 bg-black/40 z-30 transition-opacity duration-300 ease-in-out"
          onClick={() => setIsSidebarOpen(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setIsSidebarOpen(false);
            }
          }}
        />
      )}

      {/* Main Sidebar with Tabs - Drawer on mobile, collapsible on desktop */}
      <div
        ref={sidebarRef}
        className={`
          fixed lg:static inset-y-0 left-0 z-40
          transform transition-all duration-300 ease-in-out
          ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          ${isSidebarCollapsed ? 'lg:-translate-x-full lg:w-0 lg:overflow-hidden' : 'lg:translate-x-0'}
        `}
      >
        <MainSidebar
          onSelectRoom={handleSelectRoom}
          onSelectAgent={handleSelectAgent}
          onOpenDocs={() => setShowDocsModal(true)}
          onOpenSettings={() => setShowSettingsModal(true)}
          onOpenExport={() => setShowExportModal(true)}
        />
      </div>

      {/* Main Chat Area */}
      <ChatRoom
        roomId={roomContext.selectedRoomId}
        onRoomRead={roomContext.refreshRooms}
        onMarkRoomAsRead={roomContext.markRoomAsReadOptimistic}
        onRenameRoom={roomContext.renameRoom}
        isSidebarCollapsed={isSidebarCollapsed}
        onToggleSidebar={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      {/* Agent Profile Modal */}
      {agentContext.profileAgent && (
        <AgentProfileModal
          agent={agentContext.profileAgent}
          onClose={agentContext.closeProfile}
          onUpdate={agentContext.refreshAgents}
          onDelete={agentContext.deleteAgent}
        />
      )}

      {/* How To Docs Modal */}
      {showDocsModal && (
        <HowToDocsModal onClose={() => setShowDocsModal(false)} />
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <SettingsModal
          isOpen={showSettingsModal}
          onClose={() => setShowSettingsModal(false)}
        />
      )}

      {/* Export Modal */}
      {showExportModal && (
        <ExportModal
          isOpen={showExportModal}
          onClose={() => setShowExportModal(false)}
        />
      )}
    </div>
  );
}

// Main App component with providers
function App() {
  return (
    <VoiceProvider>
      <RoomProvider>
        <AgentProviderWrapper />
      </RoomProvider>
    </VoiceProvider>
  );
}

// Wrapper to access room context in agent provider
function AgentProviderWrapper() {
  const roomContext = useRoomContext();

  return (
    <AgentProvider onAgentRoomSelected={(roomId) => {
      roomContext.selectRoom(roomId);
    }}>
      <ErrorBoundary>
        <AppContent />
      </ErrorBoundary>
    </AgentProvider>
  );
}

export default App;
