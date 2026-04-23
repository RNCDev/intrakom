"""
Integration tests for server.py — exercise the FastAPI app via its
TestClient, covering receiver name validation, receiver registration,
BUSY response for simultaneous senders, audio fan-out, and cleanup
on sender disconnect.

Run with:  pytest tests/
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Allow `import server` when pytest runs from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import intrakom.server as srv  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state():
    srv.receivers.clear()
    srv.receiver_owners.clear()
    srv.sender_targets.clear()
    yield
    srv.receivers.clear()
    srv.receiver_owners.clear()
    srv.sender_targets.clear()


@pytest.fixture
def client():
    with TestClient(srv.app) as c:
        yield c


def test_ping(client):
    assert client.get("/ping").json() == {"status": "ok"}


def test_receivers_empty(client):
    assert client.get("/receivers").json() == []


def test_receiver_registers_and_appears_in_list(client):
    with client.websocket_connect("/ws/receiver/Kitchen"):
        listing = client.get("/receivers").json()
        assert len(listing) == 1
        assert listing[0]["name"] == "Kitchen"
        assert listing[0]["online"] is True
        assert "version" in listing[0]
    # After disconnect, marked offline but entry remains
    listing = client.get("/receivers").json()
    assert len(listing) == 1
    assert listing[0]["name"] == "Kitchen"
    assert listing[0]["online"] is False


def test_receivers_endpoint_includes_version_field(client):
    srv.receivers["TestVer"] = {"ws": None, "online": True, "version": "1.2.3"}
    try:
        resp = client.get("/receivers")
        assert resp.status_code == 200
        data = resp.json()
        entry = next(d for d in data if d["name"] == "TestVer")
        assert entry["version"] == "1.2.3"
    finally:
        del srv.receivers["TestVer"]


def test_admin_page_renders_and_shows_version(client):
    srv.receivers["AdminVer"] = {"ws": None, "online": True, "version": "1.0.0"}
    try:
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert "AdminVer" in resp.text
        assert "1.0.0" in resp.text
    finally:
        del srv.receivers["AdminVer"]


@pytest.mark.parametrize(
    "bad_name",
    [
        "a" * 65,          # too long
        "room.etc",        # dot
        "room!bang",       # punctuation
        "room@tag",        # at-sign
        "",                # empty (route wouldn't match, but covered for safety)
    ],
)
def test_invalid_receiver_names_rejected(client, bad_name):
    # Empty name routes to 404 (no match); other bad names should close 1008.
    if not bad_name:
        r = client.get(f"/ws/receiver/{bad_name}")
        assert r.status_code in (404, 405)
        return
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/receiver/{bad_name}"):
            pass


def test_start_to_online_receiver_claims_ownership(client):
    with client.websocket_connect("/ws/receiver/Kitchen") as rx:
        with client.websocket_connect("/ws/sender") as tx:
            tx.send_text(json.dumps({
                "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
            }))
            # Receiver should get a START message
            msg = rx.receive_text()
            assert json.loads(msg) == {"type": "START", "sampleRate": 16000}
            # And ownership is recorded
            assert "Kitchen" in srv.receiver_owners


def test_second_sender_gets_busy(client):
    with client.websocket_connect("/ws/receiver/Kitchen") as rx:
        with client.websocket_connect("/ws/sender") as tx1:
            tx1.receive_text()  # RECEIVERS_UPDATE on connect
            tx1.send_text(json.dumps({
                "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
            }))
            rx.receive_text()  # START

            with client.websocket_connect("/ws/sender") as tx2:
                tx2.receive_text()  # RECEIVERS_UPDATE on connect
                tx2.send_text(json.dumps({
                    "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
                }))
                busy = json.loads(tx2.receive_text())
                assert busy == {"type": "BUSY", "receiver": "Kitchen"}


def test_sender_drop_releases_ownership_and_sends_stop(client):
    with client.websocket_connect("/ws/receiver/Kitchen") as rx:
        with client.websocket_connect("/ws/sender") as tx:
            tx.send_text(json.dumps({
                "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
            }))
            rx.receive_text()  # START
            assert "Kitchen" in srv.receiver_owners
        # Sender context exits → disconnect → cleanup
        stop = json.loads(rx.receive_text())
        assert stop == {"type": "STOP"}
        assert "Kitchen" not in srv.receiver_owners


def test_binary_audio_is_forwarded(client):
    with client.websocket_connect("/ws/receiver/Kitchen") as rx:
        with client.websocket_connect("/ws/sender") as tx:
            tx.send_text(json.dumps({
                "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
            }))
            rx.receive_text()  # START
            payload = b"\x01\x02\x03\x04" * 512
            tx.send_bytes(payload)
            assert rx.receive_bytes() == payload


def test_invalid_sample_rate_zero_rejected(client):
    with client.websocket_connect("/ws/receiver/Kitchen"):
        with client.websocket_connect("/ws/sender") as tx:
            tx.receive_text()  # RECEIVERS_UPDATE on connect
            tx.send_text(json.dumps({"type": "START", "targets": ["Kitchen"], "sampleRate": 0}))
            msg = json.loads(tx.receive_text())
            assert msg["type"] == "ERROR"
            assert "sampleRate" in msg["reason"]


def test_invalid_sample_rate_negative_rejected(client):
    with client.websocket_connect("/ws/receiver/Kitchen"):
        with client.websocket_connect("/ws/sender") as tx:
            tx.receive_text()  # RECEIVERS_UPDATE on connect
            tx.send_text(json.dumps({"type": "START", "targets": ["Kitchen"], "sampleRate": -1}))
            msg = json.loads(tx.receive_text())
            assert msg["type"] == "ERROR"
            assert "sampleRate" in msg["reason"]


def test_too_many_targets_rejected(client):
    with client.websocket_connect("/ws/sender") as tx:
        tx.receive_text()  # RECEIVERS_UPDATE on connect
        tx.send_text(json.dumps({"type": "START", "targets": ["x"] * 51, "sampleRate": 16000}))
        msg = json.loads(tx.receive_text())
        assert msg["type"] == "ERROR"
        assert "targets" in msg["reason"]


def test_malformed_json_does_not_crash(client):
    with client.websocket_connect("/ws/sender") as tx:
        tx.send_text("not json {{{")
        # Server stays alive — a valid message after bad JSON is processed normally
        tx.send_text(json.dumps({"type": "STOP"}))
        # No exception = server survived the bad frame


def test_receiver_name_exactly_64_chars(client):
    name = "a" * 64
    with client.websocket_connect(f"/ws/receiver/{name}"):
        listing = client.get("/receivers").json()
        assert any(r["name"] == name for r in listing)


def test_receiver_name_65_chars_rejected(client):
    name = "a" * 65
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/receiver/{name}"):
            pass


def test_audio_forwarded_to_multiple_receivers(client):
    with client.websocket_connect("/ws/receiver/Room1") as rx1:
        with client.websocket_connect("/ws/receiver/Room2") as rx2:
            with client.websocket_connect("/ws/sender") as tx:
                tx.send_text(json.dumps({
                    "type": "START", "targets": ["Room1", "Room2"], "sampleRate": 16000,
                }))
                rx1.receive_text()  # START
                rx2.receive_text()  # START
                payload = b"\xAB\xCD" * 256
                tx.send_bytes(payload)
                assert rx1.receive_bytes() == payload
                assert rx2.receive_bytes() == payload


def test_root_serves_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_start_targets_offline_receiver_skipped(client):
    # Register Kitchen but don't connect it — it stays offline after disconnect
    with client.websocket_connect("/ws/receiver/Kitchen"):
        pass
    # Kitchen is now offline
    with client.websocket_connect("/ws/sender") as tx:
        tx.receive_text()  # RECEIVERS_UPDATE
        tx.send_text(json.dumps({
            "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
        }))
        # Sender should NOT be given ownership — Kitchen is offline, silently skipped
        assert "Kitchen" not in srv.receiver_owners


def test_start_targets_unknown_receiver_skipped(client):
    with client.websocket_connect("/ws/sender") as tx:
        tx.receive_text()  # RECEIVERS_UPDATE
        tx.send_text(json.dumps({
            "type": "START", "targets": ["DoesNotExist"], "sampleRate": 16000,
        }))
        assert "DoesNotExist" not in srv.receiver_owners


def test_invalid_targets_type_rejected(client):
    # targets must be a list of strings — sending a non-list should get ERROR
    with client.websocket_connect("/ws/sender") as tx:
        tx.receive_text()  # RECEIVERS_UPDATE
        tx.send_text(json.dumps({"type": "START", "targets": "Kitchen", "sampleRate": 16000}))
        msg = json.loads(tx.receive_text())
        assert msg["type"] == "ERROR"
        assert "targets" in msg["reason"]


def test_sender_explicit_stop_releases_ownership(client):
    with client.websocket_connect("/ws/receiver/Kitchen") as rx:
        with client.websocket_connect("/ws/sender") as tx:
            tx.receive_text()  # RECEIVERS_UPDATE
            tx.send_text(json.dumps({
                "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
            }))
            rx.receive_text()  # START
            assert "Kitchen" in srv.receiver_owners

            tx.send_text(json.dumps({"type": "STOP"}))
            stop = json.loads(rx.receive_text())
            assert stop == {"type": "STOP"}
            assert "Kitchen" not in srv.receiver_owners


def test_receiver_disconnect_releases_sender_ownership(client):
    # If a receiver drops while a sender owns it, ownership should be released
    with client.websocket_connect("/ws/sender") as tx:
        tx.receive_text()  # RECEIVERS_UPDATE
        with client.websocket_connect("/ws/receiver/Kitchen") as rx:
            tx.receive_text()  # RECEIVERS_UPDATE (Kitchen came online)
            tx.send_text(json.dumps({
                "type": "START", "targets": ["Kitchen"], "sampleRate": 16000,
            }))
            rx.receive_text()  # START
            assert "Kitchen" in srv.receiver_owners
        # rx context exits — receiver disconnects
        assert "Kitchen" not in srv.receiver_owners


def test_startup_banner_logs_port_scheme_mdns(caplog, client):
    """Startup banner must log Port:, TLS:, and mDNS: lines."""
    import logging
    with caplog.at_level(logging.INFO, logger="intercom"):
        with TestClient(srv.app):
            log_text = caplog.text
    assert "Port:" in log_text
    assert "TLS:" in log_text
    assert "mDNS:" in log_text


def test_uvicorn_kwargs_include_ws_ping_settings():
    """hub._build_uvicorn_kwargs must include ws_ping_interval and ws_ping_timeout."""
    import hub as hub_mod
    kwargs = hub_mod._build_uvicorn_kwargs(port=8000)
    assert kwargs.get("ws_ping_interval") == 20
    assert kwargs.get("ws_ping_timeout") == 10


def test_record_fwd_warn_evicts_oldest_at_capacity():
    srv._last_fwd_warn.clear()
    # Fill to capacity
    for i in range(srv._FWD_WARN_MAX):
        srv._record_fwd_warn(f"rx{i}", float(i))
    assert len(srv._last_fwd_warn) == srv._FWD_WARN_MAX
    # Adding one more should evict rx0 (oldest)
    srv._record_fwd_warn("new", float(srv._FWD_WARN_MAX))
    assert len(srv._last_fwd_warn) == srv._FWD_WARN_MAX
    assert "rx0" not in srv._last_fwd_warn
    assert "new" in srv._last_fwd_warn
    srv._last_fwd_warn.clear()


def test_admin_page_has_no_meta_refresh(client):
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert 'http-equiv="refresh"' not in resp.text
    assert "http-equiv='refresh'" not in resp.text


def test_admin_page_has_js_polling(client):
    resp = client.get("/admin")
    assert "setInterval" in resp.text
    assert "/receivers" in resp.text
