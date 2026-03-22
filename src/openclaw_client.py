"""
OpenClaw client wrapper for the D&D game.

Provides a singleton async client that connects to the OpenClaw agent
runtime. Used for:
  - DM logic (structured JSON output via Pydantic models)
  - STT transcription

Falls back gracefully to direct Gemini calls when OpenClaw is unavailable.
"""

import asyncio
import logging
import os
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client = None
_available: bool | None = None

DM_AGENT_ID = os.getenv("OPENCLAW_DM_AGENT", "dungeon-master")
STT_AGENT_ID = os.getenv("OPENCLAW_STT_AGENT", "stt")


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


async def _connect():
    global _client, _available
    if _client is not None:
        return _client

    try:
        from openclaw_sdk import OpenClawClient
        _client = await OpenClawClient.connect().__aenter__()
        _available = True
        logger.info("Connected to OpenClaw gateway.")
        return _client
    except Exception as e:
        _available = False
        logger.warning("OpenClaw unavailable (%s) — will fall back to Gemini.", e)
        return None


def is_available() -> bool:
    """Check if OpenClaw is reachable. Caches the result after first probe."""
    global _available
    if _available is not None:
        return _available
    loop = _get_or_create_loop()
    loop.run_until_complete(_connect())
    return _available or False


async def _execute_structured(agent_id: str, prompt: str, model: type[T],
                               session_name: str = "main") -> T | None:
    """Execute an OpenClaw agent and parse the result into a Pydantic model."""
    client = await _connect()
    if client is None:
        return None

    try:
        from openclaw_sdk.output.structured import StructuredOutput
        agent = client.get_agent(agent_id, session_name=session_name)
        result = await StructuredOutput.execute(agent, prompt, model)
        return result
    except Exception as e:
        logger.error("OpenClaw structured execution failed: %s", e)
        return None


async def _execute_text(agent_id: str, prompt: str,
                         session_name: str = "main") -> str | None:
    """Execute an OpenClaw agent and return raw text."""
    client = await _connect()
    if client is None:
        return None

    try:
        agent = client.get_agent(agent_id, session_name=session_name)
        result = await agent.execute(prompt)
        if result.success and result.content:
            return result.content.strip()
        return None
    except Exception as e:
        logger.error("OpenClaw text execution failed: %s", e)
        return None


def run_structured(agent_id: str, prompt: str, model: type[T],
                   session_name: str = "main") -> T | None:
    """Sync wrapper for structured OpenClaw execution."""
    loop = _get_or_create_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                _execute_structured(agent_id, prompt, model, session_name),
            )
            return future.result(timeout=300)
    return loop.run_until_complete(
        _execute_structured(agent_id, prompt, model, session_name)
    )


def run_text(agent_id: str, prompt: str,
             session_name: str = "main") -> str | None:
    """Sync wrapper for text OpenClaw execution."""
    loop = _get_or_create_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                _execute_text(agent_id, prompt, session_name),
            )
            return future.result(timeout=300)
    return loop.run_until_complete(
        _execute_text(agent_id, prompt, session_name)
    )


def transcribe_via_openclaw(text_prompt: str) -> str | None:
    """Use the OpenClaw STT agent to transcribe audio (text-based prompt with audio context)."""
    return run_text(STT_AGENT_ID, text_prompt, session_name="stt")
