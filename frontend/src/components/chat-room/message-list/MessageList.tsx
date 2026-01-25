import { useEffect, useRef, useState, memo, useCallback } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import type { Message } from '../../../types';
import { useWhiteboard } from '../../../hooks/useWhiteboard';
import { MessageRow } from './MessageRow';

interface MessageListProps {
  messages: Message[];
  roomId: number;
}

export const MessageList = memo(({ messages, roomId }: MessageListProps) => {
  const [expandedThinking, setExpandedThinking] = useState<Set<number | string>>(new Set());
  const seenMessagesRef = useRef<Set<number | string>>(new Set());
  const [copiedMessageId, setCopiedMessageId] = useState<number | string | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const lastMessageCountRef = useRef(0);

  // Process whiteboard diffs to get rendered content
  const whiteboardInfo = useWhiteboard(messages);

  // Reset state when messages become empty (e.g., switching rooms)
  useEffect(() => {
    if (messages.length === 0) {
      setIsAtBottom(true);
      lastMessageCountRef.current = 0;
      seenMessagesRef.current = new Set();
      setExpandedThinking(new Set());
    }
  }, [messages.length]);

  // Auto-expand thinking for new messages
  useEffect(() => {
    const messagesToExpand: (number | string)[] = [];

    messages.forEach((msg) => {
      if (!seenMessagesRef.current.has(msg.id)) {
        seenMessagesRef.current.add(msg.id);
        // Auto-expand new messages with thinking
        if (msg.role === 'assistant' && msg.thinking) {
          messagesToExpand.push(msg.id);
        }
      }
    });

    if (messagesToExpand.length > 0) {
      setExpandedThinking(prev => {
        const newSet = new Set(prev);
        messagesToExpand.forEach(id => newSet.add(id));
        return newSet;
      });
    }
  }, [messages]);

  // Auto-scroll to bottom on new messages if user is at bottom
  useEffect(() => {
    if (messages.length > 0 && virtuosoRef.current) {
      const isNewMessage = messages.length > lastMessageCountRef.current;
      lastMessageCountRef.current = messages.length;

      if (isNewMessage && isAtBottom) {
        // Scroll to bottom smoothly when new message arrives
        virtuosoRef.current.scrollToIndex({
          index: messages.length - 1,
          align: 'end',
          behavior: 'smooth',
        });
      }
    }
  }, [messages.length, isAtBottom]);

  const toggleThinking = useCallback((messageId: number | string) => {
    setExpandedThinking(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  }, []);

  const copyToClipboard = useCallback(async (messageId: number | string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, []);

  // Scroll to bottom button handler
  const scrollToBottom = useCallback(() => {
    if (virtuosoRef.current) {
      virtuosoRef.current.scrollToIndex({
        index: messages.length - 1,
        align: 'end',
        behavior: 'smooth',
      });
    }
  }, [messages.length]);

  // Item renderer for Virtuoso - delegates to memoized MessageRow
  const itemContent = useCallback((index: number) => (
    <MessageRow
      message={messages[index]}
      roomId={roomId}
      style={{}} // Virtuoso handles positioning, no need for style prop
      index={index}
      expandedThinking={expandedThinking}
      copiedMessageId={copiedMessageId}
      whiteboardInfo={whiteboardInfo}
      onToggleThinking={toggleThinking}
      onCopyToClipboard={copyToClipboard}
    />
  ), [messages, roomId, expandedThinking, copiedMessageId, whiteboardInfo, toggleThinking, copyToClipboard]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white min-w-0">
        <div className="text-center text-slate-500">
          <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <p className="text-lg font-medium">No messages yet</p>
          <p className="text-sm mt-1">Start the conversation!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden bg-white min-w-0 relative">
      <Virtuoso
        ref={virtuosoRef}
        data={messages}
        totalCount={messages.length}
        itemContent={itemContent}
        initialTopMostItemIndex={messages.length - 1}
        followOutput="smooth"
        atBottomStateChange={setIsAtBottom}
        overscan={200}
        className="h-full"
      />

      {/* Scroll to bottom button */}
      {!isAtBottom && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 sm:bottom-6 sm:right-6 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-full shadow-lg flex items-center gap-2 transition-all hover:scale-105 active:scale-95 z-10"
          title="Scroll to bottom"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
          </svg>
          <span className="text-sm font-medium">New messages</span>
        </button>
      )}
    </div>
  );
});
