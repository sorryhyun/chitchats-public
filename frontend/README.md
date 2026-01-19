# ChitChats Frontend

React + TypeScript frontend for the ChitChats multi-agent chat application.

## Tech Stack

- **React 19.1.1** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS 4.1** - Styling framework
- **shadcn/ui** - Component library built on Radix UI primitives
- **Lucide React** - Icon library
- **React Markdown** - Markdown rendering with GitHub flavored markdown support

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── Login.tsx       # Authentication login screen
│   │   ├── MainSidebar.tsx # Room list, agent list, logout
│   │   ├── ChatRoom.tsx    # Main chat interface
│   │   ├── MessageList.tsx # Message display with thinking
│   │   ├── AgentManager.tsx # Add/remove agents from rooms
│   │   ├── chat-room/      # ChatRoom sub-components
│   │   │   ├── ChatHeader.tsx    # Room controls and settings
│   │   │   └── MessageInput.tsx  # User message input
│   │   └── sidebar/        # MainSidebar sub-components
│   │       ├── CreateRoomForm.tsx   # Room creation form
│   │       ├── RoomListPanel.tsx    # Room list display
│   │       ├── CreateAgentForm.tsx  # Agent creation form
│   │       └── AgentListPanel.tsx   # Agent list display
│   ├── contexts/
│   │   └── AuthContext.tsx # JWT authentication state management
│   ├── hooks/
│   │   ├── usePolling.ts            # Message polling for real-time updates
│   │   ├── useAgents.ts             # Agent CRUD operations
│   │   ├── useRooms.ts              # Room CRUD operations
│   │   └── useFetchAgentConfigs.ts  # Agent config fetching
│   ├── utils/
│   │   └── api.ts          # API client with auth headers
│   ├── App.tsx             # Root component
│   └── main.tsx            # Entry point
├── public/                  # Static assets
├── .env.example            # Environment variable template
└── package.json
```

## Key Components

### Authentication (`Login.tsx`, `AuthContext.tsx`)

- **Login Screen**: Password-only authentication
- **JWT Token Management**: Tokens stored in localStorage
- **Auto-login**: Automatically verifies stored token on app load
- **API Integration**: All requests include `X-API-Key` header

**Flow:**
1. User enters password
2. Frontend calls `POST /auth/login`
3. Backend validates and returns JWT token
4. Token stored in localStorage and added to all API calls
5. On page reload, token is verified with `GET /auth/verify`

### Main Sidebar (`MainSidebar.tsx`)

The sidebar is composed of focused sub-components for better maintainability:

- **CreateRoomForm** (`sidebar/CreateRoomForm.tsx`): Room creation with name input
- **RoomListPanel** (`sidebar/RoomListPanel.tsx`): Display and manage rooms
- **CreateAgentForm** (`sidebar/CreateAgentForm.tsx`): Agent creation from config files
- **AgentListPanel** (`sidebar/AgentListPanel.tsx`): Display agents and 1-on-1 chats
- **Logout Button**: Clears authentication state

### Chat Room (`ChatRoom.tsx`)

The chat room is split into focused sub-components:

- **ChatHeader** (`chat-room/ChatHeader.tsx`): Room controls (pause, interaction limit, clear, agent manager)
- **MessageInput** (`chat-room/MessageInput.tsx`): Send messages with participant type selection
- **Polling Integration**: Real-time messaging via `usePolling` hook (2-second intervals)
- **Agent Manager**: Add/remove agents from current room
- **Message Display**: Shows user and agent messages with thinking text

### Message List (`MessageList.tsx`)

- **Message Rendering**: Displays chat history
- **Thinking Text**: Shows agent reasoning process (collapsible)
- **Markdown Support**: Renders markdown in messages with GitHub flavored markdown
- **Syntax Highlighting**: Code blocks with proper formatting
- **Auto-scroll**: Scrolls to bottom on new messages

### Polling Hook (`usePolling.ts`)

**Features:**
- Automatic polling every 2 seconds for new messages
- Incremental updates using `since_id` parameter
- Message state management with deduplication
- Automatic cleanup on room change

**Usage:**
```typescript
const {
  messages,
  sendMessage,
  setMessages
} = usePolling(roomId);
```

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

### Run Development Server

```bash
npm run dev
# Opens on http://localhost:5173
```

### Build for Production

```bash
npm run build
# Output in dist/

# Preview production build
npm run preview
```

## API Integration

All API calls are made through `utils/api.ts` which automatically includes:
- `X-API-Key` header with JWT token
- `Content-Type: application/json`
- `ngrok-skip-browser-warning: true` (for ngrok deployments)

**Example:**
```typescript
import { setApiKey } from './utils/api';

// Set token (done automatically by AuthContext)
setApiKey(jwtToken);

// API calls automatically include auth
const response = await fetch(`${API_BASE_URL}/rooms`, {
  headers: getHeaders(), // Includes X-API-Key
});
```

## API Authentication

All API requests include JWT token in the `X-API-Key` header:

```typescript
const response = await fetch(`${API_BASE_URL}/rooms/1/messages/poll`, {
  headers: {
    'X-API-Key': jwtToken,
  },
});
```

See [../SETUP.md](../SETUP.md) for complete authentication details.

## Styling & Components

**Tailwind CSS 4.1** with:
- **Typography Plugin**: Enhanced markdown styling
- **Animation Plugin**: Smooth transitions and animations
- **Custom Theme**: Defined in `tailwind.config.js`
- **Utility-First**: Inline utility classes for styling

**shadcn/ui Components**:
- Built on Radix UI primitives for accessibility
- Copy-paste component architecture (components in `src/components/ui/`)
- Customizable with Tailwind CSS
- Icons from Lucide React

**Adding components:**
```bash
npx shadcn@latest add [component-name]
```

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

**Messages not updating:**
- Verify backend is running and polling endpoint is accessible
- Check browser console for polling errors
- Verify background scheduler is active in backend
- Check network tab to ensure polling requests are successful

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
npm run dev       # Start development server
npm run build     # Build for production
npm run preview   # Preview production build
npm run lint      # Run ESLint
```

## Dependencies

**Core:**
- `react` ^19.1.1
- `react-dom` ^19.1.1
- `typescript` ^5.9.3

**UI Components:**
- `@radix-ui/react-*` - Accessible component primitives (avatar, dialog, dropdown, scroll-area, etc.)
- `lucide-react` ^0.555.0 - Icon library
- `class-variance-authority` ^0.7.1 - CSS variant utilities
- `clsx` ^2.1.1 - Class name management
- `tailwind-merge` ^3.4.0 - Tailwind class merging
- `tailwindcss-animate` ^1.0.7 - Animation utilities

**Markdown:**
- `react-markdown` ^10.1.0
- `react-syntax-highlighter` ^16.1.0
- `remark-gfm` ^4.0.1

**Styling:**
- `tailwindcss` ^4.1.16
- `@tailwindcss/typography` ^0.5.19

**Build Tools:**
- `vite` ^7.1.7
- `@vitejs/plugin-react` ^5.0.4

## Related Documentation

- [Main README](../README.md) - Project overview
- [SETUP.md](../SETUP.md) - Setup, authentication, deployment, and memory systems
- [Backend README](../backend/README.md) - Backend API documentation
- [SIMULATIONS.md](../SIMULATIONS.md) - Simulation and testing guide
