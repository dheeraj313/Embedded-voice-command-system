"""
simulate.py - Windows/Mac Development Simulation
==================================================
Run this file on Windows or Mac when you do NOT have a Raspberry Pi.

WHAT THIS SIMULATES:
  + Real OpenAI Whisper speech recognition (full pipeline)
  + GPIO hardware states (shown as ASCII art in terminal)
  - Actual GPIO voltage changes (no real hardware)

This is a Software-in-the-Loop (SIL) simulation layer that decouples
the application software from the physical hardware. The same
business logic (command_processor, gpio_controller) runs unchanged
on both the Raspberry Pi and this simulation.

TWO MODES:
  Voice Mode (default):  Real microphone + Whisper + Simulated GPIO
  Text  Mode (--text):   Keyboard input + Simulated GPIO (no mic needed)

HOW TO RUN:
  python simulation/simulate.py           # Voice mode
  python simulation/simulate.py --text    # Text mode (no mic needed)
"""

import os
import sys
import time
import argparse
import logging

# ──────────────────────────────────────────────────────────────────────
# WINDOWS UTF-8 FIX
# ──────────────────────────────────────────────────────────────────────
# Windows terminal defaults to cp1252 encoding which can't render
# emoji characters (🎤 💡 ⚙️  etc). This forces stdout/stderr to UTF-8.
# Required for Python 3.13 on Windows when printing Unicode/emoji.
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────────
# PATH SETUP
# ──────────────────────────────────────────────────────────────────────
# simulation/simulate.py is one level BELOW the project root.
# We need to add src/ (which is at project_root/src/) to sys.path
# so we can import config, command_processor, and gpio_controller.
_SIMULATION_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT   = os.path.dirname(_SIMULATION_DIR)
_SRC_DIR        = os.path.join(_PROJECT_ROOT, "src")

sys.path.insert(0, _SRC_DIR)

# Now we can import from src/
from command_processor import CommandProcessor
from gpio_controller   import GPIOController

# Note: SpeechRecognizer is imported ONLY in voice mode
# (importing it triggers Whisper model loading — slow and unnecessary in text mode)

# Basic logging for simulation
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors in simulation
    format="%(levelname)s: %(message)s",
)


# ──────────────────────────────────────────────────────────────────────
# VISUAL HARDWARE DISPLAY
# ──────────────────────────────────────────────────────────────────────

class HardwareDisplay:
    """
    ASCII visualization of the simulated hardware state.
    Shows LED and Motor status in the terminal, mimicking what
    you would see on the actual Raspberry Pi hardware.

    This is what you show in a job interview demo on your laptop!
    """

    def __init__(self):
        self.led_on   = False
        self.motor_on = False

    def update(self, led_on: bool, motor_on: bool):
        """Update state and re-render the display."""
        self.led_on   = led_on
        self.motor_on = motor_on
        self._render()

    def _render(self):
        """Draw the hardware state as ASCII art."""
        # Icons change based on state
        led_icon    = "💡" if self.led_on   else "○ "
        motor_icon  = "⚙️ " if self.motor_on else "○ "
        led_state   = "[ ON  ] ← GPIO17 = 3.3V" if self.led_on   else "[ OFF ] ← GPIO17 = 0V  "
        motor_state = "[ ON  ] ← GPIO27 = 3.3V" if self.motor_on else "[ OFF ] ← GPIO27 = 0V  "

        print()
        print("  ╔══════════════════════════════════════════╗")
        print("  ║         RASPBERRY PI SIMULATION          ║")
        print("  ╠══════════════════════════════════════════╣")
        print(f"  ║  {led_icon}  LED    {led_state}  ║")
        print(f"  ║  {motor_icon}  Motor  {motor_state}  ║")
        print("  ╚══════════════════════════════════════════╝")


# ──────────────────────────────────────────────────────────────────────
# VOICE MODE
# ──────────────────────────────────────────────────────────────────────

def run_voice_mode():
    """
    Full pipeline simulation with real microphone and Whisper.

    Pipeline:
      Microphone → PyAudio → WAV → Whisper → text → CommandProcessor → GPIOController

    This tests the COMPLETE system end-to-end.
    The only simulated part is the GPIO hardware output.
    """
    # Import SpeechRecognizer here (not at top) to delay Whisper model loading
    from speech_recognizer import SpeechRecognizer, MicrophoneNotFoundError

    print("\n" + "═" * 55)
    print("  🎤  VOICE MODE — Full Pipeline Simulation")
    print("  Real Whisper recognition + Simulated GPIO")
    print("═" * 55)
    print("\n[INFO] Loading Whisper model... (first run downloads ~145MB)")

    # ── MICROPHONE CHECK BEFORE LOADING WHISPER ───────────────────
    # Check mic availability FIRST — no point loading the heavy
    # Whisper model (3-10 seconds) if there's no microphone.
    try:
        import pyaudio as _pa
        _p = _pa.PyAudio()
        _p.get_default_input_device_info()   # raises OSError if no mic
        _p.terminate()
    except OSError:
        print("\n" + "═" * 55)
        print("  ❌  NO MICROPHONE DETECTED")
        print("═" * 55)
        print("  Error: No default audio input device found on this system.")
        print()
        print("  Possible reasons:")
        print("    1. No microphone is physically connected")
        print("    2. Microphone is connected but not set as default")
        print("       → Fix: Windows Settings → System → Sound → Input")
        print("               → Choose your microphone as Default Device")
        print()
        print("  ─" * 27)
        print("  💡  AUTO-SWITCHING TO TEXT MODE")
        print("  You can type commands instead of speaking them.")
        print("  This tests the full command processing pipeline.")
        print("  ─" * 27)
        run_text_mode()
        return

    try:
        recognizer = SpeechRecognizer()
    except MicrophoneNotFoundError as e:
        print(f"\n  ❌  {e}")
        print("\n  💡  Switching to TEXT MODE automatically...\n")
        run_text_mode()
        return
    processor  = CommandProcessor()
    gpio       = GPIOController()
    display    = HardwareDisplay()

    # Show initial state (everything OFF)
    status = gpio.get_status()
    display.update(status["LED"] == "ON", status["MOTOR"] == "ON")

    print("\n  Commands to say:")
    print("  'light on' / 'batti chalu' / 'बत्ती चालू'")
    print("  'light off'/ 'batti band'  / 'बत्ती बंद'")
    print("  'motor on' / 'motor chalu' / 'मोटर चालू'")
    print("  'motor off'/ 'motor band'  / 'मोटर बंद'")
    print("\n  Press Ctrl+C to exit.\n")

    total      = 0
    successful = 0

    try:
        cycle = 0
        while True:
            cycle += 1
            print(f"\n{'─' * 55}")
            print(f"  [Cycle #{cycle}] Listening...")

            # SENSE: Record and transcribe
            transcribed = recognizer.listen_and_transcribe()
            total += 1

            if not transcribed:
                print("  [⚠️]  No speech detected.")
                continue

            # PROCESS: Match command
            command = processor.match_command(transcribed)

            if command:
                device, action = processor.get_device_and_action(command)
                gpio.execute_command(device, action)
                status = gpio.get_status()
                display.update(status["LED"] == "ON", status["MOTOR"] == "ON")
                print(f"  [✅]  Executed: {command}")
                successful += 1
            else:
                print(f'  [❌]  Not recognized: "{transcribed}"')

            # Live accuracy
            acc = successful / total * 100
            print(f"  [📊]  Session accuracy: {acc:.1f}% ({successful}/{total})")

    except KeyboardInterrupt:
        recognizer.cleanup()
        gpio.cleanup()
        acc = successful / total * 100 if total > 0 else 0
        print(f"\n\n  [FINAL] Accuracy: {acc:.1f}% ({successful}/{total})")
        print("  Simulation ended.")


# ──────────────────────────────────────────────────────────────────────
# TEXT MODE
# ──────────────────────────────────────────────────────────────────────

def run_text_mode():
    """
    Type commands as text instead of speaking them.

    USE THIS MODE TO:
      1. Test the CommandProcessor + GPIOController pipeline
         without needing a microphone or internet
      2. Demo the project in an interview without audio setup
      3. Quickly verify new keywords you add to config.py
      4. Run automated tests interactively

    WHAT THIS DOES NOT TEST:
      - Whisper model (not loaded in text mode)
      - PyAudio microphone input
      But it tests everything ELSE — the core logic.
    """
    print("\n" + "═" * 55)
    print("  ⌨️   TEXT MODE — Keyboard Input Simulation")
    print("  Tests: CommandProcessor + GPIO (no mic/Whisper needed)")
    print("═" * 55)
    print()
    print("  Type commands exactly as Whisper would transcribe them.")
    print()
    print("  Examples to try:")
    print("  ┌──────────────────────────────────────────┐")
    print("  │  light on          → LED turns ON         │")
    print("  │  light off         → LED turns OFF        │")
    print("  │  batti chalu       → LED turns ON (Hindi) │")
    print("  │  batti band        → LED turns OFF        │")
    print("  │  बत्ती चालू        → LED ON (Devanagari)  │")
    print("  │  motor on          → Motor starts         │")
    print("  │  motor off         → Motor stops          │")
    print("  │  मोटर चालू         → Motor ON (Hindi)     │")
    print("  │  please light on   → LED ON (extra words) │")
    print("  │  hello world       → Not recognized ✓     │")
    print("  └──────────────────────────────────────────┘")
    print()
    print("  Type 'status' to see hardware state.")
    print("  Type 'history' to see all commands this session.")
    print("  Type 'quit' or press Ctrl+C to exit.\n")

    processor = CommandProcessor()
    gpio      = GPIOController()
    display   = HardwareDisplay()

    # Show initial state
    status = gpio.get_status()
    display.update(status["LED"] == "ON", status["MOTOR"] == "ON")

    total      = 0
    successful = 0

    while True:
        try:
            print("─" * 55)
            raw_input = input("  🎤 Enter command: ").strip()

            # ── SPECIAL COMMANDS ──────────────────────────────────
            if not raw_input:
                continue

            if raw_input.lower() in ("quit", "exit", "q"):
                break

            if raw_input.lower() == "status":
                status = gpio.get_status()
                display.update(status["LED"] == "ON", status["MOTOR"] == "ON")
                continue

            if raw_input.lower() == "history":
                history = processor.get_history()
                print(f"\n  Command history ({len(history)} entries):")
                for i, h in enumerate(history, 1):
                    result = h["command"] or "NOT RECOGNIZED"
                    print(f"  {i:2}. \"{h['input']}\" → {result} (confidence: {h['confidence']})")
                continue

            # ── NORMAL COMMAND PROCESSING ─────────────────────────
            total += 1
            print(f"  [📝 INPUT] \"{raw_input}\"")

            # This is the same processing that happens with real Whisper output
            command = processor.match_command(raw_input)

            if command:
                device, action = processor.get_device_and_action(command)
                success        = gpio.execute_command(device, action)

                if success:
                    status = gpio.get_status()
                    display.update(status["LED"] == "ON", status["MOTOR"] == "ON")
                    print(f"  [✅]  Command executed: {command}")
                    successful += 1
                else:
                    print(f"  [❌]  Execution failed: {command}")
            else:
                print(f"  [❌]  Not recognized: \"{raw_input}\"")
                print("  [💡]  Hint: try 'light on', 'batti chalu', or 'मोटर चालू'")

            # Live accuracy stats
            acc = successful / total * 100
            print(f"  [📊]  Session accuracy: {acc:.1f}% ({successful}/{total})")

        except KeyboardInterrupt:
            break

    # Cleanup and final stats
    gpio.cleanup()
    acc = successful / total * 100 if total > 0 else 0
    print(f"\n  [FINAL STATS]")
    print(f"  Total attempts:  {total}")
    print(f"  Successful:      {successful}")
    print(f"  Accuracy:        {acc:.1f}%")
    print("\n  Simulation ended.")


# ──────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="simulate.py",
        description="Voice Command System — Windows/Mac Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulation/simulate.py            # Voice mode (real mic + Whisper)
  python simulation/simulate.py --text     # Text mode  (keyboard, no mic)
        """,
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Run in text-input mode (no microphone or Whisper model needed)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 55)
    print("  🎤  VOICE COMMAND SYSTEM — SIMULATION")
    print("  Development mode: Windows / Mac")
    print("=" * 55)

    if args.text:
        run_text_mode()
    else:
        run_voice_mode()


if __name__ == "__main__":
    main()
