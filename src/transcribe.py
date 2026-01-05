"""Speech-to-text transcription using Whisper."""

import sys

import numpy as np
from faster_whisper import WhisperModel

DEFAULT_MODEL = "small"  # Good balance of speed and accuracy for GTX 1060


class Transcriber:
    """Transcribes audio to text using Whisper."""

    def __init__(self, model_size: str = DEFAULT_MODEL, device: str = "auto"):
        """
        Initialize the transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3)
            device: "cuda", "cpu", or "auto" (auto-detect)
        """
        # Force CPU - CUDA requires cuDNN 9.x which isn't available
        if device == "auto":
            device = "cpu"

        print(f"Loading Whisper model '{model_size}' on {device}...")
        try:
            self.model = WhisperModel(model_size, device=device, compute_type="int8")
        except Exception as e:
            print(
                f"Error: Failed to load speech model: {e}\n"
                "If first run, check your internet connection.",
                file=sys.stderr
            )
            sys.exit(1)
        print("Model loaded.")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcribe audio to text.

        Args:
            audio: Audio data as numpy array (float32, mono)
            sample_rate: Sample rate of the audio (default 16000)

        Returns:
            Transcribed text string
        """
        # faster-whisper expects float32 audio normalized to [-1, 1]
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Ensure audio is in valid range
        if np.max(np.abs(audio)) > 1.0:
            audio = audio / np.max(np.abs(audio))

        segments, _ = self.model.transcribe(
            audio,
            language="en",
            vad_filter=True,  # Filter out non-speech
        )

        # Collect all segment text
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        return " ".join(text_parts)
