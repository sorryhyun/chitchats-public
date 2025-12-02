import { useState, useEffect, useMemo, useCallback } from 'react';
import { api } from '../utils/api';
import type { Agent } from '../types';
import { AgentAvatar } from './AgentAvatar';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Label } from '@/components/ui/label';
import { Users, Search, Plus, X, Loader2 } from 'lucide-react';

interface AgentManagerProps {
  roomId: number;
}

export const AgentManager = ({ roomId }: AgentManagerProps) => {
  const { isAdmin } = useAuth();
  const { addToast } = useToast();
  const [roomAgents, setRoomAgents] = useState<Agent[]>([]);
  const [allAgents, setAllAgents] = useState<Agent[]>([]);
  const [showAddAgent, setShowAddAgent] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);

  const fetchRoomAgents = useCallback(async () => {
    try {
      const data = await api.getRoomAgents(roomId);
      setRoomAgents(data);
    } catch (err) {
      console.error('Failed to fetch room agents:', err);
      addToast('Unable to load room agents. Please try again.', 'error');
    }
  }, [roomId, addToast]);

  const fetchAllAgents = useCallback(async () => {
    try {
      const data = await api.getAllAgents();
      setAllAgents(data);
    } catch (err) {
      console.error('Failed to fetch all agents:', err);
      addToast('Unable to load agents. Please try again.', 'error');
    }
  }, [addToast]);

  useEffect(() => {
    if (roomId) {
      fetchRoomAgents();
      fetchAllAgents();
    }
  }, [roomId, fetchRoomAgents, fetchAllAgents]);

  const handleAddAgent = useCallback(async (agentId: number) => {
    // Find the agent to add from allAgents
    const agentToAdd = allAgents.find(a => a.id === agentId);
    if (!agentToAdd) return;

    // Optimistic update: add agent to roomAgents immediately
    setRoomAgents(prev => [...prev, agentToAdd]);
    setShowAddAgent(false);

    try {
      await api.addAgentToRoom(roomId, agentId);
      addToast('Agent added to room', 'success');
    } catch (err) {
      console.error('Failed to add agent to room:', err);
      // Rollback on error
      setRoomAgents(prev => prev.filter(a => a.id !== agentId));
      addToast('Failed to add agent to room', 'error');
    }
  }, [roomId, allAgents, addToast]);

  const handleRemoveAgent = useCallback(async (agentId: number) => {
    // Store the agent for potential rollback
    const removedAgent = roomAgents.find(a => a.id === agentId);
    if (!removedAgent) return;

    // Optimistic update: remove agent immediately
    setRoomAgents(prev => prev.filter(a => a.id !== agentId));

    try {
      await api.removeAgentFromRoom(roomId, agentId);
      addToast('Agent removed from room', 'success');
    } catch (err) {
      console.error('Failed to remove agent from room:', err);
      // Rollback on error
      setRoomAgents(prev => [...prev, removedAgent]);
      addToast('Failed to remove agent from room', 'error');
    }
  }, [roomId, roomAgents, addToast]);

  const handleUpdateAgent = useCallback(async () => {
    if (!selectedAgent) return;

    setIsUpdating(true);
    // Store original for rollback
    const originalAgent = roomAgents.find(a => a.id === selectedAgent.id);

    // Optimistic update
    setRoomAgents(prev => prev.map(a => a.id === selectedAgent.id ? selectedAgent : a));

    try {
      await api.updateAgent(selectedAgent.id, {
        in_a_nutshell: selectedAgent.in_a_nutshell,
        characteristics: selectedAgent.characteristics,
        backgrounds: selectedAgent.backgrounds,
        memory: selectedAgent.memory,
        recent_events: selectedAgent.recent_events
      });
      setSelectedAgent(null);
      addToast('Agent updated', 'success');
    } catch (err) {
      console.error('Failed to update agent:', err);
      // Rollback on error
      if (originalAgent) {
        setRoomAgents(prev => prev.map(a => a.id === originalAgent.id ? originalAgent : a));
      }
      addToast('Failed to update agent', 'error');
    } finally {
      setIsUpdating(false);
    }
  }, [selectedAgent, roomAgents, addToast]);

  // Memoize computed values to avoid recalculating on every render
  const { availableAgents, filteredAvailableAgents, filteredRoomAgents } = useMemo(() => {
    const available = allAgents.filter(
      (agent) => !roomAgents.some((ra) => ra.id === agent.id)
    );
    const searchLower = searchTerm.toLowerCase();
    return {
      availableAgents: available,
      filteredAvailableAgents: available.filter((agent) =>
        agent.name.toLowerCase().includes(searchLower)
      ),
      filteredRoomAgents: roomAgents.filter((agent) =>
        agent.name.toLowerCase().includes(searchLower)
      ),
    };
  }, [allAgents, roomAgents, searchTerm]);

  return (
    <div className="h-full flex flex-col p-4 bg-background">
      <div className="mb-4 space-y-3">
        <div className="flex items-center gap-2">
          <Users className="w-5 h-5 text-muted-foreground" />
          <h3 className="font-bold text-lg text-foreground">Room Agents</h3>
          <span className="ml-auto text-sm font-medium text-muted-foreground">({roomAgents.length})</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search agents by name"
              className="pl-10 pr-9"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        <Button
          onClick={() => setShowAddAgent(!showAddAgent)}
          variant={showAddAgent ? 'secondary' : 'default'}
          className={cn('w-full gap-2', !showAddAgent && 'bg-accent hover:bg-accent/90')}
        >
          {showAddAgent ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showAddAgent ? 'Cancel' : 'Add Agent to Room'}
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-2">
          {filteredRoomAgents.length === 0 ? (
            <div className="text-center py-8">
              <Users className="w-12 h-12 mx-auto text-muted-foreground/30 mb-2" />
              <p className="text-sm text-muted-foreground">No agents in this room</p>
              <p className="text-xs text-muted-foreground mt-1">Add one to get started</p>
            </div>
          ) : (
            filteredRoomAgents.map((agent) => (
              <div
                key={agent.id}
                className="group px-4 py-3 bg-secondary/50 border border-border rounded-lg text-sm font-medium hover:bg-secondary hover:border-accent/30 transition-all flex items-center gap-3"
              >
                <button
                  onClick={() => setSelectedAgent(agent)}
                  className="flex items-center gap-3 flex-1 min-w-0"
                  title="Click to view/edit"
                >
                  <AgentAvatar agent={agent} size="md" />
                  <span className="text-foreground truncate">{agent.name}</span>
                </button>
                {isAdmin && (
                  <Button
                    onClick={() => {
                      if (confirm(`Remove ${agent.name} from this room?`)) {
                        handleRemoveAgent(agent.id);
                      }
                    }}
                    variant="ghost"
                    size="icon"
                    className="opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 text-muted-foreground hover:text-destructive"
                    title="Remove from room"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {showAddAgent && (
        <div className="mt-4 p-4 bg-card rounded-lg border border-border">
          <div className="flex items-center gap-2 mb-3">
            <h4 className="text-sm font-semibold text-foreground">Available Agents</h4>
            <span className="text-xs text-muted-foreground">({filteredAvailableAgents.length})</span>
          </div>
          {filteredAvailableAgents.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              All agents are already in this room
            </p>
          ) : (
            <ScrollArea className="max-h-64">
              <div className="space-y-2">
                {filteredAvailableAgents.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => handleAddAgent(agent.id)}
                    className="w-full px-3 py-2 bg-secondary/50 hover:bg-accent/10 border border-border hover:border-accent/30 rounded-lg text-sm font-medium text-foreground transition-all flex items-center gap-3"
                  >
                    <AgentAvatar agent={agent} size="sm" />
                    <span className="truncate">{agent.name}</span>
                  </button>
                ))}
              </div>
            </ScrollArea>
          )}
        </div>
      )}

      {selectedAgent && (
        <div className="mt-4 p-4 bg-card rounded-lg border border-border max-h-[60vh] overflow-y-auto">
          <div className="flex justify-between items-center mb-4">
            <div className="flex items-center gap-2">
              <AgentAvatar agent={selectedAgent} size="md" className="w-9 h-9" />
              <h4 className="font-bold text-base text-foreground truncate">{selectedAgent.name}</h4>
            </div>
            <Button
              onClick={() => setSelectedAgent(null)}
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>

          {selectedAgent.config_file && (
            <div className="mb-3">
              <Label className="text-xs font-semibold mb-1.5">Config File</Label>
              <div className="px-3 py-2 bg-secondary border border-border rounded-lg text-xs text-muted-foreground break-all">
                {selectedAgent.config_file}
              </div>
            </div>
          )}

          <div className="space-y-3">
            <div>
              <Label className="text-xs font-semibold mb-1.5">In a Nutshell</Label>
              <Textarea
                value={selectedAgent.in_a_nutshell || ''}
                onChange={(e) => setSelectedAgent({ ...selectedAgent, in_a_nutshell: e.target.value })}
                className="h-16 text-xs resize-none"
                placeholder="Brief identity summary..."
              />
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1.5">Characteristics</Label>
              <Textarea
                value={selectedAgent.characteristics || ''}
                onChange={(e) => setSelectedAgent({ ...selectedAgent, characteristics: e.target.value })}
                className="h-16 text-xs resize-none"
                placeholder="Personality traits..."
              />
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1.5">Backgrounds</Label>
              <Textarea
                value={selectedAgent.backgrounds || ''}
                onChange={(e) => setSelectedAgent({ ...selectedAgent, backgrounds: e.target.value })}
                className="h-16 text-xs resize-none"
                placeholder="Backstory and history..."
              />
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1.5">Memory</Label>
              <Textarea
                value={selectedAgent.memory || ''}
                onChange={(e) => setSelectedAgent({ ...selectedAgent, memory: e.target.value })}
                className="h-16 text-xs resize-none"
                placeholder="Medium-term memory..."
              />
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1.5">Recent Events</Label>
              <Textarea
                value={selectedAgent.recent_events || ''}
                onChange={(e) => setSelectedAgent({ ...selectedAgent, recent_events: e.target.value })}
                className="h-16 text-xs resize-none"
                placeholder="Recent events..."
              />
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1.5">Current System Prompt (Read-only)</Label>
              <Textarea
                value={selectedAgent.system_prompt}
                readOnly
                className="h-24 text-xs bg-secondary text-muted-foreground resize-none"
              />
            </div>

            <Button
              onClick={handleUpdateAgent}
              disabled={isUpdating}
              className="w-full bg-accent hover:bg-accent/90"
            >
              {isUpdating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Updating...
                </>
              ) : (
                'Update Agent'
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
