"""
Reachy Mini emotion & talking-movement controller for D&D.

Maps game events to pre-built emotion animations and provides
a subtle talking head movement that runs alongside TTS.
"""

import random
import threading
import time

import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.motion.recorded_move import RecordedMoves
from reachy_mini.utils import create_head_pose

EMOTIONS_DATASET = "pollen-robotics/reachy-mini-emotions-library"

SCENE_EMOTION_MAP: dict[str, list[str]] = {
    "combat": ["furious1", "rage1", "scared1", "anxiety1"],
    "victory": ["success1", "success2", "proud1", "cheerful1", "enthusiastic1"],
    "defeat": ["sad1", "sad2", "dying1", "downcast1", "resigned1"],
    "critical_hit": ["amazed1", "enthusiastic2", "proud2", "electric1"],
    "fumble": ["oops1", "oops2", "confused1", "frustrated1"],
    "danger": ["fear1", "scared1", "anxiety1", "uncomfortable1"],
    "mystery": ["curious1", "thoughtful1", "inquiring1", "attentive1"],
    "puzzle": ["thoughtful2", "inquiring2", "attentive2", "curious1"],
    "dialogue_friendly": ["welcoming1", "cheerful1", "helpful1", "understanding1"],
    "dialogue_hostile": ["contempt1", "displeased1", "irritated1", "furious1"],
    "exploration": ["curious1", "attentive1", "inquiring3", "welcoming2"],
    "rest": ["serenity1", "calming1", "relief1", "grateful1"],
    "surprise": ["surprised1", "surprised2", "amazed1"],
    "sad": ["sad1", "sad2", "lonely1", "downcast1"],
    "funny": ["laughing1", "laughing2", "cheerful1"],
    "tension": ["anxiety1", "uncomfortable1", "uncertain1", "attentive1"],
    "knocked_out": ["dying1", "exhausted1", "resigned1"],
    "success": ["success1", "success2", "proud1", "relief1", "cheerful1"],
    "fail": ["frustrated1", "displeased2", "irritated2", "oops1"],
    "narration": ["attentive1", "thoughtful1", "curious1", "serenity1"],
}

ROLL_RESULT_EMOTIONS: dict[str, list[str]] = {
    "critical": ["amazed1", "enthusiastic2", "proud2", "electric1", "success2"],
    "success": ["cheerful1", "proud1", "success1", "relief1"],
    "fail": ["frustrated1", "oops1", "displeased1", "sad1"],
    "fumble": ["oops2", "confused1", "scared1", "dying1"],
}


class ReachyEmotions:
    def __init__(self, mini: ReachyMini):
        self.mini = mini
        self._emotions: RecordedMoves | None = None
        self._emote_thread: threading.Thread | None = None
        self._talking = False
        self._talk_thread: threading.Thread | None = None

    def load(self):
        """Download/cache the emotions library. Call once at startup."""
        print("  🎭 Loading emotion library...")
        self._emotions = RecordedMoves(EMOTIONS_DATASET)
        available = set(self._emotions.list_moves())
        for key, emotes in SCENE_EMOTION_MAP.items():
            SCENE_EMOTION_MAP[key] = [e for e in emotes if e in available]
        for key, emotes in ROLL_RESULT_EMOTIONS.items():
            ROLL_RESULT_EMOTIONS[key] = [e for e in emotes if e in available]
        print(f"  🎭 Loaded {len(available)} emotions.")

    def play_emotion(self, emotion_name: str, sound: bool = False):
        """Play a named emotion animation (non-blocking)."""
        if self._emotions is None:
            return
        try:
            move = self._emotions.get(emotion_name)
            self._emote_thread = threading.Thread(
                target=self._play_move_sync,
                args=(move, sound),
                daemon=True,
            )
            self._emote_thread.start()
        except (ValueError, Exception):
            pass

    def play_scene_emotion(self, scene_type: str, sound: bool = False):
        """Pick and play a random emotion matching the scene type."""
        emotes = SCENE_EMOTION_MAP.get(scene_type, SCENE_EMOTION_MAP["narration"])
        if emotes:
            self.play_emotion(random.choice(emotes), sound)

    def play_roll_emotion(self, result: str, sound: bool = False):
        """Play an emotion based on a dice roll result (critical/success/fail/fumble)."""
        emotes = ROLL_RESULT_EMOTIONS.get(result, [])
        if emotes:
            self.play_emotion(random.choice(emotes), sound)

    def start_talking(self):
        """Start a subtle nodding/swaying animation while TTS plays."""
        self._talking = True
        self._talk_thread = threading.Thread(target=self._talking_loop, daemon=True)
        self._talk_thread.start()

    def stop_talking(self):
        """Stop the talking animation."""
        self._talking = False
        if self._talk_thread is not None:
            self._talk_thread.join(timeout=2)
            self._talk_thread = None

    def wait_for_emotion(self):
        """Wait for the current emotion animation to finish."""
        if self._emote_thread is not None:
            self._emote_thread.join(timeout=10)
            self._emote_thread = None

    def _play_move_sync(self, move, sound: bool):
        try:
            self.mini.play_move(move, sound=sound)
        except Exception:
            pass

    def _talking_loop(self):
        """Gentle random head micro-movements to simulate talking."""
        try:
            while self._talking:
                pitch = random.uniform(-3, 3)
                yaw = random.uniform(-4, 4)
                roll = random.uniform(-2, 2)
                duration = random.uniform(0.3, 0.6)

                pose = create_head_pose(
                    pitch=pitch, yaw=yaw, roll=roll,
                    degrees=True, mm=True,
                )
                self.mini.goto_target(head=pose, duration=duration)
                time.sleep(duration)
        except Exception:
            pass
        finally:
            try:
                home = create_head_pose(degrees=True, mm=True)
                self.mini.goto_target(head=home, duration=0.4)
            except Exception:
                pass


def classify_scene(narrative: str) -> str:
    """Guess the scene mood from the narrative text."""
    text = narrative.lower()

    if any(w in text for w in ["attack", "sword", "fight", "battle", "slash", "strike", "arrow"]):
        return "combat"
    if any(w in text for w in ["dead", "death", "dying", "fallen", "knocked out"]):
        return "knocked_out"
    if any(w in text for w in ["danger", "trap", "poison", "cursed", "dark magic"]):
        return "danger"
    if any(w in text for w in ["mystery", "strange", "odd", "peculiar", "hidden"]):
        return "mystery"
    if any(w in text for w in ["puzzle", "riddle", "lock", "mechanism", "code"]):
        return "puzzle"
    if any(w in text for w in ["laugh", "funny", "joke", "silly", "clumsy"]):
        return "funny"
    if any(w in text for w in ["sad", "cry", "mourn", "loss", "grief", "tear"]):
        return "sad"
    if any(w in text for w in ["surprise", "suddenly", "gasp", "shock", "unexpected"]):
        return "surprise"
    if any(w in text for w in ["safe", "rest", "camp", "heal", "sleep", "peaceful"]):
        return "rest"
    if any(w in text for w in ["victory", "won", "triumph", "celebrate", "saved"]):
        return "victory"
    if any(w in text for w in ["tense", "nervous", "edge", "careful", "quiet"]):
        return "tension"
    if any(w in text for w in ["explore", "walk", "path", "forest", "cave", "door", "enter"]):
        return "exploration"

    return "narration"
