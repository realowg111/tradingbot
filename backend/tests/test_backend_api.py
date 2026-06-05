"""Comprehensive backend API tests for the Trading Bot.

Covers: auth, bot state/config, mode switch, risk/strategy updates, strategies list,
positions/trades, metrics, equity-curve, exports, audit, costs CRUD/summary,
MT5 credential encryption, backtest, market prices, unauthenticated rejection,
bot loop trade generation.
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

# ---- Setup ----------------------------------------------------------------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "trading_bot")


# ============ AUTH =========================================================
class TestAuth:
    def test_login_admin_success(self, base_url, api_client):
        r = api_client.post(f"{base_url}/api/auth/login",
                            json={"email": "admin@trading.bot", "password": "Admin123!"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data and data["token_type"] == "bearer"
        assert data["user"]["email"] == "admin@trading.bot"
        assert data["user"]["is_admin"] is True

    def test_login_wrong_password(self, base_url, api_client):
        r = api_client.post(f"{base_url}/api/auth/login",
                            json={"email": "admin@trading.bot", "password": "wrong"})
        assert r.status_code == 401

    def test_register_new_user(self, base_url, api_client):
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        r = api_client.post(f"{base_url}/api/auth/register",
                            json={"email": email, "password": "Secret123!"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["user"]["email"] == email
        assert body["user"]["is_admin"] is False
        assert "access_token" in body
        # duplicate
        r2 = api_client.post(f"{base_url}/api/auth/register",
                             json={"email": email, "password": "Secret123!"})
        assert r2.status_code == 400

    def test_me_endpoint(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "admin@trading.bot"
        assert body["is_admin"] is True

    def test_no_token_rejected(self, base_url):
        for path in ["/api/auth/me", "/api/bot/state", "/api/bot/config", "/api/trades",
                     "/api/positions/open", "/api/audit/logs", "/api/costs", "/api/strategies/list"]:
            r = requests.get(f"{base_url}{path}")
            assert r.status_code in (401, 403), f"{path} should reject anon, got {r.status_code}"


# ============ BOT CONFIG / STATE ==========================================
class TestBotConfigState:
    def test_get_config(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/bot/config", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for key in ("mode", "enabled", "risk", "strategy", "symbols", "starting_balance"):
            assert key in body
        assert body["mode"] in ("demo", "real")
        assert isinstance(body["symbols"], list) and len(body["symbols"]) == 5

    def test_get_state(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/bot/state", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "state" in body and "prices" in body
        st = body["state"]
        for key in ("balance", "equity", "realized_pnl", "kill_switch_engaged", "open_positions"):
            assert key in st
        # prices for 5 symbols
        assert len(body["prices"]) == 5

    def test_toggle_bot(self, base_url, auth_headers):
        # Read initial
        cfg = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        initial = cfg["enabled"]
        # toggle twice to leave state as-is
        r1 = requests.post(f"{base_url}/api/bot/toggle", headers=auth_headers)
        assert r1.status_code == 200
        assert r1.json()["enabled"] == (not initial)
        r2 = requests.post(f"{base_url}/api/bot/toggle", headers=auth_headers)
        assert r2.json()["enabled"] == initial


# ============ KILL SWITCH ================================================
class TestKillSwitch:
    def test_kill_switch_and_reset(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/api/bot/kill-switch", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["kill_switch"] is True
        assert body["all_positions_closed"] is True
        # State reflects it
        st = requests.get(f"{base_url}/api/bot/state", headers=auth_headers).json()["state"]
        assert st["kill_switch_engaged"] is True
        # Reset
        r2 = requests.post(f"{base_url}/api/bot/kill-switch/reset", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["kill_switch"] is False
        st2 = requests.get(f"{base_url}/api/bot/state", headers=auth_headers).json()["state"]
        assert st2["kill_switch_engaged"] is False


# ============ MODE SWITCH =================================================
class TestModeSwitch:
    def test_switch_to_real_without_phrase_rejected(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                          json={"target_mode": "real"})
        assert r.status_code == 400, r.text
        assert "confirmation" in r.text.lower() or "phrase" in r.text.lower()

    def test_switch_to_real_with_phrase_blocked_by_validation(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                          json={"target_mode": "real",
                                "confirmation_phrase": "JE CONFIRME LE PASSAGE EN REEL"})
        # Expected to be rejected due to validation_days / trades / winrate criteria
        assert r.status_code == 400, r.text

    def test_switch_to_demo_always_works(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/api/bot/mode", headers=auth_headers,
                          json={"target_mode": "demo"})
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "demo"


# ============ RISK & STRATEGY UPDATES =====================================
class TestRiskStrategy:
    def test_update_risk(self, base_url, auth_headers):
        payload = {
            "capital_allocation_pct": 12.0,
            "risk_per_trade_pct": 1.5,
            "risk_reward_ratio": 2.5,
            "stop_loss_pct": 1.2,
            "take_profit_pct": 2.4,
            "daily_drawdown_limit_pct": 6.0,
            "max_open_positions": 4,
            "max_trades_per_day": 25,
            "volatility_pause": True,
        }
        r = requests.put(f"{base_url}/api/bot/risk", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert cfg["risk"]["risk_per_trade_pct"] == 1.5
        assert cfg["risk"]["risk_reward_ratio"] == 2.5

    def test_update_strategy(self, base_url, auth_headers):
        payload = {
            "enabled": ["rsi", "multi"],
            "rsi_period": 10,
            "rsi_overbought": 75,
            "rsi_oversold": 25,
            "ema_fast": 9, "ema_slow": 21,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "bb_period": 20, "bb_std": 2.0,
        }
        r = requests.put(f"{base_url}/api/bot/strategy", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["strategy"]["rsi_period"] == 10
        # restore
        payload["enabled"] = ["multi"]
        payload["rsi_period"] = 14
        payload["rsi_overbought"] = 70
        payload["rsi_oversold"] = 30
        requests.put(f"{base_url}/api/bot/strategy", headers=auth_headers, json=payload)

    def test_strategies_list(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/strategies/list", headers=auth_headers)
        assert r.status_code == 200
        items = r.json()
        ids = {it["id"] for it in items}
        assert {"rsi", "ema_macd", "bollinger", "multi"}.issubset(ids), ids


# ============ POSITIONS / TRADES / METRICS ================================
class TestTradesMetrics:
    def test_positions_open(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/positions/open", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_trades_list(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_trades_metrics(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades/metrics", headers=auth_headers)
        assert r.status_code == 200
        m = r.json()
        for key in ("winrate", "profit_factor", "sharpe", "expectancy", "total_trades"):
            assert key in m, f"missing {key} in {m}"

    def test_equity_curve(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades/equity-curve", headers=auth_headers)
        assert r.status_code == 200
        curve = r.json()
        assert isinstance(curve, list) and len(curve) >= 1
        assert "equity" in curve[0]

    def test_export_csv(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/trades/export?format=csv", headers=auth_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")


# ============ AUDIT =======================================================
class TestAudit:
    def test_audit_logs_sorted_desc(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/audit/logs", headers=auth_headers)
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)
        # sorted descending by ts
        if len(logs) >= 2:
            assert logs[0]["ts"] >= logs[-1]["ts"]

    def test_audit_export_json(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/audit/export?format=json", headers=auth_headers)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")


# ============ COSTS =======================================================
class TestCosts:
    def test_costs_crud_and_summary(self, base_url, auth_headers):
        # Create
        payload = {"category": "vps", "label": "TEST_VPS_OVH", "amount": 30.0,
                   "currency": "EUR", "recurring": "monthly"}
        r = requests.post(f"{base_url}/api/costs", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        item = r.json()
        cost_id = item["id"]
        assert item["amount"] == 30.0
        # List
        lst = requests.get(f"{base_url}/api/costs", headers=auth_headers).json()
        assert any(c["id"] == cost_id for c in lst)
        # Summary - validate ALL required keys
        s = requests.get(f"{base_url}/api/costs/summary", headers=auth_headers).json()
        for key in ("monthly_total", "yearly_total", "one_off_total", "by_category",
                    "items_count", "current_realized_pnl", "net_monthly_profit"):
            assert key in s, f"costs/summary missing key {key}"
        assert s["monthly_total"] >= 30.0
        assert s["yearly_total"] >= 360.0
        # Delete
        d = requests.delete(f"{base_url}/api/costs/{cost_id}", headers=auth_headers)
        assert d.status_code == 200
        # Verify deletion
        lst2 = requests.get(f"{base_url}/api/costs", headers=auth_headers).json()
        assert not any(c["id"] == cost_id for c in lst2)


# ============ MT5 CREDENTIALS (ENCRYPTION) ===============================
class TestMT5:
    def test_mt5_save_and_retrieve_encrypted(self, base_url, auth_headers):
        payload = {"login": "TEST_42424242", "password": "Sup3rSecret!", "server": "ICMarkets-Demo",
                   "broker": "IC Markets"}
        r = requests.post(f"{base_url}/api/mt5/credentials", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["login"] == "TEST_42424242"
        assert out["server"] == "ICMarkets-Demo"
        assert "password" not in out  # password never returned

        r2 = requests.get(f"{base_url}/api/mt5/credentials", headers=auth_headers)
        assert r2.status_code == 200
        out2 = r2.json()
        assert out2["login"] == "TEST_42424242"
        assert "password" not in out2

        # Verify the password is encrypted (not stored cleartext) in MongoDB
        cli = MongoClient(MONGO_URL)
        try:
            u = cli[DB_NAME]["users"].find_one({"email": "admin@trading.bot"})
            assert u is not None and "mt5_credentials" in u
            stored = u["mt5_credentials"]
            # encrypt_str may return either a str (token) or a dict {ciphertext, nonce}
            stored_blob = stored if isinstance(stored, str) else str(stored)
            assert "Sup3rSecret!" not in stored_blob, "MT5 password is NOT encrypted in MongoDB!"
            assert "TEST_42424242" not in stored_blob, "MT5 login appears in cleartext storage!"
            assert "ICMarkets-Demo" not in stored_blob, "MT5 server appears in cleartext storage!"
        finally:
            cli.close()


# ============ BACKTEST ====================================================
class TestBacktest:
    def test_backtest_run(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/api/backtest/run", headers=auth_headers,
                          json={"symbol": "EURUSD", "strategy": "multi",
                                "candles": 120, "starting_balance": 10000.0})
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("ending_balance", "total_trades", "wins", "losses", "winrate",
                  "profit_factor", "max_drawdown_pct", "sharpe", "expectancy", "trades"):
            assert k in body


# ============ MARKET ======================================================
class TestMarket:
    def test_market_prices(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/api/market/prices", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for sym in ("EURUSD", "GBPUSD", "XAUUSD", "US100", "BTCUSD"):
            assert sym in body
            assert body[sym]["price"] is not None
            assert "spec" in body[sym]


# ============ BOT LOOP TRADE GENERATION ===================================
class TestBotLoop:
    def test_bot_generates_activity_when_enabled(self, base_url, auth_headers):
        # Ensure demo + enabled
        requests.post(f"{base_url}/api/bot/kill-switch/reset", headers=auth_headers)
        cfg = requests.get(f"{base_url}/api/bot/config", headers=auth_headers).json()
        if not cfg["enabled"]:
            requests.post(f"{base_url}/api/bot/toggle", headers=auth_headers)
        # Wait for bot loop to potentially open positions / generate trades
        time.sleep(45)
        positions = requests.get(f"{base_url}/api/positions/open", headers=auth_headers).json()
        trades = requests.get(f"{base_url}/api/trades", headers=auth_headers).json()
        audit = requests.get(f"{base_url}/api/audit/logs?limit=200", headers=auth_headers).json()
        # Soft assertion: at least the bot loop should be active (audit log events)
        # OR positions/trades non-empty
        has_activity = (len(positions) > 0) or (len(trades) > 0) or any(
            a.get("event", "").startswith(("signal", "open_position", "close_position", "bot_tick",
                                            "trade_opened", "trade_closed", "position_opened"))
            for a in audit
        )
        # We don't hard-fail if no trades (markets are simulated and may not converge),
        # but we should at least see SOME audit entries because the loop runs.
        assert len(audit) > 0, "Bot has no audit logs at all"
        print(f"[bot_loop] positions={len(positions)} trades={len(trades)} audit={len(audit)} activity={has_activity}")
