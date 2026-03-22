"""
Voice cloning via Minimax API.

During player registration, records each player's voice from the Reachy
mic, uploads the audio to Minimax, and creates a cloned voice_id that
can be used for TTS throughout the game.
"""

import io
import logging
import os
import time
import uuid
import wave

import httpx
import numpy as np

from src.audio import SAMPLE_RATE, _normalize_frame, rms

logger = logging.getLogger(__name__)

MINIMAX_UPLOAD_URL = "https://api.minimax.io/v1/files/upload"
MINIMAX_CLONE_URL = "https://api.minimax.io/v1/voice_clone"

CLONE_RECORD_S = 12.0
CLONE_ENERGY_THRESHOLD = 0.008
CLONE_POLL_S = 0.005


def _get_api_key() -> str:
    return os.environ.get("MINIMAX_TTS_KEY", "")


def record_voice_sample(robot, duration: float = CLONE_RECORD_S) -> np.ndarray | None:
    """Record a voice sample from Reachy's mic for cloning (fixed duration)."""
    reachy_sr = robot.media.get_input_audio_samplerate()
    chunks: list[np.ndarray] = []
    start = time.monotonic()

    while (time.monotonic() - start) < duration:
        frame = robot.media.get_audio_sample()
        if frame is None:
            time.sleep(CLONE_POLL_S)
            continue
        flat = _normalize_frame(frame)
        if flat.size > 0:
            chunks.append(flat)

    if not chunks:
        return None

    audio = np.concatenate(chunks)
    dur = len(audio) / reachy_sr
    logger.info("Recorded %.1fs of voice sample at %d Hz", dur, reachy_sr)

    if reachy_sr != SAMPLE_RATE:
        from scipy.signal import resample
        n_out = int(round(SAMPLE_RATE * len(audio) / reachy_sr))
        audio = resample(audio, n_out).astype(np.float32)

    return audio


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _upload_audio(wav_bytes: bytes, purpose: str = "voice_clone") -> str | None:
    """Upload audio to Minimax and return the file_id."""
    api_key = _get_api_key()
    if not api_key:
        logger.warning("No MINIMAX_TTS_KEY — skipping voice clone upload.")
        return None

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                MINIMAX_UPLOAD_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"purpose": purpose},
                files={"file": ("voice_sample.wav", wav_bytes, "audio/wav")},
            )
            resp.raise_for_status()
            data = resp.json()
            file_id = data.get("file", {}).get("file_id")
            logger.info("Uploaded audio -> file_id=%s", file_id)
            return file_id
    except Exception as e:
        logger.error("Voice clone upload failed: %s", e)
        return None


def clone_voice(audio: np.ndarray, player_index: int) -> str | None:
    """Upload audio and clone the voice. Returns the voice_id or None."""
    api_key = _get_api_key()
    if not api_key:
        return None

    wav_bytes = _audio_to_wav_bytes(audio)
    dur_s = len(audio) / SAMPLE_RATE
    if dur_s < 10.0:
        logger.warning("Audio too short for cloning (%.1fs < 10s). Padding with silence.", dur_s)
        pad_samples = int((10.5 - dur_s) * SAMPLE_RATE)
        audio = np.concatenate([audio, np.zeros(pad_samples, dtype=np.float32)])
        wav_bytes = _audio_to_wav_bytes(audio)

    file_id = _upload_audio(wav_bytes)
    if not file_id:
        return None

    voice_id = f"dnd_player_{player_index}_{uuid.uuid4().hex[:8]}"

    try:
        with httpx.Client(timeout=90) as client:
            payload = {
                "file_id": file_id,
                "voice_id": voice_id,
                "text": "Welcome to the adventure! Let us begin our quest.",
                "model": "speech-02-turbo",
            }
            resp = client.post(
                MINIMAX_CLONE_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("base_resp", {}).get("status_code", 0) != 0:
                logger.error("Clone API error: %s", result)
                return None
            logger.info("Cloned voice -> voice_id=%s", voice_id)
            print(f"  [Voice Clone] Created voice: {voice_id}")
            return voice_id
    except Exception as e:
        logger.error("Voice clone failed: %s", e)
        return None
