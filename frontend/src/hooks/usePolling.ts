import { useEffect, useRef, useState, useCallback } from 'react';
import type { Message, ImageItem } from '../types';
import { getApiKey, API_BASE_URL } from '../services';

interface UsePollingReturn {
  messages: Message[];
  sendMessage: (content: string, participant_type?: string, participant_name?: string, images?: ImageItem[], mentioned_agent_ids?: number[]) => void;
  isConnected: boolean;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  resetMessages: () => Promise<void>;
}

const POLL_INTERVAL = 500; // Poll every 500ms
const STATUS_POLL_INTERVAL = 500; // Poll agent status every 500ms (for typing indicators)

export const usePolling = (roomId: number | null): UsePollingReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusPollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const immediatePollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastMessageIdRef = useRef<number>(0);
  const isInitialLoadRef = useRef(true);

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

    // Start polling for new messages using setTimeout to prevent stacking
    const scheduleNextPoll = () => {
      if (!isActive) return;

      pollIntervalRef.current = setTimeout(async () => {
        await pollNewMessages();
        scheduleNextPoll(); // Schedule next poll after this one completes
      }, POLL_INTERVAL);
    };

    // Start polling for chatting agent status (faster polling)
    const scheduleNextStatusPoll = () => {
      if (!isActive) return;

      statusPollIntervalRef.current = setTimeout(async () => {
        await pollChattingAgents();
        scheduleNextStatusPoll(); // Schedule next poll after this one completes
      }, STATUS_POLL_INTERVAL);
    };

    // Start both polling cycles
    scheduleNextPoll();
    scheduleNextStatusPoll();

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
  }, [roomId, fetchAllMessages, pollNewMessages, pollChattingAgents]);

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

  return { messages, sendMessage, isConnected, setMessages, resetMessages };
};
