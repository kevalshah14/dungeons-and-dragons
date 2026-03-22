"""Dungeons & Dragons: AI Dungeon Master on Reachy Mini.

Pipeline:
  "Hey Reachy" wake word -> voice onboarding -> game loop
  Reachy mic -> Gemini STT -> Gemini DM -> Minimax TTS -> Reachy speaker
"""

import logging
import math
import os
import random
import time

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from reachy_mini import ReachyMini

from reachy_mini.utils import create_head_pose

from src.dungeon_master import DungeonMaster
from src.models import DynamicScene, GameState
from src.player_registry import (
    RegisteredPlayer,
    assign_characters,
    face_neutral,
    face_player,
    scan_all_players,
)
from src.reachy_emotions import ReachyEmotions, classify_scene
from src.tts import GameVoice
from src import voice_input
from src.wake_word import wait_for_wake_word, set_robot as set_wake_robot


# ---------------------------------------------------------------------------
# Onboarding — ask players & theme via Reachy mic/speaker
# ---------------------------------------------------------------------------

def run_onboarding(robot: ReachyMini, voice: GameVoice) -> tuple[int, str | None]:
    """Use Reachy's mic + speaker to gather num_players and theme."""
    print("\n  Phase 1: Voice Onboarding")
    print("  Speak to Reachy to set up your adventure!\n")

    voice.announce(
        "Greetings, adventurers! I am Reachy, your Dungeon Master! "
        "Let's set up your quest."
    )

    num_players = voice_input.ask_number(
        "How many brave heroes are joining this quest? Say a number from 1 to 6.",
        min_val=1,
        max_val=6,
    )

    theme = voice_input.ask_text(
        "What kind of adventure calls to you? "
        "Fantasy, pirate, horror, space, or something else? "
        "Say skip if you want me to choose."
    )

    voice.announce(
        f"Wonderful! {num_players} heroes on a {theme or 'surprise'} adventure. "
        "Let me prepare your quest!"
    )

    print(f"\n  Onboarding complete: {num_players} player(s), theme={theme or 'DM picks'}")
    return num_players, theme


# ---------------------------------------------------------------------------
# Game helpers
# ---------------------------------------------------------------------------

def ability_modifier(score: int) -> int:
    return math.floor((score - 10) / 2)


ANTENNA_PULL_THRESHOLD = 0.25
ANTENNA_POLL_S = 0.02
ANTENNA_TIMEOUT_S = 30.0


def wait_for_antenna_pull(robot) -> str:
    """Block until a Reachy antenna is pulled. Returns 'left' or 'right'."""
    prev_left = False
    prev_right = False
    start = time.monotonic()

    while (time.monotonic() - start) < ANTENNA_TIMEOUT_S:
        antennas = robot.get_present_antenna_joint_positions()
        right_val, left_val = antennas[0], antennas[1]

        right_pulled = right_val < -ANTENNA_PULL_THRESHOLD
        left_pulled = left_val > ANTENNA_PULL_THRESHOLD

        if right_pulled and not prev_right:
            return "right"
        if left_pulled and not prev_left:
            return "left"

        prev_right = right_pulled
        prev_left = left_pulled
        time.sleep(ANTENNA_POLL_S)

    return "timeout"


def roll_d20(robot, voice) -> int:
    """Wait for the player to pull Reachy's antenna, then roll a d20."""
    voice.announce("Pull my antenna to roll the dice!")
    print("  Waiting for antenna pull...")

    side = wait_for_antenna_pull(robot)
    result = random.randint(1, 20)

    if side == "timeout":
        print("  No antenna pull — auto-rolling.")
    else:
        print(f"  {side.upper()} antenna pulled!")

    return result


def get_modifier_for_ability(player, ability_name: str) -> int:
    scores = player.ability_scores
    mapping = {
        "strength": scores.strength,
        "dexterity": scores.dexterity,
        "constitution": scores.constitution,
        "intelligence": scores.intelligence,
        "wisdom": scores.wisdom,
        "charisma": scores.charisma,
    }
    score = mapping.get(ability_name.lower(), 10)
    return ability_modifier(score)


def present_scene(
    robot,
    scene: DynamicScene,
    game: GameState,
    voice: GameVoice,
    emotions: ReachyEmotions,
    registry: dict[str, RegisteredPlayer] | None = None,
):
    """Narrate the scene, play dialogue, and announce options."""
    mood = classify_scene(scene.narrative)
    emotions.play_scene_emotion(mood)

    print(f"\n  {'='*50}")
    print(f"  {scene.title}")
    print(f"  {'='*50}")
    print(f"\n  {scene.narrative}\n")

    voice.narrate(scene.narrative)
    emotions.wait_for_emotion()

    for line in scene.dialogue:
        print(f"  {line.character}: \"{line.line}\"")
        voice.say(line.character, line.line)

    active = scene.active_player
    player_obj = next((p for p in game.party.players if p.name == active), None)
    hp = game.get_hp(active) if player_obj else "?"

    # Let voice_input know who the active character is
    voice_input.set_active_character(active)

    # Turn toward the active player
    if registry and active in registry:
        rp = registry[active]
        face_player(robot, rp)
        real_name = rp.real_name
        print(f"\n  >> {real_name} as {active}'s turn (HP: {hp})")
        situation_text = f"{real_name}, as {active}. {scene.situation}"
    else:
        real_name = active
        print(f"\n  >> {active}'s turn (HP: {hp})")
        situation_text = f"{active}, {scene.situation}"

    print(f"  {scene.situation}\n")
    voice.announce(situation_text)

    if scene.options:
        for i, opt in enumerate(scene.options, 1):
            risk = ""
            if opt.ability_check:
                risk = f" [Roll {opt.ability_check}, DC {opt.difficulty_class}]"
            print(f"    {i}. {opt.description}{risk}")
        options_speech = ". ".join(
            f"Option {i}, {opt.description}"
            for i, opt in enumerate(scene.options, 1)
        )
        voice.announce(f"Your choices are: {options_speech}")


def handle_turn(
    robot: ReachyMini,
    scene: DynamicScene,
    game: GameState,
    voice: GameVoice,
    emotions: ReachyEmotions,
    registry: dict[str, RegisteredPlayer] | None = None,
) -> str:
    """Get player choice, resolve dice roll via antenna pull, return action summary."""
    if not scene.options:
        return "The adventure ends here."

    choice_idx = voice_input.ask_choice(
        "What do you choose?",
        [opt.description for opt in scene.options],
    )
    chosen = scene.options[choice_idx]
    active = scene.active_player
    player_obj = next((p for p in game.party.players if p.name == active), None)

    # Use real name when addressing
    real_name = registry[active].real_name if registry and active in registry else active

    print(f"\n  {real_name} as {active} chose: {chosen.description}")
    voice.announce(f"{real_name} chooses to {chosen.description}")

    summary_parts = [f"{active} chose: {chosen.description}."]

    if chosen.ability_check and chosen.difficulty_class and player_obj:
        emotions.play_emotion("inquiring1")
        raw_roll = roll_d20(robot, voice)
        mod = get_modifier_for_ability(player_obj, chosen.ability_check)
        proficiency = 2
        total = raw_roll + mod + proficiency
        dc = chosen.difficulty_class

        is_crit = raw_roll == 20
        is_fumble = raw_roll == 1
        success = is_crit or (not is_fumble and total >= dc)

        roll_announcement = (
            f"Roll for {chosen.ability_check}! "
            f"The die shows... {raw_roll}! "
            f"Plus {mod} modifier, plus {proficiency} proficiency... "
            f"Total: {total} against DC {dc}!"
        )
        voice.announce(roll_announcement)
        print(f"  Roll: d20={raw_roll} + {mod} + {proficiency} = {total} vs DC {dc}")

        if is_crit:
            voice.announce("CRITICAL HIT! Natural twenty!")
            emotions.play_roll_emotion("critical")
            print("  CRITICAL HIT!")
            summary_parts.append(
                f"Dice roll: natural 20 (CRITICAL HIT). Total {total} vs DC {dc}. Automatic success."
            )
        elif is_fumble:
            voice.announce("Oh no! Natural one! A fumble!")
            emotions.play_roll_emotion("fumble")
            print("  FUMBLE!")
            damage = int((chosen.damage_on_fail or 0) * 1.5) if chosen.damage_on_fail else 0
            if damage > 0 and player_obj:
                new_hp = game.apply_damage(active, damage)
                voice.announce(f"{active} takes {damage} damage! HP: {new_hp}")
                print(f"  {active} takes {damage} damage -> HP: {new_hp}")
                summary_parts.append(
                    f"Dice roll: natural 1 (FUMBLE). {active} takes {damage} damage (50% extra). HP now {new_hp}."
                )
            else:
                summary_parts.append(
                    f"Dice roll: natural 1 (FUMBLE). Total {total} vs DC {dc}. Failure with comedic mishap."
                )
        elif success:
            voice.announce(f"Success! {total} beats the DC!")
            emotions.play_roll_emotion("success")
            print(f"  SUCCESS!")
            summary_parts.append(
                f"Dice roll: {raw_roll} + {mod} + {proficiency} = {total} vs DC {dc}. Success!"
            )
        else:
            voice.announce(f"Failed! {total} doesn't beat DC {dc}.")
            emotions.play_roll_emotion("fail")
            print(f"  FAILED!")
            damage = chosen.damage_on_fail or 0
            if damage > 0 and player_obj:
                new_hp = game.apply_damage(active, damage)
                voice.announce(f"{active} takes {damage} damage! HP: {new_hp}")
                print(f"  {active} takes {damage} damage -> HP: {new_hp}")
                summary_parts.append(
                    f"Dice roll: {raw_roll} + {mod} + {proficiency} = {total} vs DC {dc}. "
                    f"Failure. {active} takes {damage} damage. HP now {new_hp}."
                )
            else:
                summary_parts.append(
                    f"Dice roll: {raw_roll} + {mod} + {proficiency} = {total} vs DC {dc}. Failure."
                )

        if player_obj and not game.is_conscious(active):
            voice.announce(f"{active} has been knocked out!")
            emotions.play_emotion("dying1")
            summary_parts.append(f"{active} is knocked out at 0 HP!")
    else:
        summary_parts.append("No dice roll needed (safe action).")

    if game.all_knocked_out():
        summary_parts.append("ALL players are knocked out. The adventure ends in defeat.")

    hp_summary = ", ".join(
        f"{p.name}: {game.get_hp(p.name)} HP" for p in game.party.players
    )
    summary_parts.append(f"Current party HP: {hp_summary}")

    return " ".join(summary_parts)


# ---------------------------------------------------------------------------
# Full game run
# ---------------------------------------------------------------------------

def run_game(
    robot: ReachyMini,
    voice: GameVoice,
    emotions: ReachyEmotions,
    num_players: int,
    theme: str | None,
    players: list | None = None,
):
    """Run the D&D game with Gemini + Minimax TTS."""
    print("\n  Phase 2: The Adventure Begins!")
    print("  " + "=" * 50)

    gemini_key = os.getenv("GEMINI_API_KEY")
    dm = DungeonMaster(api_key=gemini_key)

    game = dm.create_game(num_players, theme)
    voice.setup_voices(game.party, game.story)

    # Map real players to characters
    registry: dict[str, RegisteredPlayer] | None = None
    if players:
        registry = assign_characters(players, game.party)
        voice.set_registry(registry)
        voice_input.set_registry(registry)

        for char_name, rp in registry.items():
            char = next((c for c in game.party.players if c.name == char_name), None)
            if char:
                face_player(robot, rp)
                intro = (
                    f"{rp.real_name}, you will play as {char.name}, "
                    f"a {char.gender} {char.race.value} {char.character_class.value}! "
                    f"{char.backstory}"
                )
                voice.announce(intro)
                print(f"  {rp.real_name} -> {char.name}: {char.race.value} {char.character_class.value}")
                time.sleep(0.3)

        face_neutral(robot)
    else:
        for p in game.party.players:
            intro = (
                f"{p.name}, a {p.gender} {p.race.value} {p.character_class.value}. "
                f"{p.backstory}"
            )
            voice.say(p.name, intro)
            print(f"  {p.name}: {p.race.value} {p.character_class.value} — {p.backstory}")

    voice.announce(
        f"Your quest: {game.story.main_quest}. Let the adventure begin!"
    )
    emotions.play_scene_emotion("exploration")

    dm.start_session(game.story, game.party)
    scene = dm.get_first_scene()
    game.current_scene = scene
    game.turn_number = 1

    while True:
        present_scene(robot, scene, game, voice, emotions, registry)

        if scene.is_ending:
            ending = scene.ending_type or "unknown"
            if ending == "victory":
                emotions.play_scene_emotion("victory", sound=True)
                voice.announce("Victory! The heroes triumph!")
            elif ending == "defeat":
                emotions.play_scene_emotion("defeat")
                voice.announce("Defeat. The heroes have fallen.")
            else:
                emotions.play_scene_emotion("sad")
                voice.announce("The adventure ends.")
            break

        if game.all_knocked_out():
            emotions.play_scene_emotion("defeat")
            voice.announce("All heroes have fallen. The adventure ends in defeat.")
            break

        action_summary = handle_turn(robot, scene, game, voice, emotions, registry)

        game.turn_number += 1
        print(f"\n  [Turn {game.turn_number}] DM is thinking...")
        voice.announce("The story continues...")

        try:
            scene = dm.play_turn(action_summary)
            game.current_scene = scene
        except Exception as e:
            logger.error("Gemini error: %s", e)
            voice.announce("The Dungeon Master pauses for a moment...")
            try:
                scene = dm.play_turn(action_summary)
                game.current_scene = scene
            except Exception:
                voice.announce(
                    "I'm sorry adventurers, the magic has faded. "
                    "Perhaps we shall continue another time."
                )
                break

    face_neutral(robot)
    voice.announce("Would you like to play again?")
    if voice_input.ask_confirm("Play another adventure?"):
        run_game(robot, voice, emotions, num_players, theme, players)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def print_banner():
    print(
        r"""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║        ⚔️  DUNGEONS & DRAGONS: AI DUNGEON MASTER  ⚔️     ║
    ║              Reachy Mini + Gemini + Minimax               ║
    ║                                                          ║
    ║   Reachy mic → Gemini STT → Gemini DM → Minimax TTS     ║
    ║                Say "Hey Reachy" to begin!                 ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    print_banner()

    print("  Connecting to Reachy Mini...")
    try:
        robot = ReachyMini()
    except Exception as e:
        logger.error("Failed to connect to Reachy Mini: %s", e)
        print("  Could not connect. Is reachy-mini-daemon running?")
        return

    print("  Reachy Mini connected!\n")

    try:
        robot.media.start_recording()
        robot.media.start_playing()
        time.sleep(1)

        voice = GameVoice()
        voice.set_reachy(robot)

        emotions = ReachyEmotions(robot)
        emotions.load()
        voice.emotions = emotions

        voice_input.set_voice(voice)
        voice_input.set_robot(robot)
        set_wake_robot(robot)

        # Reachy sleeps until woken up.
        sleep_pose = create_head_pose(pitch=-20, yaw=0, roll=0, degrees=True, mm=True)
        robot.goto_target(head=sleep_pose, duration=1.5)
        time.sleep(1.5)
        print("  Reachy is sleeping... say 'Hey Reachy' to wake up!\n")

        wait_for_wake_word()

        # Wake up!
        awake_pose = create_head_pose(pitch=0, yaw=0, roll=0, degrees=True, mm=True)
        robot.goto_target(head=awake_pose, duration=0.5)
        time.sleep(0.5)
        emotions.play_emotion("cheerful1")

        num_players, theme = run_onboarding(robot, voice)

        # Player registration: scan faces + store positions
        players = scan_all_players(robot, voice, num_players)

        run_game(robot, voice, emotions, num_players, theme, players)

    except KeyboardInterrupt:
        logger.info("Game interrupted.")
    finally:
        try:
            robot.media.stop_recording()
        except Exception:
            pass
        try:
            robot.media.stop_playing()
        except Exception:
            pass
        try:
            robot.media.close()
        except Exception:
            pass
        robot.client.disconnect()
        time.sleep(1)
        print("\n  Thanks for playing! Until the next adventure.")


if __name__ == "__main__":
    main()
