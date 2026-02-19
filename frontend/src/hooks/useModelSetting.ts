import { useState, useEffect, useCallback } from 'react';
import { apiRequest } from '../services/apiClient';

interface ModelSetting {
  use_sonnet: boolean;
  model_name: string;
}

export function useModelSetting() {
  const [useSonnet, setUseSonnetState] = useState(false);
  const [modelName, setModelName] = useState('claude-opus-4-6');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiRequest<ModelSetting>('/settings/model')
      .then((data) => {
        setUseSonnetState(data.use_sonnet);
        setModelName(data.model_name);
      })
      .catch(() => {
        // Keep defaults on error
      })
      .finally(() => setLoading(false));
  }, []);

  const setUseSonnet = useCallback(async (value: boolean) => {
    const prevSonnet = useSonnet;
    const prevModel = modelName;

    // Optimistic update
    setUseSonnetState(value);
    setModelName(value ? 'claude-sonnet-4-6' : 'claude-opus-4-6');

    try {
      await apiRequest<ModelSetting>('/settings/model', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_sonnet: value }),
      });
    } catch {
      // Revert on failure
      setUseSonnetState(prevSonnet);
      setModelName(prevModel);
    }
  }, [useSonnet, modelName]);

  return { useSonnet, modelName, setUseSonnet, loading };
}
