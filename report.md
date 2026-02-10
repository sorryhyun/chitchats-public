# Frontend Audit Report

## High — Code Quality

### 10. Duplicated drag-and-drop logic

**Files:** `src/components/chat-room/MessageInput.tsx:142-175`, `src/components/chat-room/ChatRoom.tsx:223-257`

Nearly identical drag-drop handlers with minor variations.

**Fix:** Extract into a shared `useImageDrop` hook that returns `{ isDragging, handleDragOver, handleDragLeave, handleDrop }`.

---

## Medium — Reliability

### 12. No user-facing error feedback for API failures

**Files:** Multiple services and hooks

Service methods throw errors, but most consumers only `console.error` them. Examples:
- `usePolling.ts:395-407` — failed message send logs to console, user sees nothing
- `roomService.ts` — failed room creation may silently fail in some code paths

**Fix:** Use the existing `ToastContext` to show error toasts on API failures. Create a wrapper like `useApiCall` that handles the try/catch/toast pattern.

---

### 13. Race condition on rapid room switching

**File:** `src/hooks/usePolling.ts:289-308`

Switching rooms clears messages and starts a fetch. Switching again before the fetch completes can cause stale data from the first room to appear in the second room. The `isActive` flag mitigates this partially, but there's a window where it fails.

**Fix:** Use `AbortController` to cancel in-flight requests when the room changes. Pass the signal to `fetch()`.

---

### 14. No double-send protection

**File:** `src/hooks/usePolling.ts:358-411`

No guard against rapid repeated clicks sending duplicate messages.

**Fix:** Add an `isSending` ref. Set it `true` before the fetch, `false` on completion. Return early if already sending. Optionally disable the send button in the UI during submission.

---

### 15. SSE reconnection retries indefinitely

**File:** `src/hooks/useSSE.ts:94`

Exponential backoff is implemented, but there's no max retry limit. If the server goes down, the client retries forever, wasting resources and potentially flooding a recovering server.

**Fix:** Add a max retry count (e.g., 10). After exhausting retries, show a "connection lost" indicator and offer a manual reconnect button.

---

### 16. Toast ID collision

**File:** `src/contexts/ToastContext.tsx:24`

Uses `Date.now()` for toast IDs. Two toasts added in the same millisecond get the same ID, causing removal of the wrong toast.

**Fix:** Use an incrementing counter (`useRef(0)`) or `crypto.randomUUID()`.

---

## Medium — Architecture

### 17. No code splitting for modals

**File:** `src/App.tsx`

`HowToDocsModal`, `SettingsModal`, and `ExportModal` are eagerly imported at the top level but only rendered conditionally. They add to the initial bundle size for no benefit.

**Fix:** Use `React.lazy()` + `<Suspense>` for these modals.

---

### 18. `react-syntax-highlighter` loaded eagerly

**File:** `src/components/chat-room/message-list/MarkdownContent.tsx`

Prism syntax highlighter is imported at the top of the file. Only messages containing code fences actually need it. This adds significant weight to the initial bundle.

**Fix:** Lazy-load the syntax highlighter component. Render a plain `<code>` block as fallback while loading.

---

### 19. `AgentAvatar` not memoized, used in loops

**File:** `src/components/AgentAvatar.tsx:21`

Recomputes the profile pic URL on every render. Used inside `RoomListPanel` and `AgentListPanel` loops — causing N re-renders per parent update.

**Fix:** Wrap in `React.memo`. Memoize the URL computation.

---

### 20. `AgentListPanel` recomputes group sorting every render

**File:** `src/components/sidebar/AgentListPanel.tsx:23-31`

Creates a new `Map` and sorts agents on every render, even when the agent list hasn't changed.

**Fix:** Wrap the grouping/sorting logic in `useMemo` with `[agents]` as the dependency.

---

### 21. No URL routing

**Scope:** Entire frontend

The app is purely context-driven. There's no way to deep-link to a specific room or share a room URL. Navigation state is lost on refresh.

**Fix:** Not blocking, but consider `react-router` if shareable room URLs become a requirement. Even a simple hash-based approach (`#/room/123`) would help.

---

## Low — Cleanup

### 22. Inconsistent error message patterns

**Files:** Various services and components

Some places use i18n translation functions (`t('errors.createRoom')`), others hardcode English strings (`'Failed to create room'`). This means some error messages won't translate.

**Fix:** Standardize on `t()` for all user-facing strings. Keep raw English only in `console.error` calls.

---

### 23. Loose `Message.id` type

**File:** `src/types/index.ts:48`

```typescript
id: number | string;
```

Streaming messages use string temp IDs, persisted messages use numeric DB IDs. This union type forces runtime `typeof` checks throughout the codebase.

**Fix:** Consider a discriminated union:

```typescript
type Message = PersistedMessage | StreamingMessage;
interface PersistedMessage { id: number; is_streaming?: false; ... }
interface StreamingMessage { id: string; is_streaming: true; ... }
```

---

### 24. `any` type in usePolling

**File:** `src/hooks/usePolling.ts:372`

```typescript
const messageData: any = { content, role: 'user', ... };
```

**Fix:** Define a `SendMessagePayload` interface and use it.

---

### 25. `clearRoomMessages` return type mismatch

**File:** `src/services/messageService.ts:16`

Declared as `Promise<void>` but calls `return response.json()`, parsing a response body unnecessarily.

**Fix:** Remove the `return response.json()` line, or update the return type if the response is needed.

---

### 26. Minimal test coverage

**Scope:** Entire frontend

Only `src/hooks/usePolling.test.ts` exists. No tests for:
- Service layer (`src/services/`)
- Context providers (`src/contexts/`)
- Components (`src/components/`)
- SSE hook, rooms hook, agents hook

The testing infrastructure (Vitest + Playwright) is fully configured but unused.

**Fix:** Prioritize tests for: (1) service layer (easy to test, high value), (2) custom hooks with `@testing-library/react-hooks`, (3) critical user flows via Playwright.

---

## Summary

| Priority | # Issues | Status |
|----------|----------|--------|
| Critical | 2 | All fixed |
| High — Performance | 5 | All fixed |
| High — Code Quality | 4 | 3 fixed, 1 remaining (#10) |
| Medium — Reliability | 5 | Open |
| Medium — Architecture | 5 | Open |
| Low — Cleanup | 5 | Open |

### Remaining: 16 issues (11 fixed)
