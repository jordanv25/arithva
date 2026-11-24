"""Speech synthesis with a provider chain.

The order is deliberate:

  1. ElevenLabs, if a key is configured and the call succeeds.
  2. Amazon Polly, if AWS credentials are configured and the call succeeds.
  3. The browser's own speech synthesis, always.

The browser fallback is what makes this safe to demo. Arithva needs no API key
to work, so a missing key, an expired one, a rate limit or a slow network
degrades the voice rather than breaking the product. Nothing here ever raises:
a failure moves to the next provider, and if all of them fail the frontend
speaks the same words with the browser voice.

Configure in .env. With nothing set, no network call is made at all.
"""

from __future__ import annotations

import os

import httpx

from .registry import ok, unavailable

# ----------------------------------------------------------------- ElevenLabs

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Overridable in .env. These are ElevenLabs' published defaults; VERIFY the
# voice id and model in your dashboard, and listen to a sample in each language
# you plan to demo before relying on them.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# ---------------------------------------------------------------------- Polly

# Kajal is Polly's Indian-English and Hindi neural voice. Whether Polly covers
# Kannada at all is UNVERIFIED — check the AWS docs for your region before
# claiming it. The chain means an unsupported language degrades rather than
# breaks.
DEFAULT_POLLY_VOICE = "Kajal"
DEFAULT_POLLY_ENGINE = "neural"
DEFAULT_POLLY_REGION = "ap-south-1"

# Short on purpose. A demo that waits eight seconds for audio has already
# failed; better to move down the chain quickly.
TIMEOUT_SECONDS = 6.0

# Both providers charge per character, so a runaway string is a billing problem
# as well as a latency one. Our read-backs are a couple of sentences.
MAX_CHARACTERS = 800


def _elevenlabs_key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip() or None


def _polly_configured() -> bool:
    """True when AWS credentials look present.

    Checks the standard environment variables. boto3 also reads ~/.aws/
    credentials and instance roles, so this is a conservative check: it may say
    no when Polly would in fact work. The chain handles that correctly anyway.
    """
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True
    return bool(os.environ.get("AWS_PROFILE"))


def status() -> dict:
    """Which providers are available, without making a network call.

    The citizen screen shows this, so a judge can see the integrations are real
    and can watch them degrade when a key is removed.
    """
    chain = []
    if _elevenlabs_key():
        chain.append("elevenlabs")
    if _polly_configured():
        chain.append("polly")
    chain.append("browser")

    return ok(
        {
            "chain": chain,
            "active": chain[0],
            "fallback": "browser",
            "configured": chain[0] != "browser",
            "elevenlabs": {
                "configured": _elevenlabs_key() is not None,
                "voice_id": os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
                if _elevenlabs_key() else None,
                "model_id": os.environ.get("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)
                if _elevenlabs_key() else None,
            },
            "polly": {
                "configured": _polly_configured(),
                "voice_id": os.environ.get("AWS_POLLY_VOICE_ID", DEFAULT_POLLY_VOICE)
                if _polly_configured() else None,
                "region": os.environ.get("AWS_REGION", DEFAULT_POLLY_REGION)
                if _polly_configured() else None,
            },
            "note": (
                f"Voice chain: {' then '.join(chain)}. Each one falls through to the "
                "next if it fails, so the answer is always spoken."
            ),
        },
        source="Arithva speech provider chain",
    )


def _try_elevenlabs(text: str) -> dict:
    key = _elevenlabs_key()
    if key is None:
        return unavailable("No ElevenLabs key configured.", source="ElevenLabs")

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
        return unavailable(f"ElevenLabs did not answer ({type(exc).__name__}).",
                           source="ElevenLabs")

    if response.status_code == 401:
        return unavailable("ElevenLabs rejected the API key.", source="ElevenLabs")
    if response.status_code == 429:
        return unavailable("ElevenLabs quota or rate limit reached.", source="ElevenLabs")
    if response.status_code >= 400:
        return unavailable(f"ElevenLabs returned {response.status_code}.",
                           source="ElevenLabs")
    if not response.content:
        return unavailable("ElevenLabs returned no audio.", source="ElevenLabs")

    return ok(
        {
            "audio": response.content,
            "content_type": "audio/mpeg",
            "provider": "elevenlabs",
            "voice_id": voice_id,
            "model_id": model_id,
            "characters": len(text),
        },
        source=f"ElevenLabs text-to-speech ({model_id})",
        source_url="https://elevenlabs.io/",
    )


def _try_polly(text: str) -> dict:
    """Amazon Polly.

    boto3 is imported here rather than at module load, so the project still
    runs for anyone who has not installed it. A missing library is just another
    reason to move down the chain.
    """
    if not _polly_configured():
        return unavailable("No AWS credentials configured.", source="Amazon Polly")

    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        return unavailable(
            "boto3 is not installed, so Polly cannot be used. Run: pip install boto3",
            source="Amazon Polly",
        )

    voice_id = os.environ.get("AWS_POLLY_VOICE_ID", DEFAULT_POLLY_VOICE)
    engine = os.environ.get("AWS_POLLY_ENGINE", DEFAULT_POLLY_ENGINE)
    region = os.environ.get("AWS_REGION", DEFAULT_POLLY_REGION)

    try:
        client = boto3.client(
            "polly",
            region_name=region,
            config=Config(connect_timeout=TIMEOUT_SECONDS,
                          read_timeout=TIMEOUT_SECONDS,
                          retries={"max_attempts": 1}),
        )
        response = client.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine=engine,
        )
        audio = response["AudioStream"].read()
    except Exception as exc:
        # Bad credentials, unsupported voice or language, region problem,
        # network. All the same from here: move down the chain.
        return unavailable(f"Polly did not answer ({type(exc).__name__}).",
                           source="Amazon Polly")

    if not audio:
        return unavailable("Polly returned no audio.", source="Amazon Polly")

    return ok(
        {
            "audio": audio,
            "content_type": "audio/mpeg",
            "provider": "polly",
            "voice_id": voice_id,
            "model_id": engine,
            "characters": len(text),
        },
        source=f"Amazon Polly ({voice_id}, {engine})",
        source_url="https://aws.amazon.com/polly/",
    )


def synthesize(text: str, language: str = "en-IN") -> dict:
    """Turn text into speech audio, trying each provider in turn.

    Returns `ok` with MP3 bytes from whichever provider answered, or
    `unavailable` listing what was tried. `unavailable` is not an error to be
    hidden: it is the signal for the frontend to use the browser voice.

    `language` is passed through for logging. ElevenLabs' multilingual model
    detects the language from the text itself; Polly picks it from the voice.
    """
    text = (text or "").strip()
    if not text:
        return unavailable("Nothing to speak.")

    if len(text) > MAX_CHARACTERS:
        text = text[:MAX_CHARACTERS].rsplit(" ", 1)[0] + "."

    attempts: list[str] = []

    for provider in (_try_elevenlabs, _try_polly):
        result = provider(text)
        if result["status"] == "ok":
            result["value"]["language_hint"] = language
            result["value"]["attempts"] = attempts
            return result
        attempts.append(f"{result['source']}: {result['reason']}")

    return unavailable(
        "No speech provider answered, so the browser voice is used. "
        + " | ".join(attempts),
        source="Arithva speech provider chain",
    )
