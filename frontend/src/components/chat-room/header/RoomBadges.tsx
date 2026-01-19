import { Badge } from '@/components/ui/badge';

interface RoomBadgesProps {
  roomName: string;
  isPaused: boolean;
}

export const RoomBadges = ({ roomName, isPaused }: RoomBadgesProps) => {
  return (
    <div className="flex items-center gap-1.5">
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
