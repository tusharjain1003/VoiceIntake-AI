import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synthesize(
    text: str,
    api_key: str,
    voice_id: str,
    model: str = "eleven_multilingual_v2",
) -> Optional[bytes]:
    if not api_key or not voice_id:
        logger.warning("ElevenLabs not configured — skipping TTS")
        return None

    url = _ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPStatusError as exc:
        logger.error(
            "ElevenLabs TTS error (status=%d): %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.error("ElevenLabs TTS request failed: %s", exc)
    except Exception as exc:
        logger.error("ElevenLabs TTS unexpected error: %s", exc)

    return None
