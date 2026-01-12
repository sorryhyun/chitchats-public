import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Room, RoomCreate, ProviderType } from '../../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface CreateRoomFormProps {
  onCreateRoom: (data: RoomCreate) => Promise<Room>;
  onClose: () => void;
}

export const CreateRoomForm = ({ onCreateRoom, onClose }: CreateRoomFormProps) => {
  const { t } = useTranslation('rooms');
  const [newRoomName, setNewRoomName] = useState('');
  const [provider, setProvider] = useState<ProviderType>('claude');
  const [roomError, setRoomError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newRoomName.trim()) {
      try {
        setRoomError(null);
        await onCreateRoom({ name: newRoomName, default_provider: provider });
        setNewRoomName('');
        setProvider('claude');
        onClose();
      } catch (err) {
        setRoomError(err instanceof Error ? err.message : t('failedToCreateRoom'));
      }
    }
  };

  return (
    <div className="p-3 border-b border-border bg-muted/50">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Input
          type="text"
          value={newRoomName}
          onChange={(e) => {
            setNewRoomName(e.target.value);
            setRoomError(null);
          }}
          placeholder={t('enterRoomName')}
          autoFocus
        />
        {/* Provider Selection */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setProvider('claude')}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              provider === 'claude'
                ? 'bg-amber-600 text-white'
                : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
            }`}
          >
            <span className="text-base">🟠</span>
            Claude
          </button>
          <button
            type="button"
            onClick={() => setProvider('codex')}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              provider === 'codex'
                ? 'bg-green-600 text-white'
                : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
            }`}
          >
            <span className="text-base">🟢</span>
            Codex
          </button>
        </div>
        {roomError && (
          <div className="text-destructive text-xs sm:text-sm bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {roomError}
          </div>
        )}
        <Button type="submit" className="w-full">
          {t('createRoom')}
        </Button>
      </form>
    </div>
  );
};
