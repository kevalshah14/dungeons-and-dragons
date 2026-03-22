import os
import random

from dotenv import load_dotenv

from src.dungeon_master import DungeonMaster
from src.models import GameState, DynamicScene, ActionOption, TurnRecord
from src.tts import GameVoice

load_dotenv()

voice = GameVoice()

PROFICIENCY_BONUS = 2


def roll_d20() -> int:
    return random.randint(1, 20)


def get_ability_modifier(score: int) -> int:
    return (score - 10) // 2


def hp_bar(current: int, maximum: int, width: int = 20) -> str:
    if maximum <= 0:
        return "[dead] 0/0"
    ratio = max(0, current) / maximum
    filled = int(ratio * width)
    empty = width - filled
    if ratio > 0.5:
        bar_char = "█"
    elif ratio > 0.25:
        bar_char = "▓"
    else:
        bar_char = "▒"
    return f"[{bar_char * filled}{'░' * empty}] {current}/{maximum}"


def print_banner():
    print(r"""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║        ⚔️  DUNGEONS & DRAGONS: AI DUNGEON MASTER  ⚔️     ║
    ║                                                          ║
    ║           The dice are ready. The story awaits.          ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)


def print_story_summary(game: GameState):
    s = game.story
    print(f"\n{'─'*60}")
    print(f"  📜 {s.title}")
    print(f"{'─'*60}")
    print(f"\n  Setting: {s.setting}")
    print(f"  Difficulty: {s.difficulty.value}")
    print(f"\n  {s.backstory}")
    print(f"\n  🎯 Quest: {s.main_quest}")

    voice.narrate(
        f"{s.title}. {s.setting}. {s.backstory} Your quest: {s.main_quest}"
    )

    print(f"\n  📍 Locations:")
    for loc in s.key_locations:
        print(f"    - {loc.name}: {loc.description[:80]}...")

    print(f"\n  👥 Key NPCs:")
    for npc in s.key_npcs:
        print(f"    - {npc.name} ({npc.gender}, {npc.role}): {npc.description[:80]}...")

    npc_intro = "Let me introduce the key characters. " + " ".join(
        f"{npc.name}, the {npc.role}." for npc in s.key_npcs
    )
    voice.narrate(npc_intro)
    for npc in s.key_npcs:
        voice.say(npc.name, npc.description[:120])


def print_party(game: GameState):
    print(f"\n{'─'*60}")
    print(f"  🛡️  THE PARTY: {game.party.party_name or 'Unnamed Adventurers'}")
    print(f"{'─'*60}")
    print(f"  {game.party.shared_goal}\n")

    heroes_intro = "And now, your heroes. " + " ".join(
        f"{p.name}, a {p.gender} {p.race.value} {p.character_class.value}."
        for p in game.party.players
    )
    voice.narrate(heroes_intro)

    for i, p in enumerate(game.party.players, 1):
        scores = p.ability_scores
        print(f"  ── Player {i}: {p.name} ──")
        print(f"     {p.gender.title()} {p.race.value} {p.character_class.value} | Level {p.level}")
        print(f"     HP: {p.hit_points} | AC: {p.armor_class}")
        print(f"     STR:{scores.strength:>3} DEX:{scores.dexterity:>3} CON:{scores.constitution:>3}")
        print(f"     INT:{scores.intelligence:>3} WIS:{scores.wisdom:>3} CHA:{scores.charisma:>3}")
        print(f"     Abilities: {', '.join(p.abilities[:3])}")
        print(f"     Traits: {', '.join(p.personality_traits)}")
        print(f"     Gear: {', '.join(p.inventory[:5])}")
        print()

        voice.say(p.name, f"I'm {p.name}. {p.backstory[:100]}")


def print_hp_status(game: GameState):
    print(f"\n  {'─'*40}")
    for p in game.party.players:
        current = game.get_hp(p.name)
        bar = hp_bar(current, p.hit_points)
        status = ""
        if current <= 0:
            status = " 💀 KNOCKED OUT"
        elif current <= p.hit_points * 0.25:
            status = " ⚠️  badly hurt"
        elif current <= p.hit_points * 0.5:
            status = " 🩹 wounded"
        print(f"    {p.name:>12}: {bar}{status}")
    print(f"  {'─'*40}")


def find_player_by_name(game: GameState, name: str):
    for p in game.party.players:
        if p.name.lower() == name.lower():
            return p
    return None


def get_ability_score(player, ability: str) -> int:
    score_map = {
        "strength": player.ability_scores.strength,
        "dexterity": player.ability_scores.dexterity,
        "constitution": player.ability_scores.constitution,
        "intelligence": player.ability_scores.intelligence,
        "wisdom": player.ability_scores.wisdom,
        "charisma": player.ability_scores.charisma,
    }
    return score_map.get(ability.lower(), 10)


def resolve_option(option: ActionOption, player_name: str, game: GameState) -> dict:
    player = find_player_by_name(game, player_name)

    result = {
        "player_name": player_name,
        "action": option.description,
        "ability_checked": None,
        "roll": None,
        "modifier": None,
        "proficiency": None,
        "total": None,
        "dc": None,
        "succeeded": None,
        "was_critical": False,
        "was_fumble": False,
        "damage_taken": 0,
        "hp_after": game.get_hp(player_name),
    }

    if option.ability_check and option.difficulty_class:
        ability = option.ability_check.lower()
        score = get_ability_score(player, ability) if player else 10
        modifier = get_ability_modifier(score)
        prof = PROFICIENCY_BONUS

        print(f"\n     🎲 {player_name} rolls {ability.upper()} (DC {option.difficulty_class})")
        voice.announce(
            f"{player_name}! Roll for {ability}. "
            f"You need a {option.difficulty_class} or higher."
        )
        try:
            input(f"     Press Enter to roll... ")
        except (EOFError, KeyboardInterrupt):
            pass

        raw_roll = roll_d20()
        is_crit = raw_roll == 20
        is_fumble = raw_roll == 1
        total = raw_roll + modifier + prof

        if is_crit:
            passed = True
        elif is_fumble:
            passed = False
        else:
            passed = total >= option.difficulty_class

        result["ability_checked"] = ability
        result["roll"] = raw_roll
        result["modifier"] = modifier
        result["proficiency"] = prof
        result["total"] = total
        result["dc"] = option.difficulty_class
        result["succeeded"] = passed
        result["was_critical"] = is_crit
        result["was_fumble"] = is_fumble

        print(f"        d20 = {raw_roll}  +{modifier} (mod)  +{prof} (prof)  = {total}")

        announce_parts = []
        if is_crit:
            print(f"     🌟 NATURAL 20 -- CRITICAL HIT!")
            announce_parts.append(f"Natural twenty! Critical hit! {player_name} is unstoppable!")
        elif is_fumble:
            print(f"     💥 NATURAL 1 -- FUMBLE!")
            announce_parts.append(f"Natural one. Oh no, {player_name}! That's a fumble!")
        elif passed:
            print(f"     ✅ SUCCESS! ({total} beats DC {option.difficulty_class})")
            announce_parts.append(f"{total} beats {option.difficulty_class}. {player_name} succeeds!")
        else:
            print(f"     ❌ FAIL! ({total} doesn't beat DC {option.difficulty_class})")
            announce_parts.append(f"{total} against {option.difficulty_class}. {player_name} fails!")

        if not passed and option.damage_on_fail:
            dmg = option.damage_on_fail
            if is_fumble:
                dmg = dmg + (dmg // 2)
                print(f"     💥 Fumble! Takes {dmg} damage!")
            else:
                print(f"     💔 Takes {dmg} damage!")

            new_hp = game.apply_damage(player_name, dmg)
            result["damage_taken"] = dmg
            result["hp_after"] = new_hp

            if new_hp <= 0:
                print(f"     💀 {player_name} is KNOCKED OUT!")
                announce_parts.append(f"{player_name} is knocked out!")
            else:
                bar = hp_bar(new_hp, player.hit_points if player else 10)
                print(f"     HP: {bar}")
                announce_parts.append(f"{player_name} takes {dmg} damage. {new_hp} hit points left.")
        elif passed:
            result["hp_after"] = game.get_hp(player_name)

        voice.announce(" ".join(announce_parts))

    else:
        result["succeeded"] = True
        print(f"     ✅ No roll needed.")

    return result


def build_action_summary(result: dict, game: GameState) -> str:
    player = find_player_by_name(game, result["player_name"])
    class_info = f" ({player.race.value} {player.character_class.value})" if player else ""
    r = result

    parts = [f"{r['player_name']}{class_info} chose: \"{r['action']}\"."]

    if r["ability_checked"]:
        if r["was_critical"]:
            parts.append(
                f"NATURAL 20 -- CRITICAL HIT! "
                f"(d20=20 + {r['modifier']} mod + {r['proficiency']} prof = {r['total']} vs DC {r['dc']}). "
                f"Describe something EPIC. Make this the highlight of the story."
            )
        elif r["was_fumble"]:
            parts.append(
                f"NATURAL 1 -- FUMBLE! "
                f"(d20=1 + {r['modifier']} mod + {r['proficiency']} prof = {r['total']} vs DC {r['dc']}). "
                f"Describe something FUNNY and silly. Not cruel, just clumsy."
            )
            if r["damage_taken"]:
                parts.append(f"They took {r['damage_taken']} damage from the fumble.")
        elif r["succeeded"]:
            margin = r["total"] - r["dc"]
            feel = "a really smooth, confident success" if margin >= 5 else "a close call -- just barely made it"
            parts.append(
                f"{r['ability_checked'].upper()} check SUCCEEDED "
                f"(rolled {r['total']} vs DC {r['dc']}). Describe it as {feel}."
            )
        else:
            parts.append(
                f"{r['ability_checked'].upper()} check FAILED "
                f"(rolled {r['total']} vs DC {r['dc']}). "
                f"Describe the struggle and what went wrong."
            )
            if r["damage_taken"]:
                parts.append(f"They took {r['damage_taken']} damage!")
        if r["hp_after"] is not None and r["hp_after"] <= 0:
            parts.append(f"{r['player_name']} is KNOCKED OUT at 0 HP!")
    else:
        parts.append("No dice roll was needed. They just did it.")

    hp_lines = []
    for p in game.party.players:
        hp = game.get_hp(p.name)
        hp_lines.append(f"  {p.name}: {hp}/{p.hit_points} HP" + (" (knocked out)" if hp <= 0 else ""))
    parts.append("\nParty HP:\n" + "\n".join(hp_lines))

    if game.all_knocked_out():
        parts.append("\nALL PLAYERS KNOCKED OUT! End the adventure in defeat.")
    else:
        parts.append(
            "\nNow write the next scene. Tell the story of what happened because of this action. "
            "Then pick which player acts next -- whoever the story naturally turns to."
        )

    return "\n".join(parts)


def play_scene(scene: DynamicScene, game: GameState, dm: DungeonMaster) -> DynamicScene | None:
    game.turn_number += 1

    print(f"\n{'═'*60}")
    print(f"  Chapter {game.turn_number}: {scene.title}")
    print(f"{'═'*60}")

    # --- DM narrates the scene ---
    print(f"\n  {scene.narrative}")
    voice.narrate(scene.narrative)

    # --- Character dialogue with announcements ---
    for dl in scene.dialogue:
        print(f"\n     💬 {dl.character}: \"{dl.line}\"")
        voice.say(dl.character, dl.line)

    # --- Check for ending ---
    if scene.is_ending or not scene.options:
        ending_emoji = {"victory": "🏆", "defeat": "💀", "bittersweet": "🌅"}.get(
            scene.ending_type or "", "🔚"
        )
        print(f"\n  {ending_emoji} {(scene.ending_type or 'the end').upper()}")
        print_hp_status(game)
        print(f"\n{'═'*60}")
        print(f"  The adventure of \"{game.story.title}\" has concluded!")
        print(f"{'═'*60}")
        voice.narrate(f"And so, the adventure of {game.story.title} comes to an end.")
        game.is_over = True
        return None

    if game.all_knocked_out():
        print(f"\n  💀 The entire party has fallen!")
        voice.narrate("The entire party has fallen. The adventure is over.")
        game.is_over = True
        return None

    # --- Announce whose turn it is ---
    player = find_player_by_name(game, scene.active_player)
    if player and not game.is_conscious(scene.active_player):
        summary = (
            f"{scene.active_player} is knocked out and can't act. "
            f"Pick a different player who is still conscious."
        )
        next_scene = dm.play_turn(summary)
        game.current_scene = next_scene
        return next_scene

    class_label = ""
    current_hp = game.get_hp(scene.active_player)
    max_hp = 0
    if player:
        class_label = f" ({player.gender.title()} {player.race.value} {player.character_class.value})"
        max_hp = player.hit_points
    bar = hp_bar(current_hp, max_hp)

    print(f"\n  ── {scene.active_player}'s Turn{class_label} ──  HP: {bar}")
    voice.announce(f"{scene.active_player}! It's your turn.")

    # --- Player hears situation and options in their own voice ---
    print(f"     {scene.situation}")

    option_lines = []
    for i, opt in enumerate(scene.options, 1):
        dc_text = ""
        if opt.ability_check and opt.difficulty_class:
            dc_text = f" [🎲 {opt.ability_check.upper()} DC {opt.difficulty_class}]"
        dmg_text = ""
        if opt.damage_on_fail:
            dmg_text = f" [⚠️ {opt.damage_on_fail} dmg if fail]"
        print(f"     {i}. {opt.description}{dc_text}{dmg_text}")
        option_lines.append(f"Option {i}: {opt.description}")

    speech = scene.situation + " " + ". ".join(option_lines) + ". What do I do?"
    voice.say(scene.active_player, speech)

    # --- Player picks ---
    while True:
        try:
            raw = input(f"\n     {scene.active_player}, choose (1-{len(scene.options)}): ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(scene.options):
                break
            print(f"     Pick 1-{len(scene.options)}.")
        except ValueError:
            print(f"     Enter a number.")
        except (EOFError, KeyboardInterrupt):
            print("\n\n  The adventurers decide to rest for now...")
            return None

    chosen = scene.options[idx]
    print(f"     -> {chosen.description}")

    # --- Player character SPEAKS their action ---
    voice.say(scene.active_player, chosen.description)

    # --- Resolve the action ---
    result = resolve_option(chosen, scene.active_player, game)

    game.history.append(TurnRecord(
        turn=game.turn_number,
        scene_title=scene.title,
        narrative=scene.narrative,
        chosen_action=chosen.description,
        player_who_acted=scene.active_player,
        ability_checked=result["ability_checked"],
        dice_roll=result["roll"],
        dice_modifier=result["modifier"],
        proficiency_bonus=result["proficiency"],
        dice_total=result["total"],
        difficulty_class=result["dc"],
        succeeded=result["succeeded"],
        was_critical=result["was_critical"],
        was_fumble=result["was_fumble"],
        damage_taken=result["damage_taken"],
        hp_after=result["hp_after"],
    ))

    print_hp_status(game)

    action_summary = build_action_summary(result, game)
    print(f"\n  ⏳ The story continues...")
    next_scene = dm.play_turn(action_summary)
    game.current_scene = next_scene

    return next_scene


SAVE_DIR = os.path.join(os.path.dirname(__file__), "saves")
SAVE_PATH = os.path.join(SAVE_DIR, "game_save.json")


def save_game(game: GameState, path: str = SAVE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(game.model_dump_json(indent=2))
    print(f"  💾 Saved!")


def load_game(path: str = SAVE_PATH) -> GameState | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return GameState.model_validate_json(f.read())


def main():
    print_banner()

    while True:
        try:
            num_players = int(input("  How many players? (1-6): ").strip())
            if 1 <= num_players <= 6:
                break
            print("  Please enter a number between 1 and 6.")
        except ValueError:
            print("  Please enter a valid number.")

    theme = input("  Any theme preference? (press Enter to skip): ").strip() or None

    dm = DungeonMaster()
    game = dm.create_game(num_players, theme)

    voice.setup_voices(game.party, game.story)

    print_story_summary(game)
    print_party(game)
    save_game(game)

    print("\n  Ready to begin the adventure!")
    voice.announce("The adventure is about to begin. Are you ready?")
    start = input("  Press Enter to start (or 'q' to quit): ").strip().lower()
    if start == "q":
        print("  Until next time, adventurer...")
        return

    print("\n  ⏳ The Dungeon Master opens the book...\n")
    voice.narrate("And so, our story begins.")
    dm.start_session(game.story, game.party)
    scene = dm.get_first_scene()
    game.current_scene = scene

    while scene:
        scene = play_scene(scene, game, dm)
        save_game(game)

    print(f"\n  Thanks for playing!")
    print(f"  Chapters played: {game.turn_number}")
    crits = sum(1 for h in game.history if h.was_critical)
    fumbles = sum(1 for h in game.history if h.was_fumble)
    total_dmg = sum(h.damage_taken for h in game.history)
    print(f"  Critical hits: {crits} | Fumbles: {fumbles} | Total damage taken: {total_dmg}")


if __name__ == "__main__":
    main()
