import { memo } from 'react';
import type { Message } from '../../../types';
import { getAgentProfilePicUrl } from '../../../services/agentService';
import { ImageAttachment } from './ImageAttachment';
import { MarkdownContent } from './MarkdownContent';
import { useVoice } from '../../../contexts/VoiceContext';

export interface MessageRowProps {
  message: Message;
  roomId: number;
  style: React.CSSProperties;
  index: number;
  expandedThinking: Set<number | string>;
  copiedMessageId: number | string | null;
  whiteboardInfo: Map<number | string, any>;
  showExcuse: boolean;
  onToggleThinking: (messageId: number | string) => void;
  onCopyToClipboard: (messageId: number | string, content: string) => void;
}

export const MessageRow = memo(({
  message,
  roomId,
  style,
  index,
  expandedThinking,
  copiedMessageId,
  whiteboardInfo,
  showExcuse,
  onToggleThinking,
  onCopyToClipboard,
}: MessageRowProps) => {
  const { enabled: voiceEnabled, playingMessageId, generatingMessageId, playMessage, stopPlaying } = useVoice();

  const isPlaying = playingMessageId === message.id;
  const isGenerating = generatingMessageId === message.id;
  const canPlayVoice = voiceEnabled && message.role === 'assistant' && !message.is_typing && !message.is_chatting && !message.is_skipped;

  const handleVoiceClick = () => {
    if (isPlaying) {
      stopPlaying();
    } else if (!isGenerating) {
      playMessage(message.id as number, roomId);
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  };

  const getDisplayContent = (msg: Message): string => {
    const wbInfo = whiteboardInfo.get(msg.id);
    if (wbInfo?.isWhiteboardMessage) {
      // Use rendered content if available, otherwise fall back to original
      return wbInfo.renderedContent || msg.content;
    }
    return msg.content;
  };

  const getContentForCopy = (msg: Message): string => {
    const wbInfo = whiteboardInfo.get(msg.id);

    // For whiteboard messages, return the rendered content without the header or diff format
    if (wbInfo?.isWhiteboardMessage && wbInfo.renderedContent) {
      const rendered = wbInfo.renderedContent;
      // Strip [화이트보드] header for cleaner clipboard content
      if (rendered.startsWith('[화이트보드]\n')) {
        return rendered.slice('[화이트보드]\n'.length);
      }
      if (rendered.startsWith('[화이트보드]')) {
        return rendered.slice('[화이트보드]'.length).trim();
      }
      return rendered;
    }

    // For non-whiteboard or fallback, just return content as-is
    return msg.content;
  };

  const isWhiteboardContent = (content: string): boolean => {
    return content.startsWith('[화이트보드]');
  };

  return (
    <div style={style} className="message-padding-mobile" data-index={index}>
      {message.participant_type === 'system' ? (
        <div className="flex justify-center py-2 animate-fadeIn">
          <div className="text-center text-sm text-slate-500 bg-slate-100 px-4 py-1.5 rounded-full">
            {message.content}
          </div>
        </div>
      ) : (
        <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn`}>
          <div className={`flex gap-2 sm:gap-3 w-full max-w-[92%] sm:max-w-[85%] lg:max-w-3xl ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
            {/* Avatar */}
            {message.role === 'user' ? (
              <div className="avatar-mobile rounded-full flex items-center justify-center flex-shrink-0 bg-slate-700">
                <span className="text-white font-semibold text-sm">U</span>
              </div>
            ) : message.agent_profile_pic && message.agent_name ? (
              <img
                src={getAgentProfilePicUrl({ name: message.agent_name, profile_pic: message.agent_profile_pic }) || ''}
                alt={message.agent_name || 'Agent'}
                className="avatar-mobile avatar-img rounded-full flex-shrink-0 object-cover"
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  const parent = e.currentTarget.parentElement;
                  if (parent) {
                    const fallback = document.createElement('div');
                    fallback.className = 'avatar-mobile rounded-full flex items-center justify-center flex-shrink-0 bg-slate-300';
                    const span = document.createElement('span');
                    span.className = 'text-slate-700 font-semibold text-sm';
                    span.textContent = message.agent_name?.[0]?.toUpperCase() || 'A';
                    fallback.appendChild(span);
                    parent.appendChild(fallback);
                  }
                }}
              />
            ) : (
              <div className="avatar-mobile rounded-full flex items-center justify-center flex-shrink-0 bg-slate-300">
                <span className="text-slate-700 font-semibold text-sm">
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
                    <span className="text-xs text-slate-500">{formatTime(message.timestamp)}</span>
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
                    <span className="text-xs text-slate-500">{formatTime(message.timestamp)}</span>
                  )}
                </div>
              )}

              <div className="flex flex-col gap-2 min-w-0">
                {/* Thinking block - unified for both streaming and completed messages */}
                {message.role === 'assistant' && message.thinking && (
                  <>
                    <button
                      onClick={() => onToggleThinking(message.id)}
                      className="flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors ml-1 mb-1"
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
                      {(message.is_typing || message.is_chatting) && !message.content && (
                        <span className="text-slate-400 italic">thinking...</span>
                      )}
                    </button>

                    {/* Expanded thinking content */}
                    {expandedThinking.has(message.id) && (
                      <div className="pl-3 py-1 my-2 border-l-2 border-slate-300 text-slate-500 text-sm bg-slate-50/50 rounded-r-lg">
                        <div className="whitespace-pre-wrap break-words leading-relaxed italic font-mono text-xs">
                          {message.thinking}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* Excuse reasons - visible when agent uses the excuse tool and showExcuse is enabled */}
                {showExcuse && message.role === 'assistant' && message.excuse_reasons && message.excuse_reasons.length > 0 && (
                  <div className="pl-3 py-2 my-1 border-l-2 border-amber-300 text-amber-700 text-sm bg-amber-50/50 rounded-r-lg">
                    <div className="flex items-center gap-1.5 mb-1 font-medium text-xs text-amber-600">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>Excuse</span>
                    </div>
                    {message.excuse_reasons.map((reason, i) => (
                      <div key={i} className="whitespace-pre-wrap break-words leading-relaxed text-xs">
                        {reason}
                      </div>
                    ))}
                  </div>
                )}

                {/* Image attachment - supports both new images array and legacy single image */}
                {(message.images || (message.image_data && message.image_media_type)) && (
                  <ImageAttachment
                    images={message.images}
                    imageData={message.image_data}
                    imageMediaType={message.image_media_type}
                    isUserMessage={message.role === 'user'}
                  />
                )}

                {/* Message content */}
                <div
                  className={`relative group message-bubble-padding rounded-2xl text-sm sm:text-[15px] leading-relaxed ${
                    message.role === 'user'
                      ? 'bg-slate-700 text-white rounded-tr-sm'
                      : message.is_skipped
                      ? 'bg-slate-50 text-slate-500 rounded-tl-sm'
                      : 'bg-slate-100 text-slate-800 rounded-tl-sm'
                  } ${!message.content && (message.images || message.image_data) ? 'hidden' : ''}`}
                >
                  {message.is_typing || message.is_chatting ? (
                    <div className="flex flex-col gap-2">
                      {/* Show streaming response content with same styling as finished messages */}
                      {message.content ? (
                        <div className={`prose prose-base max-w-none break-words leading-relaxed select-text prose-p:leading-relaxed prose-pre:bg-slate-800 prose-pre:rounded-xl pr-1 ${message.role === 'user' ? 'prose-invert text-white' : ''}`}>
                          <MarkdownContent content={message.content} />
                          <span className="inline-block w-2 h-4 bg-slate-600 ml-0.5 animate-pulse"></span>
                        </div>
                      ) : !message.thinking ? (
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                          <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                          <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                          <span className="text-sm text-slate-600 ml-1">chatting...</span>
                        </div>
                      ) : null}
                    </div>
                  ) : message.is_skipped ? (
                    <div className="text-sm italic opacity-75">
                      {message.content}
                    </div>
                  ) : (
                    <>
                      <div className={`prose prose-base max-w-none break-words leading-relaxed select-text prose-p:leading-relaxed prose-pre:bg-slate-800 prose-pre:rounded-xl pr-1 ${message.role === 'user' ? 'prose-invert text-white' : ''}`}>
                        {isWhiteboardContent(getDisplayContent(message)) ? (
                          <pre className="whitespace-pre font-mono text-sm leading-relaxed overflow-x-auto bg-slate-50 p-3 rounded-lg border border-slate-200">
                            {getDisplayContent(message)}
                          </pre>
                        ) : (
                          <MarkdownContent content={getDisplayContent(message)} />
                        )}
                        {message.is_streaming && (
                          <span className="inline-block w-2 h-4 bg-slate-600 ml-0.5 animate-pulse"></span>
                        )}
                      </div>
                      {/* Action buttons */}
                      <div className="absolute bottom-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                        {/* Voice play button - only for assistant messages when voice is enabled */}
                        {canPlayVoice && (
                          <button
                            onClick={handleVoiceClick}
                            disabled={isGenerating}
                            className={`p-1.5 rounded-lg transition-all ${
                              isPlaying
                                ? 'bg-emerald-100 hover:bg-emerald-200 text-emerald-600'
                                : isGenerating
                                ? 'bg-slate-100 text-slate-400 cursor-wait'
                                : 'bg-slate-100 hover:bg-slate-200 text-slate-600'
                            }`}
                            title={isPlaying ? 'Stop playing' : isGenerating ? 'Generating audio...' : 'Play voice'}
                          >
                            {isGenerating ? (
                              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                            ) : isPlaying ? (
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                              </svg>
                            )}
                          </button>
                        )}
                        {/* Copy button */}
                        <button
                          onClick={() => onCopyToClipboard(message.id, getContentForCopy(message))}
                          className={`p-1.5 rounded-lg transition-all ${
                            message.role === 'user'
                              ? 'bg-white/20 hover:bg-white/30 text-white'
                              : 'bg-slate-100 hover:bg-slate-200 text-slate-600'
                          }`}
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
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison to prevent unnecessary re-renders
  // Only re-render if something about THIS specific message has changed
  const prevWhiteboardInfo = prevProps.whiteboardInfo.get(prevProps.message.id);
  const nextWhiteboardInfo = nextProps.whiteboardInfo.get(nextProps.message.id);

  return (
    prevProps.message.id === nextProps.message.id &&
    prevProps.message.content === nextProps.message.content &&
    prevProps.message.thinking === nextProps.message.thinking &&
    prevProps.message.excuse_reasons === nextProps.message.excuse_reasons &&
    prevProps.showExcuse === nextProps.showExcuse &&
    prevProps.message.is_typing === nextProps.message.is_typing &&
    prevProps.message.is_chatting === nextProps.message.is_chatting &&
    prevProps.message.is_streaming === nextProps.message.is_streaming &&
    prevProps.expandedThinking.has(prevProps.message.id) === nextProps.expandedThinking.has(nextProps.message.id) &&
    prevProps.copiedMessageId === nextProps.copiedMessageId &&
    prevWhiteboardInfo?.renderedContent === nextWhiteboardInfo?.renderedContent
  );
});
