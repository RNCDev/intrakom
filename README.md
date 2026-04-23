# Intrakom — Private Home Intercom

A self-hosted intercom for your home network. Hold a button in your browser to talk to any room. No cloud, no accounts, no subscriptions.

```
[Browser — any device]  ──hold-to-talk──►  [Hub — Pi/server]  ──audio──►  [Receiver — Living Room PC]
                                                                ──audio──►  [Receiver — Office PC]
```

---

## Quick Start

### 1. Install the hub (once, on your always-on device)

The hub routes audio between rooms. Install it on a Raspberry Pi, home server, or any machine that's always on.

```bash
git clone https://github.com/RNCDev/intrakom.git
cd intrakom
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python hub.py
```

You'll see:
```
  Intrakom Server Ready
  LAN URL: http://192.168.1.10:8000
```

Open that URL to confirm it works. Then [set it up to run on boot →](docs/hub-setup.md)

### 2. Install the receiver (on each device that should play audio)

Download the right file from the [latest release](../../releases/latest):

| Device | Download |
|---|---|
| Windows PC | `intrakom-receiver-windows-x64.zip` |
| Mac (Apple Silicon) | `intrakom-receiver-macos-arm64.zip` |
| Raspberry Pi / Linux arm64 | `intrakom-receiver-linux-arm64.tar.gz` or `.deb` |
| Linux x86_64 | `intrakom-receiver-linux-x64.tar.gz` or `.deb` |

Unzip and run the install script. It will ask for a room name and your hub's address.

[Detailed receiver setup →](docs/receiver-setup.md)

### 3. Talk

Open `http://<hub-ip>:8000` in any browser on your network. Hold a button to talk to that room. Release to stop.

[Sender guide →](docs/sender-guide.md)

---

## Components

| Component | What it does | How it runs |
|---|---|---|
| **Hub** | Routes audio | `python hub.py` on your always-on device |
| **Receiver** | Plays audio | Background service, starts at login |
| **Sender** | Captures and sends your voice | A web page — no install |

---

## Admin page

`http://<hub-ip>:8000/admin` shows all receivers, their online/offline status, and when they were last seen. Auto-refreshes every 10 seconds.

---

## Architecture

```
Browser (Float32 mic) → Int16 → WebSocket → Hub → WebSocket → Receiver → sounddevice
```

- **`intrakom/server.py`** — FastAPI hub. Enforces one-sender-per-receiver. Forwards raw PCM bytes unchanged. Advertises mDNS for auto-discovery.
- **`intrakom/receiver.py`** — headless daemon. WebSocket client with jitter buffer + `sounddevice.RawOutputStream` playback. Two threads: WebSocket client + audio playback.
- **`static/index.html`** — PWA sender. Converts Float32→Int16 (`Int16Array.from(s => s * 32767 | 0)`), streams binary WebSocket frames.

---

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
INTRAKOM_DISABLE_MDNS=1 pytest tests/ -q

# Run hub
python hub.py

# Run receiver (separate terminal)
python -m intrakom.receiver --name "Test" --hub http://localhost:8000
```

See [CLAUDE.md](CLAUDE.md) for the full developer guide.

---

[Troubleshooting →](docs/troubleshooting.md)
