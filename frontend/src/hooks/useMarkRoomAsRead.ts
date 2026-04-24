import { useCallback, useEffect, useRef } from 'react';
import { roomService } from '../services/roomService';

/**
 * Mark a room as read on three triggers:
 *  - room switch
 *  - new messages arriving while viewing
 *  - user click in the chatroom (throttled to 1/s)
 *
 * `onOptimisticMark` updates the unread badge in the sidebar synchronously;
 * `onServerError` lets the parent reconcile state when the server call fails.
 */
export function useMarkRoomAsRead(
  roomId: number | null,
  messageCount: number,
  onOptimisticMark?: (roomId: number) => void,
  onServerError?: () => void,
) {
  const lastMarkedRoomRef = useRef<number | null>(null);
  const lastMessageCountRef = useRef<number>(0);
  const lastClickMarkRef = useRef<number>(0);

  const optimisticRef = useRef(onOptimisticMark);
  const errorRef = useRef(onServerError);
  useEffect(() => {
    optimisticRef.current = onOptimisticMark;
    errorRef.current = onServerError;
  }, [onOptimisticMark, onServerError]);

  // Mark as read when switching rooms.
  useEffect(() => {
    if (!roomId || lastMarkedRoomRef.current === roomId) return;
    lastMarkedRoomRef.current = roomId;
    lastMessageCountRef.current = messageCount;

    optimisticRef.current?.(roomId);
    roomService.markRoomAsRead(roomId).catch(err => {
      console.error('Failed to mark room as read:', err);
      errorRef.current?.();
    });
  // We intentionally exclude messageCount: this effect only runs on room switch.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId]);

  // Mark as read when new messages arrive while viewing.
  useEffect(() => {
    if (!roomId || messageCount <= lastMessageCountRef.current) return;
    lastMessageCountRef.current = messageCount;

    optimisticRef.current?.(roomId);
    roomService.markRoomAsRead(roomId).catch(err => {
      console.error('Failed to mark room as read:', err);
    });
  }, [roomId, messageCount]);

  // Mark as read on user click — throttled to 1/s.
  const markOnClick = useCallback(() => {
    if (!roomId) return;
    const now = Date.now();
    if (now - lastClickMarkRef.current <= 1000) return;
    lastClickMarkRef.current = now;
    optimisticRef.current?.(roomId);
    roomService.markRoomAsRead(roomId).catch(err => {
      console.error('Failed to mark room as read:', err);
    });
  }, [roomId]);

  return { markOnClick };
}
