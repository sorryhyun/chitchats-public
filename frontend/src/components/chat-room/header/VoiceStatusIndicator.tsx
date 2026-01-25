import { useVoice } from '../../../contexts/VoiceContext';

export const VoiceStatusIndicator = () => {
  const { enabled, setEnabled, serverAvailable } = useVoice();

  return (
    <button
      onClick={() => setEnabled(!enabled)}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
        enabled
          ? serverAvailable
            ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
            : 'bg-amber-100 text-amber-700 hover:bg-amber-200'
          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
      }`}
      title={
        enabled
          ? serverAvailable
            ? 'Voice mode enabled - Click to disable'
            : 'Voice mode enabled but server unavailable'
          : 'Click to enable voice mode'
      }
    >
      {/* Speaker/Volume icon */}
      <svg
        className="w-3.5 h-3.5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        {enabled ? (
          <>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
            />
          </>
        ) : (
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"
          />
        )}
      </svg>
      <span>
        {enabled ? (serverAvailable ? 'Voice On' : 'Voice (No Server)') : 'Voice Off'}
      </span>
    </button>
  );
};
