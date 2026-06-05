"""Tests for new MT5 connector endpoints and WebSocket live stream.

Covers:
- GET /api/mt5/status (shape + has_native_lib/has_bridge_url + account null)
- POST /api/mt5/connect (without creds -> 400, with creds -> connected=false gracefully)
- POST /api/mt5/disconnect (always 200)
- GET /api/mt5/live (disconnected shape)
- WebSocket /api/ws?token=<JWT> (accept + snapshot, reject invalid token)
"""
import os
import json
import asyncio
import pytest
import requests
import websockets
from urllib.parse import urlparse


def _ws_url(base_url: str, token: str) -> str:
    p = urlparse(base_url)
    scheme = "wss" if p.scheme == "https" else "ws"
    return f"{scheme}://{p.netloc}/api/ws?token={token}"


# ============ MT5 status / connect / disconnect / live =====================
class TestMT5Connector:
    def test_status_shape_when_disconnected(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/mt5/status", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "status" in body and "account" in body
        st = body["status"]
        for key in ("connected", "mode", "has_native_lib", "has_bridge_url"):
            assert key in st, f"missing '{key}' in status: {st}"
        # On Linux backend, native lib should not be available
        assert st["has_native_lib"] is False
        # account is null when not connected
        if st["connected"] is False:
            assert body["account"] is None

    def test_connect_without_credentials_returns_400(self, base_url, api_client):
        # Use a fresh user that has no saved MT5 credentials
        import uuid
        email = f"test_mt5_{uuid.uuid4().hex[:8]}@example.com"
        reg = api_client.post(f"{base_url}/api/auth/register",
                              json={"email": email, "password": "Secret123!"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{base_url}/api/mt5/connect", headers=headers)
        assert r.status_code == 400, f"expected 400 without creds, got {r.status_code}: {r.text}"

    def test_connect_with_saved_credentials_fails_gracefully(self, base_url, auth_headers):
        # Ensure admin has saved credentials (TestMT5 in test_backend_api.py saves them, but be safe)
        save = requests.post(f"{base_url}/api/mt5/credentials", headers=auth_headers,
                             json={"login": "TEST_99999999", "password": "Pwd123!",
                                   "server": "ICMarkets-Demo", "broker": "IC Markets"})
        assert save.status_code == 200, save.text
        r = requests.post(f"{base_url}/api/mt5/connect", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # Linux backend: neither native nor bridge -> connected must be False with last_error
        assert body["connected"] is False, body
        assert body.get("last_error"), "Expected a last_error message when MT5 unavailable"
        assert body["mode"] in ("unavailable", "native", "bridge")
        assert body["has_native_lib"] is False

    def test_disconnect_always_ok(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/api/mt5/disconnect", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # Returns status dict
        assert "connected" in body
        assert body["connected"] is False

    def test_live_disconnected_shape(self, base_url, auth_headers):
        # Ensure disconnected
        requests.post(f"{base_url}/api/mt5/disconnect", headers=auth_headers)
        r = requests.get(f"{base_url}/api/mt5/live", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["connected"] is False
        assert body["positions"] == []
        assert "status" in body


# ============ WebSocket live stream =========================================
class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_rejects_invalid_token(self, base_url):
        url = _ws_url(base_url, "not-a-real-jwt")
        # The server should close with code 4401 (custom auth-fail code)
        try:
            async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
                # If accept happened we should still receive close shortly
                try:
                    await asyncio.wait_for(ws.recv(), timeout=3)
                except Exception:
                    pass
                # Connection closed -> check code
            # If we exit context cleanly, we missed the close frame; check code
            assert False, "Expected WebSocket to be closed by server with 4401"
        except websockets.exceptions.InvalidStatus as e:
            # Server rejected during handshake (HTTP 401/403) - acceptable
            assert e.response.status_code in (401, 403, 4401), str(e)
        except websockets.exceptions.ConnectionClosed as e:
            # Server accepted then closed
            assert e.code == 4401, f"expected 4401, got {e.code}"
        except websockets.exceptions.InvalidStatusCode as e:  # websockets <12 fallback
            assert e.status_code in (401, 403, 4401), str(e)

    @pytest.mark.asyncio
    async def test_ws_accepts_valid_token_and_sends_snapshot(self, base_url, admin_token):
        url = _ws_url(base_url, admin_token)
        async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg.get("type") == "snapshot", f"first msg type unexpected: {msg}"
            data = msg.get("data", {})
            # Required fields
            for key in ("state", "prices", "positions", "mt5_status"):
                assert key in data, f"snapshot missing key '{key}': {list(data.keys())}"
            # 5 prices
            assert len(data["prices"]) == 5, data["prices"]
            # mt5_status shape
            for k in ("connected", "mode", "has_native_lib", "has_bridge_url"):
                assert k in data["mt5_status"], data["mt5_status"]
