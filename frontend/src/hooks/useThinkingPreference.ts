import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'chitchats-thinking-expanded-default';
const SYNC_EVENT = 'chitchats-thinking-expanded-changed';

function readStored(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === null ? true : stored === 'true';
}

export function useThinkingPreference() {
  // Default to expanded (true)
  const [expandedByDefault, setExpandedByDefaultState] = useState<boolean>(readStored);

  // Sync across hook instances via custom event, so toggling in Settings reaches MessageList
  useEffect(() => {
    const handler = () => setExpandedByDefaultState(readStored());
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, []);

  const setExpandedByDefault = useCallback((value: boolean) => {
    setExpandedByDefaultState(value);
    localStorage.setItem(STORAGE_KEY, String(value));
    window.dispatchEvent(new Event(SYNC_EVENT));
  }, []);

  const toggleDefault = useCallback(() => {
    setExpandedByDefault(!readStored());
  }, [setExpandedByDefault]);

  return {
    expandedByDefault,
    setExpandedByDefault,
    toggleDefault,
  };
}
