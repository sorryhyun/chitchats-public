import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ProviderInfo, ProviderType, Room } from '../../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { roomService } from '@/services/roomService';

interface CreateRoomFormProps {
  onCreateRoom: (name: string, provider?: ProviderType) => Promise<Room>;
  onClose: () => void;
}

export const CreateRoomForm = ({ onCreateRoom, onClose }: CreateRoomFormProps) => {
  const { t } = useTranslation('rooms');
  const [newRoomName, setNewRoomName] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<ProviderType>('claude');
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [roomError, setRoomError] = useState<string | null>(null);

  // Fetch available providers
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const response = await roomService.getProviders();
        setProviders(response.providers);
        // Set default provider
        const defaultProvider = response.providers.find(p => p.name === response.default);
        if (defaultProvider) {
          setSelectedProvider(defaultProvider.name as ProviderType);
        }
      } catch (err) {
        // If we can't fetch providers, just use Claude as default
        console.error('Failed to fetch providers:', err);
        setProviders([{ name: 'claude', available: true }]);
      }
    };
    fetchProviders();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newRoomName.trim()) {
      try {
        setRoomError(null);
        await onCreateRoom(newRoomName, selectedProvider);
        setNewRoomName('');
        onClose();
      } catch (err) {
        setRoomError(err instanceof Error ? err.message : t('failedToCreateRoom'));
      }
    }
  };

  // Only show provider selection if there are multiple available providers
  const availableProviders = providers.filter(p => p.available);
  const showProviderSelection = availableProviders.length > 1;

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
        {showProviderSelection && (
          <div className="flex gap-2">
            {availableProviders.map((provider) => (
              <button
                key={provider.name}
                type="button"
                onClick={() => setSelectedProvider(provider.name as ProviderType)}
                className={`flex-1 px-3 py-2 text-xs rounded-md border transition-colors ${
                  selectedProvider === provider.name
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-background text-foreground border-border hover:bg-muted'
                }`}
              >
                {provider.name === 'claude' ? 'Claude' : 'Codex'}
              </button>
            ))}
          </div>
        )}

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
