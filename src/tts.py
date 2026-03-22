"""
Multi-voice TTS using Minimax API.

Gender-aware voice assignment -- male characters get male voices,
female characters get female voices. Every character sounds distinct.
"""

import os
import subprocess
import sys
import tempfile
import time

import httpx

MINIMAX_API_URL = "https://api.minimax.io/v1/t2a_v2"

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

        if not self.enabled:
            print("  [TTS] Minimax keys not found -- voice disabled.")

    def _get_http(self) -> httpx.Client:
        if self._http is None or self._http.is_closed:
            self._http = httpx.Client(timeout=60)
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

    def narrate(self, text: str):
        self._speak(text, self.voice_map.get("narrator", NARRATOR_VOICE))

    def say(self, character_name: str, text: str):
        voice = self.voice_map.get(character_name, NARRATOR_VOICE)
        self._speak(text, voice)

    def announce(self, text: str):
        """Short DM announcement (turn calls, roll results)."""
        self._speak(text, self.voice_map.get("narrator", NARRATOR_VOICE))

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

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                audio_bytes = self._synthesize(text, voice_id)
                self._play(audio_bytes)
                self._last_call = time.time()
                return
            except Exception as e:
                if attempt < max_retries:
                    wait = 1.0 * (attempt + 1)
                    print(f"  [TTS] Retry {attempt + 1}/{max_retries} in {wait:.0f}s ({e})")
                    time.sleep(wait)
                else:
                    print(f"  [TTS] Skipped after {max_retries + 1} attempts: {e}")

    def _synthesize(self, text: str, voice_id: str) -> bytes:
        payload = {
            "model": "speech-02-turbo",
            "text": text,
            "stream": False,
            "language_boost": "en",
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 0.95,
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }

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

        if data.get("base_resp", {}).get("status_code", 0) != 0:
            msg = data.get("base_resp", {}).get("status_msg", "Unknown error")
            raise RuntimeError(f"Minimax TTS error: {msg}")

        hex_audio = data.get("data", {}).get("audio", "")
        if not hex_audio:
            raise RuntimeError("No audio data in response")

        return bytes.fromhex(hex_audio)

    def _play(self, audio_bytes: bytes):
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
