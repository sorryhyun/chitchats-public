import { useState } from 'react';
import { useToast } from '../../../contexts/ToastContext';
import { useChatRoomControls } from '../../../contexts/ChatRoomControlsContext';

export const RoomControls = () => {
  const { addToast } = useToast();
  const { roomData, isRefreshing, onRefreshMessages, onPauseToggle, onLimitUpdate } =
    useChatRoomControls();
  const [isEditingLimit, setIsEditingLimit] = useState(false);
  const [limitInput, setLimitInput] = useState('');

  const startEditingLimit = () => {
    setLimitInput(roomData?.max_interactions?.toString() || '');
    setIsEditingLimit(true);
  };

  const handleLimitUpdate = () => {
    const newLimit = limitInput === '' ? null : parseInt(limitInput, 10);
    if (limitInput !== '' && (isNaN(newLimit as number) || (newLimit as number) < 1)) {
      addToast('Please enter a valid positive number or leave empty for unlimited', 'error');
      return;
    }
    onLimitUpdate(newLimit);
    addToast('Interaction limit updated', 'success');
    setIsEditingLimit(false);
    setLimitInput('');
  };

  return (
    <div className="flex items-center gap-1 sm:gap-mobile">
      {/* Message Limit - Hide label on very small screens */}
      <div className="flex items-center gap-1">
        <span className="text-mobile-sm text-slate-500 hidden sm:inline">Max:</span>
        {isEditingLimit ? (
          <div className="flex items-center gap-1">
            <input
              type="number"
              value={limitInput}
              onChange={(e) => setLimitInput(e.target.value)}
              placeholder="∞"
              className="w-10 sm:w-14 px-1.5 sm:px-2 py-0.5 sm:py-1 text-xs sm:text-sm border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
              min="1"
              autoFocus
            />
            <button
              onClick={handleLimitUpdate}
              className="btn-icon-mobile bg-slate-700 text-white rounded hover:bg-slate-600"
            >
              <svg className="icon-mobile" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </button>
            <button
              onClick={() => setIsEditingLimit(false)}
              className="btn-icon-mobile bg-slate-200 text-slate-700 rounded hover:bg-slate-300"
            >
              <svg className="icon-mobile" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ) : (
          <button
            onClick={startEditingLimit}
            className="px-1.5 sm:px-2 py-0.5 sm:py-1 text-xs sm:text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded transition-colors min-h-[28px] sm:min-h-[32px] min-w-[28px] sm:min-w-[32px]"
          >
            {roomData?.max_interactions ?? '∞'}
          </button>
        )}
      </div>

      {/* Refresh Messages Button */}
      <button
        onClick={onRefreshMessages}
        disabled={isRefreshing}
        className="btn-icon-mobile rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors disabled:opacity-50"
        title="Refresh messages"
      >
        <svg className={`icon-mobile ${isRefreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>

      {/* Pause/Resume Button */}
      <button
        onClick={onPauseToggle}
        className={`btn-icon-mobile rounded transition-colors ${
          roomData?.is_paused
            ? 'bg-green-50 hover:bg-green-100 text-green-600'
            : 'bg-orange-50 hover:bg-orange-100 text-orange-600'
        }`}
        title={roomData?.is_paused ? 'Resume conversation' : 'Pause conversation'}
      >
        {roomData?.is_paused ? (
          <svg className="icon-mobile" fill="currentColor" viewBox="0 0 24 24">
            <path d="M8 5v14l11-7z" />
          </svg>
        ) : (
          <svg className="icon-mobile" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
          </svg>
        )}
      </button>
    </div>
  );
};
