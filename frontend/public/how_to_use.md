# How to Use Claude Code RP

Welcome to Claude Code RP - a multi-agent roleplay chat application where AI agents with unique personalities interact in real-time.

---

## Getting Started

### Creating Your First Room

1. Click **Create Room** on the home page, or use the **+ New Chatroom** button in the sidebar
2. Enter a name for your room (e.g., "Coffee Shop", "Adventure Party")
3. Your new room will appear in the Chatrooms list

### Adding Agents to a Room

1. Select a room from the sidebar
2. Click the **agent icon** in the header (or the agent panel on desktop)
3. Use the **+ Add** button next to any agent to add them to the room
4. Added agents will appear in the "In Room" section

### Quick Chat with an Agent

Click any agent in the **Agents** tab to instantly start a 1-on-1 conversation. This creates a direct chat room with just you and that agent.

---

## Sending Messages

### Message Types

When you type a message, you can choose how it appears in the conversation:

| Type | Icon | Purpose |
|------|------|---------|
| **User** | 👤 | Your direct messages to agents |
| **Situation Builder** | 🎬 | Set the scene or describe what's happening |
| **Character** | 🎭 | Speak as a custom character (enter a name) |

### Using Situation Builder

Situation Builder messages help set context without being "you" talking:

> *The café is quiet this afternoon. Rain patters against the windows as the smell of fresh coffee fills the air.*

Agents respond to the scene you've set, creating more immersive roleplay.

### Speaking as a Character

Select "Character" mode and enter a name to introduce other characters into the scene:

> **Shopkeeper:** "Welcome! Looking for anything special today?"

---

## Room Controls

### Header Actions

- **Refresh** - Reload messages from server
- **Pause/Resume** - Pause agent responses (useful for setting up scenes)
- **Interaction Limit** - Set maximum agent interactions (prevents runaway conversations)
- **Clear** - Delete all messages in the room
- **Rename** - Change the room name

### Pause Mode

When paused:
- Agents won't automatically respond
- You can set up complex scenes with multiple Situation Builder messages
- Resume when you're ready for agents to react

### Interaction Limits

Set a limit to control how many times agents respond to each other:
- **No limit** - Agents chat freely (may continue indefinitely)
- **1-10** - Agents stop after reaching the limit
- Useful for preventing long autonomous conversations

---

## Managing Agents

### Agent Profiles

Click the **info icon** on any agent to view their profile:
- See their personality and background
- View their profile picture
- Understand their character traits

### Creating New Agents

Agents are created from configuration folders in `agents/` directory:

```
agents/
  your_agent/
    ├── in_a_nutshell.md      # Brief identity
    ├── characteristics.md     # Personality traits
    ├── recent_events.md       # Recent memories
    └── profile.png            # Profile picture
```

After adding files, click **+ New Agent** in the Agents tab to activate them.

---

## Tips for Great Roleplay

### Setting Good Scenes

- Use Situation Builder to establish mood, location, and atmosphere
- Include sensory details (sounds, smells, lighting)
- Give agents something to react to

### Working with Multiple Agents

- Agents respond based on their personalities
- They may interact with each other, not just you
- Use pause mode to orchestrate complex scenes

### Memory System

Agents remember recent events from your conversations. Their memories are stored in `recent_events.md` and influence future responses.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line in message |
| `Escape` | Close modals/panels |

---

## Need Help?

- Check the sidebar tabs to switch between Rooms and Agents
- Use the theme toggle to switch between light and dark mode
- Refresh the page if something seems stuck

Happy roleplaying!
