import { useState, FormEvent, KeyboardEvent, DragEvent, useRef, useEffect } from 'react';
import { Send, User, Sparkles, UserCircle, ImageIcon } from 'lucide-react';
import type { ParticipantType, ImageAttachment } from '../../types';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';

interface MessageInputProps {
  isConnected: boolean;
  onSendMessage: (message: string, participantType: ParticipantType, characterName?: string, imageData?: ImageAttachment) => void;
}

export const MessageInput = ({ isConnected, onSendMessage }: MessageInputProps) => {
  const [inputMessage, setInputMessage] = useState('');
  const [participantType, setParticipantType] = useState<ParticipantType>('user');
  const [characterName, setCharacterName] = useState('');
  const [showCharacterInput, setShowCharacterInput] = useState(false);
  const [imageAttachment, setImageAttachment] = useState<ImageAttachment | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Supported image types
  const SUPPORTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB

  // Cleanup: revoke object URL when component unmounts or imagePreview changes
  useEffect(() => {
    return () => {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview);
      }
    };
  }, [imagePreview]);

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
    // Allow sending if there's text OR an image
    if ((inputMessage.trim() || imageAttachment) && isConnected) {
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
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      // Allow sending if there's text OR an image
      if ((inputMessage.trim() || imageAttachment) && isConnected) {
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
  };

  const getPersonaIcon = () => {
    if (participantType === 'user') return <User className="w-4 h-4" />;
    if (participantType === 'situation_builder') return <Sparkles className="w-4 h-4" />;
    return <UserCircle className="w-4 h-4" />;
  };

  const getPersonaLabel = () => {
    if (participantType === 'character' && characterName) return characterName;
    if (participantType === 'situation_builder') return 'Situation Builder';
    return 'User';
  };

  const handlePersonaChange = (type: ParticipantType) => {
    setParticipantType(type);
    if (type === 'character') {
      setShowCharacterInput(true);
    } else {
      setShowCharacterInput(false);
    }
  };

  return (
    <div
      className={cn(
        'bg-background border-t border-border p-3 sm:p-4 relative transition-colors',
        isDragging && 'bg-primary/5 border-primary'
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay indicator */}
      {isDragging && (
        <div className="absolute inset-0 bg-primary/10 border-2 border-dashed border-primary rounded-lg flex items-center justify-center z-30 pointer-events-none">
          <div className="text-center">
            <ImageIcon className="w-12 h-12 mx-auto text-primary mb-2" />
            <p className="text-primary font-medium">Drop image here</p>
          </div>
        </div>
      )}

      {/* Image Preview */}
      {imagePreview && (
        <div className="mb-3 flex items-start gap-2 animate-fadeIn">
          <div className="relative group">
            <img
              src={imagePreview}
              alt="Attachment preview"
              className="max-h-32 max-w-48 rounded-lg border border-border shadow-sm object-contain"
            />
            <button
              type="button"
              onClick={removeImage}
              className="absolute -top-2 -right-2 w-6 h-6 bg-destructive text-destructive-foreground rounded-full flex items-center justify-center shadow-md hover:bg-destructive/90 transition-colors"
              title="Remove image"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <span className="text-xs text-muted-foreground mt-1">Image attached</span>
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

      {/* Character name input */}
      {showCharacterInput && (
        <div className="mb-3 flex items-center gap-2 animate-fadeIn">
          <Input
            type="text"
            value={characterName}
            onChange={(e) => setCharacterName(e.target.value)}
            placeholder="Character name..."
            className="flex-1 h-9"
            autoFocus
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setShowCharacterInput(false);
              if (!characterName) setParticipantType('user');
            }}
          >
            Done
          </Button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        {/* Persona selector */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={cn(
                'flex-shrink-0 w-10 h-10 sm:w-11 sm:h-11 rounded-full',
                participantType === 'user' && 'text-primary hover:text-primary hover:bg-primary/10',
                participantType === 'situation_builder' && 'text-amber-500 hover:text-amber-500 hover:bg-amber-500/10',
                participantType === 'character' && 'text-purple-500 hover:text-purple-500 hover:bg-purple-500/10'
              )}
              title={`Speaking as ${getPersonaLabel()}`}
            >
              {getPersonaIcon()}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem
              onClick={() => handlePersonaChange('user')}
              className={cn(participantType === 'user' && 'bg-primary/10 text-primary')}
            >
              <User className="w-4 h-4 mr-2" />
              User
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => handlePersonaChange('situation_builder')}
              className={cn(participantType === 'situation_builder' && 'bg-amber-500/10 text-amber-500')}
            >
              <Sparkles className="w-4 h-4 mr-2" />
              Situation Builder
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => handlePersonaChange('character')}
              className={cn(participantType === 'character' && 'bg-purple-500/10 text-purple-500')}
            >
              <UserCircle className="w-4 h-4 mr-2" />
              Character
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Image Attach Button */}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'flex-shrink-0 w-10 h-10 sm:w-11 sm:h-11 rounded-full',
            imageAttachment ? 'text-primary bg-primary/10' : 'text-muted-foreground'
          )}
          title="Attach image (or drag & drop)"
          disabled={!isConnected}
        >
          <ImageIcon className="w-5 h-5" />
        </Button>

        {/* Input field */}
        <div className="flex-1 bg-muted rounded-lg">
          <Textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message as ${getPersonaLabel()}...`}
            className={cn(
              'min-h-[44px] max-h-[200px] resize-none border-0 bg-transparent',
              'focus-visible:ring-0 focus-visible:ring-offset-0',
              'py-3 px-4'
            )}
            disabled={!isConnected}
            rows={1}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = 'auto';
              target.style.height = Math.min(target.scrollHeight, 200) + 'px';
            }}
          />
        </div>

        {/* Send button */}
        <Button
          type="submit"
          size="icon"
          disabled={!isConnected || (!inputMessage.trim() && !imageAttachment)}
          className="flex-shrink-0 w-10 h-10 sm:w-11 sm:h-11 rounded-full"
        >
          <Send className="w-4 h-4" />
        </Button>
      </form>
    </div>
  );
};
