import { useCallback } from 'react';
import { agentService } from '../services';
import { usePollingData, createChangeDetector } from './usePollingData';
import type { Agent, AgentCreate } from '../types';

const POLL_INTERVAL = 10000; // Poll every 10 seconds (agents change infrequently)

// Compare fields that affect agent display
const agentChangeDetector = createChangeDetector<Agent>([
  'name',
  'profile_pic',
  'config_file',
]);

export const useAgents = () => {
  const {
    data: agents,
    setData: setAgents,
    loading,
    error,
    setError,
    refresh,
  } = usePollingData<Agent>({
    fetchFn: agentService.getAllAgents,
    pollInterval: POLL_INTERVAL,
    hasChanges: agentChangeDetector,
  });

  const createAgent = useCallback(async (agentData: AgentCreate): Promise<Agent> => {
    try {
      const newAgent = await agentService.createAgent(agentData);
      setAgents((prev) => [...prev, newAgent]);
      return newAgent;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
      throw err;
    }
  }, [setAgents, setError]);

  const deleteAgent = useCallback(async (agentId: number): Promise<void> => {
    try {
      await agentService.deleteAgent(agentId);
      setAgents((prev) => prev.filter((agent) => agent.id !== agentId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
      throw err;
    }
  }, [setAgents, setError]);

  const refreshAgents = useCallback(() => {
    refresh();
  }, [refresh]);

  return {
    agents,
    loading,
    error,
    createAgent,
    deleteAgent,
    refreshAgents,
  };
};
