import { useState, useEffect, useCallback } from 'react';
import { useAgents } from './hooks/useAgents';
import { useRooms } from './hooks/useRooms';
import { useFocusTrap } from './hooks/useFocusTrap';
import { useAuth } from './contexts/AuthContext';
import { MainSidebar } from './components/MainSidebar';
import { ChatRoom } from './components/ChatRoom';
import { AgentProfileModal } from './components/AgentProfileModal';
import { HowToUseModal } from './components/HowToUseModal';
import { Login } from './components/Login';
import type { Agent } from './types';
import { api } from './utils/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Loader2, Menu, X } from 'lucide-react';

function App() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { agents, loading: agentsLoading, createAgent, deleteAgent, refreshAgents } = useAgents();
  const { rooms, loading: roomsLoading, createRoom, deleteRoom, renameRoom, refreshRooms, markRoomAsReadOptimistic } = useRooms();

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

  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [profileAgent, setProfileAgent] = useState<Agent | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [showHowToUse, setShowHowToUse] = useState(false);

  // Focus trap for mobile sidebar drawer
  const sidebarRef = useFocusTrap<HTMLDivElement>(isSidebarOpen);

  // Close sidebar when a room/agent is selected on mobile
  useEffect(() => {
    if (selectedRoomId !== null || selectedAgentId !== null) {
      setIsSidebarOpen(false);
    }
  }, [selectedRoomId, selectedAgentId]);

  // Handle Escape key to close sidebar - stable handler that doesn't re-register
  const handleEscape = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsSidebarOpen(false);
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [handleEscape]);

  const handleSelectAgent = async (agentId: number) => {
    try {
      // Get or create direct room with this agent
      const room = await api.getAgentDirectRoom(agentId);
      setSelectedRoomId(room.id);
      setSelectedAgentId(agentId);
    } catch (err) {
      console.error('Failed to open direct chat:', err);
    }
  };

  const handleSelectRoom = (roomId: number) => {
    setSelectedRoomId(roomId);
    setSelectedAgentId(null);
  };

  const handleDeleteRoom = async (roomId: number) => {
    await deleteRoom(roomId);
    // If we deleted the currently selected room, clear the selection
    if (selectedRoomId === roomId) {
      setSelectedRoomId(null);
      setSelectedAgentId(null);
    }
  };

  const handleViewProfile = (agent: Agent) => {
    setProfileAgent(agent);
  };

  const handleCloseProfile = () => {
    setProfileAgent(null);
  };

  const handleUpdateProfile = () => {
    refreshAgents();
  };

  // Show login screen if not authenticated
  if (authLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="flex items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-accent" />
          <p className="text-lg text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  if (agentsLoading || roomsLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="flex items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-accent" />
          <p className="text-lg text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex bg-background relative">
      {/* Mobile Hamburger Menu Button - Fixed position */}
      <Button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        size="icon"
        className="lg:hidden fixed top-4 left-4 z-50 h-12 w-12 rounded-lg shadow-lg bg-accent hover:bg-accent/90"
        aria-label="Toggle menu"
      >
        {isSidebarOpen ? (
          <X className="w-6 h-6" />
        ) : (
          <Menu className="w-6 h-6" />
        )}
      </Button>

      {/* Mobile Overlay */}
      {isSidebarOpen && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Close menu"
          className="lg:hidden fixed inset-0 bg-black/60 z-30 transition-opacity duration-300 ease-in-out"
          onClick={() => setIsSidebarOpen(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setIsSidebarOpen(false);
            }
          }}
        />
      )}

      {/* Main Sidebar with Tabs - Drawer on mobile */}
      <div
        ref={sidebarRef}
        className={cn(
          'fixed lg:static inset-y-0 left-0 z-40',
          'transform transition-transform duration-300 ease-in-out',
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        <MainSidebar
          rooms={rooms}
          selectedRoomId={selectedRoomId}
          onSelectRoom={handleSelectRoom}
          onCreateRoom={createRoom}
          onDeleteRoom={handleDeleteRoom}
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={handleSelectAgent}
          onCreateAgent={createAgent}
          onDeleteAgent={deleteAgent}
          onViewProfile={handleViewProfile}
          onShowHowToUse={() => setShowHowToUse(true)}
        />
      </div>

      {/* Main Chat Area */}
      <ChatRoom
        roomId={selectedRoomId}
        onRoomRead={refreshRooms}
        onMarkRoomAsRead={markRoomAsReadOptimistic}
        onRenameRoom={renameRoom}
        onCreateRoom={createRoom}
        onOpenSidebar={() => setIsSidebarOpen(true)}
        onShowHowToUse={() => setShowHowToUse(true)}
      />

      {/* Agent Profile Modal */}
      {profileAgent && (
        <AgentProfileModal
          agent={profileAgent}
          onClose={handleCloseProfile}
          onUpdate={handleUpdateProfile}
        />
      )}

      {/* How To Use Modal */}
      {showHowToUse && (
        <HowToUseModal onClose={() => setShowHowToUse(false)} />
      )}
    </div>
  );
}

export default App;
