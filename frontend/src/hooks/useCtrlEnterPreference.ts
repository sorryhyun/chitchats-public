import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'chitchats-ctrl-enter-to-send';
const SYNC_EVENT = 'chitchats-ctrl-enter-to-send-changed';

export function useCtrlEnterPreference() {
  const [ctrlEnterToSend, setCtrlEnterToSendState] = useState<boolean>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? false : stored === 'true';
  });

  // Sync across hook instances via custom event
  useEffect(() => {
    const handler = () => {
      const stored = localStorage.getItem(STORAGE_KEY);
      setCtrlEnterToSendState(stored === null ? false : stored === 'true');
    };
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, []);

  const setCtrlEnterToSend = useCallback((value: boolean) => {
    setCtrlEnterToSendState(value);
    localStorage.setItem(STORAGE_KEY, String(value));
    window.dispatchEvent(new Event(SYNC_EVENT));
  }, []);

  return {
    ctrlEnterToSend,
    setCtrlEnterToSend,
  };
}
