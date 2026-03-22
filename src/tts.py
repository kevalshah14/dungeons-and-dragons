"""
Multi-voice TTS using Minimax API.

Gender-aware voice assignment -- male characters get male voices,
female characters get female voices. Every character sounds distinct.

Audio plays through the Reachy Mini speaker when connected,
falls back to system speakers otherwise.
"""

import io
import os
import subprocess
import sys
import tempfile
import time

import httpx
import numpy as np
import soundfile as sf

MINIMAX_API_URL = "https://api.minimax.io/v1/t2a_v2"

# Software gain applied before pushing audio to Reachy's speaker.
# The XVF3800-based sound card is quiet by default; this compensates.
REACHY_VOLUME_GAIN = 1.0

NARRATOR_VOICE = "English_CaptivatingStoryteller"

MALE_CLASS_VOICES = {
    "Fighter": "English_PassionateWarrior",
    "Barbarian": "English_Strong-WilledBoy",
    "Paladin": "English_Trustworth_Man",
    "Wizard": "English_WiseScholar",
    "Sorcerer": "English_magnetic_voiced_man",
    "Warlock": "English_Deep-VoicedGentleman",
    "Rogue": "English_ReservedYoungMan",
    "Ranger": "English_Diligent_Man",
    "Cleric": "English_PatientMan",
    "Druid": "English_Gentle-voiced_man",
    "Bard": "English_Comedian",
    "Monk": "English_Steadymentor",
}

FEMALE_CLASS_VOICES = {
    "Fighter": "English_ConfidentWoman",
    "Barbarian": "English_AssertiveQueen",
    "Paladin": "English_Graceful_Lady",
    "Wizard": "English_Wiselady",
    "Sorcerer": "English_captivating_female1",
    "Warlock": "English_ImposingManner",
    "Rogue": "English_WhimsicalGirl",
    "Ranger": "English_Upbeat_Woman",
    "Cleric": "English_SereneWoman",
    "Druid": "English_Kind-heartedGirl",
    "Bard": "English_PlayfulGirl",
    "Monk": "English_CalmWoman",
}

MALE_RACE_OVERRIDES = {
    "Dwarf": "English_ManWithDeepVoice",
    "Halfling": "English_SadTeen",
    "Gnome": "English_Comedian",
    "Dragonborn": "English_BossyLeader",
}

FEMALE_RACE_OVERRIDES = {
    "Dwarf": "English_StressedLady",
    "Halfling": "English_Soft-spokenGirl",
    "Gnome": "English_PlayfulGirl",
    "Dragonborn": "English_ImposingManner",
}

MALE_NPC_VOICES = {
    "villain": "English_BossyLeader",
    "quest giver": "English_FriendlyPerson",
    "merchant": "English_Jovialman",
    "ally": "English_DecentYoungMan",
    "guard": "English_Trustworth_Man",
    "elder": "English_PatientMan",
    "king": "English_Deep-VoicedGentleman",
    "soldier": "English_PassionateWarrior",
    "thief": "English_ReservedYoungMan",
    "priest": "English_Gentle-voiced_man",
}

FEMALE_NPC_VOICES = {
    "villain": "English_MatureBoss",
    "quest giver": "English_Kind-heartedGirl",
    "merchant": "English_Upbeat_Woman",
    "ally": "English_Graceful_Lady",
    "guard": "English_ConfidentWoman",
    "elder": "English_Wiselady",
    "queen": "English_AssertiveQueen",
    "soldier": "English_ConfidentWoman",
    "thief": "English_WhimsicalGirl",
    "priestess": "English_SereneWoman",
}

MALE_FALLBACKS = [
    "English_Debator",
    "English_Diligent_Man",
    "English_Steadymentor",
    "English_magnetic_voiced_man",
    "English_DecentYoungMan",
]

FEMALE_FALLBACKS = [
    "English_radiant_girl",
    "English_compelling_lady1",
    "English_SentimentalLady",
    "English_LovelyGirl",
    "English_Upbeat_Woman",
]


def assign_player_voice(gender: str, race: str, character_class: str) -> str:
    is_female = gender.lower().startswith("f")
    race_map = FEMALE_RACE_OVERRIDES if is_female else MALE_RACE_OVERRIDES
    if race in race_map:
        return race_map[race]
    class_map = FEMALE_CLASS_VOICES if is_female else MALE_CLASS_VOICES
    return class_map.get(character_class, "English_ConfidentWoman" if is_female else "English_Strong-WilledBoy")


def assign_npc_voice(gender: str, role: str, used_voices: set[str]) -> str:
    is_female = gender.lower().startswith("f")
    role_map = FEMALE_NPC_VOICES if is_female else MALE_NPC_VOICES
    fallbacks = FEMALE_FALLBACKS if is_female else MALE_FALLBACKS

    role_lower = role.lower()
    for key, voice in role_map.items():
        if key in role_lower and voice not in used_voices:
            return voice

    for voice in fallbacks:
        if voice not in used_voices:
            return voice

    return "English_ConfidentWoman" if is_female else "English_expressive_narrator"


def build_voice_map(party, story) -> dict[str, str]:
    voice_map = {"narrator": NARRATOR_VOICE}
    used = {NARRATOR_VOICE}

    for p in party.players:
        v = assign_player_voice(p.gender, p.race.value, p.character_class.value)
        voice_map[p.name] = v
        used.add(v)

    for npc in story.key_npcs:
        v = assign_npc_voice(npc.gender, npc.role, used)
        voice_map[npc.name] = v
        used.add(v)

    return voice_map


class GameVoice:
    def __init__(
        self,
        api_key: str | None = None,
        group_id: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("MINIMAX_TTS_KEY", "")
        self.group_id = group_id or os.environ.get("MINIMAX_TTS_GROUP_ID", "")
        self.enabled = bool(self.api_key and self.group_id)
        self.voice_map: dict[str, str] = {"narrator": NARRATOR_VOICE}
        self._http: httpx.Client | None = None
        self._last_call: float = 0
        self._reachy = None
        self._reachy_sr: int = 16000
        self._playing = False
        self.emotions = None  # set via set_emotions()
        self._registry: dict | None = None

        if not self.enabled:
            print("  [TTS] Minimax keys not found -- voice disabled.")

    def set_reachy(self, reachy_mini):
        """Attach a ReachyMini instance to route audio through its speaker."""
        self._reachy = reachy_mini
        if reachy_mini is not None:
            reachy_mini.media.start_playing()
            self._reachy_sr = reachy_mini.media.get_output_audio_samplerate()
            self._playing = True
            self._try_max_hw_volume()
            print(f"  🔊 Audio routed to Reachy Mini speaker ({self._reachy_sr} Hz, gain={REACHY_VOLUME_GAIN}x)")

    @staticmethod
    def _try_max_hw_volume():
        """On Linux, try to set the reSpeaker PCM1 volume to 100%."""
        if sys.platform != "linux":
            return
        try:
            result = subprocess.run(
                ["bash", "-c",
                 'CARD=$(aplay -l 2>/dev/null | grep -i "reSpeaker" | head -n1 '
                 "| sed -n 's/^card \\([0-9]*\\):.*/\\1/p'); "
                 '[ -n "$CARD" ] && amixer -c "$CARD" set PCM,1 100% >/dev/null 2>&1'],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                print("  🔊 Hardware volume set to 100% (reSpeaker PCM1)")
        except Exception:
            pass

    def stop_reachy_audio(self):
        if self._playing and self._reachy is not None:
            self._reachy.media.stop_playing()
            self._playing = False

    def _get_http(self) -> httpx.Client:
        if self._http is None or self._http.is_closed:
            self._http = httpx.Client(timeout=90)
        return self._http

    def setup_voices(self, party, story):
        self.voice_map = build_voice_map(party, story)
        if self.enabled:
            print("\n  🎙️  Voice Cast:")
            print(f"    {'Narrator':>20}  →  Captivating Storyteller")
            for p in party.players:
                vid = self.voice_map.get(p.name, NARRATOR_VOICE)
                tag = vid.replace("English_", "").replace("_", " ").replace("-", " ")
                print(f"    {p.name:>20}  →  {tag}  ({p.gender})")
            for npc in story.key_npcs:
                vid = self.voice_map.get(npc.name, NARRATOR_VOICE)
                tag = vid.replace("English_", "").replace("_", " ").replace("-", " ")
                print(f"    {npc.name:>20}  →  {tag}  ({npc.gender}, {npc.role})")
            print()

    def set_registry(self, registry):
        """Store the player registry so TTS can look up real names."""
        self._registry = registry

    def _real_name_for(self, character_name: str) -> str | None:
        """Look up the real player name for a character, if registry is set."""
        if self._registry and character_name in self._registry:
            return self._registry[character_name].real_name
        return None

    def narrate(self, text: str):
        self._speak(text, self.voice_map.get("narrator", NARRATOR_VOICE))

    def say(self, character_name: str, text: str):
        narrator = self.voice_map.get("narrator", NARRATOR_VOICE)
        self._speak(f"{character_name} says", narrator)
        character_voice = self._resolve_voice(character_name)
        self._speak(text, character_voice)

    def _resolve_voice(self, character_name: str) -> str:
        """Return a consistent voice for a character, auto-assigning one if new."""
        if character_name in self.voice_map:
            return self.voice_map[character_name]
        used = set(self.voice_map.values())
        voice = assign_npc_voice("male", "", used)
        self.voice_map[character_name] = voice
        print(f"  [TTS] Auto-assigned voice for new character '{character_name}': {voice}")
        return voice

    def announce(self, text: str):
        """Short DM announcement (turn calls, roll results)."""
        self._speak(text, self.voice_map.get("narrator", NARRATOR_VOICE))

    def address_player(self, character_name: str, text: str):
        """Address a player by their real name, speaking as narrator.

        Example output: "Keval, as Elara -- what do you do?"
        Falls back to character name if registry is not set.
        """
        real_name = self._real_name_for(character_name)
        if real_name:
            speech = f"{real_name}, as {character_name}. {text}"
        else:
            speech = f"{character_name}, {text}"
        self._speak(speech, self.voice_map.get("narrator", NARRATOR_VOICE))

    def _speak(self, text: str, voice_id: str):
        if not self.enabled:
            return

        text = text.strip()
        if not text:
            return

        if len(text) > 9500:
            text = text[:9500]

        since_last = time.time() - self._last_call
        if since_last < 0.3:
            time.sleep(0.3 - since_last)

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                audio_bytes = self._synthesize(text, voice_id)
                if self.emotions:
                    self.emotions.start_talking()
                self._play(audio_bytes)
                if self.emotions:
                    self.emotions.stop_talking()
                self._last_call = time.time()
                return
            except Exception as e:
                if self.emotions:
                    self.emotions.stop_talking()
                if attempt < max_retries:
                    wait = min(2 ** attempt, 8)
                    print(f"  [TTS] Retry {attempt + 1}/{max_retries} in {wait}s ({e})")
                    time.sleep(wait)
                else:
                    print(f"  [TTS] Skipped after {max_retries + 1} attempts: {e}")

    def _synthesize(self, text: str, voice_id: str) -> bytes:
        # Request audio at Reachy's native rate to skip costly resampling
        synth_sr = self._reachy_sr if self._reachy is not None else 32000

        payload = {
            "model": "speech-02-turbo",
            "text": text,
            "stream": False,
            "language_boost": "en",
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 5,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": synth_sr,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }

        t0 = time.time()
        client = self._get_http()
        response = client.post(
            MINIMAX_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        synth_ms = int((time.time() - t0) * 1000)

        if data.get("base_resp", {}).get("status_code", 0) != 0:
            msg = data.get("base_resp", {}).get("status_msg", "Unknown error")
            raise RuntimeError(f"Minimax TTS error: {msg}")

        hex_audio = data.get("data", {}).get("audio", "")
        if not hex_audio:
            raise RuntimeError("No audio data in response")

        print(f"  [TTS] synth={synth_ms}ms sr={synth_sr} len={len(text)}ch")
        return bytes.fromhex(hex_audio)

    def _play(self, audio_bytes: bytes):
        if self._reachy is not None:
            self._play_on_reachy(audio_bytes)
        else:
            self._play_on_system(audio_bytes)

    def _play_on_reachy(self, audio_bytes: bytes):
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)

        if sr != self._reachy_sr:
            n_out = int(round(self._reachy_sr * len(data) / sr))
            x_old = np.linspace(0, 1, len(data))
            x_new = np.linspace(0, 1, n_out)
            data = np.interp(x_new, x_old, data).astype(np.float32)

        data = np.clip(data * REACHY_VOLUME_GAIN, -1.0, 1.0)
        stereo = np.column_stack((data, data))

        chunk_size = self._reachy_sr // 5  # 200ms chunks (less push overhead)
        for i in range(0, len(stereo), chunk_size):
            chunk = stereo[i : i + chunk_size]
            self._reachy.media.push_audio_sample(chunk)
            time.sleep(len(chunk) / self._reachy_sr)

    def _play_on_system(self, audio_bytes: bytes):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            if sys.platform == "darwin":
                subprocess.run(["afplay", tmp_path], check=True)
            elif sys.platform == "linux":
                subprocess.run(["mpg123", "-q", tmp_path], check=True)
            elif sys.platform == "win32":
                subprocess.run(
                    ["powershell", "-c", f'(New-Object Media.SoundPlayer "{tmp_path}").PlaySync()'],
                    check=True,
                )
            else:
                print(f"  [TTS] Unsupported platform: {sys.platform}")
        finally:
            os.unlink(tmp_path)
