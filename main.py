import os
import random

from dotenv import load_dotenv

from src.dungeon_master import DungeonMaster
from src.models import GameState, Scene, DiceCheck

load_dotenv()


def roll_d20() -> int:
    return random.randint(1, 20)


def get_ability_modifier(score: int) -> int:
    return (score - 10) // 2


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
    print(f"  Est. Sessions: {s.estimated_sessions}")
    print(f"\n  {s.backstory}")
    print(f"\n  🎯 Quest: {s.main_quest}")

    print(f"\n  📍 Locations:")
    for loc in s.key_locations:
        print(f"    - {loc.name} [{loc.danger_level.value}]: {loc.description[:80]}...")

    print(f"\n  👥 Key NPCs:")
    for npc in s.key_npcs:
        print(f"    - {npc.name} ({npc.role}): {npc.description[:80]}...")


def print_party(game: GameState):
    print(f"\n{'─'*60}")
    print(f"  🛡️  THE PARTY: {game.party.party_name or 'Unnamed Adventurers'}")
    print(f"{'─'*60}")
    print(f"  {game.party.shared_goal}\n")

    for i, p in enumerate(game.party.players, 1):
        scores = p.ability_scores
        print(f"  ── Player {i}: {p.name} ──")
        print(f"     {p.race.value} {p.character_class.value} | Level {p.level}")
        print(f"     HP: {p.hit_points} | AC: {p.armor_class}")
        print(f"     STR:{scores.strength:>3} DEX:{scores.dexterity:>3} CON:{scores.constitution:>3}")
        print(f"     INT:{scores.intelligence:>3} WIS:{scores.wisdom:>3} CHA:{scores.charisma:>3}")
        print(f"     Traits: {', '.join(p.personality_traits)}")
        print(f"     Gear: {', '.join(p.inventory[:5])}")
        print()


def print_game_tree_overview(game: GameState):
    tree = game.game_tree
    print(f"\n{'─'*60}")
    print(f"  🌳 ADVENTURE TREE")
    print(f"{'─'*60}")
    print(f"  Total Scenes: {len(tree.scenes)}")
    print(f"  Total Endings: {tree.total_endings}")
    print(f"  Shortest Path: {tree.critical_path_length} scenes\n")

    for scene in tree.scenes:
        marker = "🏁" if scene.is_ending else "📖"
        print(f"  {marker} [{scene.scene_id}] {scene.title}")
        for choice in scene.choices:
            print(f"      └─ {choice.description[:60]}... -> {choice.leads_to}")


def find_scene(game: GameState, scene_id: str) -> Scene | None:
    return next((s for s in game.game_tree.scenes if s.scene_id == scene_id), None)


def resolve_dice_check(check: DiceCheck, game: GameState) -> bool:
    """Roll a d20 + ability modifier against the DC."""
    party_avg = 0
    count = 0
    for p in game.party.players:
        scores = p.ability_scores
        score_map = {
            "strength": scores.strength,
            "dexterity": scores.dexterity,
            "constitution": scores.constitution,
            "intelligence": scores.intelligence,
            "wisdom": scores.wisdom,
            "charisma": scores.charisma,
        }
        ability_key = check.ability.lower()
        if ability_key in score_map:
            party_avg += score_map[ability_key]
            count += 1

    modifier = get_ability_modifier(party_avg // max(count, 1))
    roll = roll_d20()
    total = roll + modifier

    print(f"\n  🎲 Dice Check: {check.ability.upper()} (DC {check.difficulty_class})")
    print(f"     Roll: {roll} + {modifier} (modifier) = {total}")

    if total >= check.difficulty_class:
        print(f"     ✅ SUCCESS! {check.success_outcome}")
        return True
    else:
        print(f"     ❌ FAILURE! {check.failure_outcome}")
        return False


def play_scene(game: GameState) -> bool:
    """Play the current scene. Returns False if the game is over."""
    scene = find_scene(game, game.current_scene_id)
    if not scene:
        print(f"\n  ⚠️  Scene '{game.current_scene_id}' not found. The adventure ends abruptly.")
        return False

    print(f"\n{'═'*60}")
    print(f"  📖 {scene.title}")
    print(f"{'═'*60}")
    print(f"\n  {scene.narrative}")

    if scene.is_ending:
        ending_emoji = {"victory": "🏆", "defeat": "💀", "bittersweet": "🌅"}.get(
            scene.ending_type or "", "🔚"
        )
        print(f"\n  {ending_emoji} ENDING: {(scene.ending_type or 'unknown').upper()}")
        print(f"\n{'═'*60}")
        print(f"  The adventure of \"{game.story.title}\" has concluded.")
        print(f"{'═'*60}")
        return False

    if not scene.choices:
        print("\n  No choices available. The adventure ends here.")
        return False

    print(f"\n  What do you do?\n")
    for i, choice in enumerate(scene.choices, 1):
        risk = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴", "Deadly": "💀"}.get(
            choice.risk_level.value, "⚪"
        )
        print(f"    {i}. {risk} {choice.description}")

    while True:
        try:
            raw = input(f"\n  Choose (1-{len(scene.choices)}): ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(scene.choices):
                break
            print(f"  Please enter a number between 1 and {len(scene.choices)}.")
        except ValueError:
            print(f"  Please enter a valid number.")
        except (EOFError, KeyboardInterrupt):
            print("\n\n  The adventurers decide to rest for now...")
            return False

    chosen = scene.choices[idx]
    print(f"\n  ➡️  {chosen.description}")

    if chosen.dice_check:
        resolve_dice_check(chosen.dice_check, game)

    game.current_scene_id = chosen.leads_to
    return True


SAVE_DIR = os.path.join(os.path.dirname(__file__), "saves")
SAVE_PATH = os.path.join(SAVE_DIR, "game_save.json")


def save_game(game: GameState, path: str = SAVE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(game.model_dump_json(indent=2))
    print(f"\n  💾 Game saved to {path}")


def load_game(path: str = SAVE_PATH) -> GameState | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return GameState.model_validate_json(f.read())


def main():
    print_banner()

    existing = load_game()
    if existing:
        print("  A saved game was found!")
        choice = input("  Continue saved game? (y/n): ").strip().lower()
        if choice == "y":
            game = existing
            print_story_summary(game)
            print_party(game)
            print(f"\n  Resuming from scene: {game.current_scene_id}")
            print("\n  Let the adventure continue!\n")
            while play_scene(game):
                save_game(game)
            return

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

    print_story_summary(game)
    print_party(game)
    print_game_tree_overview(game)

    save_game(game)

    print("\n  Ready to begin the adventure!")
    start = input("  Press Enter to start (or 'q' to quit): ").strip().lower()
    if start == "q":
        print("  Until next time, adventurer...")
        return

    print("\n  Let the adventure begin!\n")
    while play_scene(game):
        save_game(game)


if __name__ == "__main__":
    main()
