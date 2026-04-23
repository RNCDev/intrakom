"""
server.py — FastAPI WebSocket intercom server.

Runs on port 8000. Receivers connect via /ws/receiver/{name}.
Senders connect via /ws/sender and push audio to named receivers.

Key design decisions:
  - Each receiver is tracked in a dict keyed by name so we can route audio.
  - Each receiver slot also stores which sender WebSocket currently "owns" it,
    so we can enforce the one-sender-per-receiver rule without a global lock.
  - Binary frames bypass JSON parsing for low latency audio forwarding.
  - RotatingFileHandler keeps logs bounded even on 24/7 deployments.
"""

import asyncio
import collections
import json
import logging
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

# Rate-limit repeated "failed to forward audio to X" warnings to once per 5s
# per receiver — otherwise an offline-but-still-owned receiver floods the log.
# Bounded to 256 entries to prevent unbounded growth with transient receiver names.
_FWD_WARN_INTERVAL = 5.0
_FWD_WARN_MAX = 256
_last_fwd_warn: "collections.OrderedDict[str, float]" = collections.OrderedDict()

def _record_fwd_warn(rname: str, ts: float) -> None:
    _last_fwd_warn[rname] = ts
    _last_fwd_warn.move_to_end(rname)
    while len(_last_fwd_warn) > _FWD_WARN_MAX:
        _last_fwd_warn.popitem(last=False)

# Valid receiver name: 1-64 chars, letters/digits/underscore/hyphen/space.
# Applied at WebSocket accept time to prevent log injection, absurdly large
# dict keys, and names that would break JSON reflections to senders.
_RECEIVER_NAME_RE = re.compile(r"^[A-Za-z0-9_\- ]{1,64}$")

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from intrakom import __version__
from intrakom import __version__ as HUB_VERSION
from intrakom import mdns as _mdns

# ---------------------------------------------------------------------------
# Logging — rotating so it never fills the disk
# ---------------------------------------------------------------------------
from intrakom.logging_setup import configure_logging
configure_logging("hub")
logger = logging.getLogger("intercom")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

# receiver_name → {"ws": WebSocket, "online": bool}
receivers: Dict[str, dict] = {}

# receiver_name → sender WebSocket that currently owns it.
# Used to enforce the one-active-stream-per-receiver rule.
receiver_owners: Dict[str, WebSocket] = {}

# sender WebSocket → set of receiver names it is streaming to.
# Needed so we can clean up when a sender drops without sending STOP.
sender_targets: Dict[WebSocket, Set[str]] = {}

# All currently connected sender WebSockets — used to push receiver list updates.
sender_connections: Set[WebSocket] = set()

# ---------------------------------------------------------------------------
# LAN IP detection
# ---------------------------------------------------------------------------

def detect_lan_ip() -> str:
    """
    Try the simplest approach first (gethostbyname), then fall back to
    connecting a UDP socket to a public address — this causes the OS to
    select the right source interface without actually sending any packets.
    """
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        pass

    return "127.0.0.1"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app):
    lan_ip = detect_lan_ip()
    hostname = socket.gethostname()
    port = int(os.environ.get("INTRAKOM_PORT", "8000"))
    scheme = os.environ.get("INTRAKOM_SCHEME", "https" if _ssl_context() else "http")
    mdns_disabled = bool(os.environ.get("INTRAKOM_DISABLE_MDNS"))
    tls_label = "enabled (cert found)" if scheme == "https" else "disabled (no cert)"
    mdns_label = "disabled (INTRAKOM_DISABLE_MDNS set)" if mdns_disabled else "enabled"

    logger.info("=" * 60)
    logger.info("Intercom server starting up")
    logger.info("Port:         %d", port)
    logger.info("LAN URL:      %s://%s:%d", scheme, lan_ip, port)
    logger.info("Hostname URL: %s://%s:%d", scheme, hostname, port)
    logger.info("TLS:          %s", tls_label)
    logger.info("mDNS:         %s", mdns_label)
    logger.info("=" * 60)
    print(f"\n{'='*60}")
    print(f"  Intercom Server Ready")
    print(f"  LAN URL:      {scheme}://{lan_ip}:{port}")
    print(f"  Hostname URL: {scheme}://{hostname}:{port}")
    print(f"  TLS:          {tls_label}")
    print(f"  mDNS:         {mdns_label}")
    print(f"{'='*60}\n")

    zc = None
    if not mdns_disabled:
        try:
            zc = _mdns.advertise_hub(port=port, version=HUB_VERSION)
        except Exception as exc:
            logger.warning("mDNS advertise failed: %s", exc)
    try:
        yield
    finally:
        if zc is not None:
            try:
                _mdns.unadvertise(zc)
            except Exception as exc:
                logger.warning("mDNS unregister failed: %s", exc)


app = FastAPI(title="Intercom Server", lifespan=_lifespan)

# Resolve static/ whether running from source or a PyInstaller onefile bundle
_STATIC_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "static"

# Serve static/ at the root URL so mobile browsers can load the sender UI
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    return FileResponse(str(_STATIC_DIR / "index.html"))

@app.get("/ping")
async def ping():
    return {"status": "ok"}

@app.get("/receivers")
async def list_receivers():
    return [
        {"name": name, "online": info["online"], "version": info.get("version", "unknown")}
        for name, info in receivers.items()
    ]


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    try:
        from packaging.version import Version, InvalidVersion
    except ImportError:
        Version = None
        InvalidVersion = Exception

    versions = []
    for info in receivers.values():
        v = info.get("version", "unknown")
        if Version and v not in ("", "unknown"):
            try:
                versions.append(Version(v))
            except InvalidVersion:
                pass
    latest = max(versions) if versions else None

    now = time.monotonic()
    rows = []
    for name, info in sorted(receivers.items()):
        v = info.get("version", "unknown")
        outdated = False
        if latest and Version and v not in ("", "unknown"):
            try:
                outdated = Version(v) < latest
            except InvalidVersion:
                pass
        status = "online" if info.get("online") else "offline"
        cell_class = "outdated" if outdated else ""
        last_seen = info.get("last_seen")
        if last_seen:
            age = int(now - last_seen)
            if age < 60:
                seen_str = f"{age}s ago"
            elif age < 3600:
                seen_str = f"{age // 60}m ago"
            else:
                seen_str = f"{age // 3600}h ago"
            stale_class = " stale" if age > 60 and not info.get("online") else ""
        else:
            seen_str = "—"
            stale_class = ""
        rows.append(
            f"<tr><td>{name}</td><td class='{status}'>{status}</td>"
            f"<td class='{cell_class}'>{v}</td>"
            f"<td class='{stale_class}'>{seen_str}</td></tr>"
        )

    html = f"""<!doctype html>
<html><head><title>Intrakom Hub — Admin</title>
<meta http-equiv="refresh" content="10">
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #ddd; }}
  th {{ background: #f4f4f4; }}
  td.online {{ color: #2a7f3a; font-weight: 600; }}
  td.offline {{ color: #a33; }}
  td.outdated {{ color: #a33; opacity: 0.85; }}
  td.stale {{ color: #999; }}
  .meta {{ color: #666; font-size: 0.9em; }}
</style></head>
<body>
  <h1>Intrakom Hub</h1>
  <p class='meta'>Hub v{__version__} &nbsp;·&nbsp; Latest receiver seen: {str(latest) if latest else "—"} &nbsp;·&nbsp; Auto-refreshes every 10s</p>
  <table>
    <thead><tr><th>Name</th><th>Status</th><th>Version</th><th>Last Seen</th></tr></thead>
    <tbody>{''.join(rows) if rows else '<tr><td colspan=4>No receivers connected yet.</td></tr>'}</tbody>
  </table>
</body></html>"""
    return html

# ---------------------------------------------------------------------------
# Receiver WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/receiver/{name}")
async def receiver_ws(websocket: WebSocket, name: str):
    if not _RECEIVER_NAME_RE.match(name):
        await websocket.close(code=1008, reason="Invalid receiver name")
        logger.warning("Rejected receiver with invalid name (len=%d)", len(name))
        return
    version = websocket.query_params.get("version", "unknown")
    await websocket.accept()
    logger.info("Receiver connected: %s (v%s)", name, version)

    receivers[name] = {"ws": websocket, "online": True, "version": version, "last_seen": time.monotonic()}
    await _broadcast_receivers()

    try:
        # Keep the connection alive. The receiver sends no meaningful data
        # upstream; we just need to detect disconnection.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Receiver disconnected: %s", name)
    except Exception as exc:
        logger.error("Receiver %s error: %s", name, exc)
    finally:
        # Only mark offline if this WebSocket is still the registered one.
        # A reconnect from the same receiver replaces the entry before the old
        # connection's finally block runs — without this guard, the cleanup
        # from the stale connection would incorrectly mark the new one offline.
        if name in receivers and receivers[name]["ws"] is websocket:
            receivers[name]["online"] = False
            receivers[name]["ws"] = None

            # Only release sender ownership if we're the current registration
            if name in receiver_owners:
                del receiver_owners[name]

            await _broadcast_receivers()

        logger.info("Receiver %s cleaned up", name)

# ---------------------------------------------------------------------------
# Sender WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/sender")
async def sender_ws(websocket: WebSocket):
    await websocket.accept()
    logger.info("Sender connected: %s", websocket.client)

    sender_connections.add(websocket)
    # Track which receivers this sender has claimed
    sender_targets[websocket] = set()
    active_sample_rate: Optional[int] = None

    # Send the current receiver list immediately on connect
    await websocket.send_text(json.dumps({
        "type": "RECEIVERS_UPDATE",
        "receivers": [
            {"name": name, "online": info["online"], "version": info.get("version", "unknown")}
            for name, info in receivers.items()
        ]
    }))

    try:
        while True:
            message = await websocket.receive()

            # --- Binary frame: raw PCM audio ---
            if "bytes" in message and message["bytes"] is not None:
                chunk = message["bytes"]
                targets = sender_targets.get(websocket, set())
                # Fan out concurrently so one slow receiver doesn't stall the
                # others. return_exceptions=True keeps a single failing send
                # from cancelling siblings.
                sends = []
                send_names: List[str] = []
                for rname in list(targets):
                    rec = receivers.get(rname)
                    if rec and rec["online"] and rec["ws"]:
                        sends.append(asyncio.wait_for(rec["ws"].send_bytes(chunk), timeout=2.0))
                        send_names.append(rname)
                if sends:
                    results = await asyncio.gather(*sends, return_exceptions=True)
                    now = time.monotonic()
                    for rname, result in zip(send_names, results):
                        if isinstance(result, Exception):
                            last = _last_fwd_warn.get(rname, 0.0)
                            if now - last >= _FWD_WARN_INTERVAL:
                                _record_fwd_warn(rname, now)
                                logger.warning(
                                    "Failed to forward audio to %s: %s", rname, result
                                )
                continue

            # --- Text frame: control message ---
            if "text" in message and message["text"] is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("Sender sent invalid JSON: %s", message["text"])
                    continue

                msg_type = data.get("type")

                if msg_type == "START":
                    requested_targets: List[str] = data.get("targets", [])
                    if not isinstance(requested_targets, list) or not all(
                        isinstance(t, str) for t in requested_targets
                    ):
                        await websocket.send_text(
                            json.dumps({"type": "ERROR", "reason": "invalid targets"})
                        )
                        continue

                    MAX_TARGETS = 50
                    if len(requested_targets) > MAX_TARGETS:
                        await websocket.send_text(
                            json.dumps({"type": "ERROR", "reason": "too many targets"})
                        )
                        continue

                    sr = data.get("sampleRate", 16000)
                    if not isinstance(sr, int) or not (8000 <= sr <= 96000):
                        await websocket.send_text(
                            json.dumps({"type": "ERROR", "reason": "invalid sampleRate"})
                        )
                        continue
                    active_sample_rate = sr

                    claimed: List[str] = []

                    for rname in requested_targets:
                        rec = receivers.get(rname)
                        if not rec or not rec["online"]:
                            # Receiver not available — skip silently
                            continue

                        # Simultaneous sender check: if another sender already
                        # owns this receiver, tell the new sender it's busy
                        # without touching the existing stream.
                        existing_owner = receiver_owners.get(rname)
                        if existing_owner is not None and existing_owner is not websocket:
                            logger.info(
                                "Receiver %s is busy (owned by another sender)", rname
                            )
                            try:
                                await websocket.send_text(
                                    json.dumps({"type": "BUSY", "receiver": rname})
                                )
                            except Exception:
                                pass
                            continue

                        # Send START to receiver first — only claim ownership on success.
                        # If send fails, the receiver never started playback, so we must
                        # not leave it marked as owned by a ghost stream.
                        try:
                            await rec["ws"].send_text(
                                json.dumps({"type": "START", "sampleRate": active_sample_rate})
                            )
                        except Exception as exc:
                            logger.warning(
                                "Failed to send START to receiver %s: %s", rname, exc
                            )
                            continue

                        receiver_owners[rname] = websocket
                        sender_targets[websocket].add(rname)
                        claimed.append(rname)

                    logger.info(
                        "Sender %s started stream to: %s", websocket.client, claimed
                    )

                elif msg_type == "STOP":
                    await _stop_sender_streams(websocket)
                    logger.info("Sender %s sent STOP", websocket.client)

    except WebSocketDisconnect:
        logger.info("Sender disconnected: %s", websocket.client)
    except Exception as exc:
        logger.error("Sender %s error: %s", websocket.client, exc)
    finally:
        # Dropped sender: if the sender disconnected without sending STOP,
        # we must still notify receivers and release ownership. Without this
        # cleanup, receivers would stay in a "streaming" state forever.
        await _stop_sender_streams(websocket)
        sender_connections.discard(websocket)
        if websocket in sender_targets:
            del sender_targets[websocket]
        logger.info("Sender %s cleaned up", websocket.client)


async def _broadcast_receivers():
    """Push the current receiver list to all connected senders."""
    if not sender_connections:
        return
    payload = json.dumps({
        "type": "RECEIVERS_UPDATE",
        "receivers": [
            {"name": name, "online": info["online"], "version": info.get("version", "unknown")}
            for name, info in receivers.items()
        ]
    })
    dead = set()
    for ws in sender_connections:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    sender_connections.difference_update(dead)


async def _stop_sender_streams(sender_ws: WebSocket):
    """
    Send STOP to all receivers owned by this sender and release ownership.
    Called both on explicit STOP message and on sender disconnect.
    """
    targets = sender_targets.get(sender_ws, set())
    for rname in list(targets):
        # Release ownership
        if receiver_owners.get(rname) is sender_ws:
            del receiver_owners[rname]

        rec = receivers.get(rname)
        if rec and rec["online"] and rec["ws"]:
            try:
                await rec["ws"].send_text(json.dumps({"type": "STOP"}))
            except Exception as exc:
                logger.warning("Failed to send STOP to %s: %s", rname, exc)

    sender_targets[sender_ws] = set()

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _ssl_context():
    """Return an SSL context if cert.pem and cert.key exist at repo root, else None."""
    import ssl
    cert, key = _REPO_ROOT / "cert.pem", _REPO_ROOT / "cert.key"
    if cert.exists() and key.exists():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        return ctx
    return None


def main():
    ssl_ctx = _ssl_context()
    uvicorn.run(
        "intrakom.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        ws_ping_interval=20,
        ws_ping_timeout=10,
        ssl_certfile=str(_REPO_ROOT / "cert.pem") if ssl_ctx else None,
        ssl_keyfile=str(_REPO_ROOT / "cert.key") if ssl_ctx else None,
    )


if __name__ == "__main__":
    main()
