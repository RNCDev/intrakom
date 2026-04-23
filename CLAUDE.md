# CLAUDE.md

Guidance for Claude Code working in this repo.

## Commands

```bash
# Dev venv (one venv for everything — any Python 3.9+)
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate.bat
pip install -r requirements.txt -r requirements-dev.txt

# Run the hub
python hub.py

# Run a receiver (first run saves config; subsequent runs use saved config)
python -m intrakom.receiver --name "Living Room" --hub http://localhost:8000
python -m intrakom.receiver   # uses ~/.intrakom/config.ini

# Tests (INTRAKOM_DISABLE_MDNS=1 skips the slow mDNS roundtrip; conftest.py sets it)
pytest tests/ -q
```

## Package layout

```
intrakom/
  __init__.py            exports __version__
  _version.py            VERSION — CI overwrites from git tag
  paths.py               per-OS config/lock/log dirs
  logging_setup.py       configure_logging(component)
  single_instance.py     acquire(name) — fcntl on POSIX, named mutex on Windows
  mdns.py                advertise_hub / discover_hubs
  server.py              FastAPI hub
  receiver.py            headless receiver daemon (2 threads: ws-client + playback)

static/
  index.html             sender PWA
  manifest.json

packaging/
  linux/                 systemd service files + build_packages.sh
  macos/                 install.command, uninstall.sh, plist template
  windows/               install.bat, uninstall.bat

docs/
  hub-setup.md           Pi/Linux hub install guide
  receiver-setup.md      Windows + macOS receiver install guide
  sender-guide.md        how to use the browser sender
  troubleshooting.md     common issues
  uninstall-guide.md     full uninstall steps for all platforms

hub.py                   entry point: python hub.py [--port 8000]
receiver.spec            PyInstaller spec (onefile, all platforms, points to intrakom/receiver.py)
```

## Architecture

Three components over WebSocket:

```
[Browser]  ──/ws/sender──►  [hub]  ──/ws/receiver/{name}──►  [receiver]
           ◄── /admin ─────        ◄── GET /receivers ──────
```

**intrakom/server.py** — FastAPI + uvicorn, port 8000. Pure async. Routing state:
- `receivers` — `name → {ws, online, version, last_seen}` for every connected receiver
- `receiver_owners` — `name → sender_ws` enforces one-sender-per-receiver
- `sender_targets` — `sender_ws → set[name]` for cleanup on sender drop

On sender disconnect, `_stop_sender_streams()` sends STOP to owned receivers and releases ownership. FastAPI lifespan advertises mDNS on startup. Set `INTRAKOM_DISABLE_MDNS=1` to skip mDNS (used by pytest).

**intrakom/receiver.py** — two daemon threads:
- `ws-client` owns an asyncio loop; connects with 2→30s exponential backoff
- `playback` waits on `_buf_ready` event, drains `_audio_queue` (deque) into `sounddevice.RawOutputStream`

Jitter buffer fill: `bytes_needed = sample_rate × (jitter_ms / 1000) × 2` (Int16, mono). `_buf_ready` is set by ws-client when deque has enough data; cleared by playback thread on wake.

**static/index.html** — PWA sender. Float32→Int16: `Int16Array.from(float32, s => s * 32767 | 0)` (do NOT reinterpret float bits). Sends `audioContext.sampleRate` in START message.

**Audio pipeline:** Float32 (browser) → Int16 bytes → WebSocket → hub (forwards unchanged) → receiver deque → RawOutputStream.

## Key Constraints

- The hub never transforms audio bytes — it forwards `message["bytes"]` directly.
- Sample-rate negotiation is via the JSON START message's `sampleRate` field.
- Receiver config lives at `~/.intrakom/config.ini`. Written on first run with --name + --hub args.
- `_sample_rate` is written by ws-client before setting `_buf_ready`. Playback reads it after wake — no lock needed (Event provides the memory barrier).
- `INTRAKOM_DISABLE_MDNS=1` skips zeroconf entirely (used by tests to avoid 5s timeout).
- The audio queue in `receiver.py` is bounded at `_AUDIO_QUEUE_MAX_CHUNKS = 200` chunks. `_enqueue_audio()` enforces the cap; oldest chunk is dropped when full with a rate-limited warning.
- The playback `RawOutputStream` is kept open across START/STOP cycles via `_playback_iteration()`. It is only closed and reopened if `_sample_rate` changes or a write error occurs.
- Uvicorn is configured with `ws_ping_interval=20, ws_ping_timeout=10` in `hub.py` (via `_build_uvicorn_kwargs()`). This is the keepalive mechanism for receivers — no application-level ping messages are used.
- The admin page at `/admin` uses JS polling of `/receivers` every 10s (via `setInterval`) instead of `<meta http-equiv="refresh">`.

## Building receiver binaries

```bash
# macOS (requires: brew install portaudio)
pip install pyinstaller
pyinstaller receiver.spec

# Windows / Linux: same command, no extra deps
pyinstaller receiver.spec
```

Output: `dist/intrakom-receiver` (or `.exe` on Windows).

## Release process

1. Bump `intrakom/_version.py`.
2. `git tag v0.X.0 && git push origin v0.X.0`
3. GitHub Actions builds receiver binaries for all 4 platforms, bundles them with install scripts, and creates a GitHub Release with checksums.

The hub has no binary release — users run it from source.
