import { useState, useCallback } from 'react';
import { agentService } from '../services/agentService';
import type { AgentConfig } from '../types';

/**
 * Custom hook for fetching available agent configurations
 * Provides loading state and error handling for agent config fetching
 */
export function useFetchAgentConfigs() {
  const [configs, setConfigs] = useState<AgentConfig>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchConfigs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await agentService.getAgentConfigs();
      setConfigs(data.configs);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to fetch configs');
      setError(error);
      console.error('Failed to fetch agent configs:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  return { configs, loading, error, fetchConfigs };
}
