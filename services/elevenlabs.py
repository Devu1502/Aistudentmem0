from __future__ import annotations

from io import BytesIO
import logging
import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from elevenlabs import ElevenLabs


logger = logging.getLogger(__name__)

dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not API_KEY:
    logger.warning("ELEVENLABS_API_KEY not found at %s", dotenv_path.resolve())
    client: ElevenLabs | None = None
else:
    try:
        client = ElevenLabs(api_key=API_KEY)
    except Exception as exc:  # pragma: no cover - network/auth errors only at startup
        logger.error("Failed to initialise ElevenLabs client: %s", exc)
        client = None
    else:
        logger.info("ElevenLabs API key loaded successfully")

DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "ztqW7U07ITK9TRp5iDUi")


def speech_to_text(audio: bytes, mime_type: str = "audio/webm") -> str:
    if not client:
        raise RuntimeError("ElevenLabs client not configured")

    try:
        result = client.speech_to_text.convert(
            file=BytesIO(audio),
            model_id="scribe_v1",
            language_code="eng",
            diarize=False,
        )
        return result.text
    except Exception as exc:  # pragma: no cover - API errors bubble to caller
        logger.error("Speech-to-text failed: %s", exc)
        raise


def text_to_speech(text: str, voice_id: str | None = None) -> bytes:
    if not client:
        raise RuntimeError("ElevenLabs client not configured")

    try:
        return client.text_to_speech.convert(
            text=text,
            voice_id=voice_id or DEFAULT_VOICE_ID,
            model_id="eleven_turbo_v2",
            output_format="mp3_44100_128",
        )
    except Exception as exc:  # pragma: no cover - API errors bubble to caller
        logger.error("Text-to-speech failed: %s", exc)
        raise


def stream_text_to_speech(text: str, voice_id: str | None = None) -> Iterable[bytes]:
    if not client:
        raise RuntimeError("ElevenLabs client not configured")

    try:
        return client.text_to_speech.stream(
            text=text,
            voice_id=voice_id or DEFAULT_VOICE_ID,
            model_id="eleven_turbo_v2",
            output_format="mp3_44100_128",
        )
    except Exception as exc:  # pragma: no cover - API errors bubble to caller
        logger.error("Text-to-speech streaming failed: %s", exc)
        raise
