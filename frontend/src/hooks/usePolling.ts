import { useEffect, useRef, useState, useCallback } from 'react';
import type { Message, ImageItem } from '../types';
import { getApiKey, API_BASE_URL } from '../services';
import { useSSE } from './useSSE';

interface UsePollingReturn {
  messages: Message[];
  sendMessage: (content: string, participant_type?: string, participant_name?: string, images?: ImageItem[], mentioned_agent_ids?: number[]) => void;
  isConnected: boolean;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  resetMessages: () => Promise<void>;
  sseConnected: boolean;
}

const POLL_INTERVAL = 5000; // Poll every 5s for new messages (fallback - SSE handles real-time)
const STATUS_POLL_INTERVAL = 5000; // Poll agent status every 5s (fallback when SSE not connected)

export const usePolling = (roomId: number | null, useSSEStreaming = true): UsePollingReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusPollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const immediatePollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastMessageIdRef = useRef<number>(0);
  const isInitialLoadRef = useRef(true);

  // SSE streaming for real-time updates
  const { isConnected: sseConnected, streamingAgents } = useSSE(useSSEStreaming ? roomId : null);

  // Track previous streaming agent count to detect when agents finish streaming
  const prevStreamingCountRef = useRef<number>(0);

  // Fetch all messages (initial load)
  const fetchAllMessages = useCallback(async () => {
    if (!roomId) return;

    try {
      const apiKey = getApiKey();
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      };

      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages`, {
        headers,
      });

      if (response.ok) {
        const allMessages = await response.json();
        setMessages(allMessages);

        // Update last message ID
        if (allMessages.length > 0) {
          lastMessageIdRef.current = allMessages[allMessages.length - 1].id;
        }

        setIsConnected(true);
      } else {
        console.error('Failed to fetch messages:', response.statusText);
        setIsConnected(false);
      }
    } catch (error) {
      console.error('Error fetching messages:', error);
      setIsConnected(false);
    }
  }, [roomId]);

  // Poll for new messages
  const pollNewMessages = useCallback(async () => {
    if (!roomId) return;

    try {
      const apiKey = getApiKey();
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      };

      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const url = lastMessageIdRef.current > 0
        ? `${API_BASE_URL}/rooms/${roomId}/messages/poll?since_id=${lastMessageIdRef.current}`
        : `${API_BASE_URL}/rooms/${roomId}/messages/poll`;

      const response = await fetch(url, { headers });

      if (response.ok) {
        const newMessages = await response.json();

        if (newMessages.length > 0) {
          setMessages((prev) => {
            // Deduplicate: only add messages not already in state
            const existingIds = new Set(prev.map(m => m.id));
            const uniqueNewMessages = newMessages.filter((m: Message) => !existingIds.has(m.id));
            if (uniqueNewMessages.length === 0) return prev;

            // Separate chatting indicators from real messages
            // Insert new messages BEFORE chatting indicators to maintain correct order
            const realMessages = prev.filter(m => !m.is_chatting);
            const chattingIndicators = prev.filter(m => m.is_chatting);

            return [...realMessages, ...uniqueNewMessages, ...chattingIndicators];
          });
          // Update last message ID
          lastMessageIdRef.current = newMessages[newMessages.length - 1].id;
        }

        setIsConnected(true);
      } else {
        console.error('Failed to poll messages:', response.statusText);
        setIsConnected(false);
      }
    } catch (error) {
      console.error('Error polling messages:', error);
      setIsConnected(false);
    }
  }, [roomId]);

  // Poll for chatting agent status
  const pollChattingAgents = useCallback(async () => {
    if (!roomId) return;

    try {
      const apiKey = getApiKey();
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      };

      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/chatting-agents`, { headers });

      if (response.ok) {
        const data = await response.json();
        const chattingAgents = data.chatting_agents || [];

        // Add/update chatting indicators in messages
        setMessages((prev) => {
          const prevChatting = prev.filter(m => m.is_chatting);

          // If nothing is chatting now and nothing was chatting before, avoid rewriting state
          if (chattingAgents.length === 0 && prevChatting.length === 0) {
            return prev;
          }

          // Remove old chatting indicators
          const withoutChatting = prev.filter(m => !m.is_chatting);

          // Add new chatting indicators for agents that are chatting
          const chattingMessages = chattingAgents.map((agent: any) => ({
            id: `chatting_${agent.id}` as any,
            agent_id: agent.id,
            agent_name: agent.name,
            agent_profile_pic: agent.profile_pic,
            content: agent.response_text || '',
            role: 'assistant' as const,
            timestamp: new Date().toISOString(),
            is_chatting: true,
            thinking: agent.thinking_text || null,
          }));

          // If the chatting state hasn't changed (same agents with same thinking/content), avoid state churn
          const hasSameChattingState =
            chattingMessages.length === prevChatting.length &&
            chattingMessages.every((msg: typeof chattingMessages[number]) =>
              prevChatting.some((prevMsg) =>
                prevMsg.agent_id === msg.agent_id &&
                prevMsg.agent_name === msg.agent_name &&
                prevMsg.agent_profile_pic === msg.agent_profile_pic &&
                prevMsg.thinking === msg.thinking &&
                prevMsg.content === msg.content
              )
            );

          if (hasSameChattingState) {
            return prev;
          }

          return [...withoutChatting, ...chattingMessages];
        });
      }
    } catch (error) {
      console.error('Error polling chatting agents:', error);
    }
  }, [roomId]);

  // Update chatting indicators from SSE streaming agents
  useEffect(() => {
    if (!sseConnected) return;

    setMessages((prev) => {
      const prevChatting = prev.filter(m => m.is_chatting);

      // If nothing is streaming now and nothing was chatting before, avoid rewriting state
      if (streamingAgents.size === 0 && prevChatting.length === 0) {
        return prev;
      }

      // Remove old chatting indicators
      const withoutChatting = prev.filter(m => !m.is_chatting);

      // Build a map of previous profile pics for fallback (from polling data)
      const prevProfilePics = new Map<number, string | null | undefined>();
      prevChatting.forEach(m => {
        if (m.agent_id !== undefined && m.agent_id !== null) {
          prevProfilePics.set(m.agent_id, m.agent_profile_pic);
        }
      });

      // Add new chatting indicators from SSE streaming agents
      const chattingMessages: Message[] = [];
      streamingAgents.forEach((state, agentId) => {
        // Use SSE profile_pic if available, otherwise fall back to previous (from polling)
        const profilePic = state.agent_profile_pic ?? prevProfilePics.get(agentId);
        chattingMessages.push({
          id: `chatting_${agentId}` as any,
          agent_id: agentId,
          agent_name: state.agent_name,
          agent_profile_pic: profilePic,
          content: state.response_text || '',
          role: 'assistant' as const,
          timestamp: new Date().toISOString(),
          is_chatting: true,
          thinking: state.thinking_text || null,
        });
      });

      // If the chatting state hasn't changed (same agents with same thinking/content), avoid state churn
      const hasSameChattingState =
        chattingMessages.length === prevChatting.length &&
        chattingMessages.every((msg) =>
          prevChatting.some((prevMsg) =>
            prevMsg.agent_id === msg.agent_id &&
            prevMsg.agent_name === msg.agent_name &&
            prevMsg.agent_profile_pic === msg.agent_profile_pic &&
            prevMsg.thinking === msg.thinking &&
            prevMsg.content === msg.content
          )
        );

      if (hasSameChattingState) {
        return prev;
      }

      return [...withoutChatting, ...chattingMessages];
    });
  }, [sseConnected, streamingAgents]);

  // Trigger immediate poll when an agent finishes streaming (stream_end received)
  // This reduces the delay between chatting indicator disappearing and message appearing
  useEffect(() => {
    const currentCount = streamingAgents.size;
    const prevCount = prevStreamingCountRef.current;

    // If count decreased, an agent finished streaming - poll immediately for the new message
    if (prevCount > 0 && currentCount < prevCount) {
      // Small delay to ensure DB write completes before polling
      const timeoutId = setTimeout(() => {
        pollNewMessages();
      }, 100);

      prevStreamingCountRef.current = currentCount;
      return () => clearTimeout(timeoutId);
    }

    prevStreamingCountRef.current = currentCount;
  }, [streamingAgents, pollNewMessages]);

  // Setup polling
  useEffect(() => {
    if (!roomId) {
      setIsConnected(false);
      return;
    }

    // Clear messages when switching rooms
    setMessages([]);
    lastMessageIdRef.current = 0;
    isInitialLoadRef.current = true;
    let isActive = true;

    // Initial load
    fetchAllMessages();

    // Immediately fetch chatting agents on room switch (don't wait for poll interval)
    // This ensures we see streaming indicators right away when switching back to a room
    pollChattingAgents();

    // Start polling for new messages using setTimeout to prevent stacking
    const scheduleNextPoll = () => {
      if (!isActive) return;

      pollIntervalRef.current = setTimeout(async () => {
        await pollNewMessages();
        scheduleNextPoll(); // Schedule next poll after this one completes
      }, POLL_INTERVAL);
    };

    // Start polling for chatting agent status (fallback when SSE not connected)
    const scheduleNextStatusPoll = () => {
      if (!isActive) return;

      statusPollIntervalRef.current = setTimeout(async () => {
        // Only poll for chatting agents if SSE is not connected
        // SSE provides real-time streaming updates when connected
        if (!sseConnected) {
          await pollChattingAgents();
        }
        scheduleNextStatusPoll(); // Schedule next poll after this one completes
      }, STATUS_POLL_INTERVAL);
    };

    // Start both polling cycles
    scheduleNextPoll();
    // Only start status polling if SSE is not connected
    if (!sseConnected) {
      scheduleNextStatusPoll();
    }

    return () => {
      // Cleanup on unmount or room change
      isActive = false;
      if (pollIntervalRef.current) {
        clearTimeout(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (statusPollIntervalRef.current) {
        clearTimeout(statusPollIntervalRef.current);
        statusPollIntervalRef.current = null;
      }
      if (immediatePollTimeoutRef.current) {
        clearTimeout(immediatePollTimeoutRef.current);
        immediatePollTimeoutRef.current = null;
      }
      setIsConnected(false);
    };
  }, [roomId, fetchAllMessages, pollNewMessages, pollChattingAgents, sseConnected]);

  const sendMessage = async (content: string, participant_type?: string, participant_name?: string, images?: ImageItem[], mentioned_agent_ids?: number[]) => {
    if (!roomId) return;

    try {
      const apiKey = getApiKey();
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      };

      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const messageData: any = {
        content,
        role: 'user',  // Required by MessageCreate schema
      };
      if (participant_type) {
        messageData.participant_type = participant_type;
      }
      if (participant_name) {
        messageData.participant_name = participant_name;
      }
      if (images && images.length > 0) {
        messageData.images = images;
      }
      if (mentioned_agent_ids && mentioned_agent_ids.length > 0) {
        messageData.mentioned_agent_ids = mentioned_agent_ids;
      }

      const response = await fetch(`${API_BASE_URL}/rooms/${roomId}/messages/send`, {
        method: 'POST',
        headers,
        body: JSON.stringify(messageData),
      });

      if (response.ok) {
        // The new message will be picked up by the next poll
        // Cancel any pending immediate poll and schedule a new one
        if (immediatePollTimeoutRef.current) {
          clearTimeout(immediatePollTimeoutRef.current);
        }
        immediatePollTimeoutRef.current = setTimeout(() => {
          pollNewMessages();
          immediatePollTimeoutRef.current = null;
        }, 100);
      } else {
        console.error('Failed to send message:', response.statusText);
      }
    } catch (error) {
      console.error('Error sending message:', error);
    }
  };

  const resetMessages = useCallback(async () => {
    // Clear all messages and reset polling state
    setMessages([]);
    lastMessageIdRef.current = 0;

    // Cancel any pending immediate poll to prevent race conditions
    if (immediatePollTimeoutRef.current) {
      clearTimeout(immediatePollTimeoutRef.current);
      immediatePollTimeoutRef.current = null;
    }

    // Trigger immediate fetch to ensure we're in sync with backend
    // Wait for this to complete before allowing polling to continue
    await fetchAllMessages();
  }, [fetchAllMessages]);

  return { messages, sendMessage, isConnected, setMessages, resetMessages, sseConnected };
};
