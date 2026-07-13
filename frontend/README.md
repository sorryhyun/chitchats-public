# ChitChats Frontend

React + TypeScript frontend for the ChitChats multi-agent chat application.

## Tech Stack

- **React 19.1.1** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS 4.1** - Styling framework (CSS-first config, no `tailwind.config.js`)
- **Radix UI** - Accessible primitives behind the local `components/ui/` set
- **Lucide React** - Icon library
- **React Markdown** - Markdown rendering with GitHub flavored markdown support
- **react-virtuoso** - Virtualized message list
- **i18next / react-i18next** - Internationalization (English + Korean)
- **Vitest** - Test runner

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── Login.tsx            # Authentication login screen
│   │   ├── AgentManager.tsx     # Add/remove agents from rooms
│   │   ├── AgentProfileModal.tsx # View/edit an agent's config
│   │   ├── AgentAvatar.tsx      # Avatar with profile picture fallback
│   │   ├── ErrorBoundary.tsx    # Top-level error boundary
│   │   ├── HowToDocsModal.tsx   # In-app docs modal
│   │   ├── LanguageSwitcher.tsx # EN/KO switcher
│   │   ├── chat-room/           # Chat interface
│   │   │   ├── ChatRoom.tsx         # Main chat container
│   │   │   ├── ChatHeader.tsx       # Room controls and status
│   │   │   ├── MessageInput.tsx     # User message input (images, @mentions)
│   │   │   ├── MentionDropdown.tsx  # @mention autocomplete
│   │   │   ├── header/              # Header sub-components
│   │   │   │   ├── RoomTitleEditor.tsx, RoomControls.tsx, RoomBadges.tsx
│   │   │   │   ├── ConnectionStatus.tsx, VoiceStatusIndicator.tsx
│   │   │   │   ├── ConversationCopyButton.tsx, AgentPanelToggle.tsx, SidebarToggle.tsx
│   │   │   └── message-list/
│   │   │       ├── MessageList.tsx      # Virtualized message display
│   │   │       ├── MessageRow.tsx       # Single message (thinking, voice playback)
│   │   │       ├── MarkdownContent.tsx  # Markdown + syntax highlighting
│   │   │       └── ImageAttachment.tsx  # Image attachments
│   │   ├── sidebar/          # MainSidebar and its panels
│   │   │   ├── MainSidebar.tsx      # Rooms/Agents tabs, logout
│   │   │   ├── RoomListPanel.tsx    # Room list display
│   │   │   ├── AgentListPanel.tsx   # Agent list and 1-on-1 chats
│   │   │   ├── CreateAgentForm.tsx  # Agent creation form
│   │   │   ├── SettingsModal.tsx    # Voice, thinking, input preferences
│   │   │   └── ExportModal.tsx      # Export Claude Code conversations
│   │   └── ui/               # Radix-based primitives (button, dialog, tooltip, ...)
│   ├── contexts/
│   │   ├── AuthContext.tsx          # JWT authentication state
│   │   ├── RoomContext.tsx          # Room list and selection
│   │   ├── AgentContext.tsx         # Agent list, selection, profiles
│   │   ├── VoiceContext.tsx         # Voice (TTS) playback state
│   │   ├── ToastContext.tsx         # Toast notifications
│   │   └── ChatRoomControlsContext.tsx # Shared chat-room controls for header
│   ├── hooks/
│   │   ├── useSSE.ts                # Server-Sent Events streaming
│   │   ├── usePolling.ts            # Message state: SSE + polling fallback
│   │   ├── usePollingData.ts        # Generic list-polling helper
│   │   ├── useAgents.ts             # Agent CRUD operations
│   │   ├── useRooms.ts              # Room CRUD operations
│   │   ├── useFetchAgentConfigs.ts  # Agent config fetching
│   │   ├── useMention.ts            # @mention parsing/autocomplete
│   │   ├── useImageUpload.ts        # Image attachments
│   │   ├── useImageDrop.ts          # Drag-and-drop images
│   │   ├── useWhiteboard.ts         # Whiteboard diff rendering
│   │   └── ...                      # Preferences, focus trap, read tracking
│   ├── services/            # API layer
│   │   ├── apiClient.ts        # Base URL resolution, auth headers, fetch helpers
│   │   ├── roomService.ts, agentService.ts, messageService.ts, voiceService.ts
│   ├── i18n/                # i18next setup + en/ko locale namespaces
│   ├── types/               # Shared TypeScript types
│   ├── styles/              # Tailwind entry, theme, utilities
│   ├── App.tsx              # Root component (providers, layout)
│   └── main.tsx             # Entry point
├── public/                  # Static assets
├── .env.example             # Environment variable template
└── package.json
```

## Key Components

### Authentication (`Login.tsx`, `AuthContext.tsx`)

- **Login Screen**: Password-only authentication (guest login supported when enabled)
- **JWT Token Management**: Tokens stored in localStorage
- **Auto-login**: Automatically verifies stored token on app load
- **API Integration**: All requests include `X-API-Key` header

**Flow:**
1. User enters password
2. Frontend calls `POST /auth/login`
3. Backend validates and returns JWT token (with role: admin/guest/user)
4. Token stored in localStorage and added to all API calls
5. On page reload, token is verified with `GET /auth/verify`

### Main Sidebar (`sidebar/MainSidebar.tsx`)

Two tabs (Rooms / Agents) composed of focused sub-components:

- **RoomListPanel** (`sidebar/RoomListPanel.tsx`): Display and manage rooms; room creation is handled inline by the sidebar
- **CreateAgentForm** (`sidebar/CreateAgentForm.tsx`): Agent creation from config files
- **AgentListPanel** (`sidebar/AgentListPanel.tsx`): Display agents and 1-on-1 chats
- **SettingsModal** / **ExportModal** / **HowToDocsModal**: Lazy-loaded modals opened from the sidebar
- **LanguageSwitcher** and **Logout Button**

### Chat Room (`chat-room/ChatRoom.tsx`)

The chat room is split into focused sub-components:

- **ChatHeader** (`chat-room/ChatHeader.tsx`): Room title editing, controls (pause, interaction limit, clear), connection and voice status, agent panel toggle
- **MessageInput** (`chat-room/MessageInput.tsx`): Send messages with participant type selection, image attachments (paste/drag-drop) and `@agent` mentions
- **Real-time Messaging**: `usePolling` hook — SSE streaming plus a polling fallback
- **Agent Manager**: Add/remove agents from current room
- **Message Display**: Shows user and agent messages with streaming thinking text

### Message List (`chat-room/message-list/MessageList.tsx`)

- **Virtualized Rendering**: `react-virtuoso` keeps long histories fast
- **Thinking Text**: Shows agent reasoning process (collapsible; default set in Settings)
- **Markdown Support**: `MarkdownContent.tsx` renders GitHub flavored markdown
- **Syntax Highlighting**: Code blocks via `react-syntax-highlighter`
- **Images & Voice**: Image attachments and per-message voice playback (`MessageRow.tsx`)
- **Auto-scroll**: Follows the bottom on new messages

### Real-time Layer (`useSSE.ts`, `usePolling.ts`)

**SSE is the primary transport, with a 5s HTTP polling fallback.**

`useSSE(roomId)` — primary, token-by-token streaming:
1. `POST /rooms/{id}/sse-ticket` to get a short-lived ticket (keeps the JWT out of URLs/logs)
2. Opens an `EventSource` at `/rooms/{id}/stream?ticket=...`
3. Handles events: `stream_start`, `content_delta`, `thinking_delta`, `stream_end`, `keepalive`, `shutdown`
4. Accumulates per-agent `response_text` / `thinking_text` into a `streamingAgents` Map
5. Reconnects with exponential backoff (1s → 30s, max 10 attempts); reconnecting clients catch up via the `stream_start` payload

```typescript
const { isConnected, streamingAgents, error } = useSSE(roomId);
```

`usePolling(roomId)` owns the message list and wraps `useSSE`. It loads history, turns `streamingAgents` into live "chatting" indicators, and keeps a **fallback** poll (`since_id` incremental, 5s) for durability when SSE drops; agent-status polling only runs while SSE is disconnected.

```typescript
const {
  messages,
  sendMessage,
  isConnected,
  sseConnected,
  setMessages,
  resetMessages
} = usePolling(roomId);
```

Room and agent lists poll separately via `usePollingData` (rooms 5s, agents 10s).

### Voice (`contexts/VoiceContext.tsx`, `services/voiceService.ts`)

Optional text-to-speech for agent messages, backed by the backend `/voice/*` endpoints.

- Toggle in **SettingsModal**; preference persists in localStorage
- `GET /voice/status` reports whether the voice server is available (surfaced by `VoiceStatusIndicator` in the header)
- `POST /voice/generate` generates audio for a message; `GET /voice/audio/{message_id}` streams it
- Play/stop controls appear on agent messages in `MessageRow.tsx`

### Exports (`sidebar/ExportModal.tsx`)

Lists Claude Code conversation files from `GET /exports/conversations` and downloads a selected transcript (optionally in simplified form).

## Development

### Setup

```bash
# Install dependencies
npm install

# Copy environment template
cp .env.example .env
```

### Environment Variables

Create `frontend/.env`:

```bash
# Backend API URL
VITE_API_BASE_URL=http://localhost:8001

# For production (Vercel):
# VITE_API_BASE_URL=https://your-ngrok-domain.ngrok-free.app
```

`VITE_API_BASE_URL` is the only variable read by the app. If it is unset, `services/apiClient.ts` auto-detects the backend (same origin in bundled mode, `localhost:8000` under Tauri, otherwise `http://<host>:8001`).

### Run Development Server

```bash
npm run dev
# Opens on http://localhost:5173 (strict port)
```

### Build for Production

```bash
npm run build
# Output in dist/

# Preview production build
npm run preview
```

## API Integration

All API calls go through `services/apiClient.ts`, which automatically includes:
- `X-API-Key` header with the JWT token
- `Content-Type: application/json` (for JSON bodies)
- `ngrok-skip-browser-warning: true` (for ngrok deployments)

**Example:**
```typescript
import { setApiKey, apiGet } from './services';

// Set token (done automatically by AuthContext)
setApiKey(jwtToken);

// Helpers (apiGet/apiPost/apiPatch/apiDelete) include auth automatically
const rooms = await apiGet<Room[]>('/rooms');
```

Domain calls are wrapped in `roomService`, `agentService`, `messageService`, and `voiceService`.

## API Authentication

All API requests include the JWT token in the `X-API-Key` header. The SSE stream is the exception: `EventSource` cannot send headers, so the frontend exchanges the JWT for a short-lived ticket (`POST /rooms/{id}/sse-ticket`) and passes it as a query parameter.

See [docs/SETUP.md](../docs/SETUP.md) for complete authentication details.

## Styling & Components

**Tailwind CSS 4.1**, configured CSS-first (no `tailwind.config.js`):
- Entry point `src/styles/index.css`; Tailwind + plugins declared in `src/styles/tailwind.css`
- **Typography Plugin**: Enhanced markdown styling
- **Animation Plugin**: Smooth transitions and animations
- **Custom Theme**: `@theme` block in `src/styles/tailwind.css`, plus `src/styles/base/theme.css`
- Three-tier responsive system: mobile (default), tablet (`sm:`), desktop (`lg:`)

**UI Primitives** (`src/components/ui/`):
- shadcn-style components copied into the repo, built on Radix UI primitives
- Customized with Tailwind CSS; icons from Lucide React

## Internationalization

`src/i18n/` configures i18next with browser language detection, English fallback, and the namespaces `common`, `auth`, `sidebar`, `chat`, `agents`, `rooms`, `docs`. Locale files live in `src/i18n/locales/{en,ko}/`.

## Deployment

### Vercel (Recommended)

1. Set environment variable in Vercel dashboard:
   ```
   VITE_API_BASE_URL=https://your-backend.ngrok-free.app
   ```

2. Deploy:
   ```bash
   vercel
   ```

3. Configure backend CORS:
   ```bash
   # In backend/.env
   FRONTEND_URL=https://your-app.vercel.app
   ```

### Manual Build

```bash
npm run build
# Serve dist/ directory with any static host
```

## Troubleshooting

**"Invalid or missing API key" error:**
- Check that you're logged in
- Verify backend is running and accessible
- Check browser console for auth errors
- Try logging out and back in

**Messages not updating / no live streaming:**
- Check the connection indicator in the chat header
- Verify the SSE stream (`/rooms/{id}/stream`) appears in the network tab and stays open
- If the ticket request (`/rooms/{id}/sse-ticket`) fails, the hook retries with backoff and only the 5s fallback poll delivers messages
- Proxies that buffer responses can break SSE; verify background scheduler is active in the backend

**CORS errors:**
- Verify backend `FRONTEND_URL` matches your frontend URL
- Check backend startup logs for CORS configuration
- Ensure backend allows your origin in CORS middleware

**Auto-login not working:**
- Check localStorage for `chitchats_api_key`
- Token may have expired (7-day expiration)
- Clear localStorage and log in again
- Check network tab for failed `/auth/verify` request

## Scripts

```bash
npm run dev            # Start development server
npm run build          # Build for production
npm run preview        # Preview production build
npm run typecheck      # TypeScript check (tsc --noEmit)
npm run lint           # Run ESLint
npm run test           # Run Vitest
npm run test:ui        # Vitest UI
npm run test:coverage  # Vitest with coverage
```

## Dependencies

**Core:**
- `react` ^19.1.1
- `react-dom` ^19.1.1
- `typescript` ^5.9.3

**UI Components:**
- `@radix-ui/react-*` - Accessible component primitives (avatar, dialog, dropdown, scroll-area, tooltip, etc.)
- `lucide-react` ^0.555.0 - Icon library
- `class-variance-authority` ^0.7.1 - CSS variant utilities
- `clsx` ^2.1.1 - Class name management
- `tailwind-merge` ^3.4.0 - Tailwind class merging
- `tailwindcss-animate` ^1.0.7 - Animation utilities
- `react-virtuoso` ^4.16.1 - List virtualization

**Markdown:**
- `react-markdown` ^10.1.0
- `react-syntax-highlighter` ^16.1.0
- `remark-gfm` ^4.0.1
- `remark-breaks` ^4.0.0

**Styling:**
- `tailwindcss` ^4.1.16
- `@tailwindcss/typography` ^0.5.19

**i18n:**
- `i18next` ^25.7.3
- `react-i18next` ^16.5.0
- `i18next-browser-languagedetector` ^8.2.0

**Build & Test:**
- `vite` ^7.1.7
- `@vitejs/plugin-react` ^5.0.4
- `vitest` ^4.0.14
- `@testing-library/react` ^16.3.0

## Related Documentation

- [Main README](../README.md) - Project overview
- [docs/SETUP.md](../docs/SETUP.md) - Setup, authentication, and deployment
- [Backend README](../backend/README.md) - Backend API documentation
