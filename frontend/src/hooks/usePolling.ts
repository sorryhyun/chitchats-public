import { useEffect, useRef, useState, useCallback } from 'react';
import type { Message, ImageItem } from '../types';
import { messageService, type ChattingAgent } from '../services/messageService';
import { useSSE } from './useSSE';

interface UsePollingReturn {
  messages: Message[];
  sendMessage: (content: string, participant_type?: string, participant_name?: string, images?: ImageItem[], mentioned_agent_ids?: number[]) => Promise<void>;
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
  const abortControllerRef = useRef<AbortController | null>(null);

  // SSE streaming for real-time updates
  const { isConnected: sseConnected, streamingAgents } = useSSE(useSSEStreaming ? roomId : null);

  // Track previous streaming agent count to detect when agents finish streaming
  const prevStreamingCountRef = useRef<number>(0);

  // Fetch all messages (initial load)
  const fetchAllMessages = useCallback(async () => {
    if (!roomId) return;

    try {
      const allMessages = await messageService.getMessages(roomId, abortControllerRef.current?.signal);
      setMessages(allMessages);

      if (allMessages.length > 0) {
        lastMessageIdRef.current = allMessages[allMessages.length - 1].id as number;
      }

      setIsConnected(true);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      console.error('Error fetching messages:', error);
      setIsConnected(false);
    }
  }, [roomId]);

  // Poll for new messages
  const pollNewMessages = useCallback(async () => {
    if (!roomId) return;

    try {
      const newMessages = await messageService.pollMessages(roomId, lastMessageIdRef.current, abortControllerRef.current?.signal);

      if (newMessages.length > 0) {
        setMessages((prev) => {
          const existingIds = new Set(prev.map(m => m.id));
          const uniqueNewMessages = newMessages.filter((m: Message) => !existingIds.has(m.id));
          if (uniqueNewMessages.length === 0) return prev;

          const newAgentIds = new Set(uniqueNewMessages.map((m: Message) => m.agent_id).filter(Boolean));
          const realMessages = prev.filter(m => !m.is_chatting);
          const chattingIndicators = prev.filter(m => m.is_chatting && !newAgentIds.has(m.agent_id));

          return [...realMessages, ...uniqueNewMessages, ...chattingIndicators];
        });
        lastMessageIdRef.current = newMessages[newMessages.length - 1].id as number;
      }

      setIsConnected(true);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      console.error('Error polling messages:', error);
      setIsConnected(false);
    }
  }, [roomId]);

  // Poll for chatting agent status
  const pollChattingAgents = useCallback(async () => {
    if (!roomId) return;

    try {
      const data = await messageService.getChattingAgents(roomId);
      const chattingAgents = data.chatting_agents || [];

      setMessages((prev) => {
        const prevChatting = prev.filter(m => m.is_chatting);

        if (chattingAgents.length === 0 && prevChatting.length === 0) {
          return prev;
        }

        const withoutChatting = prev.filter(m => !m.is_chatting);

        const chattingMessages = chattingAgents.map((agent: ChattingAgent) => ({
          id: `chatting_${agent.id}` as string,
          agent_id: agent.id,
          agent_name: agent.name,
          agent_profile_pic: agent.profile_pic,
          content: agent.response_text || '',
          role: 'assistant' as const,
          timestamp: new Date().toISOString(),
          is_chatting: true,
          thinking: agent.thinking_text || null,
        }));

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
    } catch (error) {
      console.error('Error polling chatting agents:', error);
    }
  }, [roomId]);

  // Update chatting indicators from SSE streaming agents
  useEffect(() => {
    if (!sseConnected) return;

    setMessages((prev) => {
      const prevChatting = prev.filter(m => m.is_chatting);
      const withoutChatting = prev.filter(m => !m.is_chatting);

      if (streamingAgents.size === 0 && prevChatting.length === 0) {
        return prev;
      }

      const prevProfilePics = new Map<number, string | null | undefined>();
      prevChatting.forEach(m => {
        if (m.agent_id !== undefined && m.agent_id !== null) {
          prevProfilePics.set(m.agent_id, m.agent_profile_pic);
        }
      });

      const chattingMessages: Message[] = [];
      streamingAgents.forEach((state, agentId) => {
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

      prevChatting.forEach(msg => {
        if (msg.agent_id !== undefined && msg.agent_id !== null) {
          if (!streamingAgents.has(msg.agent_id)) {
            chattingMessages.push(msg);
          }
        }
      });

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

  // Trigger immediate poll when an agent finishes streaming
  useEffect(() => {
    const currentCount = streamingAgents.size;
    const prevCount = prevStreamingCountRef.current;

    if (prevCount > 0 && currentCount < prevCount) {
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

    setMessages([]);
    lastMessageIdRef.current = 0;
    isInitialLoadRef.current = true;
    let isActive = true;

    // Abort any in-flight requests from the previous room
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    fetchAllMessages();
    pollChattingAgents();

    const scheduleNextPoll = () => {
      if (!isActive) return;

      pollIntervalRef.current = setTimeout(async () => {
        await pollNewMessages();
        scheduleNextPoll();
      }, POLL_INTERVAL);
    };

    const scheduleNextStatusPoll = () => {
      if (!isActive) return;

      statusPollIntervalRef.current = setTimeout(async () => {
        if (!sseConnected) {
          await pollChattingAgents();
        }
        scheduleNextStatusPoll();
      }, STATUS_POLL_INTERVAL);
    };

    scheduleNextPoll();
    if (!sseConnected) {
      scheduleNextStatusPoll();
    }

    return () => {
      isActive = false;
      abortControllerRef.current?.abort();
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

  const isSendingRef = useRef(false);

  const sendMessage = async (content: string, participant_type?: string, participant_name?: string, images?: ImageItem[], mentioned_agent_ids?: number[]) => {
    if (!roomId || isSendingRef.current) return;

    isSendingRef.current = true;
    try {
      await messageService.sendMessage(roomId, {
        content,
        participant_type,
        participant_name,
        images,
        mentioned_agent_ids,
      });

      // Schedule immediate poll to pick up the new message
      if (immediatePollTimeoutRef.current) {
        clearTimeout(immediatePollTimeoutRef.current);
      }
      immediatePollTimeoutRef.current = setTimeout(() => {
        pollNewMessages();
        immediatePollTimeoutRef.current = null;
      }, 100);
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    } finally {
      isSendingRef.current = false;
    }
  };

  const resetMessages = useCallback(async () => {
    setMessages([]);
    lastMessageIdRef.current = 0;

    if (immediatePollTimeoutRef.current) {
      clearTimeout(immediatePollTimeoutRef.current);
      immediatePollTimeoutRef.current = null;
    }

    await fetchAllMessages();
  }, [fetchAllMessages]);

  return { messages, sendMessage, isConnected, setMessages, resetMessages, sseConnected };
};
