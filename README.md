# Dungeons & Dragons: AI Dungeon Master

A text-based D&D game powered by Google's Gemini API. The AI acts as the Dungeon Master -- it writes the story, creates the characters, builds a branching decision tree, and runs you through the adventure scene by scene.

## How It Works

The game runs a 3-step pipeline using Gemini's structured outputs to generate valid, typed JSON at every stage:

1. **Story Creation** -- Given the number of players (and an optional theme), the AI generates a full adventure: title, setting, backstory, main quest, locations, NPCs, and one personal plot hook per player.

2. **Party Creation** -- The story is fed back to the AI, which creates a balanced party of characters. Each player gets a race, class, ability scores, hit points, inventory, and a backstory tied to their plot hook.

3. **Decision Tree** -- The story + party are fed to the AI, which builds a branching tree of 8-12 scenes. Each scene has 2-3 choices (some requiring d20 dice rolls). The tree has multiple endings: victory, defeat, and bittersweet.

Once generated, you play through the tree interactively -- making choices, rolling dice, and seeing where the story takes you.

## Project Structure

```
├── main.py                    # CLI entry point — run this to play
├── pyproject.toml             # Dependencies and project metadata
├── src/
│   ├── dungeon_master.py      # AI engine (story, party, tree generation)
│   └── models/
│       ├── enums.py           # Race, CharacterClass, Difficulty
│       ├── story.py           # NPC, Location, Story
│       ├── player.py          # AbilityScores, Player, Party
│       ├── game_tree.py       # DiceCheck, Choice, Scene, GameTree
│       └── game_state.py      # GameState (ties everything together)
├── saves/                     # Auto-saved game state (JSON)
└── docs/                      # AI/Gemini API reference docs
```

## Setup

Requires Python 3.12+ and a [Gemini API key](https://aistudio.google.com/apikey).

```bash
# Install dependencies
uv sync

# Add your API key
echo "GEMINI_API_KEY=your-key-here" > .env
```

## Usage

```bash
uv run main.py
```

The game will ask for:
- **Number of players** (1-6) -- more players means a larger party and more complex story
- **Theme** (optional) -- e.g. "horror", "pirate", "political intrigue"

Then the AI Dungeon Master builds everything and you start playing. The game auto-saves after every choice, so you can quit and resume later.

## Tech Stack

- **Google Gemini API** (`google-genai`) -- structured JSON outputs for story/character/tree generation
- **Pydantic** -- typed models for all game data (Story, Player, GameTree, etc.)
- **Python 3.12** -- the game engine and CLI
