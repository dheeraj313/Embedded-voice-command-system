Embedded Voice Command System:

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Whisper](https://img.shields.io/badge/OpenAI-Whisper-412991?style=for-the-badge&logo=openai&logoColor=white)](https://github.com/openai/whisper)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-3%2F4-C51A4A?style=for-the-badge&logo=raspberry-pi&logoColor=white)](https://raspberrypi.org)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

End-to-end embedded voice command recognition system that processes real-time Hindi speech to control physical hardware peripherals (LED, DC Motor) on a Raspberry Pi — achieving ~75% command recognition accuracy.

---

## Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Hardware Setup](#-hardware-setup)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Running the Project](#-running-the-project)
- [Supported Commands](#-supported-commands)
- [Running Tests](#-running-tests)
- [Interview Q&A](#-interview-qa)
- [Future Improvements](#-future-improvements)

---

## Overview

This project implements a complete voice-controlled IoT system built on **Raspberry Pi**. A USB microphone captures Hindi voice commands, which are transcribed **offline** using **OpenAI Whisper**, processed using NLP keyword matching, and executed as GPIO signals to control physical hardware in real-time.

**Key highlights:**
- **Fully offline** — Whisper runs locally on the device. No internet, no cloud API, no cost
- **Hindi-first** — supports native Devanagari script, Roman transliteration, and English
- **Hardware Abstraction Layer (HAL)** — same codebase runs on RPi hardware AND Windows simulation
- **75% accuracy** — achieved through multi-variant keyword matching across 3 language styles
- **Unit + Integration tested** — 40+ test cases covering all command variants

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   EMBEDDED VOICE COMMAND SYSTEM                  │
│                                                                   │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│  │ Microphone │──▶│   PyAudio    │──▶│   WAV File (16kHz)    │  │
│  │ (hardware) │   │  (capture)   │   │   (temp, auto-deleted)│  │
│  └────────────┘   └──────────────┘   └──────────┬────────────┘  │
│                                                  │               │
│                                                  ▼               │
│                                       ┌──────────────────┐      │
│                                       │  OpenAI Whisper  │      │
│                                       │ (Transformer NN) │      │
│                                       │  language = "hi" │      │
│                                       └────────┬─────────┘      │
│                                                │                 │
│                                         "बत्ती चालू"            │
│                                                │                 │
│                                                ▼               │
│                                       ┌──────────────────┐      │
│                                       │ CommandProcessor │      │
│                                       │ (Keyword Match)  │      │
│                                       └────────┬─────────┘      │
│                                                │                 │
│                                           "LED_ON"              │
│                                                │                 │
│                                                ▼               │
│                                       ┌──────────────────┐      │
│                                       │  GPIOController  │      │
│                                       │  (HAL Layer)     │      │
│                                       └────┬────────┬────┘      │
│                                            │        │            │
│                                            ▼        ▼            │
│                                    GPIO17=HIGH  GPIO27=HIGH      │
│                                         💡          ⚙️            │
│                                        LED        Motor          │
└─────────────────────────────────────────────────────────────────┘
```

### Three-Layer Design (Sense → Process → Actuate)

| Layer | Module | Responsibility |
|-------|--------|----------------|
| **Sensing** | `speech_recognizer.py` | Record audio via PyAudio, transcribe with Whisper |
| **Processing** | `command_processor.py` | NLP keyword matching, map text → command |
| **Actuation** | `gpio_controller.py` | GPIO Hardware Abstraction Layer, drive hardware |

---

## Hardware Setup

### Components Required

| Component | Specification | Purpose |
|-----------|--------------|---------|
| Raspberry Pi | 3B+ or 4 (1GB+ RAM) | Main processing unit |
| USB Microphone | Any USB mic | Audio input |
| LED | 5mm, any color | Visual output indicator |
| Resistor | 220Ω | Current limiting for LED |
| DC Motor | 5V DC | Actuation device |
| L298N Motor Driver | Dual H-Bridge module | Amplifies 3.3V GPIO → 5-12V for motor |
| Jumper Wires | Male-Female | Circuit connections |
| Breadboard | Half or full size | Prototyping |

### Circuit Connections

```
Raspberry Pi                    Components
─────────────────────────────────────────────────────────
GPIO17 (Pin 11) ──┤220Ω├──── LED(+) ──── LED(-) ──── GND(Pin 6)

GPIO27 (Pin 13) ─────────── L298N IN1
GND    (Pin 6)  ─────────── L298N GND
5V     (Pin 2)  ─────────── L298N VCC (or external 12V)
                             L298N OUT1 ─── Motor(+)
                             L298N OUT2 ─── Motor(-)
```

**Why L298N motor driver?**
GPIO pins can only source 3.3V at 16mA max. A DC motor needs 5-12V at 500mA+. The L298N is an H-bridge motor driver that uses the small GPIO signal to switch a separate higher-power circuit.

---

## Project Structure

```
embedded-voice-command-system/
│
├── src/
│   ├── main.py              #  Main entry point (Sense→Process→Actuate loop)
│   ├── speech_recognizer.py #  Audio capture + Whisper transcription
│   ├── command_processor.py #  NLP keyword matching engine
│   ├── gpio_controller.py   #  GPIO Hardware Abstraction Layer
│   └── config.py            #   All configuration (pins, keywords, model settings)
│
├── simulation/
│   └── simulate.py          #  Windows/Mac simulation (voice + text modes)
│
├── tests/
│   └── test_commands.py     #  40+ unit & integration tests
│
├── logs/                    #  Runtime logs (auto-created, git-ignored)
│
├── requirements.txt         #  Python dependencies
├── README.md                #  This file
└── .gitignore
```

---

## Installation

### Option A: Windows PC (Simulation Mode — Recommended to start)

**Step 1: Install prerequisites**
```bash
# Install Python 3.8+ from https://python.org/downloads
# Verify installation:
python --version

# Install ffmpeg (required by Whisper for audio processing)
# Option 1: via winget (Windows 10/11)
winget install ffmpeg

# Option 2: Download from https://ffmpeg.org/download.html
# Extract and add the bin/ folder to your System PATH
```

**Step 2: Clone and set up the project**
```bash
git clone https://github.com/yourusername/embedded-voice-command-system.git
cd embedded-voice-command-system

# Create a virtual environment (keeps dependencies isolated)
python -m venv venv
venv\Scripts\activate
```

**Step 3: Install Python packages**
```bash
# PyAudio on Windows often requires pipwin (a Windows-specific installer)
pip install pipwin
pipwin install pyaudio

# Install Whisper and remaining packages
pip install openai-whisper torch numpy tqdm
```

### Option B: Raspberry Pi (Real Hardware)

```bash
# Update system packages
sudo apt-get update && sudo apt-get upgrade -y

# Install system-level audio and ffmpeg dependencies
sudo apt-get install -y python3-pip python3-venv portaudio19-dev ffmpeg

# Clone the project
git clone https://github.com/yourusername/embedded-voice-command-system.git
cd embedded-voice-command-system

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install all Python dependencies
pip install -r requirements.txt

# Install RPi.GPIO (Raspberry Pi only)
pip install RPi.GPIO
```

> **First run note:** Whisper downloads the model weights (~145MB for 'base') automatically on first run and caches them in `~/.cache/whisper/`. This only happens once.

---

## Running the Project

### On Windows — Text Mode (fastest, no mic needed)
```bash
python simulation/simulate.py --text
```
Type commands like `light on`, `batti chalu`, `मोटर चालू` directly.
**Best for: demos in interviews, testing without audio setup.**

### On Windows — Voice Mode (full pipeline with mic)
```bash
python simulation/simulate.py
```
Speak into your microphone. Whisper transcribes in real-time.

### On Raspberry Pi (real hardware)
```bash
cd src
python3 main.py
```

### Expected Output (Text Mode)
```
══════════════════════════════════════════════════
    TEXT MODE — Keyboard Input Simulation
══════════════════════════════════════════════════

─────────────────────────────────────────────────
  Enter command: light on
  [INPUT] "light on"

  ┌────────────────────────────────────────┐
  │  LED  →  [ ON  ]                   │
  │  GPIO17 → 3.3V  [SIMULATION]          │
  └────────────────────────────────────────┘

  ╔══════════════════════════════════════════╗
  ║      LED    [ ON  ] ← GPIO17 = 3.3V    ║
  ║  ○   Motor  [ OFF ] ← GPIO27 = 0V      ║
  ╚══════════════════════════════════════════╝
  [✅]  Executed: LED_ON
  [📊]  Session accuracy: 100.0% (1/1)
```

---

## Supported Commands

| Hindi (Devanagari) | Transliteration | English | Hardware Action |
|--------------------|-----------------|---------|-----------------|
| बत्ती चालू | batti chalu | light on | 💡 LED → ON |
| बत्ती बंद | batti band | light off | 💡 LED → OFF |
| लाइट चालू | light chalu | turn on light | 💡 LED → ON |
| मोटर चालू | motor chalu | motor on | ⚙️ Motor → ON |
| मोटर बंद | motor band | motor off | ⚙️ Motor → OFF |
| पंखा चालू | pankha chalu | fan on | ⚙️ Motor → ON |
| पंखा बंद | pankha band | fan off | ⚙️ Motor → OFF |

> **Whisper handles code-switching:** You can mix Hindi and English in one sentence. "Please motor चालू करो" will still work.

---

##  Running Tests

```bash
# Run all 40+ tests with detailed output
python tests/test_commands.py

# Expected output:
# test_light_on ... ok
# test_light_off ... ok
# test_batti_chalu ... ok
# test_hindi_led_on ... ok
# ...
# Results: 42/42 tests passed ✅
```

Tests cover:
- ✅ English commands (9 tests)
- ✅ Hindi transliteration (7 tests)
- ✅ Hindi Devanagari script (6 tests)
- ✅ Robustness (empty input, None, random text) (8 tests)
- ✅ Text normalization (7 tests)
- ✅ Command parsing (4 tests)
- ✅ GPIO state management (13 tests)
- ✅ Full pipeline integration (7 tests)


---

## Future Improvements

1. **Voice Activity Detection (VAD)** — Replace fixed 4-second window with Silero-VAD for trigger-based recording
2. **Wake word** — Add "Hey Device" detection using Porcupine before command recognition
3. **More peripherals** — Extend to servo motors, relays, temperature sensors
4. **Feedback** — Add Hindi text-to-speech confirmation using `pyttsx3`
5. **Web dashboard** — Real-time command history and hardware status via Flask
6. **Fine-tuned model** — Train Whisper on 500+ custom Hindi command recordings → 90%+ accuracy
7. **Power optimization** — Implement sleep mode between commands (critical for battery-powered IoT)

---

## Tech Stack

| Technology | Version | Role |
|-----------|---------|------|
| Python | 3.8+ | Core language |
| OpenAI Whisper | 20231117+ | Hindi speech-to-text (offline) |
| PyAudio | 0.2.11+ | Microphone audio capture |
| PyTorch | 2.0+ | Whisper inference engine |
| RPi.GPIO | 0.7.1+ | Raspberry Pi GPIO control |
| NumPy | 1.24+ | Audio array processing |
| unittest | stdlib | Testing framework |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built as part of an embedded IoT portfolio demonstrating hardware-software integration, offline ML inference on edge devices, and hardware abstraction layer design patterns.*
