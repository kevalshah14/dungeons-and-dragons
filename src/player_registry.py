"""
Player registration for the current game session.

Uses Direction of Arrival (DoA) from Reachy's mic array to locate
each player by their voice. Reachy asks each player to say hello,
detects where the voice came from, turns toward them, and asks
their name. Stores name + yaw angle for head tracking during the game.

Wide angles use body rotation (body_yaw) so Reachy faces the player
with its whole body, not just its neck.
"""

import logging
import math
import random
import threading
import time
from dataclasses import dataclass

import numpy as np
from reachy_mini.utils import create_head_pose

logger = logging.getLogger(__name__)

# DoA returns 0 = left, π/2 = front, π = right.
# Reachy yaw: positive = left, negative = right (degrees).
_DOA_FRONT = math.pi / 2
_YAW_RANGE_DEG = 55.0

# If the target yaw exceeds this, rotate the body instead of just the neck.
_HEAD_ONLY_MAX_DEG = 35.0

DOA_POLL_S = 0.05
DOA_TIMEOUT_S = 15.0


def doa_to_yaw_deg(doa_rad: float) -> float:
    """Convert a DoA mic-array angle (radians) to Reachy yaw (degrees)."""
    offset = doa_rad - _DOA_FRONT
    return max(-_YAW_RANGE_DEG, min(_YAW_RANGE_DEG,
        -offset / _DOA_FRONT * _YAW_RANGE_DEG))


@dataclass
class RegisteredPlayer:
    real_name: str
    yaw_deg: float
    character_name: str | None = None
    cloned_voice_id: str | None = None
    hero_description: str | None = None


def _split_yaw(total_yaw_deg: float) -> tuple[float, float]:
    """Split a target yaw into (body_yaw_rad, head_yaw_deg).

    For small angles the head does all the work. For wider angles the
    body rotates to bring the player in front, and the head adds the
    remaining offset.
    """
    if abs(total_yaw_deg) <= _HEAD_ONLY_MAX_DEG:
        return 0.0, total_yaw_deg
    body_deg = total_yaw_deg - math.copysign(_HEAD_ONLY_MAX_DEG * 0.5, total_yaw_deg)
    head_deg = total_yaw_deg - body_deg
    body_rad = np.deg2rad(body_deg)
    return float(body_rad), head_deg


def _wait_for_voice(robot, timeout: float = DOA_TIMEOUT_S) -> float | None:
    """Poll DoA until speech is detected. Returns the angle in radians, or None."""
    start = time.monotonic()
    while (time.monotonic() - start) < timeout:
        result = robot.media.get_DoA()
        if result is not None:
            angle, speech = result
            if speech:
                return angle
        time.sleep(DOA_POLL_S)
    return None


def scan_all_players(robot, voice, num_players: int) -> list[RegisteredPlayer]:
    """Locate each player by voice, record them describing their hero
    (used for both voice cloning and character generation)."""
    from src.audio import transcribe
    from src.voice_clone import clone_voice, record_voice_sample

    print("\n  Player Registration (DoA + Hero + Voice Clone)")
    print("  " + "=" * 40)
    voice.announce(
        "Let me find where everyone is sitting! "
        "Each player, say hello when I call you, then describe "
        "the kind of hero you want to be. Speak for about ten seconds "
        "so I can learn your voice too!"
    )

    players: list[RegisteredPlayer] = []

    for i in range(1, num_players + 1):
        voice.announce(f"Player {i}, please say hello!")
        print(f"  Waiting for player {i} to speak...")

        doa_angle = _wait_for_voice(robot)

        if doa_angle is not None:
            yaw = doa_to_yaw_deg(doa_angle)
            logger.info("Player %d: DoA=%.2f rad -> yaw=%.1f°", i, doa_angle, yaw)
        else:
            yaw = 0.0
            logger.warning("No voice detected for player %d — defaulting to front.", i)

        # Rotate body + head toward the player
        body_rad, head_deg = _split_yaw(yaw)
        pose = create_head_pose(pitch=0, yaw=head_deg, roll=0, degrees=True, mm=True)
        robot.goto_target(head=pose, body_yaw=body_rad, duration=0.6)
        time.sleep(0.7)

        if voice.emotions:
            voice.emotions.set_base_yaw(head_deg)

        voice.announce(
            "Found you! Now tell me, what kind of hero do you want to be? "
            "A sneaky rogue? A powerful wizard? A brave warrior? "
            "Describe your dream character! Keep talking for about ten seconds."
        )
        print(f"  Recording hero description + voice sample for player {i} (~12s)...")
        audio = record_voice_sample(robot)

        # Transcribe the description for character generation
        hero_desc = None
        cloned_id = None
        if audio is not None:
            hero_desc = transcribe(audio)
            if hero_desc:
                print(f"  Player {i} wants: \"{hero_desc}\"")
            else:
                print(f"  Could not transcribe player {i}'s description.")

            # Clone the voice in parallel-ish
            print(f"  Cloning voice for player {i}...")
            cloned_id = clone_voice(audio, i)
            if cloned_id:
                print(f"  Voice cloned: {cloned_id}")
            else:
                print(f"  Voice clone failed — will use preset voice.")
        else:
            print(f"  No audio captured for player {i}.")

        voice.announce("Great choice!")
        players.append(RegisteredPlayer(
            real_name=f"Player {i}",
            yaw_deg=yaw,
            cloned_voice_id=cloned_id,
            hero_description=hero_desc,
        ))

    # Return to center (body + head)
    if voice.emotions:
        voice.emotions.set_base_yaw(0.0)
    neutral = create_head_pose(pitch=0, yaw=0, roll=0, degrees=True, mm=True)
    robot.goto_target(head=neutral, body_yaw=0.0, duration=0.5)
    time.sleep(0.5)

    voice.announce("Got everyone! Now let me craft your adventure!")
    return players


def assign_characters(
    players: list[RegisteredPlayer], party,
) -> dict[str, RegisteredPlayer]:
    """Map each RegisteredPlayer to a party character. Returns dict keyed by character name."""
    registry: dict[str, RegisteredPlayer] = {}
    for i, p in enumerate(players):
        if i < len(party.players):
            char = party.players[i]
            p.character_name = char.name
            registry[char.name] = p
    return registry


def apply_cloned_voices(registry: dict[str, RegisteredPlayer], voice_map: dict[str, str]):
    """Override voice_map entries with cloned voice_ids where available."""
    for char_name, rp in registry.items():
        if rp.cloned_voice_id:
            voice_map[char_name] = rp.cloned_voice_id
            print(f"  [Voice] {char_name} -> cloned voice ({rp.cloned_voice_id})")
        else:
            print(f"  [Voice] {char_name} -> preset voice ({voice_map.get(char_name, 'default')})")


class PlayerSweep:
    """Slowly rotate between player positions in a background thread."""

    def __init__(self, robot, players: list[RegisteredPlayer]):
        self._robot = robot
        self._players = players
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        if len(self._players) < 2:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _loop(self):
        idx = 0
        direction = 1
        try:
            while self._running:
                p = self._players[idx]
                body_rad, head_deg = _split_yaw(p.yaw_deg)
                pose = create_head_pose(
                    pitch=random.uniform(-2, 2),
                    yaw=head_deg,
                    roll=0,
                    degrees=True, mm=True,
                )
                self._robot.goto_target(
                    head=pose, body_yaw=body_rad, duration=1.2,
                )
                time.sleep(1.5)
                if not self._running:
                    break
                idx += direction
                if idx >= len(self._players) or idx < 0:
                    direction *= -1
                    idx += direction
        except Exception:
            pass


def face_player(robot, player: RegisteredPlayer, duration: float = 0.8):
    """Rotate Reachy's body + head toward the given player."""
    body_rad, head_deg = _split_yaw(player.yaw_deg)
    pose = create_head_pose(pitch=0, yaw=head_deg, roll=0, degrees=True, mm=True)
    robot.goto_target(head=pose, body_yaw=body_rad, duration=duration)
    time.sleep(duration + 0.1)


def face_neutral(robot, duration: float = 0.5):
    """Return Reachy's body + head to neutral (facing front)."""
    pose = create_head_pose(pitch=0, yaw=0, roll=0, degrees=True, mm=True)
    robot.goto_target(head=pose, body_yaw=0.0, duration=duration)
