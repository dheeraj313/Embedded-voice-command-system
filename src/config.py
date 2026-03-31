"""
config.py - Central Configuration File
=======================================
All project settings live here in one place.

Follows Single Responsibility Principle: this module has one job —
store configuration. All hardware pins, model settings, keywords,
and file paths are defined here so changing any setting only
requires editing this one file.
"""

import os

# ─────────────────────────────────────────────────────────────
# PATH SETUP
# ─────────────────────────────────────────────────────────────
# __file__ = absolute path of this config.py file
# _SRC_DIR  = the src/ folder this file lives in
# _PROJECT_ROOT = the project root (one level above src/)
_SRC_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)

# ─────────────────────────────────────────────────────────────
# WHISPER MODEL SETTINGS
# ─────────────────────────────────────────────────────────────
# OpenAI Whisper is a multilingual speech recognition model.
# It runs LOCALLY on the device - no internet needed.
# This is critical for embedded systems (RPi may not have internet).
#
# Model size comparison:
#   tiny   →  39 MB  → fastest,  lowest accuracy
#   base   →  74 MB  → fast,     good accuracy  ← BEST FOR RPi 3/4
#   small  → 244 MB  → moderate, better accuracy ← GOOD FOR PC
#   medium → 769 MB  → slow,     high accuracy
#   large  → 1.5 GB  → very slow, highest accuracy
#
# For Raspberry Pi 3 (1GB RAM): use "base"
# For Raspberry Pi 4 (2-4GB RAM): can use "small"
# For Windows PC (development): use "small" for better accuracy
WHISPER_MODEL_SIZE = "base"

# Language code for Hindi (ISO 639-1 standard)
# Setting this explicitly improves accuracy vs auto-detection.
# Other examples: "en" = English, "es" = Spanish, "zh" = Chinese
WHISPER_LANGUAGE = "hi"

# "transcribe" = keep output in original language (Hindi text output)
# "translate"  = convert to English (useful for multilingual apps)
# We use "transcribe" because our keyword list includes Hindi script
WHISPER_TASK = "transcribe"

# ─────────────────────────────────────────────────────────────
# AUDIO RECORDING SETTINGS
# ─────────────────────────────────────────────────────────────
# WHY 16000 Hz sample rate?
# Whisper was trained on 16kHz audio. Using any other rate would
# require resampling and reduce accuracy. 16kHz captures all
# frequencies important for speech (human voice: 85Hz - 8000Hz).
AUDIO_SAMPLE_RATE = 16000   # 16,000 samples per second (16 kHz)
AUDIO_CHANNELS    = 1       # Mono (1 channel) - speech doesn't need stereo
AUDIO_CHUNK_SIZE  = 1024    # Read 1024 audio frames per buffer read
AUDIO_RECORD_SECONDS = 4    # Listen for 4 seconds per voice command
                             # Adjust: shorter = more responsive, longer = more accurate

# ─────────────────────────────────────────────────────────────
# GPIO PIN CONFIGURATION
# ─────────────────────────────────────────────────────────────
# BCM numbering: uses Broadcom chip GPIO numbers (GPIO17, GPIO27).
# Alternative is BOARD (physical pin position), but BCM is preferred
# because the numbers stay consistent across all Raspberry Pi models.
#
# CIRCUIT CONNECTION:
#   LED:   GPIO17 → 220Ω resistor → LED(+) → LED(-) → GND
#   Motor: GPIO27 → L298N(IN1) → Motor
#          (L298N motor driver needed because GPIO max is 3.3V/16mA,
#           but a DC motor needs 5-12V/500mA+)
LED_PIN   = 17   # BCM GPIO17 = Physical Pin 11
MOTOR_PIN = 27   # BCM GPIO27 = Physical Pin 13

# ─────────────────────────────────────────────────────────────
# VOICE COMMAND → KEYWORD MAPPING
# ─────────────────────────────────────────────────────────────
# Each command maps to multiple trigger phrases covering three output styles
# that Whisper may produce for the same Hindi speech:
#   - Devanagari script  (बत्ती चालू)  — native Hindi output
#   - Roman transliteration (batti chalu) — Whisper sometimes romanizes
#   - English equivalent (light on)       — fallback for mixed speech
# Covering all three variants is what achieves ~75% recognition accuracy.
#
# The CommandProcessor searches for ANY matching phrase as a substring
# in the Whisper transcription.
COMMAND_KEYWORDS = {

    # ── LED ON ──────────────────────────────────────────────
    "LED_ON": [
        # Hindi Devanagari script (Whisper outputs this for Hindi speech)
        "बत्ती चालू",        # batti chalu  (common Hindi for "light on")
        "लाइट चालू",         # light chalu
        "रोशनी चालू",        # roshni chalu  (roshni = light/brightness)
        "बल्ब चालू",          # bulb chalu
        # Roman transliteration (Whisper sometimes outputs Romanized Hindi)
        "batti chalu",
        "batti on",
        "light chalu",
        "bati chalu",        # common spelling variant
        "roshni chalu",
        # English (fallback for English speakers or mixed speech)
        "light on",
        "led on",
        "bulb on",
        "lamp on",
        "turn on light",
        "switch on light",
        "turn light on",
    ],

    # ── LED OFF ─────────────────────────────────────────────
    "LED_OFF": [
        "बत्ती बंद",
        "लाइट बंद",
        "रोशनी बंद",
        "बल्ब बंद",
        "batti band",
        "batti off",
        "light band",
        "bati band",
        "roshni band",
        "light off",
        "led off",
        "bulb off",
        "lamp off",
        "turn off light",
        "switch off light",
        "turn light off",
    ],

    # ── MOTOR ON ────────────────────────────────────────────
    "MOTOR_ON": [
        "मोटर चालू",
        "पंखा चालू",         # pankha = fan
        "मोटर स्टार्ट",
        "motor chalu",
        "motor on",
        "motor start",
        "fan on",
        "fan start",
        "pankha on",
        "pankha chalu",
        "start motor",
        "turn on motor",
        "turn on fan",
    ],

    # ── MOTOR OFF ───────────────────────────────────────────
    "MOTOR_OFF": [
        "मोटर बंद",
        "पंखा बंद",
        "मोटर बंद करो",
        "motor band",
        "motor off",
        "motor stop",
        "fan off",
        "fan stop",
        "pankha off",
        "pankha band",
        "stop motor",
        "turn off motor",
        "turn off fan",
    ],
}

# ─────────────────────────────────────────────────────────────
# COMMAND MATCHING SETTINGS
# ─────────────────────────────────────────────────────────────
# Minimum match score (0.0 to 1.0) required to accept a command.
# 0.3 = at least 30% keyword overlap → low threshold = more permissive
# 0.6 = at least 60% keyword overlap → high threshold = more strict
# We use 0.3 because substring matching already filters most noise.
MATCH_CONFIDENCE_THRESHOLD = 0.3

# ─────────────────────────────────────────────────────────────
# FILE PATHS
# ─────────────────────────────────────────────────────────────
# Temporary WAV file for storing recorded audio before passing to Whisper.
# Whisper needs a file path, not a raw audio stream.
# This file is created and deleted automatically on every voice command.
AUDIO_TEMP_FILE = os.path.join(_PROJECT_ROOT, "temp_audio.wav")

# Log file location (logs/ directory in project root)
LOG_FILE  = os.path.join(_PROJECT_ROOT, "logs", "voice_command.log")
LOG_LEVEL = "INFO"  # Options: DEBUG, INFO, WARNING, ERROR

# ─────────────────────────────────────────────────────────────
# DISPLAY LABELS (used in console output)
# ─────────────────────────────────────────────────────────────
HARDWARE_LABELS = {
    "LED":   "💡  LED   (GPIO Pin 17)",
    "MOTOR": "⚙️   Motor (GPIO Pin 27)",
}
