---
name: reachy-dnd
description: >-
  Voice-driven D&D game on Reachy Mini robot. Covers the full pipeline: wake word,
  voice onboarding, player registration, Gemini DM, Minimax TTS, antenna dice rolls,
  emotion animations, and head tracking. Use when modifying the D&D game, adding
  features to Reachy, debugging audio/TTS/STT issues, or extending the game loop.
---

# Reachy Mini D&D — AI Dungeon Master

## Architecture

```
"Hey Reachy" → Voice Onboarding → Player Registration → Game Loop
                                                            ↓
                                              Gemini DM ↔ Minimax TTS
                                              Antenna → d20 roll
                                              Head tracking → face player
```

### Pipeline

| Stage | Module | API/Hardware |
|-------|--------|-------------|
| Wake word | `src/wake_word.py` | Reachy mic → Gemini STT, fuzzy match |
| STT | `src/audio.py` | Reachy mic → `gemini-2.5-flash` inline audio |
| Voice input | `src/voice_input.py` | STT + parsing (numbers, text, choices, yes/no) |
| Player registration | `src/player_registry.py` | Head rotation to evenly-spaced positions, ask names |
| DM engine | `src/dungeon_master.py` | `gemini-flash-latest` + Pydantic structured output |
| TTS | `src/tts.py` | Minimax `speech-02-turbo` → Reachy speaker |
| Emotions | `src/reachy_emotions.py` | Head pose animations via `goto_target` |
| Dice rolls | `main.py` | Antenna pull detection → random d20 |

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point: wake word → onboarding → registration → game loop |
| `src/audio.py` | Mic recording (VAD with debounce) + Gemini STT |
| `src/voice_input.py` | High-level voice prompts: `ask_number`, `ask_text`, `ask_choice`, `ask_confirm` |
| `src/player_registry.py` | `scan_all_players`, `assign_characters`, `face_player`, `face_neutral` |
| `src/dungeon_master.py` | `DungeonMaster` class: `create_story`, `create_party`, `start_session`, `play_turn` |
| `src/tts.py` | `GameVoice` class: multi-voice TTS, gender-aware voice casting, Reachy speaker output |
| `src/reachy_emotions.py` | `ReachyEmotions`: scene emotions, roll reactions, talking animation |
| `src/models/` | Pydantic models: `Story`, `Party`, `Player`, `DynamicScene`, `GameState` |

## Reachy Mini SDK Patterns

```python
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

robot = ReachyMini()

# Audio
robot.media.start_recording()
robot.media.start_playing()
frame = robot.media.get_audio_sample()       # np.ndarray (int16 or float32)
robot.media.push_audio_sample(stereo_chunk)  # Nx2 float32 array
sr_in = robot.media.get_input_audio_samplerate()
sr_out = robot.media.get_output_audio_samplerate()

# Camera
frame = robot.media.get_frame()  # OpenCV-compatible BGR numpy array

# Head movement
pose = create_head_pose(pitch=0, yaw=30, roll=0, degrees=True, mm=True)
robot.goto_target(head=pose, duration=0.6)

# Antennas
right_val, left_val = robot.get_present_antenna_joint_positions()
```

## Audio/VAD Tuning

In `src/audio.py`:

| Constant | Current | Effect |
|----------|---------|--------|
| `REACHY_ENERGY_THRESHOLD` | 0.01 | RMS level to count as speech. Higher = ignores background noise, lower = more sensitive |
| `REACHY_CONFIRM_FRAMES` | 3 | Consecutive loud frames needed before recording starts (debounce) |
| `REACHY_SILENCE_TIMEOUT_S` | 1.2 | Seconds of silence after speech to stop recording |
| `MIN_SPEECH_S` | 0.5 | Minimum duration to accept (filters noise bursts) |

Reachy mic returns `int16` — `_normalize_frame()` converts to `float32 [-1, 1]`.

## TTS Volume Tuning

In `src/tts.py`:

| Constant | Current | Effect |
|----------|---------|--------|
| `REACHY_VOLUME_GAIN` | 1.0 | Software amplification before pushing to speaker |
| `vol` in payload | 10 | Minimax API-side volume (0-10) |

On Linux (Reachy hardware), `_try_max_hw_volume()` auto-sets reSpeaker PCM1 to 100%.

## DM System Prompt

`SYSTEM_INSTRUCTION` in `src/dungeon_master.py` controls all DM behavior:
- Narrative style (simple words, sounds, feelings)
- Player rotation logic
- Dice roll rules (DC thresholds, damage)
- **First-person dialogue** — all character speech must be first person
- Scene structure (2-3 options, at least one safe + one risky)

## Game Models (Pydantic)

All Gemini responses use `response_json_schema` for structured output:
- `Story` → title, setting, NPCs, locations, hooks, quest
- `Party` → list of `Player` with ability scores, HP, AC, abilities
- `DynamicScene` → narrative, dialogue, active_player, situation, options, is_ending

## Adding New Features

### New voice command
Add to `src/voice_input.py` following the pattern of `ask_number`/`ask_text`.

### New emotion
Add to `src/reachy_emotions.py` animation list, then call via `emotions.play_emotion("name")`.

### New TTS voice
Add to the voice maps in `src/tts.py` (`MALE_CLASS_VOICES`, `FEMALE_CLASS_VOICES`, etc.).

### Modify DM behavior
Edit `SYSTEM_INSTRUCTION` in `src/dungeon_master.py`. The prompt is the single source of truth for how Gemini generates scenes.

## Environment Variables

| Variable | Required | Used by |
|----------|----------|---------|
| `GEMINI_API_KEY` | Yes | DM engine + STT |
| `MINIMAX_TTS_KEY` | Yes | TTS |
| `MINIMAX_TTS_GROUP_ID` | Yes | TTS |
