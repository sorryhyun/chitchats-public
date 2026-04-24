import { useState, useCallback, memo, FormEvent, KeyboardEvent, useRef, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import type { Agent, ParticipantType, ImageItem } from '../../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useMention } from '../../hooks/useMention';
import { useImageDrop } from '../../hooks/useImageDrop';
import { useCtrlEnterPreference } from '../../hooks/useCtrlEnterPreference';
import { useImageUpload, MAX_IMAGES } from '../../hooks/useImageUpload';
import { MentionDropdown } from './MentionDropdown';

interface MessageInputProps {
  isConnected: boolean;
  onSendMessage: (message: string, participantType: ParticipantType, characterName?: string, images?: ImageItem[], mentionedAgentIds?: number[]) => void;
  roomAgents?: Agent[];
}

export interface MessageInputHandle {
  handleFileSelect: (file: File) => Promise<void>;
}

export const MessageInput = memo(forwardRef<MessageInputHandle, MessageInputProps>(({ isConnected, onSendMessage, roomAgents = [] }, ref) => {
  const { t } = useTranslation('chat');
  const [inputMessage, setInputMessage] = useState('');
  const [participantType, setParticipantType] = useState<ParticipantType>('user');
  const [characterName, setCharacterName] = useState('');
  const [showPersonaMenu, setShowPersonaMenu] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const mention = useMention(roomAgents);
  const { ctrlEnterToSend } = useCtrlEnterPreference();

  const {
    images: attachedImages,
    addOne: handleFileSelect,
    handleFiles: handleDroppedFiles,
    handleInputChange: handleFileInputChange,
    handlePaste,
    remove: removeImage,
    clear: clearAllImages,
  } = useImageUpload();

  useImperativeHandle(ref, () => ({ handleFileSelect }));

  const { isDragging, dragHandlers } = useImageDrop({ onFiles: handleDroppedFiles });

  const submit = useCallback(() => {
    if (!isConnected) return;
    if (!inputMessage.trim() && attachedImages.length === 0) return;
    const { cleanContent, mentionedAgentIds } = mention.extractMentionsAndClean(inputMessage);
    const images = attachedImages.length > 0
      ? attachedImages.map(img => ({ data: img.data, media_type: img.mediaType }))
      : undefined;
    onSendMessage(
      cleanContent || inputMessage,
      participantType,
      participantType === 'character' ? characterName : undefined,
      images,
      mentionedAgentIds.length > 0 ? mentionedAgentIds : undefined
    );
    setInputMessage('');
    clearAllImages();
  }, [isConnected, inputMessage, attachedImages, mention, participantType, characterName, onSendMessage, clearAllImages]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle mention dropdown keyboard navigation first
    if (mention.isDropdownOpen) {
      const handled = mention.handleKeyDown(e);
      if (handled) {
        // If Enter or Tab was pressed to select an agent
        if ((e.key === 'Enter' || e.key === 'Tab') && mention.filteredAgents[mention.selectedIndex]) {
          const newValue = mention.selectAgent(mention.filteredAgents[mention.selectedIndex], inputMessage);
          setInputMessage(newValue);
          // Move cursor to end of inserted mention
          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.focus();
              textareaRef.current.selectionStart = newValue.length;
              textareaRef.current.selectionEnd = newValue.length;
            }
          }, 0);
        }
        return;
      }
    }

    // Determine if this keypress should submit
    const isEnter = e.key === 'Enter';
    const hasModifier = e.ctrlKey || e.metaKey;
    const shouldSubmit = isEnter && (ctrlEnterToSend ? hasModifier : !hasModifier && !e.shiftKey);
    const shouldNewline = isEnter && (ctrlEnterToSend ? !hasModifier : (hasModifier || e.shiftKey));

    if (shouldSubmit) {
      e.preventDefault();
      submit();
    } else if (shouldNewline && !ctrlEnterToSend) {
      // When Enter sends: Shift+Enter or Ctrl+Enter inserts newline (default textarea behavior)
    }
  };

  // Helper to get the current icon
  const getPersonaIcon = () => {
    if (participantType === 'user') return <span className="font-bold text-sm">U</span>;
    if (participantType === 'situation_builder') return <span className="font-bold text-sm">S</span>;
    return <span className="font-bold text-sm">C</span>;
  };

  // Helper to get persona label
  const getPersonaLabel = () => {
    if (participantType === 'character' && characterName) return characterName;
    if (participantType === 'situation_builder') return 'Situation Builder';
    return 'User';
  };

  return (
    <div
      className={cn(
        "relative bg-white/90 backdrop-blur border-t border-border input-padding-mobile shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)] z-20 transition-all flex-shrink-0",
        isDragging && "bg-blue-50 border-blue-300"
      )}
      {...dragHandlers}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 bg-blue-100/80 backdrop-blur-sm flex items-center justify-center z-30 pointer-events-none">
          <div className="text-blue-600 font-medium flex items-center gap-2">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            Drop images here (up to {MAX_IMAGES - attachedImages.length} more)
          </div>
        </div>
      )}

      {/* Hidden file input - supports multiple files */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        onChange={handleFileInputChange}
        className="hidden"
        multiple
      />

      {/* Image Preview Grid */}
      {attachedImages.length > 0 && (
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-slate-500">{attachedImages.length}/{MAX_IMAGES} images</span>
            {attachedImages.length > 1 && (
              <button
                type="button"
                onClick={clearAllImages}
                className="text-xs text-red-500 hover:text-red-600 transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {attachedImages.map((image, index) => (
              <div key={index} className="relative inline-block">
                <img
                  src={image.preview}
                  alt={`Attached ${index + 1}`}
                  className="h-20 w-20 object-cover rounded-lg border border-slate-200 shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => removeImage(index)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors shadow-md"
                  title="Remove image"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Persona Selection Popup (Only visible when toggled) */}
      {showPersonaMenu && (
        <div className="mb-3 p-3 bg-slate-50 rounded-xl border border-slate-300 animate-fadeIn">
          <label className="block text-xs font-bold text-slate-600 mb-2 uppercase tracking-wide">Speaking As</label>
          <div className="flex flex-wrap gap-2">
            {(['user', 'situation_builder', 'character'] as ParticipantType[]).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => {
                  setParticipantType(type);
                  // Don't close immediately if character (needs name input), otherwise close
                  if (type !== 'character') setShowPersonaMenu(false);
                }}
                className={`px-3 py-2 text-sm rounded-lg border transition-all ${
                  participantType === type
                    ? 'bg-slate-700 text-white border-slate-700'
                    : 'bg-white text-slate-600 border-slate-300 hover:border-slate-400'
                }`}
              >
                {type === 'situation_builder' ? 'Builder' : type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
          {participantType === 'character' && (
            <Input
              type="text"
              value={characterName}
              onChange={(e) => setCharacterName(e.target.value)}
              placeholder="Character Name"
              className="mt-3"
              autoFocus
            />
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-end gap-1 sm:gap-2 min-w-0">
        {/* Compact Toggle Button */}
        <button
          type="button"
          onClick={() => setShowPersonaMenu(!showPersonaMenu)}
          className={`flex-shrink-0 w-9 h-9 sm:w-12 sm:h-12 rounded-full flex items-center justify-center transition-all ${
            participantType === 'user' ? 'bg-slate-100 text-slate-600 hover:bg-slate-200' :
            participantType === 'situation_builder' ? 'bg-amber-100 text-amber-700 hover:bg-amber-200' :
            'bg-purple-100 text-purple-700 hover:bg-purple-200'
          }`}
          title={`Change persona (currently: ${getPersonaLabel()})`}
        >
          {getPersonaIcon()}
        </button>

        {/* Attach Image Button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={!isConnected || attachedImages.length >= MAX_IMAGES}
          className="flex-shrink-0 w-9 h-9 sm:w-12 sm:h-12 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center hover:bg-slate-200 transition-all disabled:bg-slate-50 disabled:text-slate-300"
          title={attachedImages.length >= MAX_IMAGES ? `Maximum ${MAX_IMAGES} images` : `Attach images (${attachedImages.length}/${MAX_IMAGES})`}
        >
          <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>

        {/* Streamlined Input Field with Mention Dropdown */}
        <div className="relative flex-1 min-w-0">
          {/* Mention Dropdown */}
          {mention.isDropdownOpen && roomAgents.length > 0 && (
            <MentionDropdown
              agents={mention.filteredAgents}
              selectedIndex={mention.selectedIndex}
              onSelect={(agent) => {
                const newValue = mention.selectAgent(agent, inputMessage);
                setInputMessage(newValue);
                textareaRef.current?.focus();
              }}
              onClose={mention.closeDropdown}
            />
          )}

          <textarea
            ref={textareaRef}
            value={inputMessage}
            onChange={(e) => {
              setInputMessage(e.target.value);
              mention.handleInputChange(e.target.value, e.target.selectionStart ?? e.target.value.length);
            }}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={t('messageAsUser', { persona: getPersonaLabel() })}
            className="w-full bg-slate-50 px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base border-0 rounded-2xl focus:ring-2 focus:ring-slate-400 focus:bg-white transition-all resize-none min-h-[40px] sm:min-h-[48px] max-h-[120px] disabled:bg-slate-100 disabled:text-slate-500"
            disabled={!isConnected}
            rows={1}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = 'auto';
              target.style.height = Math.min(target.scrollHeight, 120) + 'px';
            }}
          />
        </div>

        {/* Icon-Only Send Button (Saves width) */}
        <Button
          type="submit"
          disabled={!isConnected || (!inputMessage.trim() && attachedImages.length === 0)}
          size="icon"
          className="flex-shrink-0 w-9 h-9 sm:w-12 sm:h-12 rounded-full"
        >
          <svg className="w-4 h-4 sm:w-5 sm:h-5 translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </Button>
      </form>
    </div>
  );
}));
