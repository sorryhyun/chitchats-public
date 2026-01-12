import { Badge } from '@/components/ui/badge';
import type { ProviderType } from '../../../types';

interface RoomBadgesProps {
  roomName: string;
  isPaused: boolean;
  provider?: ProviderType;
}

export const RoomBadges = ({ roomName, isPaused, provider }: RoomBadgesProps) => {
  return (
    <div className="flex items-center gap-1.5">
      {/* Provider Badge */}
      {provider && (
        <Badge
          variant="outline"
          className={`rounded-full text-xs ${
            provider === 'codex'
              ? 'bg-green-100 text-green-700 border-green-200'
              : 'bg-amber-100 text-amber-700 border-amber-200'
          }`}
        >
          {provider === 'codex' ? 'Codex' : 'Claude'}
        </Badge>
      )}
      {roomName.startsWith('Direct:') && (
        <Badge variant="secondary" className="rounded-full text-xs">
          Direct Chat
        </Badge>
      )}
      {isPaused && (
        <Badge variant="outline" className="rounded-full bg-orange-100 text-orange-700 border-orange-200 text-xs">
          Paused
        </Badge>
      )}
    </div>
  );
};
