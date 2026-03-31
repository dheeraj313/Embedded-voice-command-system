"""
command_processor.py - NLP Keyword Matching Engine
====================================================
Converts raw Whisper transcription text into structured hardware commands.

ARCHITECTURE ROLE:
  speech_recognizer.py  ->  "बत्ती चालू"   (raw text)
  command_processor.py  ->  "LED_ON"        (structured command)
  gpio_controller.py    ->  GPIO17 = HIGH   (hardware action)

This is the PROCESSING layer of the Sense → Process → Actuate pipeline.

ALGORITHM: Keyword Spotting
────────────────────────────
  Keyword spotting scans transcribed text for known trigger phrases,
  similar to wake-word detection in voice assistants (Alexa, Google Home).
  For a small fixed command set (4 commands), this approach is preferred
  over neural-network-based intent recognition because:

  1. No training data needed
  2. Fully deterministic — same input always gives same output
  3. Runs in microseconds vs milliseconds for ML inference
  4. New commands are added simply by editing config.py
"""

import logging
from typing import Optional, Tuple, List, Dict

from config import COMMAND_KEYWORDS, MATCH_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)


class CommandProcessor:
    """
    Maps transcribed speech text to hardware commands.

    Supported commands:
        LED_ON    → Turn LED on
        LED_OFF   → Turn LED off
        MOTOR_ON  → Start motor
        MOTOR_OFF → Stop motor
    """

    def __init__(self):
        """Initialize the command processor with keyword mappings from config."""
        self.command_keywords = COMMAND_KEYWORDS
        self.threshold        = MATCH_CONFIDENCE_THRESHOLD

        # Command history: stores every command processed this session.
        # Useful for debugging accuracy and reviewing what was said.
        self._history: List[Dict] = []

        logger.info(
            f"CommandProcessor initialized | "
            f"{len(self.command_keywords)} commands | "
            f"threshold={self.threshold}"
        )

    # ──────────────────────────────────────────────────────────────
    # TEXT NORMALIZATION
    # ──────────────────────────────────────────────────────────────

    def normalize_text(self, text: str) -> str:
        """
        Clean and normalize raw text for reliable matching.

        NORMALIZATION STEPS:
          1. Lowercase → "Light ON" becomes "light on"
          2. Strip whitespace → "  light on  " becomes "light on"
          3. Remove punctuation → Whisper adds "." at end of sentences
          4. Collapse spaces → "light  on" becomes "light on"

        Hindi note: Hindi Devanagari characters are NOT lowercased
        (they don't have case), only ASCII English is affected.

        Args:
            text: Raw text from Whisper or user input.

        Returns:
            str: Cleaned, normalized text ready for matching.
        """
        if not text:
            return ""

        # Step 1 & 2: lowercase and strip
        normalized = text.lower().strip()

        # Step 3: remove punctuation
        # '।' is the Hindi/Devanagari full stop (like English '.')
        for char in [".", ",", "!", "?", "-", "_", "।", ":", ";"]:
            normalized = normalized.replace(char, " ")

        # Step 4: collapse multiple spaces into single space
        normalized = " ".join(normalized.split())

        return normalized

    # ──────────────────────────────────────────────────────────────
    # COMMAND MATCHING
    # ──────────────────────────────────────────────────────────────

    def match_command(self, transcribed_text: str) -> Optional[str]:
        """
        Match transcribed text to a command by searching for keywords.

        MATCHING STRATEGY (two-pass approach):
          Pass 1 - Exact phrase match:
            Check if any keyword phrase is a SUBSTRING of the transcription.
            Example: keyword="light on", transcription="please light on yaar"
            → "light on" IS a substring of the transcription → MATCH (score=1.0)

          Pass 2 - Word overlap (partial match):
            If no exact phrase matches, check how many individual words
            from the keyword appear in the transcription.
            Example: keyword="light on" (2 words), transcription has "light"
            → 1 out of 2 words match → score = 0.5

          Whichever command gets the highest score wins.
          If the winning score is below MATCH_CONFIDENCE_THRESHOLD → no match.

        Args:
            transcribed_text: Raw text from Whisper transcription.

        Returns:
            str: Command name like "LED_ON", or None if no command matched.
        """
        # Guard: handle None and empty string gracefully
        if not transcribed_text:
            logger.warning("Empty/None transcription passed to match_command")
            return None

        normalized = self.normalize_text(transcribed_text)
        logger.info(f"Matching: '{normalized}'")

        best_command = None
        best_score   = 0.0

        # Score every possible command and find the best match
        for command_name, keywords in self.command_keywords.items():
            score = self._calculate_match_score(normalized, keywords)
            logger.debug(f"  {command_name}: score={score:.2f}")

            if score > best_score:
                best_score   = score
                best_command = command_name

        # Accept the match only if it meets our confidence threshold
        if best_score >= self.threshold:
            logger.info(f"✓ Matched '{best_command}' with score={best_score:.2f}")
            self._history.append({
                "input":      transcribed_text,
                "normalized": normalized,
                "command":    best_command,
                "confidence": round(best_score, 2),
            })
            return best_command

        # No confident match found
        logger.warning(
            f"✗ No match. Best: {best_command} ({best_score:.2f}) < threshold ({self.threshold})"
        )
        self._history.append({
            "input":      transcribed_text,
            "normalized": normalized,
            "command":    None,
            "confidence": round(best_score, 2),
        })
        return None

    def _calculate_match_score(self, normalized_text: str, keywords: List[str]) -> float:
        """
        Compute how well the normalized text matches a list of keyword phrases.

        SCORING LOGIC:
          1. Exact substring check first (fast, highest confidence)
             → Score = 1.0 if any keyword phrase is found inside the text
          2. Word-level overlap for partial matches
             → Score = (matching words) / (total keyword words)
             → Take the best score across all keyword phrases

        Args:
            normalized_text: Already-normalized transcription.
            keywords:        List of keyword phrases for one command.

        Returns:
            float: Best match score (0.0 = no match, 1.0 = perfect match).
        """
        # ── PASS 1: Exact phrase substring match ──────────────────
        for keyword in keywords:
            keyword_norm = self.normalize_text(keyword)
            if keyword_norm and keyword_norm in normalized_text:
                return 1.0  # Found an exact keyword phrase in the text

        # ── PASS 2: Word-level overlap (handles partial transcriptions) ──
        text_words   = set(normalized_text.split())
        best_overlap = 0.0

        for keyword in keywords:
            keyword_words = set(self.normalize_text(keyword).split())
            if not keyword_words:
                continue

            # Intersection = words that appear in BOTH the text and keyword
            matching_words = text_words & keyword_words  # & is set intersection

            # Jaccard-like score: matching / total keyword words
            # Example: keyword="motor on" (2 words), text has "motor" only
            #   matching_words = {"motor"} → score = 1/2 = 0.5
            overlap_score = len(matching_words) / len(keyword_words)
            best_overlap  = max(best_overlap, overlap_score)

        return best_overlap

    # ──────────────────────────────────────────────────────────────
    # COMMAND PARSING
    # ──────────────────────────────────────────────────────────────

    def get_device_and_action(self, command: str) -> Tuple[str, str]:
        """
        Split a command string into device and action components.

        Command format is always: DEVICE_ACTION
          "LED_ON"    -> device="LED",   action="ON"
          "LED_OFF"   -> device="LED",   action="OFF"
          "MOTOR_ON"  -> device="MOTOR", action="ON"
          "MOTOR_OFF" -> device="MOTOR", action="OFF"

        Splitting device from action makes the GPIO controller flexible —
        adding a new device (e.g. FAN) only requires new keywords in config.py,
        not structural changes to the controller.

        Args:
            command: Command string like "LED_ON".

        Returns:
            Tuple[str, str]: (device, action) e.g. ("LED", "ON")
        """
        parts  = command.split("_", maxsplit=1)   # Split on first underscore only
        device = parts[0]                          # "LED" or "MOTOR"
        action = parts[1] if len(parts) > 1 else ""  # "ON" or "OFF"
        return device, action

    # ──────────────────────────────────────────────────────────────
    # DIAGNOSTICS
    # ──────────────────────────────────────────────────────────────

    def get_session_accuracy(self) -> Dict:
        """
        Calculate recognition accuracy for the current session.
        accuracy = (matched commands / total attempts) x 100

        Returns:
            Dict with total, successful, failed, and accuracy_percent.
        """
        total      = len(self._history)
        successful = sum(1 for h in self._history if h["command"] is not None)
        failed     = total - successful
        accuracy   = (successful / total * 100) if total > 0 else 0.0

        return {
            "total":            total,
            "successful":       successful,
            "failed":           failed,
            "accuracy_percent": round(accuracy, 1),
        }

    def get_history(self) -> List[Dict]:
        """Return full command history for this session (useful for debugging)."""
        return self._history.copy()
