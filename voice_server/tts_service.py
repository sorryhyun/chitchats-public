"""
TTS service using Qwen3-TTS with vLLM backend.

This module provides text-to-speech synthesis using the Qwen3-TTS model
with optional voice cloning from reference audio samples.
"""

import io
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger("TTSService")

# Model constants
MODEL_ID = "Qwen/Qwen3-TTS"
SAMPLE_RATE = 24000


class TTSService:
    """
    Text-to-speech service using Qwen3-TTS via vLLM.

    This service provides:
    - Text-to-speech synthesis
    - Voice cloning from reference audio
    - WAV format output
    """

    def __init__(self):
        """Initialize the TTS service."""
        self._model = None
        self._processor = None
        self._vllm_engine = None
        self._ready = False
        self._use_vllm = True  # Try vLLM first, fallback to direct

    async def initialize(self) -> bool:
        """
        Initialize the TTS model and processor.

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            logger.info(f"Loading TTS model: {MODEL_ID}")

            # Try vLLM first for better performance
            if self._use_vllm:
                try:
                    from vllm import LLM, SamplingParams

                    logger.info("Initializing vLLM engine for TTS...")
                    self._vllm_engine = LLM(
                        model=MODEL_ID,
                        trust_remote_code=True,
                        dtype="auto",
                        gpu_memory_utilization=0.8,
                    )
                    logger.info("vLLM engine initialized successfully")
                except ImportError:
                    logger.warning("vLLM not available, falling back to transformers")
                    self._use_vllm = False
                except Exception as e:
                    logger.warning(f"vLLM initialization failed: {e}, falling back to transformers")
                    self._use_vllm = False

            # Fallback to transformers if vLLM is not available
            if not self._use_vllm:
                from transformers import AutoModelForCausalLM, AutoProcessor

                self._processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
                self._model = AutoModelForCausalLM.from_pretrained(
                    MODEL_ID,
                    trust_remote_code=True,
                    device_map="auto",
                    torch_dtype="auto",
                )
                logger.info("Transformers model loaded successfully")

            self._ready = True
            logger.info("TTS service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize TTS service: {e}")
            import traceback

            traceback.print_exc()
            return False

    @property
    def is_ready(self) -> bool:
        """Check if the TTS service is ready."""
        return self._ready

    async def generate(
        self,
        text: str,
        voice_file: Optional[str] = None,
        voice_text: Optional[str] = None,
    ) -> Tuple[bytes, int]:
        """
        Generate speech audio from text.

        Args:
            text: The text to synthesize
            voice_file: Optional path to reference voice audio for cloning
            voice_text: Optional transcript of the reference audio

        Returns:
            Tuple of (WAV audio bytes, duration in milliseconds)

        Raises:
            RuntimeError: If the service is not initialized
        """
        if not self._ready:
            raise RuntimeError("TTS service not initialized")

        try:
            # Load reference audio if provided
            ref_audio = None
            if voice_file and Path(voice_file).exists():
                ref_audio = self._load_audio(voice_file)

            # Generate audio
            if self._use_vllm and self._vllm_engine:
                audio_array = await self._generate_with_vllm(text, ref_audio, voice_text)
            else:
                audio_array = await self._generate_with_transformers(text, ref_audio, voice_text)

            # Convert to WAV bytes
            wav_bytes = self._array_to_wav(audio_array)
            duration_ms = int(len(audio_array) / SAMPLE_RATE * 1000)

            return wav_bytes, duration_ms

        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            import traceback

            traceback.print_exc()
            raise

    def _load_audio(self, file_path: str) -> np.ndarray:
        """Load audio file and return as numpy array."""
        import soundfile as sf

        audio, sr = sf.read(file_path)

        # Resample if necessary
        if sr != SAMPLE_RATE:
            import librosa

            audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

        # Convert to mono if stereo
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        return audio.astype(np.float32)

    async def _generate_with_vllm(
        self,
        text: str,
        ref_audio: Optional[np.ndarray] = None,
        ref_text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate audio using vLLM engine."""
        from vllm import SamplingParams

        # Prepare prompt based on whether we have reference audio
        if ref_audio is not None and ref_text:
            # Voice cloning mode
            prompt = f"<|VOICE_CLONE|>{ref_text}<|SYNTHESIZE|>{text}"
            # Note: vLLM handling of audio input may vary by model
        else:
            # Default voice mode
            prompt = f"<|SYNTHESIZE|>{text}"

        sampling_params = SamplingParams(
            temperature=0.7,
            max_tokens=4096,
        )

        outputs = self._vllm_engine.generate(prompt, sampling_params)

        # Extract audio from model output
        # The exact format depends on Qwen3-TTS output structure
        if outputs and len(outputs) > 0:
            output = outputs[0]
            if hasattr(output, "audio"):
                return np.array(output.audio, dtype=np.float32)
            elif hasattr(output, "outputs") and len(output.outputs) > 0:
                # Try to parse audio tokens
                return self._tokens_to_audio(output.outputs[0].token_ids)

        raise RuntimeError("Failed to extract audio from model output")

    async def _generate_with_transformers(
        self,
        text: str,
        ref_audio: Optional[np.ndarray] = None,
        ref_text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate audio using transformers model."""
        import torch

        # Prepare inputs
        if ref_audio is not None and ref_text:
            # Voice cloning mode
            inputs = self._processor(
                text=text,
                audio=ref_audio,
                sampling_rate=SAMPLE_RATE,
                voice_prompt=ref_text,
                return_tensors="pt",
            )
        else:
            # Default voice mode
            inputs = self._processor(
                text=text,
                return_tensors="pt",
            )

        # Move to device
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}

        # Generate
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=4096,
                do_sample=True,
                temperature=0.7,
            )

        # Decode audio
        audio = self._processor.decode(outputs[0])

        return np.array(audio, dtype=np.float32)

    def _tokens_to_audio(self, token_ids: list) -> np.ndarray:
        """Convert audio tokens to waveform."""
        # This is a placeholder - actual implementation depends on Qwen3-TTS tokenizer
        # The model may output audio codes that need to be decoded by a vocoder
        if self._processor:
            return np.array(self._processor.decode(token_ids), dtype=np.float32)
        raise NotImplementedError("Audio token decoding not implemented for vLLM mode")

    def _array_to_wav(self, audio: np.ndarray) -> bytes:
        """Convert numpy audio array to WAV bytes."""
        import soundfile as sf

        buffer = io.BytesIO()
        sf.write(buffer, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        buffer.seek(0)
        return buffer.read()


# Singleton instance
_tts_service: Optional[TTSService] = None


async def get_tts_service() -> TTSService:
    """Get or create the TTS service singleton."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
        await _tts_service.initialize()
    return _tts_service
