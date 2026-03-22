"""
Player registration for the current game session.

Reachy rotates to each player position (evenly spaced), asks
their name, and stores name + yaw angle. During the game,
Reachy turns to face the active player on their turn.

No camera, no face detection -- just in-memory state.
"""

import logging
import time
from dataclasses import dataclass

from reachy_mini.utils import create_head_pose

logger = logging.getLogger(__name__)

SCAN_MIN_DEG = -50.0
SCAN_MAX_DEG = 50.0


@dataclass
class RegisteredPlayer:
    real_name: str
    yaw_deg: float
    character_name: str | None = None


def _player_positions(num_players: int) -> list[float]:
    """Evenly space players across the yaw range."""
    if num_players == 1:
        return [0.0]
    step = (SCAN_MAX_DEG - SCAN_MIN_DEG) / (num_players - 1)
    return [SCAN_MIN_DEG + i * step for i in range(num_players)]


def scan_all_players(robot, voice, num_players: int) -> list[RegisteredPlayer]:
    """Rotate to each player position and ask for their name."""
    from src import voice_input

    print("\n  Player Registration")
    print("  " + "=" * 40)
    voice.announce("Let me meet everyone!")

    positions = _player_positions(num_players)
    players: list[RegisteredPlayer] = []

    for i, yaw in enumerate(positions):
        pose = create_head_pose(pitch=0, yaw=yaw, roll=0, degrees=True, mm=True)
        robot.goto_target(head=pose, duration=0.6)
        time.sleep(0.7)

        voice.announce(f"Hello, player {i + 1}! What should I call you?")
        name = voice_input.ask_text("What should I call you?")
        if not name:
            name = f"Player {i + 1}"

        voice.announce(f"Nice to meet you, {name}!")
        players.append(RegisteredPlayer(real_name=name, yaw_deg=yaw))
        print(f"  Player {i + 1}: {name} (yaw: {yaw:.0f}°)")

    # Return to center
    neutral = create_head_pose(pitch=0, yaw=0, roll=0, degrees=True, mm=True)
    robot.goto_target(head=neutral, duration=0.5)
    time.sleep(0.5)

    names = ", ".join(p.real_name for p in players)
    voice.announce(f"Great! Welcome {names}! Let's begin!")
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


def face_player(robot, player: RegisteredPlayer, duration: float = 0.6):
    """Turn Reachy's head toward the given player's stored position."""
    pose = create_head_pose(pitch=0, yaw=player.yaw_deg, roll=0, degrees=True, mm=True)
    robot.goto_target(head=pose, duration=duration)
    time.sleep(duration + 0.1)


def face_neutral(robot, duration: float = 0.4):
    """Return Reachy's head to neutral (facing front)."""
    pose = create_head_pose(pitch=0, yaw=0, roll=0, degrees=True, mm=True)
    robot.goto_target(head=pose, duration=duration)
