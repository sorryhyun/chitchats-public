# Frontend Improvement Todo List

Audit date: 2025-12-02
Last updated: 2025-12-02

---

## Medium Priority

### 1. Add retry logic with exponential backoff to polling
- **File:** `src/hooks/usePolling.ts`
- **Problem:** Poll failures are logged but don't trigger retries with backoff.
- **Fix:**
```typescript
const pollFailuresRef = useRef(0);
const MAX_RETRIES = 3;
const getNextPollDelay = () => {
  const baseDelay = 2000;
  return Math.min(baseDelay * Math.pow(2, pollFailuresRef.current), 30000);
};
```

### 2. Fix race condition in poll scheduling
- **File:** `src/hooks/usePolling.ts`
- **Problem:** `scheduleNextPoll()` and `scheduleNextStatusPoll()` share cleanup flag but scheduled independently.
- **Fix:**
```typescript
const timeoutsRef = useRef<NodeJS.Timeout[]>([]);
// Clear all on unmount: timeoutsRef.current.forEach(t => clearTimeout(t));
```

---

## Low Priority

### 3. Centralize polling interval constants
- **Files:** Multiple (usePolling.ts, useRooms.ts, useAgents.ts)
- **Problem:** Poll intervals hardcoded in several places with no central config.
- **Fix:**
```typescript
// constants.ts
export const POLLING = {
  MESSAGES: 2000,
  STATUS: 2000,
  ROOMS: 2000,
  AGENTS: 2000,
} as const;
```

### 4. Simplify useEffect dependency chain
- **File:** `src/hooks/usePolling.ts`
- **Problem:** Dependency array includes `fetchAllMessages`, `pollNewMessages`, `pollChattingAgents` which creates circular dependency chain.
- **Fix:** Simplify to only `roomId` and create functions inline if needed.

---

## Summary

| Priority | Count |
|----------|-------|
| High | 0 |
| Medium | 2 |
| Low | 2 |
| **Total** | **4** |

---

## Completed Items (2025-12-02)

### High Priority (4/4 completed)
- [x] Add AbortController to all fetch operations
- [x] Fix AgentManager duplicate API calls (optimistic updates)
- [x] Fix immediate poll race condition
- [x] Implement request deduplication in api.ts

### Medium Priority (10/12 completed)
- [x] Extract polling headers to utility function (DRY)
- [x] Fix O(n²) chatting agents comparison
- [x] Memoize event handlers in ChatRoom.tsx
- [x] Add React.memo to MessageList component
- [x] Memoize ReactMarkdown plugins/components
- [x] Fix keyboard handler cleanup in App.tsx
- [x] Add URL.revokeObjectURL cleanup in MessageInput.tsx
- [x] Memoize AgentManager filtered lists
- [x] Throttle scroll check in MessageList
- [x] Create typed ApiError class

### Low Priority (2/4 completed)
- [x] Fix poll interval comment mismatch
- [x] Add proper TypeScript types for chatting agents
