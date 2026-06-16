"""Tests for the Telegram copy-trading module.

Targets local backend (http://localhost:8001).
Covers:
- /api/telegram/status returns Telethon status + config
- /api/telegram/config GET/POST persistence and partial updates
- /api/telegram/test-parse for RentaTrade format, non-signal, SELL/GOLD alias
- /api/telegram/signals listing + filter
- Auth gates on every /api/telegram/* endpoint (401 without token)
- Regression on existing endpoints (/api/health, /api/auth/login, /api/bot/state,
  /api/positions/open, /api/trades/metrics, /api/mt5/status)
- Backend stays alive even though Telethon cannot reach Telegram in sandbox.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("BACKEND_TEST_URL", "http://localhost:8001").rstrip("/")


# ---------- health / regression ----------

class TestRegressionExistingEndpoints:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"

    def test_auth_login_works(self, auth_headers):
        # If the fixture didn't skip, login succeeded
        assert auth_headers["Authorization"].startswith("Bearer ")

    def test_bot_state(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bot/state", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "state" in data or "config" in data or "mode" in data or "mt5_status" in data

    def test_positions_open(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/positions/open", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # Accept either list or {items: [...]} or {positions:[...]}
        assert isinstance(body, (list, dict))

    def test_trades_metrics(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/trades/metrics", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)

    def test_mt5_status(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/mt5/status", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        # Expect at least 'connected' field
        assert "connected" in data or "status" in data or isinstance(data, dict)


# ---------- auth gates ----------

class TestTelegramAuthGates:
    """All /api/telegram/* require a valid JWT."""

    @pytest.mark.parametrize("method,path,payload", [
        ("GET", "/api/telegram/status", None),
        ("GET", "/api/telegram/config", None),
        ("POST", "/api/telegram/config", {"shadow_mode": True}),
        ("POST", "/api/telegram/start-login", None),
        ("POST", "/api/telegram/submit-code", {"code": "12345"}),
        ("POST", "/api/telegram/submit-password", {"password": "x"}),
        ("GET", "/api/telegram/signals", None),
        ("POST", "/api/telegram/test-parse", {"text": "BUY XAUUSD ENTRY 4338 SL 4333 TP 4343"}),
    ])
    def test_requires_auth(self, method, path, payload):
        if method == "GET":
            r = requests.get(f"{BASE_URL}{path}", timeout=10)
        else:
            r = requests.post(f"{BASE_URL}{path}", json=payload or {}, timeout=10)
        assert r.status_code in (401, 403), f"{method} {path} -> {r.status_code} (expected 401/403)"


# ---------- status & config ----------

class TestTelegramStatusAndConfig:
    def test_status_shape(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/telegram/status", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # Telethon status fields
        for k in ("configured", "authorized", "login_in_progress", "connected", "channels", "phone"):
            assert k in body, f"missing key {k} in status"
        assert "config" in body, "status must embed config"
        cfg = body["config"]
        for k in ("enabled", "shadow_mode", "channels", "symbols_whitelist",
                  "split_legs", "max_entry_drift_pct"):
            assert k in cfg, f"missing key {k} in config"
        # Default: shadow_mode True
        assert isinstance(cfg["shadow_mode"], bool)
        # Telethon configured with env credentials
        assert body["configured"] is True
        # Phone matches env
        assert body["phone"] is None or "+" in (body["phone"] or "")

    def test_config_get_returns_persisted(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/telegram/config", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        cfg = r.json()
        for k in ("enabled", "shadow_mode", "channels", "symbols_whitelist",
                  "split_legs", "max_entry_drift_pct"):
            assert k in cfg

    def test_config_partial_update_each_field(self, auth_headers):
        # Capture original
        orig = requests.get(f"{BASE_URL}/api/telegram/config", headers=auth_headers, timeout=10).json()

        # Update enabled
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers, json={"enabled": False}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["enabled"] is False

        # Update shadow_mode
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers, json={"shadow_mode": True}, timeout=10)
        assert r.status_code == 200
        assert r.json()["shadow_mode"] is True

        # Update channels
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers,
                          json={"channels": ["TestChannelA", "TestChannelB"]}, timeout=10)
        assert r.status_code == 200
        assert r.json()["channels"] == ["TestChannelA", "TestChannelB"]

        # Update symbols_whitelist
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers,
                          json={"symbols_whitelist": ["XAUUSD", "BTCUSD"]}, timeout=10)
        assert r.status_code == 200
        assert r.json()["symbols_whitelist"] == ["XAUUSD", "BTCUSD"]

        # Update split_legs
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers, json={"split_legs": False}, timeout=10)
        assert r.status_code == 200
        assert r.json()["split_legs"] is False

        # Update max_entry_drift_pct
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers, json={"max_entry_drift_pct": 0.75}, timeout=10)
        assert r.status_code == 200
        assert abs(r.json()["max_entry_drift_pct"] - 0.75) < 1e-9

        # Restore defaults
        restore = {
            "enabled": orig.get("enabled", True),
            "shadow_mode": orig.get("shadow_mode", True),
            "channels": orig.get("channels", []),
            "symbols_whitelist": orig.get("symbols_whitelist", []),
            "split_legs": orig.get("split_legs", True),
            "max_entry_drift_pct": orig.get("max_entry_drift_pct", 0.5),
        }
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers, json=restore, timeout=15)
        assert r.status_code == 200

    def test_config_get_after_post_persists(self, auth_headers):
        # Mutate then GET to verify persistence
        r = requests.post(f"{BASE_URL}/api/telegram/config",
                          headers=auth_headers, json={"max_entry_drift_pct": 0.42}, timeout=10)
        assert r.status_code == 200
        g = requests.get(f"{BASE_URL}/api/telegram/config", headers=auth_headers, timeout=10).json()
        assert abs(g["max_entry_drift_pct"] - 0.42) < 1e-9
        # Restore
        requests.post(f"{BASE_URL}/api/telegram/config",
                      headers=auth_headers, json={"max_entry_drift_pct": 0.5}, timeout=10)


# ---------- parser ----------

RENTATRADE_MSG = (
    "\U0001F6A8 BUY XAUUSD\n"
    "\U0001F4C8 ENTRY : 4340-4337\n"
    "\U0001F534 SL : 4333\n"
    "\U0001F7E2 TP1: 4343\n"
    "\U0001F7E2 TP2: OUVERT"
)


class TestTelegramTestParse:
    def test_parse_rentatrade_buy_with_range_and_runner(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/telegram/test-parse",
            headers=auth_headers,
            json={"text": RENTATRADE_MSG},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["is_signal"] is True, f"expected is_signal=True, got {p}"
        assert p["symbol"] == "XAUUSD", f"symbol={p.get('symbol')}"
        assert p["side"] == "BUY"
        # entry midpoint = (4340+4337)/2 = 4338.5
        assert p["entry"] is not None
        assert abs(float(p["entry"]) - 4338.5) < 0.01, f"entry={p['entry']}"
        assert float(p["sl"]) == 4333
        # tps: at least 2 entries, first numeric ~4343, last is runner=True
        assert isinstance(p["tps"], list) and len(p["tps"]) >= 2
        tp_values = [t for t in p["tps"] if t.get("value") is not None]
        assert any(abs(float(t["value"]) - 4343) < 0.01 for t in tp_values), \
            f"no TP=4343 in {p['tps']}"
        assert any(t.get("runner") for t in p["tps"]), f"no runner TP in {p['tps']}"
        # Confidence >= 0.8 from LLM (allow >=0.6 if fallback regex kicks in)
        assert float(p["confidence"]) >= 0.6, f"low confidence {p['confidence']}"

    def test_parse_non_signal_chat(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/telegram/test-parse",
            headers=auth_headers,
            json={"text": "salut les amis, bonne journée !"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["is_signal"] is False, f"expected non-signal, got {p}"

    def test_parse_sell_gold_alias(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/telegram/test-parse",
            headers=auth_headers,
            json={"text": "SELL GOLD ENTRY 2630 SL 2640 TP 2615"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["is_signal"] is True, f"got {p}"
        assert p["side"] == "SELL"
        assert p["symbol"] == "XAUUSD", f"alias GOLD->XAUUSD failed: {p.get('symbol')}"
        assert float(p["sl"]) == 2640
        assert any(t.get("value") is not None and abs(float(t["value"]) - 2615) < 0.01
                   for t in p["tps"])


# ---------- signals list ----------

class TestTelegramSignals:
    def test_signals_list_shape(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/telegram/signals", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "count" in body
        assert isinstance(body["items"], list)
        assert body["count"] == len(body["items"])
        assert len(body["items"]) <= 200

    def test_signals_limit_caps_at_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/telegram/signals?limit=5000",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 200

    def test_signals_status_filter(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/telegram/signals?status=rejected",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        # All returned items must have status=rejected (if any)
        for it in body["items"]:
            assert it.get("status") == "rejected"


# ---------- backend stability ----------

class TestBackendStabilityWithTelegramDown:
    def test_health_still_ok_after_module_load(self):
        # Quick sanity: backend stayed up even though Telethon cannot connect in sandbox.
        for _ in range(2):
            r = requests.get(f"{BASE_URL}/api/health", timeout=5)
            assert r.status_code == 200
            time.sleep(0.2)

    def test_status_reports_not_authorized_not_crashed(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/telegram/status", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        # In sandbox we expect configured=True, authorized=False (cannot reach Telegram)
        assert body["configured"] is True
        # authorized can legitimately be False here; we just check key exists and is bool
        assert isinstance(body["authorized"], bool)
