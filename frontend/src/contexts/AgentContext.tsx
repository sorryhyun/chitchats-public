import { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';
import type { Agent, AgentCreate } from '../types';
import { useAgents } from '../hooks/useAgents';
import { agentService } from '../services/agentService';

type Provider = 'claude' | 'codex';

interface AgentContextValue {
  // Agent data
  agents: Agent[];
  selectedAgentId: number | null;
  profileAgent: Agent | null;
  loading: boolean;

  // Agent actions
  selectAgent: (agentId: number, provider?: Provider, model?: string) => Promise<void>;
  createAgent: (agentData: AgentCreate) => Promise<Agent>;
  deleteAgent: (agentId: number) => Promise<void>;
  refreshAgents: () => void;
  viewProfile: (agent: Agent) => void;
  closeProfile: () => void;
  clearSelection: () => void;
}

const AgentContext = createContext<AgentContextValue | undefined>(undefined);

export function useAgentContext() {
  const context = useContext(AgentContext);
  if (context === undefined) {
    throw new Error('useAgentContext must be used within an AgentProvider');
  }
  return context;
}

interface AgentProviderProps {
  children: ReactNode;
  onAgentRoomSelected?: (roomId: number) => void; // Callback when agent's direct room is selected
}

export function AgentProvider({ children, onAgentRoomSelected }: AgentProviderProps) {
  const {
    agents,
    loading,
    createAgent: createAgentHook,
    deleteAgent: deleteAgentHook,
    refreshAgents
  } = useAgents();

  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [profileAgent, setProfileAgent] = useState<Agent | null>(null);

  const selectAgent = useCallback(async (agentId: number, provider: Provider = 'claude', model?: string) => {
    try {
      const room = await agentService.getAgentDirectRoom(agentId, provider, model);
      setSelectedAgentId(agentId);
      onAgentRoomSelected?.(room.id);
    } catch (err) {
      console.error('Failed to open direct chat:', err);
      throw err;
    }
  }, [onAgentRoomSelected]);

  const createAgent = useCallback(async (agentData: AgentCreate) => {
    return await createAgentHook(agentData);
  }, [createAgentHook]);

  const deleteAgent = useCallback(async (agentId: number) => {
    await deleteAgentHook(agentId);
    setSelectedAgentId((prev) => (prev === agentId ? null : prev));
  }, [deleteAgentHook]);

  const viewProfile = useCallback((agent: Agent) => {
    setProfileAgent(agent);
  }, []);

  const closeProfile = useCallback(() => {
    setProfileAgent(null);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedAgentId(null);
  }, []);

  const value = useMemo<AgentContextValue>(() => ({
    agents,
    selectedAgentId,
    profileAgent,
    loading,
    selectAgent,
    createAgent,
    deleteAgent,
    refreshAgents,
    viewProfile,
    closeProfile,
    clearSelection,
  }), [agents, selectedAgentId, profileAgent, loading, selectAgent, createAgent, deleteAgent, refreshAgents, viewProfile, closeProfile, clearSelection]);

  return (
    <AgentContext.Provider value={value}>
      {children}
    </AgentContext.Provider>
  );
}
