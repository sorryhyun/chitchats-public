import { memo } from 'react';
import type { VoiceStatus } from '../../hooks/useVoiceRealtime';

interface VoiceRecordButtonProps {
  status: VoiceStatus;
  onStart: () => void;
  onStop: () => void;
  errorMessage?: string | null;
  disabled?: boolean;
}

/**
 * Microphone button for realtime voice mode in Codex rooms.
 *
 * States:
 *  - idle: gray mic icon, click to start
 *  - connecting: spinning indicator
 *  - active: pulsing red ring, click to stop
 *  - error: red icon with tooltip
 */
export const VoiceRecordButton = memo(({ status, onStart, onStop, errorMessage, disabled }: VoiceRecordButtonProps) => {
  const handleClick = () => {
    if (status === 'active') {
      onStop();
    } else if (status === 'idle' || status === 'error') {
      onStart();
    }
  };

  const isActive = status === 'active';
  const isConnecting = status === 'connecting';
  const isError = status === 'error';

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || isConnecting}
      title={
        isError
          ? errorMessage || 'Voice error - click to retry'
          : isActive
            ? 'Stop recording'
            : isConnecting
              ? 'Connecting...'
              : 'Start voice mode'
      }
      className={`
        relative flex-shrink-0 w-9 h-9 sm:w-12 sm:h-12 rounded-full flex items-center justify-center transition-all
        disabled:opacity-50 disabled:cursor-not-allowed
        ${isActive
          ? 'bg-red-100 text-red-600 hover:bg-red-200'
          : isError
            ? 'bg-red-50 text-red-500 hover:bg-red-100'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
        }
      `}
    >
      {/* Pulsing ring when active */}
      {isActive && (
        <span className="absolute inset-0 rounded-full animate-ping bg-red-200 opacity-40" />
      )}

      {/* Spinner when connecting */}
      {isConnecting ? (
        <svg className="w-4 h-4 sm:w-5 sm:h-5 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : (
        /* Mic icon */
        <svg className="w-4 h-4 sm:w-5 sm:h-5 relative z-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z"
          />
        </svg>
      )}
    </button>
  );
});
