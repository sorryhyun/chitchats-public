import { useState, useRef, useCallback } from 'react';
import { API_BASE_URL, getApiKey } from '../services/apiClient';
import { AudioPlaybackBuffer } from '../utils/audioPlayback';

export type VoiceStatus = 'idle' | 'connecting' | 'active' | 'error';

interface TranscriptItem {
  item: Record<string, unknown>;
}

const SAMPLE_RATE = 24000;
const FRAME_SIZE = 480; // 20ms at 24kHz

/**
 * Hook for bidirectional realtime voice communication with Codex rooms.
 *
 * Captures microphone audio as PCM16 and streams it over WebSocket to
 * the backend, which bridges to the Codex app-server realtime API.
 * Plays back audio responses from the model.
 */
export function useVoiceRealtime(roomId: number | null) {
  const [status, setStatus] = useState<VoiceStatus>('idle');
  const [transcript, setTranscript] = useState<TranscriptItem | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<ScriptProcessorNode | null>(null);
  const playbackRef = useRef<AudioPlaybackBuffer | null>(null);
  const pcmBufferRef = useRef<Float32Array>(new Float32Array(0));

  const cleanup = useCallback(() => {
    // Stop mic stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(t => t.stop());
      mediaStreamRef.current = null;
    }

    // Disconnect audio processing
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    // Close capture AudioContext
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    // Stop playback
    if (playbackRef.current) {
      playbackRef.current.destroy();
      playbackRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    pcmBufferRef.current = new Float32Array(0);
  }, []);

  const start = useCallback(async () => {
    if (!roomId || status === 'active' || status === 'connecting') return;

    setStatus('connecting');
    setErrorMessage(null);
    setTranscript(null);

    try {
      // 1. Request mic permission
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      mediaStreamRef.current = stream;

      // 2. Open WebSocket
      const token = getApiKey() || '';
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const apiUrl = new URL(API_BASE_URL);
      const wsUrl = `${wsProtocol}//${apiUrl.host}/rooms/${roomId}/voice/realtime?token=${encodeURIComponent(token)}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      // 3. Set up playback buffer
      const playback = new AudioPlaybackBuffer(SAMPLE_RATE);
      playbackRef.current = playback;

      // 4. Handle WS messages
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          switch (msg.type) {
            case 'audio':
              playback.enqueue(msg.data, msg.sampleRate || SAMPLE_RATE);
              break;
            case 'transcript':
              setTranscript({ item: msg.item });
              break;
            case 'error':
              setErrorMessage(msg.message || 'Unknown error');
              break;
            case 'closed':
              setStatus('idle');
              cleanup();
              break;
            case 'started':
              // Session confirmed by server
              break;
          }
        } catch (err) {
          console.error('Failed to parse voice WS message:', err);
        }
      };

      ws.onerror = () => {
        setStatus('error');
        setErrorMessage('WebSocket connection error');
        cleanup();
      };

      ws.onclose = () => {
        if (status !== 'idle') {
          setStatus('idle');
        }
      };

      // Wait for WS to open
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        const originalOnError = ws.onerror;
        ws.onerror = (e) => {
          originalOnError?.call(ws, e);
          reject(new Error('WebSocket failed to connect'));
        };
      });

      // 5. Set up audio capture
      const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);

      // ScriptProcessorNode for PCM capture (AudioWorklet is more complex to set up)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      workletNodeRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return;

        const inputData = e.inputBuffer.getChannelData(0);

        // Accumulate samples
        const combined = new Float32Array(pcmBufferRef.current.length + inputData.length);
        combined.set(pcmBufferRef.current);
        combined.set(inputData, pcmBufferRef.current.length);
        pcmBufferRef.current = combined;

        // Send in FRAME_SIZE chunks (20ms)
        while (pcmBufferRef.current.length >= FRAME_SIZE) {
          const frame = pcmBufferRef.current.slice(0, FRAME_SIZE);
          pcmBufferRef.current = pcmBufferRef.current.slice(FRAME_SIZE);

          // Convert Float32 → PCM16 little-endian
          const pcm16 = new Int16Array(frame.length);
          for (let i = 0; i < frame.length; i++) {
            const s = Math.max(-1, Math.min(1, frame[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }

          // Encode to base64
          const bytes = new Uint8Array(pcm16.buffer);
          let binary = '';
          for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          const base64 = btoa(binary);

          ws.send(JSON.stringify({
            type: 'audio',
            data: base64,
            sampleRate: SAMPLE_RATE,
            numChannels: 1,
            samplesPerChannel: FRAME_SIZE,
          }));
        }
      };

      source.connect(processor);
      processor.connect(audioCtx.destination); // Required for ScriptProcessor to fire

      setStatus('active');
    } catch (err) {
      console.error('Failed to start voice mode:', err);
      setStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'Failed to start voice mode');
      cleanup();
    }
  }, [roomId, status, cleanup]);

  const stop = useCallback(() => {
    // Send stop message before cleanup
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
    }
    setStatus('idle');
    cleanup();
  }, [cleanup]);

  return { status, start, stop, transcript, errorMessage, cleanup };
}
