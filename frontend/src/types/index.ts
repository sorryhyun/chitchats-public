export interface Agent {
  id: number;
  name: string;
  group: string | null;
  config_file: string | null;
  profile_pic: string | null;
  in_a_nutshell: string | null;
  characteristics: string | null;
  backgrounds: string | null;
  memory: string | null;
  recent_events: string | null;
  system_prompt: string;
  session_id: string | null;
  is_critic: boolean;
  created_at: string;
}

export interface AgentCreate {
  name: string;
  group?: string | null;
  config_file?: string | null;
  profile_pic?: string | null;
  in_a_nutshell?: string | null;
  characteristics?: string | null;
  backgrounds?: string | null;
  memory?: string | null;
  recent_events?: string | null;
}

export interface AgentUpdate {
  profile_pic?: string | null;
  in_a_nutshell?: string | null;
  characteristics?: string | null;
  backgrounds?: string | null;
  memory?: string | null;
  recent_events?: string | null;
}

export interface AgentConfig {
  [key: string]: string;
}

export interface ImageAttachment {
  data: string;  // Base64-encoded image data
  media_type: string;  // MIME type (e.g., 'image/png', 'image/jpeg')
}

export interface Message {
  id: number | string;  // Can be temp_id (string) during streaming or real DB id (number) after
  room_id?: number;
  agent_id: number | null;
  content: string;
  role: string;
  participant_type?: string | null;
  participant_name?: string | null;
  timestamp: string;
  agent_name?: string;
  agent_profile_pic?: string | null;
  is_typing?: boolean;
  is_chatting?: boolean;  // True when agent is generating a response (polling-based indicator)
  thinking?: string | null;
  is_streaming?: boolean;  // True while message is being streamed
  temp_id?: string;  // Temporary ID for streaming messages
  is_skipped?: boolean;  // True when agent chose to skip/ignore the message
  image_data?: ImageAttachment | null;  // Optional attached image
}

export interface MessageCreate {
  content: string;
  role: string;
  agent_id?: number | null;
  image_data?: ImageAttachment | null;  // Optional attached image
}

export interface Room {
  id: number;
  name: string;
   owner_id?: string | null;
  max_interactions: number | null;
  is_paused: boolean;
  created_at: string;
  last_activity_at: string | null;
  last_read_at: string | null;
  agents: Agent[];
  messages: Message[];
}

export interface RoomSummary {
  id: number;
  name: string;
   owner_id?: string | null;
  max_interactions: number | null;
  is_paused: boolean;
  created_at: string;
  last_activity_at: string | null;
  last_read_at: string | null;
  has_unread: boolean;
}

export interface RoomCreate {
  name: string;
  max_interactions?: number | null;
}

export interface RoomUpdate {
  max_interactions?: number | null;
  is_paused?: boolean;
}

export type ParticipantType = 'user' | 'situation_builder' | 'character';
