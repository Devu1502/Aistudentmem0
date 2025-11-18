# Audio endpoints that expose ElevenLabs speech-to-text/text-to-speech.
from __future__ import annotations

import logging
from typing import Callable, Iterable

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.elevenlabs import (
    DEFAULT_VOICE_ID,
    client as elevenlabs_client,
    speech_to_text as elevenlabs_speech_to_text,
    stream_text_to_speech as elevenlabs_stream_tts,
)


# Standard FastAPI logger plus APIRouter for grouping audio routes.
logger = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None


SpeechToTextHandler = Callable[[bytes, str], str]
StreamTextToSpeechHandler = Callable[[str, str | None], Iterable[bytes]]

# Pick handlers only if the ElevenLabs client initialized successfully.
speech_to_text_handler: SpeechToTextHandler | None = (
    elevenlabs_speech_to_text if elevenlabs_client else None
)
stream_text_to_speech_handler: StreamTextToSpeechHandler | None = (
    elevenlabs_stream_tts if elevenlabs_client else None
)


@router.post("/stt")
# Convert uploaded audio into text using ElevenLabs STT.
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, str]:
    if not speech_to_text_handler:
        raise HTTPException(status_code=500, detail="Speech-to-text unavailable")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    try:
        transcript = speech_to_text_handler(audio_bytes, file.content_type or "audio/webm")
    except Exception as exc:  # pragma: no cover - upstream errors
        logger.exception("STT failed: %s", exc)
        raise HTTPException(status_code=502, detail="Speech-to-text failed") from exc

    return {"text": transcript}


@router.post("/tts")
# Stream synthesised speech back to the caller.
async def synthesize_speech(payload: TTSRequest) -> StreamingResponse:
    if not stream_text_to_speech_handler:
        raise HTTPException(status_code=500, detail="TTS unavailable")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required for synthesis")

    voice_id = payload.voice_id or DEFAULT_VOICE_ID

    try:
        audio_stream = stream_text_to_speech_handler(text, voice_id)
    except Exception as exc:  # pragma: no cover - upstream errors
        logger.exception("TTS failed: %s", exc)
        raise HTTPException(status_code=502, detail="Text-to-speech failed") from exc

    headers = {"Content-Disposition": 'inline; filename="speech.mp3"'}
    return StreamingResponse(audio_stream, media_type="audio/mpeg", headers=headers)
