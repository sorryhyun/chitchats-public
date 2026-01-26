import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

interface UsePollingDataOptions<T> {
  fetchFn: () => Promise<T[]>;
  pollInterval: number;
  hasChanges: (prev: T[], next: T[]) => boolean;
  enabled?: boolean;
}

interface UsePollingDataResult<T> {
  data: T[];
  setData: React.Dispatch<React.SetStateAction<T[]>>;
  loading: boolean;
  error: string | null;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  refresh: () => Promise<void>;
}

/**
 * Generic hook for polling data from an API endpoint with change detection.
 * Prevents unnecessary re-renders by only updating state when data actually changes.
 */
export function usePollingData<T>({
  fetchFn,
  pollInterval,
  hasChanges,
  enabled = true,
}: UsePollingDataOptions<T>): UsePollingDataResult<T> {
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { apiKey } = useAuth();

  const fetchData = useCallback(async (isInitial = false) => {
    try {
      if (isInitial) {
        setLoading(true);
      }
      setError(null);
      const newData = await fetchFn();

      // Only update state if data has actually changed
      setData((prevData) => {
        if (hasChanges(prevData, newData)) {
          return newData;
        }
        return prevData;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Polling fetch error:', err);
    } finally {
      if (isInitial) {
        setLoading(false);
      }
    }
  }, [fetchFn, hasChanges]);

  useEffect(() => {
    // Only fetch if API key is available and polling is enabled
    if (!apiKey || !enabled) {
      setLoading(false);
      return;
    }

    let isActive = true;

    const doFetch = async (isInitial = false) => {
      try {
        if (isInitial) {
          setLoading(true);
        }
        setError(null);
        const newData = await fetchFn();

        if (!isActive) return;

        // Only update state if data has actually changed
        setData((prevData) => {
          if (hasChanges(prevData, newData)) {
            return newData;
          }
          return prevData;
        });
      } catch (err) {
        if (!isActive) return;
        setError(err instanceof Error ? err.message : 'An error occurred');
        console.error('Polling fetch error:', err);
      } finally {
        // Always set loading to false after initial fetch, regardless of isActive
        // This prevents stuck loading state if the component unmounts during fetch
        if (isInitial) {
          setLoading(false);
        }
      }
    };

    // Initial fetch
    doFetch(true);

    // Setup polling using setTimeout to prevent stacking
    const scheduleNextPoll = () => {
      if (!isActive) return;

      pollIntervalRef.current = setTimeout(async () => {
        await doFetch(false);
        scheduleNextPoll(); // Schedule next poll after this one completes
      }, pollInterval);
    };

    // Start polling
    scheduleNextPoll();

    return () => {
      isActive = false;
      if (pollIntervalRef.current) {
        clearTimeout(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [apiKey, enabled, fetchFn, hasChanges, pollInterval]);

  return {
    data,
    setData,
    loading,
    error,
    setError,
    refresh: fetchData,
  };
}

/**
 * Helper function to create a change detector that compares specific fields.
 * Works for any type with an 'id' property.
 */
export function createChangeDetector<T extends { id: number }>(
  compareFields: (keyof T)[]
): (prev: T[], next: T[]) => boolean {
  return (prev: T[], next: T[]): boolean => {
    if (prev.length !== next.length) {
      return true;
    }

    return next.some((newItem) => {
      const prevItem = prev.find((p) => p.id === newItem.id);
      if (!prevItem) return true;

      return compareFields.some(
        (field) => prevItem[field] !== newItem[field]
      );
    });
  };
}
