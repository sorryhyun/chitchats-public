import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check, ChevronRight, MessageSquare } from 'lucide-react';
import type { Message } from '../types';
import { getAgentProfilePicUrl } from '../utils/api';
import { cn } from '@/lib/utils';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface MessageListProps {
  messages: Message[];
}

// Memoized ReactMarkdown plugins to prevent recreation on each render
const remarkPlugins = [remarkGfm];

// Memoized ReactMarkdown components to prevent recreation on each render
const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-1 last:mb-0">{children}</p>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="list-disc list-inside my-1">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="list-decimal list-inside my-1">{children}</ol>,
  li: ({ children }: { children?: React.ReactNode }) => <li className="mb-0.5">{children}</li>,
  code: ({ className, children, ...props }: React.ComponentPropsWithoutRef<'code'> & { className?: string }) => {
    const isInline = !className;
    return isInline ? (
      <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
        {children}
      </code>
    ) : (
      <code className="block bg-secondary text-secondary-foreground p-3 rounded-lg text-sm font-mono overflow-x-auto" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }: { children?: React.ReactNode }) => <pre className="my-2 rounded-lg overflow-hidden">{children}</pre>,
};

// Check if two messages should be grouped (same sender, within 5 minutes)
const shouldGroupWithPrevious = (current: Message, previous: Message | null): boolean => {
  if (!previous) return false;
  if (current.role !== previous.role) return false;
  if (current.participant_type === 'system' || previous.participant_type === 'system') return false;

  // For assistant messages, check agent_id
  if (current.role === 'assistant') {
    if (current.agent_id !== previous.agent_id) return false;
  }

  // For user messages, check participant type and name
  if (current.role === 'user') {
    if (current.participant_type !== previous.participant_type) return false;
    if (current.participant_name !== previous.participant_name) return false;
  }

  // Check time difference (5 minutes)
  const timeDiff = new Date(current.timestamp).getTime() - new Date(previous.timestamp).getTime();
  return timeDiff < 5 * 60 * 1000;
};

export const MessageList = React.memo(({ messages }: MessageListProps) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [expandedThinking, setExpandedThinking] = useState<Set<number | string>>(new Set());
  const [copiedMessageId, setCopiedMessageId] = useState<number | string | null>(null);
  const hasScrolledInitiallyRef = useRef(false);
  const scrollCheckTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Reset scroll flag when messages become empty (e.g., switching rooms)
  useEffect(() => {
    if (messages.length === 0) {
      hasScrolledInitiallyRef.current = false;
    }
  }, [messages.length]);

  // Scroll to bottom on initial load or when first messages arrive
  useEffect(() => {
    if (messages.length > 0 && !hasScrolledInitiallyRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
      hasScrolledInitiallyRef.current = true;
    }
  }, [messages.length > 0]);

  // Smart scroll for new messages (only if user is near bottom) - throttled to avoid DOM reflows
  useEffect(() => {
    if (hasScrolledInitiallyRef.current) {
      if (scrollCheckTimeoutRef.current) {
        clearTimeout(scrollCheckTimeoutRef.current);
      }
      scrollCheckTimeoutRef.current = setTimeout(() => {
        const container = containerRef.current;
        if (container) {
          const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
          if (isNearBottom) {
            scrollToBottom();
          }
        }
        scrollCheckTimeoutRef.current = null;
      }, 50);
    }

    return () => {
      if (scrollCheckTimeoutRef.current) {
        clearTimeout(scrollCheckTimeoutRef.current);
      }
    };
  }, [messages, scrollToBottom]);

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

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  };

  const formatFullTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const today = new Date();
    const isToday = date.toDateString() === today.toDateString();

    if (isToday) {
      return `Today at ${formatTime(timestamp)}`;
    }

    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined,
    }) + ` at ${formatTime(timestamp)}`;
  };

  const copyToClipboard = useCallback(async (messageId: number | string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, []);

  // Get sender name for a message
  const getSenderName = (message: Message): string => {
    if (message.role === 'user') {
      if (message.participant_type === 'character' && message.participant_name) {
        return message.participant_name;
      } else if (message.participant_type === 'situation_builder') {
        return 'Situation Builder';
      }
      return 'You';
    }
    return message.agent_name || 'Agent';
  };

  // Compute grouped messages
  const groupedMessages = useMemo(() => {
    return messages.map((message, index) => ({
      message,
      isGrouped: shouldGroupWithPrevious(message, messages[index - 1] || null),
    }));
  }, [messages]);

  return (
    <ScrollArea ref={containerRef} className="flex-1 bg-background">
      <div className="px-4 py-2">
        {messages.length === 0 ? (
          <div className="h-full min-h-[400px] flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <MessageSquare className="w-16 h-16 mx-auto mb-4 opacity-50" strokeWidth={1.5} />
              <p className="text-lg font-medium">No messages yet</p>
              <p className="text-sm mt-1">Start the conversation!</p>
            </div>
          </div>
        ) : (
          <TooltipProvider>
            {groupedMessages.map(({ message, isGrouped }, index) => {
              // System messages
              if (message.participant_type === 'system') {
                return (
                  <div key={message.id || index} className="flex justify-center py-2 animate-fadeIn">
                    <div className="text-center text-xs text-muted-foreground bg-muted px-4 py-1.5 rounded-full">
                      {message.content}
                    </div>
                  </div>
                );
              }

              const senderName = getSenderName(message);
              const isUser = message.role === 'user';

              return (
                <div
                  key={message.id || index}
                  className={cn(
                    'message-row group relative py-1 px-2 -mx-2 rounded transition-colors',
                    !isGrouped && 'mt-3',
                    index === 0 && 'mt-0',
                    isUser ? 'flex justify-end' : ''
                  )}
                >
                  {/* Hover timestamp for grouped messages */}
                  {isGrouped && !isUser && (
                    <span className="message-actions absolute left-0 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground w-12 text-right pr-2">
                      {formatTime(message.timestamp)}
                    </span>
                  )}

                  <div className={cn(
                    'flex gap-3',
                    isUser ? 'flex-row-reverse max-w-[80%]' : 'max-w-[85%]'
                  )}>
                    {/* Avatar - only show for first message in group (agents only) */}
                    {!isUser && (
                      <div className="w-10 flex-shrink-0">
                        {!isGrouped && (
                          <Avatar className="w-10 h-10">
                            {message.agent_profile_pic && message.agent_name ? (
                              <>
                                <AvatarImage
                                  src={getAgentProfilePicUrl({ name: message.agent_name, profile_pic: message.agent_profile_pic }) || ''}
                                  alt={message.agent_name}
                                />
                                <AvatarFallback className="bg-gradient-to-br from-emerald-400 to-cyan-500 text-white font-semibold">
                                  {message.agent_name[0].toUpperCase()}
                                </AvatarFallback>
                              </>
                            ) : (
                              <AvatarFallback className="bg-gradient-to-br from-emerald-400 to-cyan-500 text-white font-semibold">
                                {message.agent_name?.[0]?.toUpperCase() || 'A'}
                              </AvatarFallback>
                            )}
                          </Avatar>
                        )}
                      </div>
                    )}

                    <div className={cn(
                      'min-w-0',
                      isUser ? 'flex flex-col items-end' : 'flex-1'
                    )}>
                      {/* Header with name and timestamp - only for standalone messages (agents only) */}
                      {!isGrouped && !isUser && (
                        <div className="flex items-baseline gap-2 mb-0.5">
                          <span className="font-semibold text-sm hover:underline cursor-pointer text-foreground">
                            {senderName}
                          </span>
                          {!message.is_typing && !message.is_chatting && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="text-xs text-muted-foreground cursor-default">
                                  {formatFullTimestamp(message.timestamp)}
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>
                                {new Date(message.timestamp).toLocaleString()}
                              </TooltipContent>
                            </Tooltip>
                          )}
                        </div>
                      )}

                      {/* Thinking block */}
                      {message.role === 'assistant' && message.thinking && !message.is_typing && !message.is_chatting && (
                        <>
                          <button
                            onClick={() => toggleThinking(message.id)}
                            className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-primary transition-colors mb-1"
                          >
                            <ChevronRight
                              className={cn('w-4 h-4 transition-transform', expandedThinking.has(message.id) && 'rotate-90')}
                            />
                            <span>Thinking Process</span>
                          </button>
                          {expandedThinking.has(message.id) && (
                            <div className="pl-3 py-2 my-1 border-l-2 border-primary/30 text-muted-foreground text-sm bg-muted/30 rounded-r-lg">
                              <div className="whitespace-pre-wrap break-words leading-relaxed italic font-mono text-xs">
                                {message.thinking}
                              </div>
                            </div>
                          )}
                        </>
                      )}

                      {/* Image attachment */}
                      {message.image_data && (
                        <div className="mb-2">
                          <img
                            src={`data:${message.image_data.media_type};base64,${message.image_data.data}`}
                            alt="Attached image"
                            className="max-w-full max-h-80 rounded-xl shadow-sm cursor-pointer hover:opacity-95 transition-opacity"
                            onClick={() => {
                              const win = window.open();
                              if (win) {
                                win.document.write(`<img src="data:${message.image_data!.media_type};base64,${message.image_data!.data}" />`);
                              }
                            }}
                          />
                        </div>
                      )}

                      {/* Partial thinking while chatting */}
                      {message.is_chatting && message.thinking && (
                        <div className="pl-3 py-2 my-1 border-l-2 border-primary/30 text-muted-foreground text-sm bg-muted/30 rounded-r-lg">
                          <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-1">
                            <ChevronRight className="w-4 h-4 rotate-90" />
                            <span>Thinking...</span>
                          </div>
                          <div className="whitespace-pre-wrap break-words leading-relaxed italic font-mono text-xs max-h-40 overflow-y-auto">
                            {message.thinking}
                            <span className="inline-block w-1.5 h-3 bg-muted-foreground/60 ml-0.5 animate-pulse"></span>
                          </div>
                        </div>
                      )}

                      {/* Message content */}
                      <div className={cn(
                        'relative px-4 py-2 rounded-2xl',
                        isUser ? 'bg-primary text-primary-foreground rounded-br-md' : 'bg-muted rounded-bl-md'
                      )}>
                        {message.is_typing || (message.is_chatting && !message.content) ? (
                          <div className="flex items-center gap-1.5 py-1">
                            <span className="typing-dot"></span>
                            <span className="typing-dot"></span>
                            <span className="typing-dot"></span>
                          </div>
                        ) : message.is_chatting && message.content ? (
                          <div className={cn(
                            'text-sm leading-relaxed select-text',
                            'prose prose-sm dark:prose-invert max-w-none',
                            'prose-p:my-1 prose-p:leading-relaxed',
                            'prose-pre:bg-secondary prose-pre:rounded-lg',
                            'prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono prose-code:before:content-none prose-code:after:content-none'
                          )}>
                            <ReactMarkdown
                              remarkPlugins={remarkPlugins}
                              components={markdownComponents}
                            >
                              {message.content}
                            </ReactMarkdown>
                            <span className="inline-block w-2 h-4 bg-foreground/60 ml-0.5 animate-pulse"></span>
                          </div>
                        ) : message.is_skipped ? (
                          <div className="text-sm italic text-muted-foreground">
                            {message.content}
                          </div>
                        ) : (
                          <div className={cn(
                            'text-sm leading-relaxed select-text',
                            !isUser && 'prose prose-sm dark:prose-invert max-w-none',
                            !isUser && 'prose-p:my-1 prose-p:leading-relaxed',
                            !isUser && 'prose-pre:bg-secondary prose-pre:rounded-lg',
                            !isUser && 'prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono prose-code:before:content-none prose-code:after:content-none'
                          )}>
                            <ReactMarkdown
                              remarkPlugins={remarkPlugins}
                              components={markdownComponents}
                            >
                              {message.content}
                            </ReactMarkdown>
                            {message.is_streaming && (
                              <span className="inline-block w-2 h-4 bg-foreground/60 ml-0.5 animate-pulse"></span>
                            )}
                          </div>
                        )}

                        {/* Action buttons on hover */}
                        {!message.is_typing && !message.is_chatting && (
                          <div className={cn(
                            'message-actions absolute -top-3 flex items-center gap-0.5 bg-card border border-border rounded-md shadow-sm',
                            isUser ? '-left-2' : '-right-2'
                          )}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  onClick={() => copyToClipboard(message.id, message.content)}
                                  className="p-1.5 hover:bg-muted rounded transition-colors text-muted-foreground hover:text-foreground"
                                >
                                  {copiedMessageId === message.id ? (
                                    <Check className="w-4 h-4 text-accent" />
                                  ) : (
                                    <Copy className="w-4 h-4" />
                                  )}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>
                                {copiedMessageId === message.id ? 'Copied!' : 'Copy message'}
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        )}
                      </div>

                      {/* Timestamp for user messages */}
                      {isUser && !message.is_typing && !message.is_chatting && !isGrouped && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-xs text-muted-foreground mt-1 cursor-default">
                              {formatFullTimestamp(message.timestamp)}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            {new Date(message.timestamp).toLocaleString()}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </TooltipProvider>
        )}
        <div ref={messagesEndRef} />
      </div>
    </ScrollArea>
  );
});
