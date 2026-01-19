import { createContext, useContext, useState, ReactNode } from 'react';
import type { Agent, AgentCreate } from '../types';
import { useAgents } from '../hooks/useAgents';
import { api } from '../services';

type Provider = 'claude' | 'codex';

interface AgentContextValue {
  // Agent data
  agents: Agent[];
  selectedAgentId: number | null;
  profileAgent: Agent | null;
  loading: boolean;

  // Agent actions
  selectAgent: (agentId: number, provider?: Provider) => Promise<void>;
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

  const selectAgent = async (agentId: number, provider: Provider = 'claude') => {
    try {
      // Get or create direct room with this agent using the specified provider
      const room = await api.getAgentDirectRoom(agentId, provider);
      setSelectedAgentId(agentId);

      // Notify parent (App) about the room selection
      if (onAgentRoomSelected) {
        onAgentRoomSelected(room.id);
      }
    } catch (err) {
      console.error('Failed to open direct chat:', err);
      throw err;
    }
  };

  const createAgent = async (agentData: AgentCreate) => {
    return await createAgentHook(agentData);
  };

  const deleteAgent = async (agentId: number) => {
    await deleteAgentHook(agentId);
    // Clear selection if we deleted the currently selected agent
    if (selectedAgentId === agentId) {
      setSelectedAgentId(null);
    }
  };

  const viewProfile = (agent: Agent) => {
    setProfileAgent(agent);
  };

  const closeProfile = () => {
    setProfileAgent(null);
  };

  const clearSelection = () => {
    setSelectedAgentId(null);
  };

  const value: AgentContextValue = {
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
  };

  return (
    <AgentContext.Provider value={value}>
      {children}
    </AgentContext.Provider>
  );
}
