"""Unit tests for intrakom/receiver.py audio queue behaviour."""
import sys
import collections
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import intrakom.receiver as rcv


@pytest.fixture(autouse=True)
def reset_audio_state():
    rcv._audio_queue.clear()
    rcv._buffered_bytes = 0
    rcv._bytes_needed = 0
    rcv._buf_ready.clear()
    rcv._stop_evt.clear()
    rcv._stream = None
    rcv._stream_sr = 0
    rcv._queue_drop_warned_at = -6.0
    yield
    rcv._audio_queue.clear()
    rcv._buffered_bytes = 0
    rcv._buf_ready.clear()
    rcv._stop_evt.clear()
    rcv._stream = None
    rcv._stream_sr = 0
    rcv._queue_drop_warned_at = -6.0


def test_queue_accepts_chunks_below_cap():
    chunk = b"\x00\x01" * 100
    for _ in range(rcv._AUDIO_QUEUE_MAX_CHUNKS):
        rcv._enqueue_audio(chunk)
    assert len(rcv._audio_queue) == rcv._AUDIO_QUEUE_MAX_CHUNKS


def test_queue_drops_oldest_when_at_cap(caplog):
    import logging
    chunk_a = b"\xAA" * 100
    chunk_b = b"\xBB" * 100
    for _ in range(rcv._AUDIO_QUEUE_MAX_CHUNKS):
        rcv._enqueue_audio(chunk_a)
    with caplog.at_level(logging.WARNING, logger="receiver"):
        rcv._enqueue_audio(chunk_b)
    assert len(rcv._audio_queue) == rcv._AUDIO_QUEUE_MAX_CHUNKS
    assert rcv._audio_queue[-1] == chunk_b
    assert "queue full" in caplog.text.lower()


def test_buffered_bytes_stays_accurate_after_drop():
    chunk = b"\x00" * 200
    for _ in range(rcv._AUDIO_QUEUE_MAX_CHUNKS):
        rcv._enqueue_audio(chunk)
    expected = rcv._AUDIO_QUEUE_MAX_CHUNKS * len(chunk)
    assert rcv._buffered_bytes == expected
    rcv._enqueue_audio(chunk)
    assert rcv._buffered_bytes == expected


def test_audio_stream_reused_for_same_sample_rate():
    """RawOutputStream must be instantiated only once across two START/STOP cycles at the same sample rate."""
    call_count = 0

    def make_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.write = MagicMock()
        return m

    with patch("sounddevice.RawOutputStream", side_effect=make_stream):
        rcv._sample_rate = 16000
        rcv._bytes_needed = 0

        # Cycle 1
        rcv._enqueue_audio(b"\x00" * 32)
        rcv._buf_ready.set()
        rcv._stop_evt.set()
        rcv._playback_iteration()

        # Cycle 2 — same sample rate
        rcv._enqueue_audio(b"\x00" * 32)
        rcv._buf_ready.set()
        rcv._stop_evt.set()
        rcv._playback_iteration()

    assert call_count == 1, f"Expected 1 stream creation, got {call_count}"


def test_audio_stream_reopened_for_different_sample_rate():
    """RawOutputStream must be recreated when sample rate changes between transmissions."""
    call_count = 0

    def make_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        return MagicMock()

    with patch("sounddevice.RawOutputStream", side_effect=make_stream):
        rcv._sample_rate = 16000
        rcv._bytes_needed = 0
        rcv._enqueue_audio(b"\x00" * 32)
        rcv._buf_ready.set()
        rcv._stop_evt.set()
        rcv._playback_iteration()

        # Change sample rate between transmissions
        rcv._sample_rate = 44100
        rcv._enqueue_audio(b"\x00" * 32)
        rcv._buf_ready.set()
        rcv._stop_evt.set()
        rcv._playback_iteration()

    assert call_count == 2, f"Expected 2 stream creations (rate changed), got {call_count}"
