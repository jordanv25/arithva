"""Speech synthesis with a provider chain.

The order is deliberate:

  1. ElevenLabs, if a key is configured and the call succeeds.
  2. The browser's own speech synthesis, always.

The browser fallback is what makes this safe to demo. Arithva needs no API key
to work, so a missing key, an expired one, a rate limit or a slow network
degrades the voice rather than breaking the product. Nothing here ever raises:
a failure returns `unavailable` and the frontend speaks the same words with the
browser voice instead.

Configure with ELEVENLABS_API_KEY in .env. Without it, this module makes no
network calls at all.
"""

from __future__ import annotations

import os

import httpx

from .registry import ok, unavailable

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Both are overridable in .env. The defaults are ElevenLabs' own published
# values; VERIFY the voice id and model against your dashboard, and listen to a
# sample in each language you care about before relying on them.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# Short on purpose. A demo that waits eight seconds for audio has already
# failed; better to fall back to the browser voice quickly.
TIMEOUT_SECONDS = 6.0

# ElevenLabs charges per character, so a runaway string is a billing problem as
# well as a latency one. Our read-backs are a couple of sentences.
MAX_CHARACTERS = 800


def _api_key() -> str | None:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    return key or None


def status() -> dict:
    """Which provider is active, without making a network call.

    The citizen screen shows this, so a judge can see the integration is real
    and can see it degrade when the key is removed.
    """
    configured = _api_key() is not None
    return ok(
        {
            "primary": "elevenlabs" if configured else None,
            "fallback": "browser",
            "active": "elevenlabs" if configured else "browser",
            "configured": configured,
            "voice_id": os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID) if configured else None,
            "model_id": os.environ.get("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID) if configured else None,
            "note": (
                "ElevenLabs is configured. If a call fails for any reason, the browser "
                "voice speaks the same words instead."
                if configured else
                "No ElevenLabs key set, so the browser voice is used. Arithva needs no "
                "API key to work."
            ),
        },
        source="Arithva speech provider chain",
    )


def synthesize(text: str, language: str = "en-IN") -> dict:
    """Turn text into speech audio.

    Returns `ok` with MP3 bytes when ElevenLabs answers, or `unavailable` with
    a reason. `unavailable` is not an error path to be hidden: it is the signal
    for the frontend to use the browser voice.

    `language` is passed through for logging only. The multilingual model
    detects the language from the text itself, so one voice handles Kannada,
    Hindi and English without switching voices mid-conversation.
    """
    text = (text or "").strip()
    if not text:
        return unavailable("Nothing to speak.")

    key = _api_key()
    if key is None:
        return unavailable(
            "No ElevenLabs key configured, so the browser voice is used.",
            source="Arithva speech provider chain",
        )

    if len(text) > MAX_CHARACTERS:
        text = text[:MAX_CHARACTERS].rsplit(" ", 1)[0] + "."

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)

    try:
        response = httpx.post(
            f"{ELEVENLABS_URL}/{voice_id}",
            headers={"xi-api-key": key, "accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # Network down, DNS, timeout. Never raises to the caller.
        return unavailable(
            f"ElevenLabs did not answer ({type(exc).__name__}); using the browser voice.",
            source="ElevenLabs",
        )

    if response.status_code == 401:
        return unavailable(
            "ElevenLabs rejected the API key; using the browser voice.",
            source="ElevenLabs",
        )
    if response.status_code == 429:
        return unavailable(
            "ElevenLabs quota or rate limit reached; using the browser voice.",
            source="ElevenLabs",
        )
    if response.status_code >= 400:
        return unavailable(
            f"ElevenLabs returned {response.status_code}; using the browser voice.",
            source="ElevenLabs",
        )

    audio = response.content
    if not audio:
        return unavailable("ElevenLabs returned no audio; using the browser voice.",
                           source="ElevenLabs")

    return ok(
        {
            "audio": audio,
            "content_type": "audio/mpeg",
            "characters": len(text),
            "voice_id": voice_id,
            "model_id": model_id,
            "language_hint": language,
        },
        source=f"ElevenLabs text-to-speech ({model_id})",
        source_url="https://elevenlabs.io/",
    )
