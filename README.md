# Dungeons & Dragons: AI Dungeon Master on Reachy Mini

A fully voice-driven D&D game running on the [Reachy Mini](https://www.pollen-robotics.com/reachy-mini/) robot. Reachy acts as the Dungeon Master -- it listens through its microphone, thinks with Gemini, speaks with Minimax TTS, expresses emotions through head movements, and lets you roll dice by pulling its antenna.

## How It Works

```
Reachy mic → Gemini STT → Gemini DM → Minimax TTS → Reachy speaker
                                ↕
                    Antenna pull → d20 dice roll
```

1. **Wake word** -- Reachy sleeps with its head down. Say **"Hey Reachy"** to wake it up.
2. **Voice onboarding** -- Reachy asks how many players (1-6) and what theme you want (fantasy, pirate, horror, etc.). Speak your answers.
3. **Story & party creation** -- Gemini generates a full adventure with title, setting, NPCs, quest hooks, and a balanced party of characters with unique backstories.
4. **Game loop** -- Each turn:
   - Reachy narrates the scene with emotion-driven head movements
   - NPCs speak in distinct voices (gender-aware voice casting)
   - The active player hears their situation and choices
   - Player speaks their choice
   - **Pull Reachy's antenna** to roll a d20 (auto-rolls after 30s timeout)
   - Dice results are resolved with ability modifiers, proficiency, crits, and fumbles
   - Gemini generates the next scene based on what happened
5. **Endings** -- Victory, defeat, or bittersweet. Reachy asks if you want to play again.

## Project Structure

```
├── main.py                    # Entry point — wake word, onboarding, game loop
├── pyproject.toml             # Dependencies (uv)
├── .env                       # API keys (Gemini, Minimax)
├── src/
│   ├── audio.py               # Reachy mic recording + Gemini-powered STT
│   ├── wake_word.py           # "Hey Reachy" wake word detection
│   ├── voice_input.py         # Voice-based input (numbers, text, choices, yes/no)
│   ├── dungeon_master.py      # Gemini DM engine (story, party, scene generation)
│   ├── tts.py                 # Multi-voice Minimax TTS with Reachy speaker output
│   ├── reachy_emotions.py     # Emotion animations + talking head movements
│   └── models/
│       ├── enums.py           # Race, CharacterClass, Difficulty
│       ├── story.py           # NPC, Location, Story
│       ├── player.py          # AbilityScores, Player, Party
│       ├── game_tree.py       # DiceCheck, Choice, Scene, GameTree
│       └── game_state.py      # GameState (HP tracking, scene history)
├── test_antenna_roll.py       # Standalone antenna pull test
└── saves/                     # Auto-saved game state (JSON)
```

## Setup

Requires Python 3.12+, a [Gemini API key](https://aistudio.google.com/apikey), a [Minimax TTS key](https://www.minimax.io/), and a running `reachy-mini-daemon`.

```bash
# Install dependencies
uv sync

# Configure API keys
cp .env.example .env
# Edit .env with your keys
```

### Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key (for DM + STT) |
| `MINIMAX_TTS_KEY` | Minimax API key (for multi-voice TTS) |
| `MINIMAX_TTS_GROUP_ID` | Minimax group ID |
| `PLAYBACK_VOLUME` | Speaker volume 0.0-1.0 (default: 1.0) |

## Usage

Start the Reachy Mini daemon in one terminal, then run the game:

```bash
# Terminal 1 — robot daemon
reachy-mini-daemon

# Terminal 2 — the game
uv run main.py
```

Reachy will fall asleep. Say **"Hey Reachy"** to begin.

## Tech Stack

- **[Reachy Mini](https://www.pollen-robotics.com/reachy-mini/)** -- robot hardware (mic, speaker, head motors, antennas)
- **[Google Gemini](https://ai.google.dev/)** (`google-genai`) -- Dungeon Master AI + speech-to-text via native audio understanding
- **[Minimax TTS](https://www.minimax.io/)** -- multi-voice text-to-speech (narrator + distinct character voices)
- **[Pydantic](https://docs.pydantic.dev/)** -- structured output models for all game data
- **[uv](https://docs.astral.sh/uv/)** -- Python package management
