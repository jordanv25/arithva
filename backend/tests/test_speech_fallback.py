"""The speech provider chain.

What matters is not that ElevenLabs or Polly work, but that Arithva keeps
working when they do not. These tests make no network calls.
"""

from __future__ import annotations

import pytest

from backend.tools import speech_tool

AWS_VARS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE")


@pytest.fixture
def nothing_configured(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    for var in AWS_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def elevenlabs_only(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    for var in AWS_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def polly_only(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key-not-real")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret-not-real")


# ------------------------------------------------------------------- status

def test_chain_is_browser_only_when_nothing_is_configured(nothing_configured):
    value = speech_tool.status()["value"]
    assert value["chain"] == ["browser"]
    assert value["active"] == "browser"
    assert value["configured"] is False


def test_chain_reports_both_providers_when_both_configured(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    value = speech_tool.status()["value"]
    assert value["chain"] == ["elevenlabs", "polly", "browser"]
    assert value["active"] == "elevenlabs"
    assert value["fallback"] == "browser"      # always the last resort


def test_polly_leads_the_chain_when_elevenlabs_is_absent(polly_only):
    value = speech_tool.status()["value"]
    assert value["chain"] == ["polly", "browser"]
    assert value["active"] == "polly"


# ----------------------------------------------------------------- fallback

def test_nothing_configured_makes_no_network_call(nothing_configured, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no network call should happen with nothing configured")

    monkeypatch.setattr(speech_tool.httpx, "post", explode)

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "unavailable"
    assert "browser voice" in result["reason"]


@pytest.mark.parametrize("code,expected", [
    (401, "rejected the API key"),
    (429, "quota or rate limit"),
    (500, "returned 500"),
])
def test_elevenlabs_errors_degrade_rather_than_raise(elevenlabs_only, monkeypatch,
                                                     code, expected):
    class FakeResponse:
        status_code = code
        content = b""

    monkeypatch.setattr(speech_tool.httpx, "post", lambda *a, **k: FakeResponse())

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "unavailable"
    assert expected in result["reason"]


def test_a_network_failure_degrades_rather_than_raises(elevenlabs_only, monkeypatch):
    def boom(*args, **kwargs):
        raise TimeoutError("too slow")

    monkeypatch.setattr(speech_tool.httpx, "post", boom)

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "unavailable"
    assert "browser voice" in result["reason"]


def test_polly_catches_what_elevenlabs_drops(monkeypatch):
    """The point of the chain: one provider failing is not a failure."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "bad-key")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")

    class Rejected:
        status_code = 401
        content = b""

    monkeypatch.setattr(speech_tool.httpx, "post", lambda *a, **k: Rejected())
    monkeypatch.setattr(
        speech_tool, "_try_polly",
        lambda text: speech_tool.ok(
            {"audio": b"polly-mp3", "content_type": "audio/mpeg", "provider": "polly",
             "voice_id": "Kajal", "model_id": "neural", "characters": len(text)},
            source="Amazon Polly (Kajal, neural)"),
    )

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "ok"
    assert result["value"]["provider"] == "polly"
    # and it records why the first provider was skipped
    assert any("ElevenLabs" in attempt for attempt in result["value"]["attempts"])


def test_polly_without_boto3_degrades(polly_only, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_boto3(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("no boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_boto3)

    result = speech_tool._try_polly("Hello")
    assert result["status"] == "unavailable"
    assert "boto3 is not installed" in result["reason"]


# ------------------------------------------------------------------ success

def test_successful_synthesis_returns_audio(elevenlabs_only, monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b"fake-mp3-bytes"

    monkeypatch.setattr(speech_tool.httpx, "post", lambda *a, **k: FakeResponse())

    result = speech_tool.synthesize("One lakh fifty thousand rupees", "kn-IN")
    assert result["status"] == "ok"
    assert result["value"]["audio"] == b"fake-mp3-bytes"
    assert result["value"]["provider"] == "elevenlabs"
    assert result["value"]["content_type"] == "audio/mpeg"


def test_long_text_is_trimmed_before_it_is_billed(elevenlabs_only, monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"audio"

    def capture(url, **kwargs):
        captured["text"] = kwargs["json"]["text"]
        return FakeResponse()

    monkeypatch.setattr(speech_tool.httpx, "post", capture)

    speech_tool.synthesize("word " * 500)
    assert len(captured["text"]) <= speech_tool.MAX_CHARACTERS


def test_empty_text_is_refused_early(elevenlabs_only, monkeypatch):
    monkeypatch.setattr(speech_tool.httpx, "post",
                        lambda *a, **k: pytest.fail("should not call out"))
    assert speech_tool.synthesize("   ")["status"] == "unavailable"
