"""Regression tests for WebRTC stream teardown."""

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, Mock

import pytest
from ring_doorbell.webrtcstream import RingWebRtcMessage, RingWebRtcStream

CLOSE_MESSAGE = {
    "method": "close",
    "body": {"reason": {"code": "normal", "text": "Session ended"}},
}


class WebSocketStub:
    """A deterministic in-memory websocket; never connects to Ring."""

    def __init__(self) -> None:
        """Initialize the message queue and close notification."""
        self.messages: asyncio.Queue = asyncio.Queue()
        self.closed = asyncio.Event()
        self.close_calls = 0

    def __aiter__(self) -> WebSocketStub:
        """Return the websocket message iterator."""
        return self

    async def __anext__(self) -> str:
        """Read the next queued message, or finish after close."""
        message = await self.messages.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def close(self) -> None:
        """Wake the reader as a closed websocket would."""
        self.close_calls += 1
        self.closed.set()
        self.messages.put_nowait(None)


async def start_reader(stream, websocket):
    """Start a real reader task and a cancellable keep-alive task."""
    stream.websocket = websocket
    stream.session_id = "test-session"
    stream.read_task = asyncio.create_task(stream.reader())
    stream.ping_task = asyncio.create_task(asyncio.Event().wait())
    # Let both tasks start, so cancelling keep-alive exercises its await path.
    await asyncio.sleep(0)
    return stream.read_task, stream.ping_task


async def stop_tasks(*tasks: asyncio.Task) -> None:
    """Leave no pending task behind even when a regression assertion fails."""
    for task in tasks:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            await task


@pytest.mark.parametrize("with_close_callback", [False, True])
async def test_server_close_from_reader(with_close_callback):
    """A server close must finish without the reader awaiting itself."""
    on_message = Mock()
    on_close = AsyncMock()
    stream = RingWebRtcStream(
        Mock(),
        123,
        on_message_callback=on_message,
        on_close_callback=on_close if with_close_callback else None,
    )
    websocket = WebSocketStub()
    reader, pinger = await start_reader(stream, websocket)
    websocket.messages.put_nowait(json.dumps(CLOSE_MESSAGE))
    try:
        await asyncio.wait_for(asyncio.shield(reader), timeout=1)
        assert stream.is_alive is False
        assert stream.session_id is None
        assert stream.websocket is None
        assert stream.read_task is None
        assert stream.ping_task is None
        assert pinger.cancelled()
        assert websocket.close_calls == 1
        on_message.assert_called_once_with(
            RingWebRtcMessage(error_code="normal", error_message="Session ended")
        )
        if with_close_callback:
            on_close.assert_awaited_once_with()
        else:
            on_close.assert_not_awaited()

        # A caller may also close after the server has already finished.
        await stream.close()
        assert websocket.close_calls == 1
        assert on_close.await_count == int(with_close_callback)
    finally:
        await stop_tasks(reader, pinger)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_doorbot_server_close_and_reopen(ring, mocker, asynchronous):
    """Exercise the real DoorBot callback that re-enters stream.close()."""
    doorbot = ring.devices()["doorbots"][0]
    streams = []
    tasks = []
    on_message = Mock()

    async def generate(stream, sdp_offer) -> None:
        websocket = WebSocketStub()
        streams.append((stream, websocket))
        tasks.extend(await start_reader(stream, websocket))
        stream.sdp = "test-answer"
        stream._sdp_answer_event.set()

    mocker.patch.object(RingWebRtcStream, "_generate", generate)

    try:
        # Reuse the same offer identity only after the previous reader exits.
        # No real Ring API, camera, authentication, or websocket is involved.
        for _ in range(2):
            offer = "v=0\no=- 123 1 IN IP4 127.0.0.1\n"
            if asynchronous:
                await doorbot.generate_async_webrtc_stream(offer, "123", on_message)
            else:
                assert await doorbot.generate_webrtc_stream(offer) == "test-answer"
            stream, websocket = streams[-1]
            assert doorbot._webrtc_streams == {"123": stream}
            reader = stream.read_task
            websocket.messages.put_nowait(json.dumps(CLOSE_MESSAGE))
            await asyncio.wait_for(asyncio.shield(reader), timeout=1)

            assert doorbot._webrtc_streams == {}
            assert stream.is_alive is False
            assert stream.session_id is None
            assert stream.websocket is None
            assert stream.read_task is None
            assert stream.ping_task is None
            assert stream._on_close_callback is None
            assert websocket.close_calls == 1

        assert len(streams) == 2
        assert streams[0][0] is not streams[1][0]
        assert on_message.call_count == (2 if asynchronous else 0)
        if asynchronous:
            on_message.assert_called_with(
                RingWebRtcMessage(error_code="normal", error_message="Session ended")
            )
    finally:
        await stop_tasks(*tasks)


async def test_external_close_waits_for_reader():
    """Do not fix self-await by dropping the await for a different reader task."""
    websocket = WebSocketStub()
    on_close = AsyncMock()
    stream = RingWebRtcStream(Mock(), 123, on_close_callback=on_close)
    stream.websocket = websocket
    release_reader = asyncio.Event()
    reader_finished = asyncio.Event()

    async def reader() -> None:
        await websocket.closed.wait()
        await release_reader.wait()
        reader_finished.set()

    stream.read_task = read_task = asyncio.create_task(reader())
    close_task = asyncio.create_task(stream.close())
    try:
        await asyncio.wait_for(websocket.closed.wait(), timeout=1)
        assert not close_task.done()
        assert not reader_finished.is_set()

        release_reader.set()
        await asyncio.wait_for(asyncio.shield(close_task), timeout=1)
        assert reader_finished.is_set()
        assert read_task.done()
        assert not read_task.cancelled()
        assert stream.read_task is None
        assert stream.websocket is None
        assert stream.is_alive is False
        on_close.assert_not_awaited()
        await stream.close()
        assert websocket.close_calls == 1
    finally:
        release_reader.set()
        await stop_tasks(close_task, read_task)


async def test_close_without_started_tasks():
    """Closing an unstarted stream repeatedly is harmless."""
    stream = RingWebRtcStream(Mock(), 123)
    await stream.close()
    await stream.close()
    assert stream.is_alive is False
    assert stream.websocket is None
    assert stream.read_task is None
    assert stream.ping_task is None
    assert stream._close_task is None
