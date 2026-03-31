"""
speech_recognizer.py - Whisper-Based Hindi Speech Recognition Module
======================================================================
Handles two responsibilities:
  1. AUDIO CAPTURE   -- Record microphone input via PyAudio
  2. TRANSCRIPTION   -- Convert audio to text via OpenAI Whisper

Pipeline:
  Microphone -> PyAudio -> WAV File (16kHz mono) -> Whisper -> Text

WHY WHISPER:
  - Runs fully OFFLINE (no internet required, critical for embedded systems)
  - Native Hindi support (trained on 680,000 hours of multilingual audio)
  - Free and open-source (no API cost, no rate limits)
  - Audio stays on device (privacy for IoT applications)
  - Handles accents, background noise, and Hindi-English code-switching

Alternatives considered:
  Google Speech API  -> requires internet, paid, no offline support
  CMU Sphinx         -> open source but very poor Hindi accuracy
  DeepSpeech         -> Mozilla model, limited Hindi language support
"""

import os
import wave
import logging
import time

import numpy as np
import pyaudio
import whisper

# Import config values from the same src/ directory
from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_LANGUAGE,
    WHISPER_TASK,
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    AUDIO_CHUNK_SIZE,
    AUDIO_RECORD_SECONDS,
    AUDIO_TEMP_FILE,
)

# Module-level logger (follows Python logging best practice)
# Each module gets its own logger named after the module
logger = logging.getLogger(__name__)


class MicrophoneNotFoundError(RuntimeError):
    """
    Raised when no microphone input device is available.
    Separate exception type so callers can catch it specifically
    and offer a fallback (e.g. text mode) instead of crashing.
    """
    pass


class SpeechRecognizer:
    """
    Encapsulates all speech recognition functionality.

    This is the SENSING layer of the Sense -> Process -> Actuate pipeline.
    It handles audio capture and transcription. It does not contain any
    command matching or hardware control logic (Encapsulation / SRP).

    Usage:
        recognizer = SpeechRecognizer()           # Load model once
        text = recognizer.listen_and_transcribe()  # Call in a loop
        recognizer.cleanup()                       # Free resources when done
    """

    def __init__(self):
        """
        Load the Whisper model into memory and initialize PyAudio.

        NOTE: Whisper model loading takes 3-10 seconds depending on
        hardware. We do it ONCE at startup, not every time we listen.
        This is called "lazy initialization" — load heavy resources
        once, reuse them many times. Critical for performance.
        """
        logger.info(f"Initializing SpeechRecognizer (Whisper model: '{WHISPER_MODEL_SIZE}')")
        print(f"\n[INIT] Loading Whisper '{WHISPER_MODEL_SIZE}' model...")
        print(f"[INIT] First run will download model (~145MB for 'base'). Please wait...")

        # Load the Whisper model
        # whisper.load_model() downloads the model on first run,
        # then caches it at ~/.cache/whisper/ for future runs
        self.model = whisper.load_model(WHISPER_MODEL_SIZE)

        # Initialize PyAudio — the Python wrapper for PortAudio
        # PortAudio is a cross-platform audio I/O library
        self.audio_interface = pyaudio.PyAudio()

        # ── MICROPHONE AVAILABILITY CHECK ──────────────────────────
        # Check ONCE at init time whether a microphone is available.
        # This prevents the main loop from spinning in an error cycle
        # when no mic is connected.
        self._verify_microphone()

        # Store config values as instance variables for easy access
        self.sample_rate     = AUDIO_SAMPLE_RATE
        self.channels        = AUDIO_CHANNELS
        self.chunk_size      = AUDIO_CHUNK_SIZE
        self.record_seconds  = AUDIO_RECORD_SECONDS
        self.temp_file       = AUDIO_TEMP_FILE

        logger.info("SpeechRecognizer initialized successfully")
        print("[INIT] ✓ Whisper model loaded and ready!")

    # ──────────────────────────────────────────────────────────────
    # MICROPHONE CHECK
    # ──────────────────────────────────────────────────────────────

    def _verify_microphone(self):
        """
        Verify a working microphone input device exists.
        Raises MicrophoneNotFoundError immediately if none found.
        Called once at __init__ time — not on every recording attempt.
        """
        try:
            default = self.audio_interface.get_default_input_device_info()
            logger.info(f"Microphone found: [{default['index']}] {default['name']}")
            print(f"[AUDIO] ✓ Microphone: [{default['index']}] {default['name']}")
        except OSError:
            # No default input device — list what IS available
            available = []
            for i in range(self.audio_interface.get_device_count()):
                d = self.audio_interface.get_device_info_by_index(i)
                if d['maxInputChannels'] > 0:
                    available.append(f"  [{i}] {d['name']}")

            self.audio_interface.terminate()
            msg = (
                "No microphone (input device) found on this system.\n"
                "  → Connect a USB/3.5mm microphone and try again.\n"
                "  → Or run in TEXT MODE: python simulation/simulate.py --text"
            )
            if available:
                msg += "\n\nInput devices found but none set as default:\n" + "\n".join(available)
                msg += "\n  → Go to Windows Sound Settings → Input → set a Default Device."
            raise MicrophoneNotFoundError(msg)

    # ──────────────────────────────────────────────────────────────
    # AUDIO RECORDING
    # ──────────────────────────────────────────────────────────────

    def record_audio(self) -> str:
        """
        Record audio from microphone and save as a WAV file.

        HOW PYAUDIO WORKS (interview explanation):
          PyAudio opens a "stream" to the microphone.
          We read from this stream in chunks (1024 frames at a time).
          Each chunk is raw PCM audio data (16-bit integers).
          We collect all chunks, then write them to a WAV file.
          WAV format = uncompressed audio (PCM) with a header.

        WHY SAVE TO FILE? (not stream directly to Whisper)
          Whisper's API expects a file path or numpy array.
          Saving to a WAV file is simpler and more reliable.
          The file is deleted immediately after transcription.

        Returns:
            str: Absolute path to the saved WAV file.
        """
        print(f"\n[🎤 LISTENING] Speak now... ({self.record_seconds} seconds)")
        logger.info(f"Starting audio recording ({self.record_seconds}s at {self.sample_rate}Hz)")

        # Open audio input stream
        # format=paInt16 → 16-bit integer PCM (standard for speech)
        # channels=1     → Mono (left channel only, no stereo needed)
        # rate=16000     → 16kHz (Whisper's expected sample rate)
        # input=True     → We are READING from mic (not writing/playing)
        # frames_per_buffer=1024 → Read 1024 samples per read() call
        stream = self.audio_interface.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
        )

        frames = []  # Will hold all recorded audio chunks

        # Calculate how many chunks we need to record the desired duration
        # Formula: (samples/second) / (samples/chunk) × seconds = chunks
        # Example: (16000 / 1024) × 4 ≈ 62 chunks
        total_chunks = int((self.sample_rate / self.chunk_size) * self.record_seconds)

        for i in range(total_chunks):
            # Read one chunk of raw audio from microphone
            # exception_on_overflow=False → don't crash if buffer fills up
            data = stream.read(self.chunk_size, exception_on_overflow=False)
            frames.append(data)

            # Show a live progress bar in the terminal
            progress   = int((i / total_chunks) * 30)
            remaining  = 30 - progress
            time_left  = round(self.record_seconds - (i / total_chunks) * self.record_seconds, 1)
            print(f"\r  [{'█' * progress}{'░' * remaining}] {time_left}s remaining", end="", flush=True)

        print(f"\r  [{'█' * 30}] Done!                    ")  # Complete the bar
        print("[✓] Recording complete!")

        # Stop and close the audio stream to free microphone resource
        stream.stop_stream()
        stream.close()

        # Write all collected audio frames to a WAV file
        # WAV header contains: channels, sample width, frame rate
        # WAV body contains: raw PCM audio data (frames joined)
        with wave.open(self.temp_file, "wb") as wf:
            wf.setnchannels(self.channels)
            # get_sample_size returns bytes per sample for paInt16 = 2 bytes
            wf.setsampwidth(self.audio_interface.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))  # Join all chunks into one bytestring

        logger.info(f"Audio saved to: {self.temp_file}")
        return self.temp_file

    # ──────────────────────────────────────────────────────────────
    # WHISPER TRANSCRIPTION
    # ──────────────────────────────────────────────────────────────

    def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribe a WAV file to text using the Whisper model.

        HOW WHISPER WORKS INTERNALLY:
          Step 1: Audio -> Mel Spectrogram
            A mel spectrogram is a 2D frequency-time representation of audio.
            Whisper converts raw audio into this format before processing.

          Step 2: Spectrogram -> Transformer Encoder
            Whisper uses a Transformer neural network (same architecture as GPT).
            The encoder reads the spectrogram and builds a rich audio representation.

          Step 3: Transformer Decoder -> Text Tokens
            The decoder generates text tokens autoregressively (one at a time),
            using the encoder output and previously generated tokens.

          Step 4: Tokens -> Final Text
            Tokens are decoded using Whisper's vocabulary into the final string.

        Args:
            audio_file_path (str): Path to the WAV file to transcribe.

        Returns:
            str: Transcribed text (in Hindi or mixed Hindi/English).
        """
        if not os.path.exists(audio_file_path):
            logger.error(f"Audio file not found: {audio_file_path}")
            return ""

        print("[🧠 PROCESSING] Transcribing with Whisper...")
        logger.info(f"Transcribing: {audio_file_path}")

        start_time = time.time()

        # Run Whisper transcription
        # language="hi"     → Tell Whisper to expect Hindi (improves accuracy)
        # task="transcribe" → Output in original language
        # fp16=False        → Use 32-bit float math
        #                     fp16 (half precision) needs GPU support.
        #                     Raspberry Pi is CPU-only, so we must use fp16=False.
        #                     On a machine with GPU, set fp16=True for 2x speed.
        result = self.model.transcribe(
            audio_file_path,
            language=WHISPER_LANGUAGE,
            task=WHISPER_TASK,
            fp16=False,
        )

        elapsed = round(time.time() - start_time, 2)

        # result is a dict: {"text": "...", "segments": [...], "language": "hi"}
        transcribed_text = result["text"].strip()
        detected_language = result.get("language", "unknown")

        logger.info(f"Transcription: '{transcribed_text}' | Lang: {detected_language} | Time: {elapsed}s")
        print(f"[📝 TRANSCRIPT] \"{transcribed_text}\"  (lang={detected_language}, time={elapsed}s)")

        # Delete the temp WAV file to save disk space
        # Embedded systems often have small storage (SD card on RPi)
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)
            logger.debug(f"Temp file deleted: {audio_file_path}")

        return transcribed_text

    # ──────────────────────────────────────────────────────────────
    # CONVENIENCE METHOD
    # ──────────────────────────────────────────────────────────────

    def listen_and_transcribe(self) -> str:
        """
        One-call convenience method: record audio AND transcribe it.
        This is the only method called from main.py in the main loop.

        This is a FACADE pattern — it hides the two-step process
        (record → transcribe) behind a single clean method call.
        main.py doesn't need to know about WAV files at all.

        Returns:
            str: Transcribed text, or "" if nothing was heard.
        """
        try:
            audio_path       = self.record_audio()
            transcribed_text = self.transcribe(audio_path)
            return transcribed_text
        except OSError as e:
            # Microphone not found or PyAudio error
            logger.error(f"Audio recording failed: {e}")
            print(f"[ERROR] Microphone error: {e}")
            print("[TIP]  Check microphone is connected and not in use by another app.")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error during transcription: {e}")
            print(f"[ERROR] Transcription failed: {e}")
            return ""

    # ──────────────────────────────────────────────────────────────
    # RESOURCE CLEANUP
    # ──────────────────────────────────────────────────────────────

    def cleanup(self):
        """
        Release all audio resources held by PyAudio.

        Audio I/O resources on embedded systems are shared and limited.
        Failing to release them can leave the microphone locked for other
        processes, especially on Raspberry Pi with PortAudio.
        """
        self.audio_interface.terminate()
        logger.info("PyAudio resources released cleanly")
        print("[CLEANUP] ✓ Audio interface released")
