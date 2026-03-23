"""
Shared audio recording and transcription utilities.

Supports two mic sources:
  1. System microphone via sounddevice (default / fallback)
  2. Reachy Mini robot microphone via robot.media

Both use VAD (energy threshold + silence timeout).
Transcription is handled by Gemini's native audio understanding
(inline WAV bytes sent to generateContent).
"""

import io
import logging
import os
import time
import wave

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
ENERGY_THRESHOLD = 0.01
SILENCE_TIMEOUT_S = 0.8
MIN_SPEECH_S = 0.3
MAX_SPEECH_S = 6.0
CHUNK_FRAMES = 1600  # 100ms at 16kHz

REACHY_ENERGY_THRESHOLD = 0.01
REACHY_SILENCE_TIMEOUT_S = 1.2
REACHY_MAX_SPEECH_S = 10.0
REACHY_POLL_S = 0.005
REACHY_WAIT_TIMEOUT_S = 15.0
REACHY_CONFIRM_FRAMES = 2  # consecutive loud frames needed before counting as speech

STT_MODEL = "gemini-3-flash-preview"

# ---------------------------------------------------------------------------
# Lazy Gemini client
# ---------------------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _gemini_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert a float32 [-1,1] numpy array to 16-bit PCM WAV bytes."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# System mic recording
# ---------------------------------------------------------------------------

def record_speech(
    max_duration: float = MAX_SPEECH_S,
    silence_timeout: float = SILENCE_TIMEOUT_S,
) -> np.ndarray | None:
    """Record from the system mic until speech ends or max duration is reached."""
    import sounddevice as sd

    chunks: list[np.ndarray] = []
    silent_chunks = 0
    speaking = False
    total_samples = 0
    chunk_duration = CHUNK_FRAMES / SAMPLE_RATE

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=CHUNK_FRAMES
    ) as stream:
        while True:
            data, _ = stream.read(CHUNK_FRAMES)
            flat = data.flatten()
            energy = rms(flat)

            if energy > ENERGY_THRESHOLD:
                speaking = True
                silent_chunks = 0
                chunks.append(flat)
                total_samples += len(flat)
            elif speaking:
                chunks.append(flat)
                total_samples += len(flat)
                silent_chunks += 1
                if silent_chunks * chunk_duration > silence_timeout:
                    break

            if total_samples / SAMPLE_RATE > max_duration:
                break

    if not chunks:
        return None

    audio = np.concatenate(chunks)
    if len(audio) / SAMPLE_RATE < MIN_SPEECH_S:
        return None

    return audio


# ---------------------------------------------------------------------------
# Reachy mic recording
# ---------------------------------------------------------------------------

def _normalize_frame(frame: np.ndarray) -> np.ndarray:
    """Convert any audio frame to mono float32 in [-1, 1]."""
    if frame.ndim > 1:
        frame = frame.mean(axis=1)
    flat = frame.flatten().astype(np.float32)
    if flat.size == 0:
        return flat
    if frame.dtype == np.int16 or np.max(np.abs(flat)) > 2.0:
        flat = flat / 32768.0
    return flat


def record_speech_reachy(
    robot,
    max_duration: float = REACHY_MAX_SPEECH_S,
    silence_timeout: float = REACHY_SILENCE_TIMEOUT_S,
) -> np.ndarray | None:
    """Record from the Reachy Mini mic until speech ends or max duration."""
    reachy_sr = robot.media.get_input_audio_samplerate()
    logger.debug("Reachy mic sample rate: %d Hz", reachy_sr)

    chunks: list[np.ndarray] = []
    pending: list[np.ndarray] = []  # buffered frames waiting to confirm speech
    loud_streak = 0
    silent_time = 0.0
    speaking = False
    speech_time = 0.0
    wall_start = time.monotonic()

    while speech_time < max_duration:
        if not speaking and (time.monotonic() - wall_start) > REACHY_WAIT_TIMEOUT_S:
            logger.debug("No speech detected within %.1fs — giving up.", REACHY_WAIT_TIMEOUT_S)
            break

        frame = robot.media.get_audio_sample()
        if frame is None:
            time.sleep(REACHY_POLL_S)
            continue

        flat = _normalize_frame(frame)
        if flat.size == 0:
            time.sleep(REACHY_POLL_S)
            continue

        energy = rms(flat)
        frame_dur = len(flat) / reachy_sr

        if energy > REACHY_ENERGY_THRESHOLD:
            if not speaking:
                loud_streak += 1
                pending.append(flat)
                if loud_streak >= REACHY_CONFIRM_FRAMES:
                    speaking = True
                    chunks.extend(pending)
                    speech_time += sum(len(p) / reachy_sr for p in pending)
                    pending.clear()
                    logger.debug("Speech confirmed (energy=%.4f, streak=%d)", energy, loud_streak)
            else:
                silent_time = 0.0
                chunks.append(flat)
                speech_time += frame_dur
        elif speaking:
            chunks.append(flat)
            speech_time += frame_dur
            silent_time += frame_dur
            if silent_time > silence_timeout:
                logger.debug("Silence timeout — speech ended (%.2fs captured)", speech_time)
                break
        else:
            loud_streak = 0
            pending.clear()
            time.sleep(REACHY_POLL_S)

    if not chunks:
        logger.debug("No audio chunks captured.")
        return None

    audio = np.concatenate(chunks)
    duration_s = len(audio) / reachy_sr
    if duration_s < MIN_SPEECH_S:
        logger.debug("Audio too short (%.2fs < %.2fs) — discarding.", duration_s, MIN_SPEECH_S)
        return None

    logger.debug("Captured %.2fs of speech at %d Hz", duration_s, reachy_sr)

    if reachy_sr != SAMPLE_RATE:
        from scipy.signal import resample
        n_out = int(round(SAMPLE_RATE * len(audio) / reachy_sr))
        audio = resample(audio, n_out).astype(np.float32)

    return audio


# ---------------------------------------------------------------------------
# Gemini-based transcription
# ---------------------------------------------------------------------------

def transcribe(audio: np.ndarray) -> str | None:
    """Transcribe a float32 audio array using Gemini's audio understanding."""
    from google.genai import types

    wav_bytes = _audio_to_wav_bytes(audio)
    client = _get_gemini_client()

    t0 = time.monotonic()
    try:
        response = client.models.generate_content(
            model=STT_MODEL,
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                "Transcribe this speech exactly. "
                "Return ONLY the spoken words, nothing else. "
                "If no clear speech is present, return an empty string.",
            ],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        elapsed = time.monotonic() - t0
        text = response.text.strip().strip('"').strip("'").lower()
        if not text:
            logger.debug("STT returned empty (%.2fs)", elapsed)
            return None
        logger.info("STT [%s]: '%s' (%.2fs)", STT_MODEL, text, elapsed)
        return text
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.warning("Gemini transcription failed (%.2fs): %s", elapsed, e)
        return None


# ---------------------------------------------------------------------------
# High-level listen functions
# ---------------------------------------------------------------------------

def listen() -> str | None:
    """Record speech from the system mic and transcribe it."""
    segment = record_speech()
    if segment is None:
        return None
    return transcribe(segment)


def listen_reachy(robot) -> str | None:
    """Record speech from the Reachy Mini mic and transcribe it."""
    segment = record_speech_reachy(robot)
    if segment is None:
        logger.debug("listen_reachy: no speech segment captured.")
        return None
    text = transcribe(segment)
    if text is None:
        logger.debug("listen_reachy: transcription returned nothing.")
    else:
        logger.debug("listen_reachy: transcribed '%s'", text)
    return text
