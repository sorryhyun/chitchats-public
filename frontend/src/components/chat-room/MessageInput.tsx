import { useState, FormEvent, KeyboardEvent, DragEvent, useRef } from 'react';
import type { ParticipantType, ImageAttachment } from '../../types';

interface MessageInputProps {
  isConnected: boolean;
  onSendMessage: (message: string, participantType: ParticipantType, characterName?: string, imageData?: ImageAttachment) => void;
}

export const MessageInput = ({ isConnected, onSendMessage }: MessageInputProps) => {
  const [inputMessage, setInputMessage] = useState('');
  const [participantType, setParticipantType] = useState<ParticipantType>('user');
  const [characterName, setCharacterName] = useState('');
  const [imageAttachment, setImageAttachment] = useState<ImageAttachment | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // State to toggle the persona menu
  const [showPersonaMenu, setShowPersonaMenu] = useState(false);

  // Supported image types
  const SUPPORTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB

  // Process a file into base64
  const processImageFile = async (file: File): Promise<void> => {
    if (!SUPPORTED_IMAGE_TYPES.includes(file.type)) {
      alert('Please upload a PNG, JPEG, GIF, or WebP image.');
      return;
    }

    if (file.size > MAX_IMAGE_SIZE) {
      alert('Image size must be less than 10MB.');
      return;
    }

    try {
      const base64 = await fileToBase64(file);
      setImageAttachment({
        data: base64,
        media_type: file.type,
      });
      setImagePreview(URL.createObjectURL(file));
    } catch (error) {
      console.error('Error processing image:', error);
      alert('Failed to process image. Please try again.');
    }
  };

  // Convert file to base64
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Remove the data URL prefix (e.g., "data:image/png;base64,")
        const base64 = result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  // Handle drag events
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (file.type.startsWith('image/')) {
        await processImageFile(file);
      }
    }
  };

  // Handle file input change
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await processImageFile(files[0]);
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Remove attached image
  const removeImage = () => {
    setImageAttachment(null);
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
    }
    setImagePreview(null);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    console.log('[MessageInput] handleSubmit called');
    // Allow sending if there's text OR an image
    if ((inputMessage.trim() || imageAttachment) && isConnected) {
      console.log('[MessageInput] Calling onSendMessage from handleSubmit');
      onSendMessage(
        inputMessage || '[Image]',
        participantType,
        participantType === 'character' ? characterName : undefined,
        imageAttachment || undefined
      );
      setInputMessage('');
      removeImage();
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Ctrl+Enter
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      console.log('[MessageInput] handleKeyDown - Ctrl+Enter pressed');
      // Allow sending if there's text OR an image
      if ((inputMessage.trim() || imageAttachment) && isConnected) {
        console.log('[MessageInput] Calling onSendMessage from handleKeyDown');
        onSendMessage(
          inputMessage || '[Image]',
          participantType,
          participantType === 'character' ? characterName : undefined,
          imageAttachment || undefined
        );
        setInputMessage('');
        removeImage();
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
      className={`bg-white/90 backdrop-blur border-t border-slate-100 p-2 sm:p-4 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)] z-20 transition-colors ${
        isDragging ? 'bg-indigo-50 border-indigo-300' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay indicator */}
      {isDragging && (
        <div className="absolute inset-0 bg-indigo-100/80 border-2 border-dashed border-indigo-400 rounded-lg flex items-center justify-center z-30 pointer-events-none">
          <div className="text-center">
            <svg className="w-12 h-12 mx-auto text-indigo-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <p className="text-indigo-600 font-medium">Drop image here</p>
          </div>
        </div>
      )}

      {/* Image Preview */}
      {imagePreview && (
        <div className="mb-3 flex items-start gap-2">
          <div className="relative group">
            <img
              src={imagePreview}
              alt="Attachment preview"
              className="max-h-32 max-w-48 rounded-lg border border-slate-200 shadow-sm object-contain"
            />
            <button
              type="button"
              onClick={removeImage}
              className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center shadow-md hover:bg-red-600 transition-colors"
              title="Remove image"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <span className="text-xs text-slate-500 mt-1">Image attached</span>
        </div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* Persona Selection Popup (Only visible when toggled) */}
      {showPersonaMenu && (
        <div className="mb-3 p-3 bg-slate-50 rounded-xl border border-slate-200 animate-fadeIn">
          <label className="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wide">Speaking As</label>
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
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-md'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'
                }`}
              >
                {type === 'situation_builder' ? 'Builder' : type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
          {participantType === 'character' && (
            <input
              type="text"
              value={characterName}
              onChange={(e) => setCharacterName(e.target.value)}
              placeholder="Character Name"
              className="mt-3 w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
              autoFocus
            />
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        {/* Compact Toggle Button */}
        <button
          type="button"
          onClick={() => setShowPersonaMenu(!showPersonaMenu)}
          className={`flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center transition-all ${
            participantType === 'user' ? 'bg-slate-100 text-slate-600 hover:bg-slate-200' :
            participantType === 'situation_builder' ? 'bg-amber-100 text-amber-700 hover:bg-amber-200' :
            'bg-purple-100 text-purple-700 hover:bg-purple-200'
          }`}
          title={`Change persona (currently: ${getPersonaLabel()})`}
        >
          {getPersonaIcon()}
        </button>

        {/* Image Attach Button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className={`flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center transition-all ${
            imageAttachment
              ? 'bg-indigo-100 text-indigo-600 hover:bg-indigo-200'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
          }`}
          title="Attach image (or drag & drop)"
          disabled={!isConnected}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </button>

        {/* Streamlined Input Field */}
        <textarea
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Message as ${getPersonaLabel()}...`}
          className="flex-1 bg-slate-50 px-4 py-3 text-base border-0 rounded-2xl focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all resize-none min-h-[44px] sm:min-h-[48px] max-h-[120px] disabled:bg-slate-100 disabled:text-slate-400"
          disabled={!isConnected}
          rows={1}
          onInput={(e) => {
            const target = e.target as HTMLTextAreaElement;
            target.style.height = 'auto';
            target.style.height = Math.min(target.scrollHeight, 120) + 'px';
          }}
        />

        {/* Icon-Only Send Button (Saves width) */}
        <button
          type="submit"
          disabled={!isConnected || (!inputMessage.trim() && !imageAttachment)}
          className="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 bg-indigo-600 text-white rounded-full flex items-center justify-center hover:bg-indigo-700 active:scale-95 transition-all shadow-md disabled:bg-slate-300 disabled:shadow-none"
        >
          <svg className="w-5 h-5 translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </form>
    </div>
  );
};
