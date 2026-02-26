/**
 * PCM16 audio playback buffer for streaming realtime voice responses.
 *
 * Decodes base64-encoded PCM16 chunks from the Codex realtime API
 * and plays them back sequentially with gap-free scheduling.
 */

export class AudioPlaybackBuffer {
  private audioContext: AudioContext | null = null;
  private queue: { buffer: AudioBuffer }[] = [];
  private isPlaying = false;
  private nextStartTime = 0;
  private currentSource: AudioBufferSourceNode | null = null;

  constructor(private sampleRate: number = 24000) {}

  private getContext(): AudioContext {
    if (!this.audioContext) {
      this.audioContext = new AudioContext({ sampleRate: this.sampleRate });
    }
    return this.audioContext;
  }

  /**
   * Decode base64 PCM16 and enqueue for playback.
   */
  enqueue(pcm16Base64: string, sampleRate?: number): void {
    const ctx = this.getContext();
    const rate = sampleRate ?? this.sampleRate;

    // Decode base64 → raw bytes
    const binaryStr = atob(pcm16Base64);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }

    // PCM16 little-endian → Float32
    const sampleCount = bytes.length / 2;
    const audioBuffer = ctx.createBuffer(1, sampleCount, rate);
    const channel = audioBuffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

    for (let i = 0; i < sampleCount; i++) {
      const int16 = view.getInt16(i * 2, true); // little-endian
      channel[i] = int16 / 32768;
    }

    this.queue.push({ buffer: audioBuffer });

    if (!this.isPlaying) {
      this.playNext();
    }
  }

  private playNext(): void {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      return;
    }

    this.isPlaying = true;
    const ctx = this.getContext();
    const { buffer } = this.queue.shift()!;

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // Schedule gap-free: start at nextStartTime or now (whichever is later)
    const now = ctx.currentTime;
    const startTime = Math.max(this.nextStartTime, now);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;

    this.currentSource = source;

    source.onended = () => {
      if (this.currentSource === source) {
        this.currentSource = null;
      }
      this.playNext();
    };
  }

  /**
   * Stop playback and clear the queue.
   */
  stop(): void {
    this.queue = [];
    this.isPlaying = false;
    this.nextStartTime = 0;

    if (this.currentSource) {
      try {
        this.currentSource.stop();
      } catch {
        // Already stopped
      }
      this.currentSource = null;
    }
  }

  /**
   * Release all resources (close AudioContext).
   */
  destroy(): void {
    this.stop();
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
  }
}
