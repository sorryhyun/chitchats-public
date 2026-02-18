import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'chitchats-show-excuse';
const SYNC_EVENT = 'chitchats-show-excuse-changed';

export function useExcusePreference() {
  const [showExcuse, setShowExcuseState] = useState<boolean>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? true : stored === 'true';
  });

  // Sync across hook instances via custom event
  useEffect(() => {
    const handler = () => {
      const stored = localStorage.getItem(STORAGE_KEY);
      setShowExcuseState(stored === null ? true : stored === 'true');
    };
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, []);

  const setShowExcuse = useCallback((value: boolean) => {
    setShowExcuseState(value);
    localStorage.setItem(STORAGE_KEY, String(value));
    window.dispatchEvent(new Event(SYNC_EVENT));
  }, []);

  return {
    showExcuse,
    setShowExcuse,
  };
}
