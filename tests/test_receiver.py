"""Unit tests for intrakom/receiver.py audio queue behaviour."""
import sys
import collections
import threading
from pathlib import Path

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
    yield
    rcv._audio_queue.clear()
    rcv._buffered_bytes = 0
    rcv._buf_ready.clear()
    rcv._stop_evt.clear()


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
