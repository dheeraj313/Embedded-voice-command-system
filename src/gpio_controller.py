"""
gpio_controller.py - GPIO Hardware Abstraction Layer (HAL)
===========================================================
Controls physical hardware (LED, DC Motor) via Raspberry Pi GPIO pins.

WHAT IS GPIO:
  GPIO (General Purpose Input/Output) are programmable digital I/O pins.
  Each pin can be:
    INPUT  -> reads voltage from a sensor (button, temperature sensor)
    OUTPUT -> sends voltage to a device (LED, motor driver)

  When set HIGH -> pin outputs 3.3V (up to 16mA current)
  When set LOW  -> pin outputs 0V (GND)

  This project uses OUTPUT mode:
    GPIO17 (Pin 11) -> LED (through 220 ohm resistor)
    GPIO27 (Pin 13) -> L298N motor driver input

HARDWARE ABSTRACTION LAYER (HAL) DESIGN:
  HAL separates "what to do" from "how to do it on this specific hardware."

  Without HAL: main.py calls GPIO.output(17, GPIO.HIGH) directly.
    -> Porting to a different platform requires rewriting main.py.

  With HAL (this file): main.py calls gpio_controller.led_on().
    -> Porting only requires rewriting gpio_controller.py.
    -> The same main.py also runs on Windows via the simulation fallback.

CIRCUIT CONNECTIONS:
  LED:
    GPIO17 ---- 220 ohm resistor ---- LED(+) ---- LED(-) ---- GND
    Resistor limits current to 15mA (GPIO max is 16mA).

  Motor (via L298N H-bridge motor driver):
    GPIO27 ---- L298N IN1
    GND    ---- L298N GND
    5V     ---- L298N VCC
    L298N amplifies the 3.3V/16mA GPIO signal to the 5-12V/500mA
    needed to drive a standard DC motor.
"""

import logging
import time
from typing import Dict

from config import LED_PIN, MOTOR_PIN

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# PLATFORM DETECTION
# ──────────────────────────────────────────────────────────────────────
# Try to import RPi.GPIO — this library only exists on Raspberry Pi.
# On Windows/Mac, this import will fail with ImportError.
# We catch the error and set a flag to use simulation mode instead.
# This is the core of the HAL's platform portability.
try:
    import RPi.GPIO as GPIO
    _RUNNING_ON_RASPI = True
    logger.info("RPi.GPIO imported successfully -> Hardware mode active")
except ImportError:
    _RUNNING_ON_RASPI = False
    logger.warning("RPi.GPIO not available -> Simulation mode active (Windows/Mac)")


class GPIOController:
    """
    Hardware Abstraction Layer for GPIO-controlled peripherals.

    Automatically detects platform:
      - Raspberry Pi → uses real RPi.GPIO library
      - Windows/Mac  → uses simulated GPIO (prints to console)

    Public interface (used by main.py and command_processor):
      gpio.led_on()              → Turn LED on
      gpio.led_off()             → Turn LED off
      gpio.motor_on()            → Start motor
      gpio.motor_off()           → Stop motor
      gpio.execute_command(d, a) → Execute any command by name
      gpio.get_status()          → Get current state of all hardware
      gpio.cleanup()             → Release GPIO resources safely
    """

    def __init__(self):
        """
        Initialize GPIO pins and set initial state (everything OFF).

        BCM vs BOARD pin numbering:
          GPIO.setmode(GPIO.BCM)   -> Broadcom GPIO numbers (GPIO17, GPIO27)
          GPIO.setmode(GPIO.BOARD) -> Physical pin position (Pin 11, Pin 13)

          BCM is used here because the numbers stay consistent across
          all Raspberry Pi hardware revisions.
        """
        self.led_pin   = LED_PIN    # GPIO17
        self.motor_pin = MOTOR_PIN  # GPIO27

        # Track current state in software (mirrors the physical pin state)
        # This lets get_status() return current state without reading GPIO
        self.led_state   = False   # False = OFF
        self.motor_state = False   # False = OFF

        self.is_simulated = not _RUNNING_ON_RASPI

        # Initialize the appropriate GPIO backend
        if _RUNNING_ON_RASPI:
            self._init_real_gpio()
        else:
            self._init_simulated_gpio()

    def _init_real_gpio(self):
        """
        Configure real Raspberry Pi GPIO pins.
        Called only when RPi.GPIO is available.
        """
        # Tell RPi.GPIO to use BCM pin numbering
        GPIO.setmode(GPIO.BCM)

        # Suppress "channel already in use" warnings
        # (happens if the program was closed without cleanup)
        GPIO.setwarnings(False)

        # Configure both pins as OUTPUT
        # GPIO.OUT = we control the voltage, not read it
        GPIO.setup(self.led_pin,   GPIO.OUT)
        GPIO.setup(self.motor_pin, GPIO.OUT)

        # Start with both devices OFF (safety default)
        GPIO.output(self.led_pin,   GPIO.LOW)
        GPIO.output(self.motor_pin, GPIO.LOW)

        logger.info(f"Real GPIO initialized — LED:GPIO{self.led_pin}, Motor:GPIO{self.motor_pin}")
        print(f"[GPIO] ✓ Hardware GPIO initialized")
        print(f"[GPIO]   LED   → GPIO{self.led_pin}  (BCM) = Physical Pin 11")
        print(f"[GPIO]   Motor → GPIO{self.motor_pin} (BCM) = Physical Pin 13")

    def _init_simulated_gpio(self):
        """
        Set up simulated GPIO for Windows/Mac development.
        No real hardware — everything is printed to the console.
        """
        logger.info("Simulated GPIO initialized (no real hardware)")
        print("[GPIO] ⚠️  SIMULATION MODE — No Raspberry Pi detected")
        print(f"[GPIO]   LED   → GPIO{self.led_pin}  (simulated)")
        print(f"[GPIO]   Motor → GPIO{self.motor_pin} (simulated)")
        print("[GPIO]   Hardware states will be shown in console\n")

    # ──────────────────────────────────────────────────────────────
    # LOW-LEVEL PIN CONTROL (private - not called directly)
    # ──────────────────────────────────────────────────────────────

    def _write_pin(self, pin: int, state: bool):
        """
        Set a GPIO pin to HIGH (True) or LOW (False).

        This is the single point where software meets hardware.
        ALL hardware writes in this class go through this method.
        This is the "abstraction" in Hardware Abstraction Layer.

        Args:
            pin:   BCM GPIO pin number (e.g., 17 or 27)
            state: True = HIGH (3.3V), False = LOW (0V)
        """
        if _RUNNING_ON_RASPI:
            # Real hardware: write to the actual GPIO register via RPi.GPIO
            GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
        else:
            # Simulation: just log the pin change
            voltage = "3.3V ⚡ (HIGH)" if state else "0V   (LOW) "
            logger.debug(f"[SIM] GPIO{pin} → {voltage}")

    # ──────────────────────────────────────────────────────────────
    # LED CONTROL
    # ──────────────────────────────────────────────────────────────

    def led_on(self):
        """
        Turn the LED ON.
        Sets GPIO17 to HIGH (3.3V), current flows through LED → light on.
        """
        self._write_pin(self.led_pin, True)
        self.led_state = True
        logger.info(f"LED ON  ← GPIO{self.led_pin} set HIGH")
        self._print_hardware_change("💡 LED", "ON ", self.led_pin, "3.3V")

    def led_off(self):
        """
        Turn the LED OFF.
        Sets GPIO17 to LOW (0V), no current flows → light off.
        """
        self._write_pin(self.led_pin, False)
        self.led_state = False
        logger.info(f"LED OFF ← GPIO{self.led_pin} set LOW")
        self._print_hardware_change("💡 LED", "OFF", self.led_pin, "0V  ")

    # ──────────────────────────────────────────────────────────────
    # MOTOR CONTROL
    # ──────────────────────────────────────────────────────────────

    def motor_on(self):
        """
        Start the DC motor.
        Sets GPIO27 to HIGH → L298N driver receives signal → motor runs.
        """
        self._write_pin(self.motor_pin, True)
        self.motor_state = True
        logger.info(f"Motor ON  ← GPIO{self.motor_pin} set HIGH")
        self._print_hardware_change("⚙️  Motor", "ON ", self.motor_pin, "3.3V")

    def motor_off(self):
        """
        Stop the DC motor.
        Sets GPIO27 to LOW → L298N driver loses signal → motor stops.
        """
        self._write_pin(self.motor_pin, False)
        self.motor_state = False
        logger.info(f"Motor OFF ← GPIO{self.motor_pin} set LOW")
        self._print_hardware_change("⚙️  Motor", "OFF", self.motor_pin, "0V  ")

    # ──────────────────────────────────────────────────────────────
    # HAL INTERFACE - execute_command()
    # ──────────────────────────────────────────────────────────────

    def execute_command(self, device: str, action: str) -> bool:
        """
        Execute a hardware command by device name and action.

        This is the main HAL interface method.
        main.py calls this with high-level commands like ("LED", "ON").
        The HAL translates this into the correct GPIO operation.

        DESIGN PATTERN: Command Map (dictionary of function references)
          Instead of a long if/elif chain, we use a dictionary that maps
          (device, action) tuples to bound methods.
          This is cleaner and easy to extend — just add to the dict.

        Args:
            device: "LED" or "MOTOR"
            action: "ON" or "OFF"

        Returns:
            bool: True if command executed successfully, False if unknown.
        """
        # Map (device, action) tuples to the corresponding method
        # Value is a function reference (no parentheses = not called yet)
        command_map = {
            ("LED",   "ON"):  self.led_on,
            ("LED",   "OFF"): self.led_off,
            ("MOTOR", "ON"):  self.motor_on,
            ("MOTOR", "OFF"): self.motor_off,
        }

        handler = command_map.get((device.upper(), action.upper()))

        if handler:
            handler()  # Call the method (e.g., self.led_on())
            return True
        else:
            logger.error(f"Unknown command: device='{device}', action='{action}'")
            print(f"[GPIO][ERROR] Unknown command: {device} {action}")
            return False

    # ──────────────────────────────────────────────────────────────
    # STATUS & DISPLAY
    # ──────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, str]:
        """
        Return the current state of all hardware devices.

        Returns:
            Dict with LED, MOTOR state strings and operating mode.
        """
        return {
            "LED":   "ON" if self.led_state   else "OFF",
            "MOTOR": "ON" if self.motor_state else "OFF",
            "mode":  "HARDWARE" if _RUNNING_ON_RASPI else "SIMULATION",
        }

    def _print_hardware_change(self, device: str, state: str, pin: int, voltage: str):
        """Print a formatted hardware state change to the console."""
        mode_label = "HARDWARE" if _RUNNING_ON_RASPI else "SIMULATION"
        print(f"\n  ┌────────────────────────────────────────┐")
        print(f"  │  {device}  →  [ {state} ]                   │")
        print(f"  │  GPIO{pin} → {voltage}  [{mode_label}]          │")
        print(f"  └────────────────────────────────────────┘")

    # ──────────────────────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────────────────────

    def cleanup(self):
        """
        Safely reset all GPIO pins and release resources.

        If a program exits without calling GPIO.cleanup(), pins stay in
        their last state (a motor could keep running, and the next run
        may throw 'RuntimeWarning: channel already in use').
        GPIO.cleanup() resets all configured pins to INPUT mode (safe state).
        """
        if _RUNNING_ON_RASPI:
            GPIO.cleanup()
            logger.info("GPIO.cleanup() called — all pins reset to safe state")
        else:
            logger.info("Simulated GPIO cleanup complete")

        # Reset software state to match (even in simulation)
        self.led_state   = False
        self.motor_state = False

        print("\n[GPIO] ✓ All pins reset to safe state. Hardware shutdown complete.")
