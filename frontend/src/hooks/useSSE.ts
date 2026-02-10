import { useEffect, useRef, useState, useCallback } from 'react';
import { getApiKey, getFetchOptions, API_BASE_URL } from '../services';

interface StreamingAgent {
  thinking_text: string;
  response_text: string;
  agent_name?: string;
  agent_profile_pic?: string | null;
}

interface SSEEvent {
  type: 'stream_start' | 'content_delta' | 'thinking_delta' | 'stream_end' | 'keepalive' | 'new_message' | 'shutdown';
  agent_id?: number;
  agent_name?: string;
  agent_profile_pic?: string | null;
  delta?: string;
  temp_id?: string;
  response_text?: string | null;
  thinking_text?: string | null;
  skipped?: boolean;
  timestamp?: number;
}

interface SSETicketResponse {
  ticket: string;
  expires_in: number;
  room_id: number;
}

interface UseSSEReturn {
  isConnected: boolean;
  streamingAgents: Map<number, StreamingAgent>;
  error: string | null;
}

// Reconnection backoff intervals in milliseconds
const BACKOFF_INTERVALS = [1000, 2000, 5000, 10000, 30000];
const MAX_RECONNECT_ATTEMPTS = 10;

/**
 * Fetch a short-lived SSE ticket for the given room.
 * This keeps the main JWT out of URLs/logs.
 */
async function fetchSSETicket(roomId: number): Promise<string | null> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/rooms/${roomId}/sse-ticket`,
      getFetchOptions({ method: 'POST' })
    );
    if (!response.ok) {
      console.error('Failed to fetch SSE ticket:', response.status);
      return null;
    }
    const data: SSETicketResponse = await response.json();
    return data.ticket;
  } catch (e) {
    console.error('Error fetching SSE ticket:', e);
    return null;
  }
}

export const useSSE = (roomId: number | null): UseSSEReturn => {
  const [isConnected, setIsConnected] = useState(false);
  const [streamingAgents, setStreamingAgents] = useState<Map<number, StreamingAgent>>(new Map());
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(async () => {
    if (!roomId) return;

    // Check if EventSource is available (browser-only API)
    if (typeof EventSource === 'undefined') {
      setError('EventSource not available');
      return;
    }

    const apiKey = getApiKey();
    if (!apiKey) {
      setError('No API key available');
      return;
    }

    // Fetch a short-lived ticket (keeps main JWT out of URLs/logs)
    const ticket = await fetchSSETicket(roomId);
    if (!ticket) {
      if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setError('Connection lost. Please refresh to reconnect.');
        return;
      }
      setError('Failed to obtain SSE ticket');
      const backoffIndex = Math.min(reconnectAttemptRef.current, BACKOFF_INTERVALS.length - 1);
      const delay = BACKOFF_INTERVALS[backoffIndex];
      reconnectAttemptRef.current++;
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
      return;
    }

    // Build SSE URL with short-lived ticket (not the main JWT)
    const url = new URL(`${API_BASE_URL}/rooms/${roomId}/stream`);
    url.searchParams.set('ticket', ticket);

    // Close existing connection if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const eventSource = new EventSource(url.toString());
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
      reconnectAttemptRef.current = 0; // Reset backoff on successful connection
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();
      eventSourceRef.current = null;

      if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setError('Connection lost. Please refresh to reconnect.');
        return;
      }

      // Schedule reconnection with exponential backoff
      const backoffIndex = Math.min(reconnectAttemptRef.current, BACKOFF_INTERVALS.length - 1);
      const delay = BACKOFF_INTERVALS[backoffIndex];
      reconnectAttemptRef.current++;

      setError(`SSE connection lost, reconnecting in ${delay / 1000}s...`);

      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    // Handle stream_start event
    eventSource.addEventListener('stream_start', (event: MessageEvent) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        if (data.agent_id !== undefined) {
          setStreamingAgents(prev => {
            const next = new Map(prev);
            // Use initial thinking_text/response_text if provided (catch-up for reconnecting clients)
            next.set(data.agent_id!, {
              thinking_text: data.thinking_text || '',
              response_text: data.response_text || '',
              agent_name: data.agent_name,
              agent_profile_pic: data.agent_profile_pic,
            });
            return next;
          });
        }
      } catch (e) {
        console.error('Failed to parse stream_start event:', e);
      }
    });

    // Handle content_delta event
    eventSource.addEventListener('content_delta', (event: MessageEvent) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        if (data.agent_id !== undefined && data.delta) {
          setStreamingAgents(prev => {
            const next = new Map(prev);
            const current = next.get(data.agent_id!) || { thinking_text: '', response_text: '' };
            next.set(data.agent_id!, {
              ...current,
              response_text: current.response_text + data.delta,
            });
            return next;
          });
        }
      } catch (e) {
        console.error('Failed to parse content_delta event:', e);
      }
    });

    // Handle thinking_delta event
    eventSource.addEventListener('thinking_delta', (event: MessageEvent) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        if (data.agent_id !== undefined && data.delta) {
          setStreamingAgents(prev => {
            const next = new Map(prev);
            const current = next.get(data.agent_id!) || { thinking_text: '', response_text: '' };
            next.set(data.agent_id!, {
              ...current,
              thinking_text: current.thinking_text + data.delta,
            });
            return next;
          });
        }
      } catch (e) {
        console.error('Failed to parse thinking_delta event:', e);
      }
    });

    // Handle stream_end event
    eventSource.addEventListener('stream_end', (event: MessageEvent) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        if (data.agent_id !== undefined) {
          setStreamingAgents(prev => {
            const next = new Map(prev);
            next.delete(data.agent_id!);
            return next;
          });
        }
      } catch (e) {
        console.error('Failed to parse stream_end event:', e);
      }
    });

    // Handle keepalive (just a ping, no action needed)
    eventSource.addEventListener('keepalive', () => {
      // Connection is alive
    });

    // Handle server shutdown (close connection gracefully)
    eventSource.addEventListener('shutdown', () => {
      console.log('SSE: Server shutting down, closing connection');
      eventSource.close();
      eventSourceRef.current = null;
      setIsConnected(false);
      setStreamingAgents(new Map());
    });

  }, [roomId]);

  // Connect/disconnect on room change
  useEffect(() => {
    if (!roomId) {
      // Clear state when no room
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      setIsConnected(false);
      setStreamingAgents(new Map());
      setError(null);
      return;
    }

    // Connect to new room
    connect();

    // Cleanup on unmount or room change
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      setStreamingAgents(new Map());
    };
  }, [roomId, connect]);

  return { isConnected, streamingAgents, error };
};
