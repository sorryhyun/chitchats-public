import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'chitchats-thinking-expanded-default';

export function useThinkingPreference() {
  // Default to expanded (true)
  const [expandedByDefault, setExpandedByDefault] = useState<boolean>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? true : stored === 'true';
  });

  // Persist to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(expandedByDefault));
  }, [expandedByDefault]);

  const toggleDefault = useCallback(() => {
    setExpandedByDefault(prev => !prev);
  }, []);

  return {
    expandedByDefault,
    setExpandedByDefault,
    toggleDefault,
  };
}
