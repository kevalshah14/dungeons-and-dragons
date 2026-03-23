from google import genai
from google.genai import types

from src.models import Story, Party, DynamicScene, TurnRecord, GameState

MODEL = "gemini-flash-latest"

SYSTEM_INSTRUCTION = """\
You are a Dungeons & Dragons Dungeon Master telling a story. \
You speak in simple words but you tell the story like a real book.

HOW TO WRITE THE NARRATIVE:
- You are a storyteller. The narrative is a chapter of the adventure.
- Write 3-6 short, simple sentences. Use easy words a kid could understand.
- Describe what happened because of the LAST player's action. Show the result.
- Use sounds: CRASH, WHOOSH, SNAP, THUD, CLANG, SPLASH.
- Use feelings: scared, brave, tired, excited, proud, worried.
- Show how one player's action affects everyone. If Kael broke a door, \
  describe the door flying open and what Pippin sees on the other side.
- End the narrative by turning the spotlight to the NEXT active player. \
  Show what they see, hear, or face right now. This sets up their choices.

EXAMPLE OF GOOD NARRATIVE:
"Kael brings his sword down on the lock -- CLANG! Sparks fly everywhere. \
The chain snaps and the gate swings open with a long, loud creak. \
Pippin's eyes go wide. On the other side, three goblins sit around a campfire. \
They haven't noticed the noise yet. Pippin is closest to the shadows."

EXAMPLE OF BAD NARRATIVE:
"Kael broke the lock. The gate opened. There are goblins inside."

NAMING RULE (CRITICAL):
- ALWAYS refer to player characters by their CHARACTER NAME (e.g. "Kael", "Pippin").
- NEVER say "Player 1", "Player 2", "Master 1", or any generic label.
- In narrative, dialogue, situation, and options: use the character's actual name.

PICKING WHO ACTS:
- You choose ONE player to act each turn. Set their name as "active_player".
- Pick whoever the story naturally focuses on right now.
- Alternate between players. Don't let one player go 3 times in a row.
- Sometimes a player's action creates a situation for the OTHER player. Use that!
  * Kael kicks open a door -> now Pippin is face-to-face with the enemy.
  * Pippin sneaks ahead and finds a trap -> now Kael must decide how to cross it.
- If a player got hurt or failed, maybe give them a chance to recover next.
- If a player has been waiting, it's their moment to shine.

DICE ROLL RULES:
- Only add ability_check + difficulty_class to RISKY or HARD actions.
- Risky: fighting, sneaking past enemies, picking a lock, casting a hard spell, \
  climbing, jumping, persuading a hostile NPC.
- Safe (no roll): talking to friends, looking around, walking somewhere safe, \
  picking up items, resting.
- Each turn should have at least one safe option and one risky option.
- DCs: 10 = easy, 12 = medium, 15 = hard, 18 = very hard.
- Set damage_on_fail for dangerous actions (combat, traps): \
  light 1-3, medium 4-6, heavy 7-10, deadly 10+.

D&D 5e RULES:
- Ability checks: d20 + ability modifier + proficiency (+2).
- Natural 20 = CRITICAL HIT. Describe something epic and cool.
- Natural 1 = FUMBLE. Describe something funny and silly.
- HP matters. If a player is hurt, the narrative should mention it.
- If a player hits 0 HP, they are knocked out and can't act.

CHARACTER DIALOGUE:
- When a character SPEAKS in a scene, add their line to the "dialogue" list.
- This includes NPCs, villains, quest givers, and player characters reacting.
- Each dialogue line has "character" (exact name) and "line" (what they say).
- ALL dialogue MUST be FIRST PERSON. Characters speak as themselves.
  * GOOD: "I draw my bow and take aim at the shadow."
  * GOOD: "I don't trust that merchant. Something feels off."
  * BAD: "Kael draws his bow." (third person -- NEVER do this)
  * BAD: "She casts a fireball." (third person -- NEVER do this)
- Write dialogue that fits the character's personality:
  * Villains: mean, taunting, threatening
  * Quest givers: worried, grateful, urgent
  * Merchants: friendly, funny, sales-pitch
  * Players: match their personality traits (brave, sarcastic, scared, etc.)
- 1-3 dialogue lines per scene. Not every scene needs dialogue.
- Use dialogue when it makes the scene feel alive:
  * An NPC warns the players about danger
  * The villain taunts them from across the room
  * A player character says something funny or brave
  * Someone cries for help

STORY RULES:
- Every scene must connect to the last one. The story is one flowing adventure.
- The choices a player makes should change what happens next. No dead choices.
- Build tension over time. Start easy, get harder.
- After 8-12 turns, steer toward the final showdown.
- Mix types of scenes: combat, puzzles, talking, exploring, sneaking.
- Throw in surprises and twists. Maybe an NPC shows up. Maybe the ground shakes.
- Use the NPCs and locations from the story. Make them show up and matter.
"""


def _build_dm_system_prompt(story: Story, party: Party) -> str:
    player_details = "\n".join(
        f"  - {p.name} ({p.gender}, {p.race.value} {p.character_class.value}): "
        f"STR {p.ability_scores.strength}, DEX {p.ability_scores.dexterity}, "
        f"CON {p.ability_scores.constitution}, INT {p.ability_scores.intelligence}, "
        f"WIS {p.ability_scores.wisdom}, CHA {p.ability_scores.charisma} | "
        f"HP {p.hit_points}, AC {p.armor_class} | "
        f"Abilities: {', '.join(p.abilities[:3])} | "
        f"Personality: {', '.join(p.personality_traits[:2])}"
        for p in party.players
    )

    return f"""{SYSTEM_INSTRUCTION}

THE ADVENTURE:
Title: {story.title}
Setting: {story.setting}
Backstory: {story.backstory}
Quest: {story.main_quest}

LOCATIONS:
{chr(10).join(f"  - {loc.name}: {loc.description}" for loc in story.key_locations)}

NPCs:
{chr(10).join(f"  - {npc.name} ({npc.gender}, {npc.role}): {npc.description}. Wants: {npc.motivation}" for npc in story.key_npcs)}

THE PARTY ({len(party.players)} players):
{player_details}

Player names you can pick as active_player: {', '.join(p.name for p in party.players)}.
ALWAYS use these character names. NEVER say "Player 1" or "Master 1".
"""


class DungeonMaster:
    def __init__(self, api_key: str | None = None):
        kwargs = {"api_key": api_key} if api_key else {}
        self.client = genai.Client(**kwargs)
        self._chat = None
        self._config = None

    def create_story(self, num_players: int, theme: str | None = None) -> Story:
        theme_line = f"Theme/tone requested: {theme}" if theme else "Choose an exciting theme."

        prompt = f"""\
Create a fun D&D adventure for {num_players} player(s).

{theme_line}

Requirements:
- Exactly {num_players} plot hook(s), one per player -- 1-2 sentences each
- 3-5 locations that the players will visit in order -- describe each in 1-2 sentences
- 2-4 NPCs including a villain -- each NPC MUST have a gender ("male" or "female"). Describe them like you'd describe someone to a friend
- A short backstory (3-4 sentences) that sets up why the quest matters
- One clear main quest goal
- Use simple everyday words. No fancy fantasy language.
- The locations should tell a journey: start somewhere safe, travel through danger, reach the goal.
"""

        response = self.client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=Story.model_json_schema(),
            ),
        )

        return Story.model_validate_json(response.text)

    def create_party(self, story: Story, num_players: int) -> Party:
        prompt = f"""\
Create {num_players} player character(s) for this adventure:

Title: {story.title}
Setting: {story.setting}
Main Quest: {story.main_quest}

Plot hooks (one per character):
{chr(10).join(f"- Player {i+1}: {hook}" for i, hook in enumerate(story.hooks))}

Requirements:
- Exactly {num_players} character(s) at level 1
- Each character MUST have a gender ("male" or "female"). Mix genders for variety.
- Each backstory: 1-2 sentences connecting to their hook
- Different classes that complement each other (fighter + rogue, wizard + cleric, etc.)
- Ability scores 8-18. High stats match the class.
- 2-3 fun personality traits that affect how they act
- Correct starting gear, HP, and AC for their class
- List 2-3 class abilities
- Simple language everywhere
- Give them a relationship to each other (friends, siblings, rivals, etc.)
- Every character MUST have a unique fantasy name. NEVER use generic labels like "Player 1".
"""

        response = self.client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=Party.model_json_schema(),
            ),
        )

        return Party.model_validate_json(response.text)

    def start_session(self, story: Story, party: Party):
        system_prompt = _build_dm_system_prompt(story, party)

        self._config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_json_schema=DynamicScene.model_json_schema(),
        )

        self._chat = self.client.chats.create(model=MODEL, config=self._config)

    def get_first_scene(self) -> DynamicScene:
        if not self._chat:
            raise RuntimeError("Call start_session() first.")

        response = self._chat.send_message(
            "Begin the adventure. Write the opening scene like the first page of a book. "
            "Set the mood, introduce what the players see. "
            "Pick one player to act first -- whoever the story naturally starts with."
        )
        return DynamicScene.model_validate_json(response.text)

    def play_turn(self, action_summary: str) -> DynamicScene:
        if not self._chat:
            raise RuntimeError("Call start_session() first.")

        response = self._chat.send_message(action_summary)
        return DynamicScene.model_validate_json(response.text)

    def create_game(self, num_players: int, theme: str | None = None) -> GameState:
        print(f"\n{'='*60}")
        print(f"  The Dungeon Master is crafting your adventure...")
        print(f"  Players: {num_players}")
        if theme:
            print(f"  Theme: {theme}")
        print(f"{'='*60}\n")

        print("[1/2] Writing the story...")
        story = self.create_story(num_players, theme)
        print(f"  -> \"{story.title}\" -- {story.setting}")
        print(f"  -> Difficulty: {story.difficulty.value}")
        print()

        print("[2/2] Creating the heroes...")
        party = self.create_party(story, num_players)
        for p in party.players:
            print(f"  -> {p.name} -- {p.gender} {p.race.value} {p.character_class.value} (HP: {p.hit_points}, AC: {p.armor_class})")
        print()

        game = GameState(story=story, party=party)
        game.init_hp()
        return game
