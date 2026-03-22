from google import genai
from google.genai import types

from src.models import Story, Party, GameTree, GameState

MODEL = "gemini-3-flash-preview"

SYSTEM_INSTRUCTION = """\
You are an expert Dungeons & Dragons 5th Edition Dungeon Master with decades of experience \
crafting immersive, balanced, and memorable adventures. You create content that is:

- Rich in vivid, atmospheric descriptions that bring the world to life
- Balanced for the number of players -- more players means tougher enemies but also more \
  complex social dynamics and branching paths
- True to D&D 5e mechanics (ability scores, armor class, hit points, difficulty classes)
- Full of meaningful choices where no option is obviously "correct"
- Respectful of player agency -- every choice should feel impactful

When generating characters, ensure the party is well-balanced with a mix of combat, \
magic, stealth, and social abilities. Each character should have a unique personality \
and a backstory that ties into the adventure's plot hooks.

When building decision trees, create branching narratives where choices genuinely matter. \
Include a mix of combat encounters, social encounters, puzzles, and exploration. \
Every branch should eventually lead to a satisfying conclusion -- whether victory, \
defeat, or something bittersweet.
"""


class DungeonMaster:
    def __init__(self, api_key: str | None = None):
        kwargs = {"api_key": api_key} if api_key else {}
        self.client = genai.Client(**kwargs)

    def create_story(self, num_players: int, theme: str | None = None) -> Story:
        """Generate a complete adventure story scaled for the given number of players."""
        theme_line = f"Theme/tone requested: {theme}" if theme else "Choose an exciting theme."

        prompt = f"""\
Create a Dungeons & Dragons adventure for {num_players} player(s).

{theme_line}

Requirements:
- Exactly {num_players} plot hook(s), one to personally draw in each player character
- 3-5 key locations that the adventure spans across
- 2-4 important NPCs including at least one antagonist
- Scale the difficulty appropriately: {num_players} player(s) means \
{"a tightly focused, personal story" if num_players <= 2 else "a grand, multi-threaded adventure with complex dynamics"}
- The story should be completable in 3-6 sessions
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
        """Generate a balanced party of player characters tied to the story."""
        prompt = f"""\
Create {num_players} player character(s) for the following D&D adventure:

Title: {story.title}
Setting: {story.setting}
Backstory: {story.backstory}
Main Quest: {story.main_quest}

Plot hooks (one per character):
{chr(10).join(f"- Player {i+1}: {hook}" for i, hook in enumerate(story.hooks))}

Key NPCs:
{chr(10).join(f"- {npc.name} ({npc.role}): {npc.description}" for npc in story.key_npcs)}

Requirements:
- Create exactly {num_players} character(s) at level 1
- Each character's backstory MUST tie into their corresponding plot hook
- Ensure the party is balanced (mix of melee, ranged, magic, support)
- Use standard 5e ability score generation (scores between 8-18, with racial bonuses)
- Give each character 2-3 distinctive personality traits
- Starting equipment should be appropriate for their class
- Hit points and armor class should follow 5e rules for level 1 characters
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

    def create_game_tree(self, story: Story, party: Party) -> GameTree:
        """Generate a branching decision tree for how the adventure can unfold."""
        player_summary = "\n".join(
            f"- {p.name} ({p.race.value} {p.character_class.value}): {p.backstory[:100]}..."
            for p in party.players
        )

        prompt = f"""\
Create a branching decision tree for the following D&D adventure:

STORY:
Title: {story.title}
Setting: {story.setting}
Main Quest: {story.main_quest}
Backstory: {story.backstory}

LOCATIONS:
{chr(10).join(f"- {loc.name}: {loc.description}" for loc in story.key_locations)}

NPCs:
{chr(10).join(f"- {npc.name} ({npc.role}): {npc.motivation}" for npc in story.key_npcs)}

PARTY:
{player_summary}

Requirements:
- Start with an opening scene (root) that sets the stage
- Create 8-12 scenes total forming a branching tree
- Each non-ending scene should have 2-3 meaningful choices
- Include at least 2 victory endings, 1 defeat ending, and 1 bittersweet ending
- Some choices should require dice checks (with appropriate DCs)
- Reference specific locations and NPCs from the story
- The critical path (shortest route to an ending) should be 4-5 scenes
- Ensure scene_ids are consistent: use 'scene_1', 'scene_2a', 'scene_2b', etc.
- Every choice's 'leads_to' must reference a valid scene_id
- Make choices that feel genuinely different -- not just "door A or door B"
"""

        response = self.client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=GameTree.model_json_schema(),
            ),
        )

        return GameTree.model_validate_json(response.text)

    def create_game(self, num_players: int, theme: str | None = None) -> GameState:
        """Run the full pipeline: story -> party -> game tree."""
        print(f"\n{'='*60}")
        print(f"  The Dungeon Master is crafting your adventure...")
        print(f"  Players: {num_players}")
        if theme:
            print(f"  Theme: {theme}")
        print(f"{'='*60}\n")

        print("[1/3] Weaving the story...")
        story = self.create_story(num_players, theme)
        print(f"  -> \"{story.title}\" -- {story.setting}")
        print(f"  -> Difficulty: {story.difficulty.value}")
        print()

        print("[2/3] Creating the heroes...")
        party = self.create_party(story, num_players)
        for p in party.players:
            print(f"  -> {p.name} -- {p.race.value} {p.character_class.value} (HP: {p.hit_points})")
        print()

        print("[3/3] Building the decision tree...")
        game_tree = self.create_game_tree(story, party)
        print(f"  -> {len(game_tree.scenes)} scenes, {game_tree.total_endings} endings")
        print(f"  -> Shortest path: {game_tree.critical_path_length} scenes")
        print()

        return GameState(
            story=story,
            party=party,
            game_tree=game_tree,
            current_scene_id=game_tree.root_scene_id,
        )
