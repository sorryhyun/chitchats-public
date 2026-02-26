import { useState, useCallback, memo, FormEvent, KeyboardEvent, ClipboardEvent, useRef, ChangeEvent, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import type { Agent, ParticipantType, ImageItem, ProviderType } from '../../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useMention } from '../../hooks/useMention';
import { useImageDrop } from '../../hooks/useImageDrop';
import { useVoiceRealtime } from '../../hooks/useVoiceRealtime';
import { MentionDropdown } from './MentionDropdown';
import { VoiceRecordButton } from './VoiceRecordButton';

interface ImageData {
  data: string;  // Base64 encoded (without data URL prefix)
  mediaType: string;  // MIME type
  preview: string;  // Full data URL for preview
}

interface MessageInputProps {
  isConnected: boolean;
  onSendMessage: (message: string, participantType: ParticipantType, characterName?: string, images?: ImageItem[], mentionedAgentIds?: number[]) => void;
  roomAgents?: Agent[];
  provider?: ProviderType;
  roomId?: number | null;
}

export interface MessageInputHandle {
  handleFileSelect: (file: File) => Promise<void>;
}

// Allowed image types
const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB max
const MAX_IMAGES = 5;  // Maximum number of images per message

export const MessageInput = memo(forwardRef<MessageInputHandle, MessageInputProps>(({ isConnected, onSendMessage, roomAgents = [], provider, roomId }, ref) => {
  const { t } = useTranslation('chat');
  const [inputMessage, setInputMessage] = useState('');
  const [participantType, setParticipantType] = useState<ParticipantType>('user');
  const [characterName, setCharacterName] = useState('');
  const [attachedImages, setAttachedImages] = useState<ImageData[]>([]);

  // Voice mode (only for Codex rooms)
  const voice = useVoiceRealtime(provider === 'codex' ? (roomId ?? null) : null);
  const showVoiceButton = provider === 'codex';

  // State to toggle the persona menu
  const [showPersonaMenu, setShowPersonaMenu] = useState(false);

  // File input ref
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Mention hook
  const mention = useMention(roomAgents);

  // Expose handleFileSelect to parent via ref
  useImperativeHandle(ref, () => ({
    handleFileSelect,
  }));

  // Convert file to base64
  const fileToBase64 = (file: File): Promise<ImageData> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Extract base64 data without the data URL prefix
        const base64Data = result.split(',')[1];
        resolve({
          data: base64Data,
          mediaType: file.type,
          preview: result,
        });
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  // Handle file selection (adds to existing images, respects MAX_IMAGES limit)
  const handleFileSelect = async (file: File) => {
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      alert('Please select a valid image file (PNG, JPEG, GIF, or WebP)');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      alert('Image size must be less than 10MB');
      return;
    }
    if (attachedImages.length >= MAX_IMAGES) {
      alert(`Maximum ${MAX_IMAGES} images allowed`);
      return;
    }
    try {
      const imageData = await fileToBase64(file);
      setAttachedImages(prev => [...prev, imageData].slice(0, MAX_IMAGES));
    } catch (error) {
      console.error('Error converting image:', error);
      alert('Failed to process image');
    }
  };

  // Handle multiple file selection
  const handleMultipleFileSelect = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const remainingSlots = MAX_IMAGES - attachedImages.length;

    if (remainingSlots <= 0) {
      alert(`Maximum ${MAX_IMAGES} images allowed`);
      return;
    }

    const filesToProcess = fileArray.slice(0, remainingSlots);
    const validFiles = filesToProcess.filter(file => {
      if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
        console.warn(`Skipping invalid file type: ${file.type}`);
        return false;
      }
      if (file.size > MAX_IMAGE_SIZE) {
        console.warn(`Skipping file too large: ${file.name}`);
        return false;
      }
      return true;
    });

    try {
      const newImages = await Promise.all(validFiles.map(file => fileToBase64(file)));
      setAttachedImages(prev => [...prev, ...newImages].slice(0, MAX_IMAGES));
    } catch (error) {
      console.error('Error converting images:', error);
      alert('Failed to process some images');
    }
  };

  // Handle file input change (supports multiple files)
  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      if (files.length === 1) {
        handleFileSelect(files[0]);
      } else {
        handleMultipleFileSelect(files);
      }
    }
    // Reset input so same file can be selected again
    e.target.value = '';
  };

  // Drag-and-drop via shared hook
  const handleDroppedFiles = useCallback((files: File[]) => {
    if (files.length === 1) {
      handleFileSelect(files[0]);
    } else if (files.length > 1) {
      handleMultipleFileSelect(files);
    }
  }, []);
  const { isDragging, dragHandlers } = useImageDrop({ onFiles: handleDroppedFiles });

  // Handle paste from clipboard (Ctrl+V) - supports multiple images
  const handlePaste = (e: ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const imageFiles: File[] = [];
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          imageFiles.push(file);
        }
      }
    }

    if (imageFiles.length > 0) {
      e.preventDefault();
      if (imageFiles.length === 1) {
        handleFileSelect(imageFiles[0]);
      } else {
        handleMultipleFileSelect(imageFiles);
      }
    }
    // If no image, allow default paste behavior for text
  };

  // Remove attached image by index
  const removeImage = (index: number) => {
    setAttachedImages(prev => prev.filter((_, i) => i !== index));
  };

  // Clear all images
  const clearAllImages = () => {
    setAttachedImages([]);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if ((inputMessage.trim() || attachedImages.length > 0) && isConnected) {
      // Extract mentions and get clean content
      const { cleanContent, mentionedAgentIds } = mention.extractMentionsAndClean(inputMessage);

      // Convert to ImageItem format for API
      const images = attachedImages.length > 0
        ? attachedImages.map(img => ({ data: img.data, media_type: img.mediaType }))
        : undefined;

      onSendMessage(
        cleanContent || inputMessage, // Use clean content if mentions were found
        participantType,
        participantType === 'character' ? characterName : undefined,
        images,
        mentionedAgentIds.length > 0 ? mentionedAgentIds : undefined
      );
      setInputMessage('');
      setAttachedImages([]);
    }
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

    // Submit on Ctrl+Enter
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if ((inputMessage.trim() || attachedImages.length > 0) && isConnected) {
        // Extract mentions and get clean content
        const { cleanContent, mentionedAgentIds } = mention.extractMentionsAndClean(inputMessage);

        // Convert to ImageItem format for API
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
        setAttachedImages([]);
      }
    }
    // Allow Enter to create line breaks (default behavior)
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

        {/* Voice Record Button (Codex rooms only) */}
        {showVoiceButton && (
          <VoiceRecordButton
            status={voice.status}
            onStart={voice.start}
            onStop={voice.stop}
            errorMessage={voice.errorMessage}
            disabled={!isConnected}
          />
        )}

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
