"""
Wake word detection — "Dungeon Master".

Continuously records short snippets from the mic (Reachy or system)
and sends them to Gemini for transcription. Triggers when the
transcription contains a wake phrase.
"""

from src.audio import listen, listen_reachy

WAKE_PHRASES = [
    "dungeon master", "dungeon masters", "dungeonmaster",
    "dungeon muster", "dungeon monster", "dunjon master",
    "hey dungeon master", "hey dungeon",
]

_robot = None


def set_robot(reachy_mini):
    """Route wake-word listening through the Reachy Mini mic."""
    global _robot
    _robot = reachy_mini


def wait_for_wake_word():
    """Block until 'Dungeon Master' is detected."""
    print("  Listening for 'Dungeon Master'...")
    while True:
        if _robot is not None:
            text = listen_reachy(_robot)
        else:
            text = listen()
        if text and any(phrase in text for phrase in WAKE_PHRASES):
            print(f"  Heard: \"{text}\" — Wake word detected!")
            return
