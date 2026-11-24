"""The speech provider chain.

What matters is not that ElevenLabs works, but that Arithva keeps working when
it does not. These tests make no network calls.
"""

from __future__ import annotations

import pytest

from backend.tools import speech_tool


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")


def test_without_a_key_it_falls_back_without_calling_out(no_key, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no network call should happen without a key")

    monkeypatch.setattr(speech_tool.httpx, "post", explode)

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "unavailable"
    assert "browser voice" in result["reason"]


def test_status_reports_the_browser_when_unconfigured(no_key):
    value = speech_tool.status()["value"]
    assert value["configured"] is False
    assert value["active"] == "browser"
    assert value["fallback"] == "browser"


def test_status_reports_elevenlabs_when_configured(with_key):
    value = speech_tool.status()["value"]
    assert value["configured"] is True
    assert value["active"] == "elevenlabs"
    assert value["fallback"] == "browser"   # fallback stays available


@pytest.mark.parametrize("code,expected", [
    (401, "rejected the API key"),
    (429, "quota or rate limit"),
    (500, "returned 500"),
])
def test_api_errors_degrade_rather_than_raise(with_key, monkeypatch, code, expected):
    class FakeResponse:
        status_code = code
        content = b""

    monkeypatch.setattr(speech_tool.httpx, "post", lambda *a, **k: FakeResponse())

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "unavailable"
    assert expected in result["reason"]


def test_a_network_failure_degrades_rather_than_raises(with_key, monkeypatch):
    def boom(*args, **kwargs):
        raise TimeoutError("too slow")

    monkeypatch.setattr(speech_tool.httpx, "post", boom)

    result = speech_tool.synthesize("Hello")
    assert result["status"] == "unavailable"
    assert "browser voice" in result["reason"]


def test_successful_synthesis_returns_audio(with_key, monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b"fake-mp3-bytes"

    monkeypatch.setattr(speech_tool.httpx, "post", lambda *a, **k: FakeResponse())

    result = speech_tool.synthesize("One lakh fifty thousand rupees", "kn-IN")
    assert result["status"] == "ok"
    assert result["value"]["audio"] == b"fake-mp3-bytes"
    assert result["value"]["content_type"] == "audio/mpeg"
    assert "ElevenLabs" in result["source"]


def test_long_text_is_trimmed_before_it_is_billed(with_key, monkeypatch):
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


def test_empty_text_is_refused_early(with_key, monkeypatch):
    monkeypatch.setattr(speech_tool.httpx, "post",
                        lambda *a, **k: pytest.fail("should not call out"))
    assert speech_tool.synthesize("   ")["status"] == "unavailable"
