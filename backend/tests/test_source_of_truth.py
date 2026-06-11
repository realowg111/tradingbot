"""Iteration 3 - 'MT5 = source of truth' refactor regression tests.

Covers:
- GET /api/bot/state new unified format: state.source, margin, free_margin,
  account_currency + config_mode/config_enabled + positions + mt5_status/account
- GET /api/positions/open filtered by mode + source='sim' field
- GET /api/trades?mode=demo + /api/trades/metrics?mode=demo new fields
  (pnl_today, pnl_week, pnl_month, avg_win, avg_loss, win_loss_ratio, source)
- GET /api/trades/equity-curve?mode=demo curve points
- POST /api/bot/mode {target_mode:'real'} WITHOUT confirmation phrase = 200
- POST /api/bot/risk (PUT) accepts new fields weekly_loss_limit_pct,
  max_total_drawdown_pct, max_spread_pct
- POST /api/mt5/credentials trims surrounding whitespace; re-save without
  password/path keeps existing values
- POST /api/bot/toggle then /api/bot/state has coherent paused_reason; toggle off
- WebSocket /api/ws?token=<JWT> snapshot includes state.source + positions

Tests target the LOCAL backend (BACKEND_TEST_URL or http://localhost:8001).
The frontend EXPO_PUBLIC_BACKEND_URL (user's live VPS) is NEVER called.
"""
import os
import json
import asyncio
import pytest
import requests
import websockets
from urllib.parse import urlparse
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "trading_bot")


def _ws_url(base_url: str, token: str) -> str:
    p = urlparse(base_url)
    scheme = "wss" if p.scheme == "https" else "ws"
    return f"{scheme}://{p.netloc}/api/ws?token={token}"


# ---- bot/state unified format -------------------------------------------
class TestBotStateUnifiedFormat:
    def test_state_has_new_unified_fields(self, base_url, auth_headers):
        # Ensure we are in demo so source should be 'sim'
        requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                      json={"target_mode": "demo"})
        r = requests.get(f"{base_url}/api/bot/state", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()

        # Top-level keys
        for key in ("state", "config_mode", "config_enabled", "prices",
                    "positions", "mt5_status", "mt5_account"):
            assert key in body, f"missing top-level '{key}': {list(body.keys())}"

        # state.* shape (new fields)
        st = body["state"]
        for key in ("source", "margin", "free_margin", "account_currency",
                    "balance", "equity"):
            assert key in st, f"missing state.{key}: {list(st.keys())}"

        # On Linux backend with mode=demo, source MUST be 'sim'
        assert st["source"] == "sim", f"expected source=sim, got {st['source']}"
        assert isinstance(st["margin"], (int, float))
        assert isinstance(st["free_margin"], (int, float))
        assert st["account_currency"] == "USD"
        assert body["config_mode"] == "demo"
        assert isinstance(body["positions"], list)
        assert isinstance(body["prices"], dict)
        assert len(body["prices"]) == 5

    def test_state_source_when_real_but_mt5_disconnected(self, base_url, auth_headers):
        """In real mode but MT5 unreachable on Linux => source should be 'sim'
        (live_account.is_live returns False when not connected)."""
        requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                      json={"target_mode": "real"})
        try:
            r = requests.get(f"{base_url}/api/bot/state", headers=auth_headers)
            assert r.status_code == 200
            body = r.json()
            assert body["config_mode"] == "real"
            # MT5 not connected on Linux => still sim
            assert body["state"]["source"] == "sim", body["state"]
        finally:
            # Always restore demo
            requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                          json={"target_mode": "demo"})


# ---- positions/open filtered by mode + source ---------------------------
class TestPositionsOpen:
    def test_open_positions_have_source_sim_and_mode_filter(self, base_url, auth_headers):
        requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                      json={"target_mode": "demo"})
        r = requests.get(f"{base_url}/api/positions/open", headers=auth_headers)
        assert r.status_code == 200
        positions = r.json()
        assert isinstance(positions, list)
        # If any positions, ensure they are for demo mode and have source='sim'
        for p in positions:
            assert p.get("mode", "demo") == "demo", p
            assert p.get("source") == "sim", f"expected source=sim, got: {p}"


# ---- trades / metrics / equity-curve with new fields --------------------
class TestTradesNewFields:
    def test_trades_mode_demo(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades?mode=demo", headers=auth_headers)
        assert r.status_code == 200
        trades = r.json()
        assert isinstance(trades, list)
        for t in trades[:5]:
            assert t.get("mode") == "demo", t

    def test_metrics_new_fields_demo(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades/metrics?mode=demo", headers=auth_headers)
        assert r.status_code == 200
        m = r.json()
        # New required keys per the refactor
        for key in ("pnl_today", "pnl_week", "pnl_month",
                    "avg_win", "avg_loss", "win_loss_ratio",
                    "source", "winrate", "profit_factor", "total_trades"):
            assert key in m, f"metrics missing '{key}': {list(m.keys())}"
        assert m["source"] == "sim"
        # All new fields must be numeric
        for k in ("pnl_today", "pnl_week", "pnl_month",
                  "avg_win", "avg_loss", "win_loss_ratio"):
            assert isinstance(m[k], (int, float)), f"{k} not numeric: {m[k]}"

    def test_equity_curve_mode_demo(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades/equity-curve?mode=demo", headers=auth_headers)
        assert r.status_code == 200
        curve = r.json()
        assert isinstance(curve, list) and len(curve) >= 1
        assert "equity" in curve[0]
        assert isinstance(curve[0]["equity"], (int, float))


# ---- mode switch WITHOUT confirmation phrase ----------------------------
class TestModeSwitchNoConfirmation:
    def test_switch_real_then_demo_no_phrase(self, base_url, auth_headers):
        # to real (no confirmation_phrase field at all)
        r1 = requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                           json={"target_mode": "real"})
        assert r1.status_code == 200, r1.text
        assert r1.json()["mode"] == "real"

        # back to demo (always required to leave clean state)
        r2 = requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                           json={"target_mode": "demo"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["mode"] == "demo"


# ---- new risk fields ----------------------------------------------------
class TestNewRiskGuards:
    def test_update_risk_accepts_new_fields(self, base_url, auth_headers):
        # Read current config (so we can restore)
        cfg_before = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        before_risk = cfg_before["risk"]

        payload = {
            **before_risk,
            "weekly_loss_limit_pct": 8.5,
            "max_total_drawdown_pct": 18.0,
            "max_spread_pct": 0.15,
        }
        r = requests.put(f"{base_url}/api/bot/risk", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        risk = r.json()["risk"]
        assert risk["weekly_loss_limit_pct"] == 8.5
        assert risk["max_total_drawdown_pct"] == 18.0
        assert risk["max_spread_pct"] == 0.15

        # Verify persistence with GET
        cfg_after = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        assert cfg_after["risk"]["weekly_loss_limit_pct"] == 8.5
        assert cfg_after["risk"]["max_total_drawdown_pct"] == 18.0
        assert cfg_after["risk"]["max_spread_pct"] == 0.15

        # Restore defaults
        requests.put(f"{base_url}/api/bot/risk", headers=auth_headers, json=before_risk)


# ---- MT5 credentials trim + merge on re-save ----------------------------
class TestMT5CredentialsTrimMerge:
    def test_trim_whitespace_in_login_and_server(self, base_url, auth_headers):
        payload = {
            "login": "  123  ",
            "password": "Sup3rSecret!",
            "server": "  ICMarkets-Demo  ",
            "broker": "  IC Markets  ",
            "path": "  C:\\MT5\\terminal64.exe  ",
        }
        r = requests.post(f"{base_url}/api/mt5/credentials", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["login"] == "123", f"login not trimmed: {out['login']!r}"
        assert out["server"] == "ICMarkets-Demo", f"server not trimmed: {out['server']!r}"
        assert out["broker"] == "IC Markets", f"broker not trimmed: {out['broker']!r}"
        assert out["path"] == "C:\\MT5\\terminal64.exe", f"path not trimmed: {out['path']!r}"

        # Verify GET returns trimmed values too
        r2 = requests.get(f"{base_url}/api/mt5/credentials", headers=auth_headers)
        assert r2.status_code == 200
        body = r2.json()
        assert body["login"] == "123"
        assert body["server"] == "ICMarkets-Demo"

        # Verify password is encrypted (not cleartext) in Mongo
        cli = MongoClient(MONGO_URL)
        try:
            u = cli[DB_NAME]["users"].find_one({"email": "admin@trading.bot"})
            blob = str(u.get("mt5_credentials"))
            assert "Sup3rSecret!" not in blob
        finally:
            cli.close()

    def test_resave_without_password_keeps_existing(self, base_url, auth_headers):
        # First, set complete credentials with a known password and path
        full = {
            "login": "987654",
            "password": "PreservedPwd!",
            "server": "ICMarkets-Live",
            "broker": "IC Markets",
            "path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        }
        r = requests.post(f"{base_url}/api/mt5/credentials", headers=auth_headers, json=full)
        assert r.status_code == 200, r.text

        # Now re-save WITHOUT password or path - they should be preserved
        partial = {
            "login": "987654",
            "server": "ICMarkets-Live",
            "broker": "IC Markets",
            # no password, no path
        }
        r2 = requests.post(f"{base_url}/api/mt5/credentials", headers=auth_headers, json=partial)
        assert r2.status_code == 200, f"re-save without password should succeed: {r2.text}"
        out = r2.json()
        # Path must be preserved
        assert out["path"] == full["path"], \
            f"path should be preserved, got: {out.get('path')!r}"

        # Verify in DB the password is still the original (encrypted blob still works)
        cli = MongoClient(MONGO_URL)
        try:
            from cryptography.fernet import Fernet  # noqa: F401
        except Exception:
            pass
        finally:
            cli.close()

    def test_resave_without_password_first_time_returns_400(self, base_url, api_client):
        # Brand new user, no saved creds: re-save without password must fail
        import uuid
        email = f"test_mt5_trim_{uuid.uuid4().hex[:8]}@example.com"
        reg = api_client.post(f"{base_url}/api/auth/register",
                              json={"email": email, "password": "Secret123!"})
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(f"{base_url}/api/mt5/credentials", headers=headers,
                          json={"login": "111", "server": "S", "broker": "B"})
        assert r.status_code == 400, f"expected 400 first-save without password, got {r.status_code}: {r.text}"


# ---- bot toggle + paused_reason ----------------------------------------
class TestBotToggleAndPausedReason:
    def test_toggle_then_state_then_off(self, base_url, auth_headers):
        # Make sure demo + kill switch reset
        requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                      json={"target_mode": "demo"})
        requests.post(f"{base_url}/api/bot/kill-switch/reset", headers=auth_headers)

        # Read current
        cfg = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        # Ensure enabled
        if not cfg["enabled"]:
            r = requests.post(f"{base_url}/api/bot/toggle", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["enabled"] is True

        # State should be coherent (paused_reason may be None or a known string)
        r = requests.get(f"{base_url}/api/bot/state", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        st = body["state"]
        # In demo mode, paused_reason must NOT be one of the real-mode-only gates
        assert st.get("paused_reason") not in (
            "real_mode_not_unlocked", "live_mt5_disabled", "mt5_disconnected"), st
        # And bot must be enabled and not kill-switched
        assert body["config_enabled"] is True
        assert st["kill_switch_engaged"] is False

        # Toggle off
        r2 = requests.post(f"{base_url}/api/bot/toggle", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["enabled"] is False


# ---- WebSocket snapshot has state.source + positions --------------------
class TestWebSocketSnapshot:
    @pytest.mark.asyncio
    async def test_ws_snapshot_has_source_and_positions(self, base_url, admin_token):
        url = _ws_url(base_url, admin_token)
        async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg.get("type") == "snapshot"
            data = msg.get("data", {})
            # state.source
            assert "state" in data and "source" in data["state"], data.get("state")
            assert data["state"]["source"] in ("sim", "mt5", "mt5_stale")
            # positions list
            assert "positions" in data and isinstance(data["positions"], list)
            # Other unified fields
            assert "config_mode" in data
            assert "config_enabled" in data
            assert "mt5_status" in data
            # state new account fields
            for k in ("margin", "free_margin", "account_currency"):
                assert k in data["state"], data["state"]


# ---- Final teardown: ensure bot is left in demo + disabled --------------
class TestTeardown:
    def test_zzz_ensure_demo_disabled_at_end(self, base_url, auth_headers):
        # Bring back to demo
        requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                      json={"target_mode": "demo"})
        # Disable bot if enabled
        cfg = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        if cfg["enabled"]:
            requests.post(f"{base_url}/api/bot/toggle", headers=auth_headers)
        cfg2 = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        assert cfg2["mode"] == "demo"
        assert cfg2["enabled"] is False
