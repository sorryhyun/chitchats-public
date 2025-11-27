import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '../types';
import { getAgentProfilePicUrl } from '../utils/api';

interface MessageListProps {
  messages: Message[];
}

export const MessageList = ({ messages }: MessageListProps) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [expandedThinking, setExpandedThinking] = useState<Set<number | string>>(new Set());
  const [copiedMessageId, setCopiedMessageId] = useState<number | string | null>(null);
  const hasScrolledInitiallyRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Reset scroll flag when messages become empty (e.g., switching rooms)
  useEffect(() => {
    if (messages.length === 0) {
      hasScrolledInitiallyRef.current = false;
    }
  }, [messages.length]);

  // Scroll to bottom on initial load or when first messages arrive
  useEffect(() => {
    if (messages.length > 0 && !hasScrolledInitiallyRef.current) {
      // Use instant scroll on initial load for better UX
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
      hasScrolledInitiallyRef.current = true;
    }
  }, [messages.length > 0]);

  // Smart scroll for new messages (only if user is near bottom)
  useEffect(() => {
    if (hasScrolledInitiallyRef.current) {
      const container = containerRef.current;
      if (container) {
        const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
        if (isNearBottom) {
          scrollToBottom();
        }
      }
    }
  }, [messages]);

  const toggleThinking = (messageId: number | string) => {
    setExpandedThinking(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  };

  const copyToClipboard = async (messageId: number | string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50">
      {messages.length === 0 ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center text-slate-400">
            <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-lg font-medium">No messages yet</p>
            <p className="text-sm mt-1">Start the conversation!</p>
          </div>
        </div>
      ) : (
        messages.map((message, index) => {
          // Render system messages (e.g., "invited [agent_name]") with centered styling
          if (message.participant_type === 'system') {
            return (
              <div key={message.id || index} className="flex justify-center py-2 animate-fadeIn">
                <div className="text-center text-sm text-slate-400 bg-slate-100 px-4 py-1.5 rounded-full">
                  {message.content}
                </div>
              </div>
            );
          }

          // Regular messages (user or assistant)
          return (
            <div
              key={message.id || index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn`}
            >
              <div className={`flex gap-3 max-w-3xl ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
              {/* Avatar */}
              {message.role === 'user' ? (
                <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm bg-gradient-to-br from-indigo-500 to-purple-600">
                  <span className="text-white font-bold text-sm">U</span>
                </div>
              ) : message.agent_profile_pic && message.agent_name ? (
                <img
                  src={getAgentProfilePicUrl({ name: message.agent_name, profile_pic: message.agent_profile_pic }) || ''}
                  alt={message.agent_name || 'Agent'}
                  className="w-10 h-10 rounded-full flex-shrink-0 shadow-sm object-cover"
                  onError={(e) => {
                    // Fallback to default avatar if image fails to load
                    e.currentTarget.style.display = 'none';
                    const parent = e.currentTarget.parentElement;
                    if (parent) {
                      const fallback = document.createElement('div');
                      fallback.className = 'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm bg-gradient-to-br from-emerald-400 to-cyan-500';
                      fallback.innerHTML = `<span class="text-white font-bold text-sm">${message.agent_name?.[0]?.toUpperCase() || 'A'}</span>`;
                      parent.appendChild(fallback);
                    }
                  }}
                />
              ) : (
                <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm bg-gradient-to-br from-emerald-400 to-cyan-500">
                  <span className="text-white font-bold text-sm">
                    {message.agent_name?.[0]?.toUpperCase() || 'A'}
                  </span>
                </div>
              )}

              {/* Message Content */}
              <div className="flex flex-col gap-1 min-w-0">
                {message.role === 'assistant' && message.agent_name && (
                  <div className="flex items-center gap-2 px-1">
                    <span className="font-semibold text-sm text-slate-700">{message.agent_name}</span>
                    {!message.is_typing && !message.is_chatting && (
                      <span className="text-xs text-slate-400">{formatTime(message.timestamp)}</span>
                    )}
                  </div>
                )}
                {message.role === 'user' && (
                  <div className="flex items-center gap-2 px-1 justify-end">
                    <span className="font-semibold text-sm text-slate-700">
                      {message.participant_type === 'character' && message.participant_name
                        ? message.participant_name
                        : message.participant_type === 'situation_builder'
                        ? 'Situation Builder'
                        : 'You'}
                    </span>
                    {!message.is_typing && !message.is_chatting && (
                      <span className="text-xs text-slate-400">{formatTime(message.timestamp)}</span>
                    )}
                  </div>
                )}

                <div className="flex flex-col gap-2 min-w-0">
                  {/* Thinking block for assistant messages */}
                  {message.role === 'assistant' && message.thinking && !message.is_typing && !message.is_chatting && (
                    <button
                      onClick={() => toggleThinking(message.id)}
                      className="flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-indigo-600 transition-colors ml-1 mb-1"
                    >
                      <svg
                        className={`w-4 h-4 transition-transform ${expandedThinking.has(message.id) ? 'rotate-90' : ''}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                      <span>Thinking Process</span>
                    </button>
                  )}

                  {/* Expanded thinking content */}
                  {message.role === 'assistant' && message.thinking && expandedThinking.has(message.id) && (
                    <div className="pl-3 py-1 my-2 border-l-2 border-indigo-200 text-slate-500 text-sm bg-slate-50/50 rounded-r-lg">
                      <div className="whitespace-pre-wrap break-words leading-relaxed italic font-mono text-xs">
                        {message.thinking}
                      </div>
                    </div>
                  )}

                  {/* Image attachment */}
                  {message.image_data && (
                    <div className="mb-2">
                      <img
                        src={`data:${message.image_data.media_type};base64,${message.image_data.data}`}
                        alt="Attached image"
                        className="max-w-full max-h-80 rounded-xl shadow-sm cursor-pointer hover:opacity-95 transition-opacity"
                        onClick={() => {
                          // Open image in new tab for full view
                          const win = window.open();
                          if (win) {
                            win.document.write(`<img src="data:${message.image_data!.media_type};base64,${message.image_data!.data}" />`);
                          }
                        }}
                      />
                    </div>
                  )}

                  {/* Message content */}
                  <div
                    className={`relative group px-4 py-3 rounded-2xl shadow-sm ${
                      message.role === 'user'
                        ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-tr-sm shadow-indigo-200'
                        : message.is_skipped
                        ? 'bg-slate-50 text-slate-400 rounded-tl-sm'
                        : 'bg-white text-slate-800 rounded-tl-sm shadow-slate-200/50 ring-1 ring-slate-100'
                    }`}
                  >
                    {message.is_typing || message.is_chatting ? (
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                        <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                        <span className="text-sm text-slate-500 ml-1">chatting...</span>
                      </div>
                    ) : message.is_skipped ? (
                      <div className="text-sm italic opacity-75">
                        {message.content}
                      </div>
                    ) : (
                      <>
                        <div className="prose prose-sm max-w-none break-words leading-relaxed select-text prose-p:leading-relaxed prose-pre:bg-slate-800 prose-pre:rounded-xl">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              // Custom styling for markdown elements
                              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                              strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                              em: ({ children }) => <em className="italic">{children}</em>,
                              ul: ({ children }) => <ul className="list-disc list-inside mb-2">{children}</ul>,
                              ol: ({ children }) => <ol className="list-decimal list-inside mb-2">{children}</ol>,
                              li: ({ children }) => <li className="mb-1">{children}</li>,
                              code: ({ className, children, ...props }: any) => {
                                const isInline = !className;
                                return isInline ? (
                                  <code className="bg-slate-200 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                                    {children}
                                  </code>
                                ) : (
                                  <code className="block bg-slate-800 text-slate-100 p-3 rounded-xl text-sm font-mono overflow-x-auto" {...props}>
                                    {children}
                                  </code>
                                );
                              },
                              pre: ({ children }) => <pre className="mb-2 rounded-xl overflow-hidden">{children}</pre>,
                            }}
                          >
                            {message.content}
                          </ReactMarkdown>
                          {message.is_streaming && (
                            <span className="inline-block w-2 h-4 bg-slate-600 ml-0.5 animate-pulse"></span>
                          )}
                        </div>
                        {/* Copy button */}
                        <button
                          onClick={() => copyToClipboard(message.id, message.content)}
                          className={`absolute bottom-2 right-2 p-1.5 rounded-lg transition-all ${
                            message.role === 'user'
                              ? 'bg-white/20 hover:bg-white/30 text-white'
                              : 'bg-slate-100 hover:bg-slate-200 text-slate-600'
                          } opacity-0 group-hover:opacity-100 focus:opacity-100`}
                          title="Copy message"
                        >
                          {copiedMessageId === message.id ? (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                          )}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
          );
        })
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};
