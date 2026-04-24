import { useEffect, useState } from 'react';

/** Boolean state mirrored to localStorage under `key`. */
export function usePersistentBoolean(key: string, defaultValue = false) {
  const [value, setValue] = useState<boolean>(() => {
    const saved = localStorage.getItem(key);
    return saved === null ? defaultValue : saved === 'true';
  });

  useEffect(() => {
    localStorage.setItem(key, String(value));
  }, [key, value]);

  return [value, setValue] as const;
}
