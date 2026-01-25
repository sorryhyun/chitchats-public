// Re-export everything from services
export * from './apiClient';
export * from './roomService';
export * from './agentService';
export * from './messageService';
export * from './voiceService';

// Import services
import { roomService } from './roomService';
import { agentService } from './agentService';
import { messageService } from './messageService';
import { voiceService } from './voiceService';

/**
 * Legacy API object for backward compatibility.
 * @deprecated Use individual services (roomService, agentService, messageService, voiceService) instead.
 */
export const api = {
  // Room operations
  ...roomService,

  // Agent operations
  ...agentService,

  // Message operations
  ...messageService,

  // Voice operations
  ...voiceService,
};
