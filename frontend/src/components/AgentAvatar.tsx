import type { Agent } from '../types';
import { getAgentProfilePicUrl } from '../services/agentService';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';

interface AgentAvatarProps {
  agent: Agent;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  onClick?: () => void;
}

// Size to display pixels mapping
const sizeToPixels: Record<'sm' | 'md' | 'lg' | 'xl', number> = {
  sm: 32,
  md: 40,
  lg: 56,
  xl: 96,
};

export const AgentAvatar = ({ agent, size = 'md', className = '', onClick }: AgentAvatarProps) => {
  const sizeClasses = {
    sm: 'h-8 w-8 text-xs',
    md: 'h-10 w-10 text-sm',
    lg: 'h-14 w-14 text-xl',
    xl: 'h-24 w-24 text-3xl',
  };

  // Request 2x size for Retina displays
  const requestSize = sizeToPixels[size] * 2;
  const profilePicUrl = agent.profile_pic ? getAgentProfilePicUrl(agent, requestSize) : null;

  return (
    <Avatar
      className={cn(
        sizeClasses[size],
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
      title={onClick ? 'Click to change profile picture' : agent.name}
    >
      {profilePicUrl && (
        <AvatarImage src={profilePicUrl} alt={agent.name} loading="lazy" />
      )}
      <AvatarFallback className="bg-gradient-to-br from-emerald-400 to-cyan-500 text-white font-bold">
        {agent.name[0]?.toUpperCase()}
      </AvatarFallback>
    </Avatar>
  );
};
