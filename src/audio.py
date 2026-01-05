"""Audio capture with voice activity detection."""

from collections.abc import Callable

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Hz, what Whisper expects
CHUNK_SIZE = 1024    # samples per chunk (~64ms at 16kHz)
CHANNELS = 1         # mono

# VAD parameters
ENERGY_THRESHOLD = 0.01      # RMS threshold for speech detection
SILENCE_DURATION = 2.0       # seconds of silence to end utterance
MIN_SPEECH_DURATION = 0.3    # minimum seconds of speech to count as valid


def calculate_rms(audio_chunk: np.ndarray) -> float:
    """Calculate root mean square energy of audio chunk."""
    return float(np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2)))


class AudioCapture:
    """Captures audio from microphone with voice activity detection."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        chunk_size: int = CHUNK_SIZE,
        energy_threshold: float = ENERGY_THRESHOLD,
        silence_duration: float = SILENCE_DURATION,
        min_speech_duration: float = MIN_SPEECH_DURATION,
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.energy_threshold = energy_threshold
        self.silence_duration = silence_duration
        self.min_speech_duration = min_speech_duration

        # Calculate chunk counts for duration thresholds
        chunk_duration = chunk_size / sample_rate
        self.silence_chunks = int(silence_duration / chunk_duration)
        self.min_speech_chunks = int(min_speech_duration / chunk_duration)

    def listen(
        self,
        should_stop: Callable[[], bool] | None = None,
        on_speech_start: Callable[[], None] | None = None,
    ) -> np.ndarray | None:
        """
        Listen for speech and return audio buffer when utterance ends.

        Blocks until speech is detected and then silence follows.
        Returns None if no valid speech detected (too short) or if stopped.

        Args:
            should_stop: Optional callback that returns True to abort listening
            on_speech_start: Optional callback called when speech first detected
        """
        audio_buffer = []
        silence_count = 0
        speech_count = 0
        is_speaking = False
        check_interval = 10  # Check should_stop every N chunks

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=np.float32,
            blocksize=self.chunk_size,
        ) as stream:
            chunk_count = 0
            while True:
                chunk, _ = stream.read(self.chunk_size)
                chunk = chunk.flatten()
                chunk_count += 1

                # Periodically check if we should stop
                if should_stop and chunk_count % check_interval == 0:
                    if should_stop():
                        return None

                rms = calculate_rms(chunk)
                is_speech = rms > self.energy_threshold

                if is_speech:
                    silence_count = 0
                    speech_count += 1
                    if not is_speaking:
                        is_speaking = True
                        if on_speech_start:
                            on_speech_start()
                    audio_buffer.append(chunk)
                elif is_speaking:
                    # Still collecting during silence after speech
                    silence_count += 1
                    audio_buffer.append(chunk)

                    if silence_count >= self.silence_chunks:
                        # Silence threshold reached, end utterance
                        break

        # Check if we got enough speech
        if speech_count < self.min_speech_chunks:
            return None

        # Concatenate and return audio
        return np.concatenate(audio_buffer)


def list_audio_devices() -> None:
    """List available audio input devices."""
    print(sd.query_devices())
