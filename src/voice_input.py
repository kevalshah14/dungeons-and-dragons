"""
Voice-based input for the D&D game.

Replaces all CLI input() calls. Reachy asks via TTS,
listens via the microphone, and parses responses.
Supports both system mic and Reachy Mini mic.
"""

import re

from src.audio import listen, listen_reachy

MAX_RETRIES = 3

_voice = None
_robot = None
_registry = None
_active_character: str | None = None


def set_voice(game_voice):
    global _voice
    _voice = game_voice


def set_robot(reachy_mini):
    """Attach a ReachyMini so mic input is routed through the robot."""
    global _robot
    _robot = reachy_mini


def set_registry(registry):
    """Store the player registry (dict keyed by character name)."""
    global _registry
    _registry = registry


def set_active_character(character_name: str | None):
    """Set which character is currently being addressed."""
    global _active_character
    _active_character = character_name


def _active_real_name() -> str | None:
    """Get the real name for the currently active character."""
    if _registry and _active_character and _active_character in _registry:
        return _registry[_active_character].real_name
    return None


def _say(text: str):
    if _voice:
        _voice.announce(text)
    else:
        print(f"  [VOICE] {text}")


def _ask_once() -> str | None:
    """Listen once and return transcribed text or None."""
    if _robot is not None:
        return listen_reachy(_robot)
    return listen()


WORD_TO_NUM = {
    "one": 1, "won": 1, "want": 1,
    "two": 2, "to": 2, "too": 2, "tu": 2,
    "three": 3, "free": 3, "tree": 3,
    "four": 4, "for": 4, "fore": 4,
    "five": 5,
    "six": 6, "sex": 6,
}


def _parse_number(text: str) -> int | None:
    """Extract a number from transcribed speech."""
    for word in text.split():
        cleaned = word.strip(".,!?")
        if cleaned.isdigit():
            return int(cleaned)
        if cleaned in WORD_TO_NUM:
            return WORD_TO_NUM[cleaned]
    return None


def ask_number(question: str, min_val: int, max_val: int) -> int:
    """Ask a question expecting a number in [min_val, max_val]."""
    _say(question)
    print(f"  🎤 Listening for a number ({min_val}-{max_val})...")

    for attempt in range(MAX_RETRIES):
        text = _ask_once()
        if text:
            num = _parse_number(text)
            if num is not None and min_val <= num <= max_val:
                print(f"  🎤 Heard: \"{text}\" -> {num}")
                return num
            print(f"  🎤 Heard: \"{text}\" (not a valid number)")

        if attempt < MAX_RETRIES - 1:
            _say(f"Sorry, I need a number between {min_val} and {max_val}. Try again.")
            print(f"  🎤 Retrying ({attempt + 2}/{MAX_RETRIES})...")

    _say(f"I'll go with {min_val}.")
    print(f"  🎤 Defaulting to {min_val}")
    return min_val


def ask_text(question: str) -> str | None:
    """Ask a question expecting free-form text. Returns None for 'skip'/'no'/'none'."""
    _say(question)
    print(f"  🎤 Listening...")

    for attempt in range(MAX_RETRIES):
        text = _ask_once()
        if text:
            print(f"  🎤 Heard: \"{text}\"")
            if any(w in text for w in ["skip", "no", "none", "nothing", "nah", "nope"]):
                return None
            return text

        if attempt < MAX_RETRIES - 1:
            _say("I didn't catch that. Could you say it again?")
            print(f"  🎤 Retrying ({attempt + 2}/{MAX_RETRIES})...")

    return None


def ask_confirm(question: str) -> bool:
    """Ask a yes/no question. Returns True for yes, False for no/quit."""
    _say(question)
    print(f"  🎤 Listening for yes/no...")

    for attempt in range(MAX_RETRIES):
        text = _ask_once()
        if text:
            print(f"  🎤 Heard: \"{text}\"")
            if any(w in text for w in ["yes", "yeah", "yep", "ready", "sure", "let's go",
                                        "go", "okay", "ok", "start", "begin"]):
                return True
            if any(w in text for w in ["no", "nah", "nope", "quit", "stop", "exit"]):
                return False

        if attempt < MAX_RETRIES - 1:
            _say("Say yes or no.")
            print(f"  🎤 Retrying ({attempt + 2}/{MAX_RETRIES})...")

    _say("I'll take that as a yes!")
    return True


def _fuzzy_match_option(text: str, options: list[str]) -> int | None:
    """Try to match spoken text to one of the options by keyword overlap."""
    text_words = set(re.findall(r"[a-z]+", text.lower()))
    if not text_words:
        return None

    best_idx = None
    best_score = 0

    for i, option in enumerate(options):
        option_words = set(re.findall(r"[a-z]+", option.lower()))
        # Remove common words that don't help distinguish options
        stop_words = {"the", "a", "an", "to", "and", "or", "of", "in", "on", "it", "is", "i"}
        meaningful = option_words - stop_words
        if not meaningful:
            meaningful = option_words

        overlap = len(text_words & meaningful)
        if overlap > best_score:
            best_score = overlap
            best_idx = i

    if best_score >= 1:
        return best_idx
    return None


def ask_choice(question: str, options: list[str]) -> int:
    """Ask the player to pick from numbered options. Returns 0-based index.

    Understands spoken numbers ("one", "two") and fuzzy keyword
    matching ("sneak" matches "Sneak past the guards").
    """
    print(f"  🎤 Listening for choice (1-{len(options)})...")

    for attempt in range(MAX_RETRIES):
        text = _ask_once()
        if text:
            print(f"  🎤 Heard: \"{text}\"")

            # Try parsing a number first
            num = _parse_number(text)
            if num is not None and 1 <= num <= len(options):
                return num - 1

            # Try fuzzy keyword matching
            match = _fuzzy_match_option(text, options)
            if match is not None:
                print(f"  🎤 Matched to option {match + 1}: {options[match]}")
                return match

        if attempt < MAX_RETRIES - 1:
            opts_speech = ". ".join(f"{i+1}, {opt}" for i, opt in enumerate(options))
            _say(f"I didn't catch that. Your options are: {opts_speech}. Say the number.")
            print(f"  🎤 Retrying ({attempt + 2}/{MAX_RETRIES})...")

    _say("I'll pick the first option.")
    print(f"  🎤 Defaulting to option 1")
    return 0
