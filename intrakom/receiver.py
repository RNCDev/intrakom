"""Headless audio receiver daemon.

Two threads:
  ws-client   asyncio loop, WebSocket client with exponential backoff
  playback    jitter-buffered RawOutputStream drain

Config: CLI args → ~/.intrakom/config.ini → print usage + exit
Autostart is handled by the install scripts in packaging/.
"""

import argparse
import asyncio
import collections
import configparser
import json
import logging
import ssl as _ssl
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import sounddevice as sd
import websockets

from intrakom import __version__
from intrakom import single_instance
from intrakom.logging_setup import configure_logging

logger = logging.getLogger("receiver")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_FILE = Path.home() / ".intrakom" / "config.ini"


@dataclass
class ReceiverConfig:
    name: str
    hub_url: str
    jitter_ms: int = 80


def load_config(args: argparse.Namespace) -> ReceiverConfig:
    name = args.name
    hub_url = args.hub
    jitter_ms = args.jitter

    if not (name and hub_url):
        if not CONFIG_FILE.exists():
            print("No config found. Run with --name and --hub to configure, e.g.:")
            print("  receiver --name 'Living Room' --hub http://pi.local:8000")
            sys.exit(1)
        cp = configparser.ConfigParser()
        cp.read(CONFIG_FILE)
        name = name or cp.get("receiver", "name", fallback=None)
        hub_url = hub_url or cp.get("receiver", "hub_url", fallback=None)
        if jitter_ms is None:
            jitter_ms = cp.getint("receiver", "jitter_ms", fallback=80)
        if not name or not hub_url:
            print("Config incomplete. Run with --name and --hub to reconfigure:")
            print("  receiver --name 'Living Room' --hub http://pi.local:8000")
            sys.exit(1)

    # Persist on first run with explicit args so subsequent headless starts work.
    if args.name and args.hub:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        cp = configparser.ConfigParser()
        if CONFIG_FILE.exists():
            cp.read(CONFIG_FILE)
        if "receiver" not in cp:
            cp["receiver"] = {}
        cp["receiver"]["name"] = name
        cp["receiver"]["hub_url"] = hub_url.rstrip("/")
        cp["receiver"]["jitter_ms"] = str(jitter_ms or 80)
        with open(CONFIG_FILE, "w") as fh:
            cp.write(fh)
        logger.info("Config saved to %s", CONFIG_FILE)

    return ReceiverConfig(
        name=name,
        hub_url=hub_url.rstrip("/"),
        jitter_ms=jitter_ms or 80,
    )


# ---------------------------------------------------------------------------
# Shared audio state (written by ws thread, read by playback thread)
# ---------------------------------------------------------------------------

_audio_queue: collections.deque = collections.deque()
_audio_cv = threading.Condition()
_buffered_bytes: int = 0      # maintained under _audio_cv for O(1) check
_bytes_needed: int = 0        # set by START handler before setting _buf_ready
_sample_rate: int = 44100     # written before _buf_ready.set(); safe without lock

_buf_ready = threading.Event()  # buffer has >= jitter_ms of audio; start playback
_stop_evt = threading.Event()   # STOP received or ws disconnected mid-stream

_stream: Optional[sd.RawOutputStream] = None
_stream_sr: int = 0

_AUDIO_QUEUE_MAX_CHUNKS = 200   # ~6s at 16kHz mono int16, ~400KB
_queue_drop_warned_at: float = -6.0  # ensures first drop always warns


def _enqueue_audio(chunk: bytes) -> None:
    """Append audio chunk to queue, dropping the oldest if at capacity."""
    global _buffered_bytes, _queue_drop_warned_at

    with _audio_cv:
        if len(_audio_queue) >= _AUDIO_QUEUE_MAX_CHUNKS:
            dropped = _audio_queue.popleft()
            _buffered_bytes -= len(dropped)
            now = time.monotonic()
            if now - _queue_drop_warned_at >= 5.0:
                _queue_drop_warned_at = now
                logger.warning(
                    "Audio queue full (%d chunks); dropping oldest chunk",
                    _AUDIO_QUEUE_MAX_CHUNKS,
                )
        _audio_queue.append(chunk)
        _buffered_bytes += len(chunk)
        if _buffered_bytes >= _bytes_needed and not _buf_ready.is_set():
            _buf_ready.set()
        _audio_cv.notify_all()

# SSL context for wss:// (self-signed LAN certs, no hostname verification)
_ssl_ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = _ssl.CERT_NONE


# ---------------------------------------------------------------------------
# Playback thread
# ---------------------------------------------------------------------------

def _playback_iteration() -> None:
    """Run one START→STOP playback cycle. Reuses open stream if sample rate unchanged."""
    global _buffered_bytes, _stream, _stream_sr

    sr = _sample_rate

    try:
        if _stream is None or _stream_sr != sr:
            if _stream is not None:
                try:
                    _stream.stop()
                    _stream.close()
                except Exception:
                    pass
            _stream = sd.RawOutputStream(
                samplerate=sr, channels=1, dtype="int16", blocksize=1024
            )
            _stream.start()
            _stream_sr = sr
            logger.info("Audio stream opened at %d Hz", sr)

        while True:
            with _audio_cv:
                while not _audio_queue and not _stop_evt.is_set():
                    _audio_cv.wait(timeout=0.1)
                chunk = _audio_queue.popleft() if _audio_queue else None
                if chunk:
                    _buffered_bytes -= len(chunk)

            if chunk is None:
                break  # _stop_evt set and queue drained

            try:
                _stream.write(chunk)
            except Exception as exc:
                logger.error("Stream write error: %s", exc)
                _stream = None  # force reopen on next START
                break

    except Exception as exc:
        logger.error("Failed to open audio device: %s", exc)
        _stream = None

    finally:
        _stop_evt.clear()
        with _audio_cv:
            _audio_queue.clear()
            _buffered_bytes = 0


def playback_thread_func():
    global _buffered_bytes

    while True:
        _buf_ready.wait()
        _buf_ready.clear()

        # Spurious wake during a disconnect-before-START
        if _stop_evt.is_set():
            _stop_evt.clear()
            continue

        _playback_iteration()


# ---------------------------------------------------------------------------
# WebSocket client
# ---------------------------------------------------------------------------

async def ws_client(cfg: ReceiverConfig):
    global _buffered_bytes, _sample_rate, _bytes_needed

    # Normalize http→ws, https→wss
    base = cfg.hub_url.replace("https://", "wss://").replace("http://", "ws://")
    url = f"{base}/ws/receiver/{quote(cfg.name)}?version={quote(__version__)}"
    ssl_arg = _ssl_ctx if base.startswith("wss://") else None

    delay = 2.0

    while True:
        logger.info("Connecting to hub (retry delay %.0fs)", delay)
        try:
            async with websockets.connect(
                url, ssl=ssl_arg, ping_interval=20, ping_timeout=10
            ) as ws:
                delay = 2.0
                logger.info("Connected as '%s'", cfg.name)

                async for message in ws:
                    if isinstance(message, bytes):
                        _enqueue_audio(message)

                    elif isinstance(message, str):
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        msg_type = data.get("type")

                        if msg_type == "START":
                            _sample_rate = data.get("sampleRate", 44100)
                            _bytes_needed = int(_sample_rate * (cfg.jitter_ms / 1000.0) * 2)
                            logger.info(
                                "START: %d Hz, jitter buffer %d bytes",
                                _sample_rate, _bytes_needed,
                            )
                            with _audio_cv:
                                _audio_queue.clear()
                                _buffered_bytes = 0
                            _stop_evt.clear()
                            _buf_ready.clear()

                        elif msg_type == "STOP":
                            logger.info("STOP received")
                            _stop_evt.set()
                            _buf_ready.set()  # wake playback so it can drain+exit
                            with _audio_cv:
                                _audio_cv.notify_all()

        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.WebSocketException,
            OSError,
        ) as exc:
            logger.warning("WebSocket disconnected: %s", exc)
        except Exception as exc:
            logger.error("Unexpected error: %s", exc)

        # Ensure playback stops if we were mid-stream
        _stop_evt.set()
        _buf_ready.set()
        with _audio_cv:
            _audio_cv.notify_all()

        logger.info("Reconnecting in %.0fs", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)


def ws_thread_func(cfg: ReceiverConfig):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ws_client(cfg))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Intrakom receiver — headless audio daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  receiver.py --name 'Living Room' --hub http://pi.local:8000\n"
            "  receiver.py  # uses saved ~/.intrakom/config.ini\n"
        ),
    )
    parser.add_argument("--name", help="Receiver name shown on the hub (e.g. 'Living Room')")
    parser.add_argument("--hub", help="Hub URL (e.g. http://pi.local:8000 or http://192.168.1.10:8000)")
    parser.add_argument("--jitter", type=int, metavar="MS", help="Jitter buffer size in ms (default 80)")
    args = parser.parse_args()

    configure_logging("receiver")
    cfg = load_config(args)

    logger.info("Intrakom receiver v%s starting as '%s'", __version__, cfg.name)
    logger.info("Hub: %s  jitter: %dms", cfg.hub_url, cfg.jitter_ms)

    handle = single_instance.acquire(cfg.name)
    if handle is None:
        logger.error("Another receiver named '%s' is already running. Exiting.", cfg.name)
        sys.exit(1)
    main._lock = handle  # keep the lock alive for the process lifetime

    pb = threading.Thread(target=playback_thread_func, daemon=True, name="playback")
    pb.start()

    ws = threading.Thread(target=ws_thread_func, args=(cfg,), daemon=True, name="ws-client")
    ws.start()
    ws.join()  # blocks until ws thread exits (which it never does normally)


if __name__ == "__main__":
    main()
