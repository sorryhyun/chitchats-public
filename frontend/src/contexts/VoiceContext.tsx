import {
  createContext,
  useContext,
  useMemo,
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import { voiceService, type VoiceStatus } from '../services/voiceService';

interface VoiceContextValue {
  /** Whether voice mode is enabled by user */
  enabled: boolean;
  /** Toggle voice mode on/off */
  setEnabled: (enabled: boolean) => void;
  /** Whether voice server is available */
  serverAvailable: boolean;
  /** ID of message currently playing audio */
  playingMessageId: number | null;
  /** ID of message currently generating audio */
  generatingMessageId: number | null;
  /** Play audio for a message (generates if needed) */
  playMessage: (messageId: number, roomId: number) => Promise<void>;
  /** Stop currently playing audio */
  stopPlaying: () => void;
  /** Check if audio exists for a message */
  hasAudio: (messageId: number) => boolean;
  /** Set of message IDs that have cached audio */
  cachedMessageIds: Set<number>;
}

const VoiceContext = createContext<VoiceContextValue | undefined>(undefined);

const VOICE_ENABLED_KEY = 'chitchats_voice_enabled';

export const VoiceProvider = ({ children }: { children: ReactNode }) => {
  // Load initial state from localStorage
  const [enabled, setEnabledState] = useState(() => {
    const saved = localStorage.getItem(VOICE_ENABLED_KEY);
    return saved === 'true';
  });

  const [serverAvailable, setServerAvailable] = useState(false);
  const [playingMessageId, setPlayingMessageId] = useState<number | null>(null);
  const [generatingMessageId, setGeneratingMessageId] = useState<number | null>(null);
  const [cachedMessageIds, setCachedMessageIds] = useState<Set<number>>(new Set());

  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Save enabled state to localStorage
  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value);
    localStorage.setItem(VOICE_ENABLED_KEY, value.toString());
  }, []);

  // Check server status periodically
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const status: VoiceStatus = await voiceService.getStatus();
        setServerAvailable(status.server_available);
      } catch {
        setServerAvailable(false);
      }
    };

    // Initial check
    checkStatus();

    // Only poll if voice is enabled
    if (enabled) {
      const interval = setInterval(checkStatus, 30000);
      return () => clearInterval(interval);
    }
  }, [enabled]);

  // Stop playing when component unmounts
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  const stopPlaying = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlayingMessageId(null);
  }, []);

  const playMessage = useCallback(async (messageId: number, roomId: number) => {
    // Stop any current playback
    stopPlaying();

    try {
      // Check if audio already exists
      const existsResult = await voiceService.exists(messageId);

      if (!existsResult.exists) {
        // Generate audio
        setGeneratingMessageId(messageId);
        const generateResult = await voiceService.generate(messageId, roomId);
        setGeneratingMessageId(null);

        if (generateResult.status === 'error') {
          console.error('Voice generation failed:', generateResult.error);
          return;
        }

        // Add to cached set
        setCachedMessageIds(prev => new Set([...prev, messageId]));
      }

      // Play the audio
      const audioUrl = voiceService.getAudioUrl(messageId);
      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onended = () => {
        setPlayingMessageId(null);
        audioRef.current = null;
      };

      audio.onerror = () => {
        console.error('Audio playback error');
        setPlayingMessageId(null);
        audioRef.current = null;
      };

      setPlayingMessageId(messageId);
      await audio.play();

    } catch (error) {
      console.error('Voice playback error:', error);
      setGeneratingMessageId(null);
      setPlayingMessageId(null);
    }
  }, [stopPlaying]);

  const hasAudio = useCallback((messageId: number): boolean => {
    return cachedMessageIds.has(messageId);
  }, [cachedMessageIds]);

  const value = useMemo(
    () => ({
      enabled,
      setEnabled,
      serverAvailable,
      playingMessageId,
      generatingMessageId,
      playMessage,
      stopPlaying,
      hasAudio,
      cachedMessageIds,
    }),
    [
      enabled,
      setEnabled,
      serverAvailable,
      playingMessageId,
      generatingMessageId,
      playMessage,
      stopPlaying,
      hasAudio,
      cachedMessageIds,
    ]
  );

  return (
    <VoiceContext.Provider value={value}>
      {children}
    </VoiceContext.Provider>
  );
};

export const useVoice = (): VoiceContextValue => {
  const context = useContext(VoiceContext);
  if (!context) {
    throw new Error('useVoice must be used within a VoiceProvider');
  }
  return context;
};
