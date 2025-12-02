import { useState } from 'react';
import { Hash, Users, Plus, X, Search, LogOut, BookOpen } from 'lucide-react';
import type { Agent, AgentCreate, RoomSummary, Room } from '../types';
import { useAuth } from '../contexts/AuthContext';
import { useFetchAgentConfigs } from '../hooks/useFetchAgentConfigs';
import { CreateRoomForm } from './sidebar/CreateRoomForm';
import { RoomListPanel } from './sidebar/RoomListPanel';
import { CreateAgentForm } from './sidebar/CreateAgentForm';
import { AgentListPanel } from './sidebar/AgentListPanel';
import { ThemeToggle } from './ThemeToggle';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

interface MainSidebarProps {
  rooms: RoomSummary[];
  selectedRoomId: number | null;
  onSelectRoom: (roomId: number) => void;
  onCreateRoom: (name: string) => Promise<Room>;
  onDeleteRoom: (roomId: number) => Promise<void>;
  agents: Agent[];
  selectedAgentId: number | null;
  onSelectAgent: (agentId: number) => void;
  onCreateAgent: (agentData: AgentCreate) => Promise<Agent>;
  onDeleteAgent: (agentId: number) => Promise<void>;
  onViewProfile: (agent: Agent) => void;
  onShowHowToUse?: () => void;
}

export const MainSidebar = ({
  rooms,
  selectedRoomId,
  onSelectRoom,
  onCreateRoom,
  onDeleteRoom,
  agents,
  selectedAgentId,
  onSelectAgent,
  onCreateAgent,
  onDeleteAgent,
  onViewProfile,
  onShowHowToUse,
}: MainSidebarProps) => {
  const { logout } = useAuth();
  const [activeTab, setActiveTab] = useState<'rooms' | 'agents'>('rooms');
  const [showRoomForm, setShowRoomForm] = useState(false);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [agentSearchQuery, setAgentSearchQuery] = useState('');
  const { configs: availableConfigs, fetchConfigs } = useFetchAgentConfigs();

  const handleShowAgentForm = () => {
    if (!showAgentForm) {
      fetchConfigs();
    }
    setShowAgentForm(!showAgentForm);
  };

  const filteredAndSortedAgents = agents
    .filter(agent =>
      agent.name.toLowerCase().includes(agentSearchQuery.toLowerCase())
    )
    .sort((a, b) =>
      a.name.localeCompare(b.name, 'ko-KR', { sensitivity: 'base' })
    );

  return (
    <div className="w-80 bg-sidebar-background flex flex-col border-r border-sidebar-border h-full">
      {/* Header */}
      <div className="pl-16 pr-4 py-4 sm:p-5 border-b border-sidebar-border">
        <h2 className="text-lg sm:text-xl font-bold text-sidebar-foreground">Claude Code RP</h2>
        <p className="text-sidebar-foreground/60 text-xs">Multi-agent role play</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-sidebar-border">
        <button
          onClick={() => setActiveTab('rooms')}
          className={cn(
            'flex-1 px-3 py-2.5 font-medium text-sm transition-all flex items-center justify-center gap-2',
            activeTab === 'rooms'
              ? 'text-sidebar-primary border-b-2 border-sidebar-primary bg-sidebar-accent'
              : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground'
          )}
        >
          <Hash className="w-4 h-4" />
          Chatrooms
        </button>
        <button
          onClick={() => setActiveTab('agents')}
          className={cn(
            'flex-1 px-3 py-2.5 font-medium text-sm transition-all flex items-center justify-center gap-2',
            activeTab === 'agents'
              ? 'text-accent border-b-2 border-accent bg-accent/10'
              : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground'
          )}
        >
          <Users className="w-4 h-4" />
          Agents
        </button>
      </div>

      {/* Rooms Tab Content */}
      {activeTab === 'rooms' && (
        <>
          {/* New Room Button (Desktop only) */}
          <div className="hidden lg:block p-3 border-b border-sidebar-border">
            <Button
              onClick={() => setShowRoomForm(!showRoomForm)}
              variant={showRoomForm ? 'secondary' : 'default'}
              className="w-full gap-2"
            >
              {showRoomForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              {showRoomForm ? 'Cancel' : 'New Chatroom'}
            </Button>
          </div>

          {/* Create Room Form */}
          {showRoomForm && (
            <CreateRoomForm
              onCreateRoom={onCreateRoom}
              onClose={() => setShowRoomForm(false)}
            />
          )}

          {/* Rooms List with FAB Container */}
          <div className="relative flex-1 min-h-0">
            <ScrollArea className="h-full">
              <RoomListPanel
                rooms={rooms}
                selectedRoomId={selectedRoomId}
                onSelectRoom={onSelectRoom}
                onDeleteRoom={onDeleteRoom}
              />
            </ScrollArea>

            {/* Floating Action Button (Mobile only) */}
            <Button
              onClick={() => setShowRoomForm(!showRoomForm)}
              size="icon"
              className="lg:hidden fixed bottom-6 right-6 w-14 h-14 rounded-full shadow-lg z-30"
            >
              {showRoomForm ? <X className="w-6 h-6" /> : <Plus className="w-6 h-6" />}
            </Button>
          </div>
        </>
      )}

      {/* Agents Tab Content */}
      {activeTab === 'agents' && (
        <>
          {/* New Agent Button (Desktop only) */}
          <div className="hidden lg:block p-3 border-b border-sidebar-border">
            <Button
              onClick={handleShowAgentForm}
              variant={showAgentForm ? 'secondary' : 'default'}
              className={cn('w-full gap-2', !showAgentForm && 'bg-accent hover:bg-accent/90')}
            >
              {showAgentForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              {showAgentForm ? 'Cancel' : 'New Agent'}
            </Button>
          </div>

          {/* Create Agent Form */}
          {showAgentForm && (
            <CreateAgentForm
              availableConfigs={availableConfigs}
              onCreateAgent={onCreateAgent}
              onClose={() => setShowAgentForm(false)}
            />
          )}

          {/* Search Agents */}
          <div className="p-3 border-b border-sidebar-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                type="text"
                value={agentSearchQuery}
                onChange={(e) => setAgentSearchQuery(e.target.value)}
                placeholder="Search agents..."
                className="pl-9 pr-9 bg-sidebar-accent border-sidebar-border"
              />
              {agentSearchQuery && (
                <button
                  onClick={() => setAgentSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* Agents List with FAB Container */}
          <div className="relative flex-1 min-h-0">
            <ScrollArea className="h-full">
              <AgentListPanel
                agents={filteredAndSortedAgents}
                selectedAgentId={selectedAgentId}
                onSelectAgent={onSelectAgent}
                onDeleteAgent={onDeleteAgent}
                onViewProfile={onViewProfile}
              />
            </ScrollArea>

            {/* Floating Action Button (Mobile only) */}
            <Button
              onClick={handleShowAgentForm}
              size="icon"
              className={cn(
                'lg:hidden fixed bottom-6 right-6 w-14 h-14 rounded-full shadow-lg z-30',
                !showAgentForm && 'bg-accent hover:bg-accent/90'
              )}
            >
              {showAgentForm ? <X className="w-6 h-6" /> : <Plus className="w-6 h-6" />}
            </Button>
          </div>
        </>
      )}

      {/* Footer */}
      <div className="mt-auto border-t border-sidebar-border p-3 space-y-3">
        {/* Theme Toggle */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Theme</span>
          <ThemeToggle />
        </div>

        <Separator className="bg-sidebar-border" />

        {/* How To Use Button */}
        {onShowHowToUse && (
          <Button
            onClick={onShowHowToUse}
            variant="ghost"
            className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
          >
            <BookOpen className="w-4 h-4" />
            How to Use
          </Button>
        )}

        {/* Logout Button */}
        <Button
          onClick={() => {
            if (confirm('Are you sure you want to logout?')) {
              logout();
            }
          }}
          variant="ghost"
          className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </Button>
      </div>
    </div>
  );
};
