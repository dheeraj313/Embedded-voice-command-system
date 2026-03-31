"""
main.py - Main Entry Point: Embedded Voice Command System
==========================================================
Orchestrates the full Sense -> Process -> Actuate pipeline.

  INIT   -> Load Whisper model, set up GPIO pins
  SENSE  -> Record microphone audio via PyAudio
  PROCESS-> Whisper transcribes; CommandProcessor matches keywords
  ACTUATE-> GPIOController sends HIGH/LOW signals to LED/Motor

Runs as a continuous loop until Ctrl+C.
On Raspberry Pi, configure as a systemd service to auto-start on boot.

Run on Raspberry Pi:  cd src && python3 main.py
Run on Windows:       python simulation/simulate.py
"""

import os
import sys
import logging
import time

# ──────────────────────────────────────────────────────────────────────
# WINDOWS UTF-8 FIX
# ──────────────────────────────────────────────────────────────────────
# Force UTF-8 output on Windows (default is cp1252 which breaks emoji)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────────
# PATH SETUP
# ──────────────────────────────────────────────────────────────────────
# Make sure Python can find the other modules in this src/ directory.
# os.path.dirname(__file__) = absolute path of the src/ folder.
# Adding it to sys.path means: "look here when importing modules."
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speech_recognizer import SpeechRecognizer
from command_processor  import CommandProcessor
from gpio_controller    import GPIOController
from config             import LOG_FILE, LOG_LEVEL

# ──────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ──────────────────────────────────────────────────────────────────────
# Create logs/ directory if it doesn't exist
_log_dir = os.path.dirname(LOG_FILE)
if _log_dir:
    os.makedirs(_log_dir, exist_ok=True)

# Configure Python's built-in logging system:
#   FileHandler    → writes logs to file (persistent, for debugging later)
#   StreamHandler  → also prints logs to terminal (for live viewing)
#   format         → timestamp + module name + level + message
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ──────────────────────────────────────────────────────────────────────

def print_banner():
    """Print startup banner with available commands."""
    print("\n" + "=" * 60)
    print("  🎤  EMBEDDED VOICE COMMAND SYSTEM")
    print("  Hindi Speech Recognition → GPIO Hardware Control")
    print("  Powered by: OpenAI Whisper + RPi.GPIO + PyAudio")
    print("=" * 60)
    print()
    print("  📢  SUPPORTED COMMANDS:")
    print("  ┌──────────────────┬────────────────┬───────────────┐")
    print("  │ Hindi (Devnagri) │ Transliteration│ English       │")
    print("  ├──────────────────┼────────────────┼───────────────┤")
    print("  │ बत्ती चालू       │ batti chalu    │ light on      │")
    print("  │ बत्ती बंद        │ batti band     │ light off     │")
    print("  │ मोटर चालू        │ motor chalu    │ motor on      │")
    print("  │ मोटर बंद         │ motor band     │ motor off     │")
    print("  └──────────────────┴────────────────┴───────────────┘")
    print()
    print("  Press Ctrl+C at any time to exit safely.\n")


def print_status(gpio: GPIOController):
    """Display current hardware state."""
    status = gpio.get_status()
    led_icon   = "💡 ON " if status["LED"]   == "ON" else "⚫ OFF"
    motor_icon = "⚙️  ON " if status["MOTOR"] == "ON" else "⏹️  OFF"
    mode = status["mode"]
    print(f"\n  [STATUS] LED: {led_icon} | Motor: {motor_icon} | Mode: {mode}")


def print_iteration_header(iteration: int):
    """Print a separator before each listen cycle."""
    print(f"\n{'─' * 60}")
    print(f"  [Cycle #{iteration}] Waiting for voice command...")


# ──────────────────────────────────────────────────────────────────────
# MAIN CONTROL LOOP
# ──────────────────────────────────────────────────────────────────────

def main():
    """
    Main program: initialize all subsystems, then run the SENSE→PROCESS→ACTUATE loop.

    ARCHITECTURE NOTE:
      We create exactly ONE instance of each class:
        SpeechRecognizer → loads Whisper model ONCE (expensive: ~5 seconds)
        CommandProcessor → loads keyword map ONCE
        GPIOController   → initializes GPIO pins ONCE

      These objects are reused for every voice command.
      Creating new instances each loop would be extremely slow.

    ERROR HANDLING STRATEGY:
      Individual command failures (bad audio, unknown command) are caught
      INSIDE the loop and handled gracefully — the loop continues.
      Only fatal errors (e.g., GPIO hardware failure) propagate up and exit.
      This is critical for embedded systems: "keep running, log the error."
    """
    print_banner()
    logger.info("=" * 50)
    logger.info("Voice Command System STARTING")
    logger.info("=" * 50)

    # ── INITIALIZE ALL THREE LAYERS ────────────────────────────────
    # Layer 1: Sensing (speech → text)
    recognizer = SpeechRecognizer()

    # Layer 2: Processing (text → command)
    processor = CommandProcessor()

    # Layer 3: Actuation (command → GPIO signal → hardware)
    gpio = GPIOController()

    # Show initial hardware state (everything OFF at startup)
    print_status(gpio)

    # Session statistics — tracks accuracy metrics
    iteration      = 0
    total_attempts = 0
    successful_cmds = 0

    # ── MAIN LOOP: SENSE → PROCESS → ACTUATE ──────────────────────
    try:
        while True:
            iteration += 1
            print_iteration_header(iteration)

            # ── SENSE: Record audio and transcribe with Whisper ────
            transcribed_text = recognizer.listen_and_transcribe()
            total_attempts  += 1

            if not transcribed_text:
                print("  [⚠️]  No speech detected. Please speak clearly.")
                logger.warning("Empty transcription — no speech detected")
                continue  # Go back to listening

            # ── PROCESS: Match transcription to a command ──────────
            command = processor.match_command(transcribed_text)

            if command is None:
                print(f'  [❌]  Command not recognized: "{transcribed_text}"')
                print("  [💡]  Try: 'light on', 'batti chalu', or 'मोटर बंद'")
                logger.info(f"No match for: '{transcribed_text}'")
                continue  # Go back to listening

            # ── ACTUATE: Send command to GPIO hardware ─────────────
            device, action = processor.get_device_and_action(command)
            success        = gpio.execute_command(device, action)

            if success:
                successful_cmds += 1
                print(f"  [✅]  Command executed: {command}")
                logger.info(f"Executed: {command} (device={device}, action={action})")
            else:
                print(f"  [❌]  Execution failed: {command}")
                logger.error(f"Failed to execute: {command}")

            # Show updated hardware status after each command
            print_status(gpio)

            # Show live accuracy stats
            accuracy = (successful_cmds / total_attempts * 100) if total_attempts > 0 else 0
            print(f"\n  [📊 STATS] "
                  f"Accuracy: {accuracy:.1f}% "
                  f"({successful_cmds}/{total_attempts} commands recognized)")

    except KeyboardInterrupt:
        # User pressed Ctrl+C — this is the expected way to exit
        print("\n\n  [EXIT] Ctrl+C detected — shutting down gracefully...")
        logger.info("Shutdown requested by user (KeyboardInterrupt)")

    finally:
        # ── CLEANUP: ALWAYS runs, even if an exception occurred ────
        # This block guarantees GPIO pins are reset and resources freed.
        # "finally" is Python's way to ensure cleanup happens no matter what.
        logger.info("Running cleanup...")
        recognizer.cleanup()
        gpio.cleanup()

        # Print final session statistics
        accuracy = (successful_cmds / total_attempts * 100) if total_attempts > 0 else 0
        print("\n" + "=" * 60)
        print("  📊  FINAL SESSION STATISTICS")
        print("=" * 60)
        print(f"  Total attempts:      {total_attempts}")
        print(f"  Successful commands: {successful_cmds}")
        print(f"  Session accuracy:    {accuracy:.1f}%")
        print("=" * 60)
        logger.info(f"Session ended | Accuracy: {accuracy:.1f}% ({successful_cmds}/{total_attempts})")
        print("\n  ✓ System shut down safely. All GPIO pins reset.\n")


# ──────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────
# This block runs only when the script is executed directly.
# It does NOT run when the file is imported as a module (important for tests).
# __name__ == "__main__" is Python's standard entry-point guard.
if __name__ == "__main__":
    main()
