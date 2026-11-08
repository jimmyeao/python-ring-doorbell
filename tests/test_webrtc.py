"""Tests for the WebRTC stream handling on doorbells and intercoms."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from ring_doorbell.doorbot import RingDoorBell
from ring_doorbell.other import RingOther
from ring_doorbell.webrtcdevice import RingWebRtcMixin
from ring_doorbell.webrtcstream import RingWebRtcMessage, RingWebRtcStream

SDP_OFFER = "v=0\r\n" "o=- 987654321 1 IN IP4 127.0.0.1\r\n" "s=-\r\n" "t=0 0\r\n"
SESSION_ID = "987654321"
CANDIDATE = "candidate:1 1 udp 123 192.168.1.2 5000 typ host"


def get_doorbell(ring) -> RingDoorBell:
    """Return the mocked doorbell device."""
    return ring.devices()["doorbots"][0]


def test_intercom_has_webrtc_methods():
    for cls in (RingDoorBell, RingOther):
        assert issubclass(cls, RingWebRtcMixin)
        for name in (
            "generate_webrtc_stream",
            "generate_async_webrtc_stream",
            "on_webrtc_candidate",
            "close_webrtc_stream",
            "sync_close_webrtc_stream",
            "keep_alive_webrtc_stream",
            "get_ice_servers",
        ):
            assert callable(getattr(cls, name))


async def test_server_close_does_not_await_reader_from_itself():
    """Ring's close message is handled inside the reader task.

    _close() must not await read_task from within it, and the close reason
    must reach the message callback.
    """
    messages: list[RingWebRtcMessage] = []
    other = RingOther(MagicMock(), 1)
    stream = RingWebRtcStream(MagicMock(), 1, on_message_callback=messages.append)

    async def _close_callback() -> None:
        other._webrtc_streams.pop("session", None)

    stream._on_close_callback = _close_callback
    stream.websocket = AsyncMock()
    stream.is_alive = True
    other._webrtc_streams["session"] = stream

    async def reader() -> None:
        await stream.handle_close_message(
            {"body": {"reason": {"code": 1, "text": "bye"}}}
        )

    stream.read_task = asyncio.create_task(reader())
    await stream.read_task

    assert "session" not in other._webrtc_streams
    assert [(m.error_code, m.error_message) for m in messages] == [(1, "bye")]


async def test_on_webrtc_candidate_unknown_session_does_not_raise(ring) -> None:
    """An ICE candidate for a session with no stream must not raise (#560)."""
    dev = get_doorbell(ring)

    # No stream registered for this session: the trickle-ICE race.
    await dev.on_webrtc_candidate("no-such-session", CANDIDATE, 0)


async def test_on_webrtc_candidate_after_close_does_not_raise(ring) -> None:
    """An ICE candidate arriving after the stream closed must not raise."""
    dev = get_doorbell(ring)
    stream = AsyncMock()
    dev._webrtc_streams[SESSION_ID] = stream

    await dev.close_webrtc_stream(SESSION_ID)
    assert SESSION_ID not in dev._webrtc_streams

    await dev.on_webrtc_candidate(SESSION_ID, CANDIDATE, 0)


async def test_on_webrtc_candidate_during_generate_is_delivered(ring, mocker) -> None:
    """A candidate arriving while generate is running reaches the stream."""
    dev = get_doorbell(ring)
    generate_started = asyncio.Event()
    release_generate = asyncio.Event()

    async def fake_generate(self, _offer: str) -> str:
        generate_started.set()
        await release_generate.wait()
        return "v=0\r\ns=answer\r\n"

    # Patch the methods, not the class: patching the class would also
    # replace get_sdp_session_id, so the stream would register under a
    # mock session id instead of the offer's real one.
    on_ice = mocker.patch.object(RingWebRtcStream, "on_ice_candidate", new=AsyncMock())
    mocker.patch.object(RingWebRtcStream, "generate", new=fake_generate)

    task = asyncio.create_task(dev.generate_webrtc_stream(SDP_OFFER))
    try:
        await generate_started.wait()
        # The stream is not yet registered on base: this raises RingError.
        await dev.on_webrtc_candidate(SESSION_ID, CANDIDATE, 0)
    finally:
        release_generate.set()
        await task

    on_ice.assert_awaited_once_with(CANDIDATE, 0)
    assert SESSION_ID in dev._webrtc_streams


async def test_generate_webrtc_stream_unregisters_on_failure(ring, mocker) -> None:
    """A failed generate must not leave a stale stream registered."""
    dev = get_doorbell(ring)
    mocker.patch.object(
        RingWebRtcStream,
        "generate",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await dev.generate_webrtc_stream(SDP_OFFER)

    assert SESSION_ID not in dev._webrtc_streams


async def test_generate_webrtc_stream_cancellation_unregisters(ring, mocker) -> None:
    """Cancelling generate must not leave a stale stream registered."""
    dev = get_doorbell(ring)
    generate_started = asyncio.Event()

    async def fake_generate(self, _offer: str) -> str:
        generate_started.set()
        await asyncio.Event().wait()
        return "v=0\r\ns=answer\r\n"

    mocker.patch.object(RingWebRtcStream, "generate", new=fake_generate)

    task = asyncio.create_task(dev.generate_webrtc_stream(SDP_OFFER))
    await generate_started.wait()
    stream = dev._webrtc_streams[SESSION_ID]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert SESSION_ID not in dev._webrtc_streams
    assert stream.is_alive is False


async def test_generate_async_webrtc_stream_cancellation_unregisters(
    ring, mocker
) -> None:
    """Cancelling the async generate must not leave a stale stream."""
    dev = get_doorbell(ring)
    generate_started = asyncio.Event()

    async def fake_generate(self, _offer: str) -> str:
        generate_started.set()
        await asyncio.Event().wait()
        return "v=0\r\ns=answer\r\n"

    mocker.patch.object(RingWebRtcStream, "generate", new=fake_generate)

    task = asyncio.create_task(
        dev.generate_async_webrtc_stream(SDP_OFFER, SESSION_ID, lambda _: None)
    )
    await generate_started.wait()
    stream = dev._webrtc_streams[SESSION_ID]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert SESSION_ID not in dev._webrtc_streams
    assert stream.is_alive is False


async def test_on_webrtc_candidate_live_stream_forwards(ring) -> None:
    """A candidate for a live stream is still forwarded (control case)."""
    dev = get_doorbell(ring)
    stream = AsyncMock()
    dev._webrtc_streams[SESSION_ID] = stream

    await dev.on_webrtc_candidate(SESSION_ID, CANDIDATE, 0)

    stream.on_ice_candidate.assert_awaited_once_with(CANDIDATE, 0)
