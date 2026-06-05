"""MT5 Broker Connector.

This module attempts to use the official MetaTrader5 Python library
(only available on Windows) to provide a live connection to MT5.

Architecture:
- On Windows: native MetaTrader5 lib is used directly.
- On Linux (most VPS): the lib cannot be installed. The user must run
  a small "MT5 bridge agent" on a Windows machine that exposes MT5
  data over HTTP. Configure MT5_BRIDGE_URL in .env to use it.
- Otherwise: connector is unavailable and the system falls back to the
  internal simulator.

The MT5Connector is read-only by default (sync of account/positions).
Order execution via MT5 is enabled when `enable_trading=True`.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

import httpx

logger = logging.getLogger("mt5_broker")

# Try native MT5 lib (Windows only) -----------------------------
try:
    import MetaTrader5 as mt5  # type: ignore
    HAS_MT5_NATIVE = True
except Exception:
    mt5 = None
    HAS_MT5_NATIVE = False


class MT5Connector:
    """Connector to MetaTrader 5 with auto-reconnection."""

    def __init__(self):
        self.connected = False
        self.last_error: Optional[str] = None
        self.last_heartbeat: Optional[datetime] = None
        self.account_login: Optional[str] = None
        self.server: Optional[str] = None
        self.broker: Optional[str] = None
        self.mode: str = "unavailable"  # "native" | "bridge" | "unavailable"
        self.bridge_url: Optional[str] = os.environ.get("MT5_BRIDGE_URL") or None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._password: Optional[str] = None
        self._client = httpx.AsyncClient(timeout=8.0)

    # ----- Connection lifecycle -----
    async def connect(self, login: str, password: str, server: str, broker: Optional[str] = None) -> Dict[str, Any]:
        """Attempt to connect to MT5. Returns status dict."""
        self.account_login = login
        self.server = server
        self.broker = broker
        self._password = password

        if HAS_MT5_NATIVE:
            return await self._connect_native(login, password, server)
        if self.bridge_url:
            return await self._connect_bridge(login, password, server)

        self.connected = False
        self.mode = "unavailable"
        self.last_error = (
            "MT5 indisponible : la librairie MetaTrader5 n'est pas installée (Windows requis) "
            "et aucun MT5_BRIDGE_URL n'est configuré. Le simulateur reste actif."
        )
        return self.status()

    async def _connect_native(self, login: str, password: str, server: str) -> Dict[str, Any]:
        try:
            ok = await asyncio.to_thread(mt5.initialize, login=int(login), password=password, server=server)
            if not ok:
                err = mt5.last_error()
                self.connected = False
                self.last_error = f"MT5 initialize failed: {err}"
                return self.status()
            self.connected = True
            self.mode = "native"
            self.last_error = None
            self.last_heartbeat = datetime.now(timezone.utc)
            self._ensure_reconnect_loop()
            return self.status()
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            return self.status()

    async def _connect_bridge(self, login: str, password: str, server: str) -> Dict[str, Any]:
        try:
            r = await self._client.post(
                f"{self.bridge_url}/connect",
                json={"login": login, "password": password, "server": server},
            )
            data = r.json()
            if r.status_code == 200 and data.get("connected"):
                self.connected = True
                self.mode = "bridge"
                self.last_error = None
                self.last_heartbeat = datetime.now(timezone.utc)
                self._ensure_reconnect_loop()
                return self.status()
            self.connected = False
            self.last_error = data.get("error", "Bridge refused connection")
            return self.status()
        except Exception as e:
            self.connected = False
            self.last_error = f"Bridge unreachable: {e}"
            return self.status()

    async def disconnect(self):
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self.mode == "native" and HAS_MT5_NATIVE:
            try:
                await asyncio.to_thread(mt5.shutdown)
            except Exception:
                pass
        self.connected = False

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "has_native_lib": HAS_MT5_NATIVE,
            "has_bridge_url": bool(self.bridge_url),
            "login": self.account_login,
            "server": self.server,
            "broker": self.broker,
            "last_error": self.last_error,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
        }

    # ----- Auto-reconnect loop -----
    def _ensure_reconnect_loop(self):
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                if self.mode == "native" and HAS_MT5_NATIVE:
                    info = await asyncio.to_thread(mt5.terminal_info)
                    if info is None:
                        logger.warning("MT5 terminal not responding, attempting reconnect...")
                        if self._password and self.account_login and self.server:
                            await self._connect_native(self.account_login, self._password, self.server)
                    else:
                        self.last_heartbeat = datetime.now(timezone.utc)
                elif self.mode == "bridge":
                    r = await self._client.get(f"{self.bridge_url}/health")
                    if r.status_code == 200 and r.json().get("connected"):
                        self.last_heartbeat = datetime.now(timezone.utc)
                    else:
                        logger.warning("MT5 bridge disconnected, attempting reconnect...")
                        if self._password and self.account_login and self.server:
                            await self._connect_bridge(self.account_login, self._password, self.server)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Reconnect loop error: %s", e)

    # ----- Data accessors -----
    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        if not self.connected:
            return None
        try:
            if self.mode == "native" and HAS_MT5_NATIVE:
                info = await asyncio.to_thread(mt5.account_info)
                if info is None:
                    return None
                return {
                    "balance": info.balance,
                    "equity": info.equity,
                    "margin": info.margin,
                    "free_margin": info.margin_free,
                    "profit": info.profit,
                    "currency": info.currency,
                    "leverage": info.leverage,
                    "name": info.name,
                    "server": info.server,
                    "login": info.login,
                }
            if self.mode == "bridge":
                r = await self._client.get(f"{self.bridge_url}/account")
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning("get_account_info error: %s", e)
        return None

    async def get_positions(self) -> List[Dict[str, Any]]:
        if not self.connected:
            return []
        try:
            if self.mode == "native" and HAS_MT5_NATIVE:
                positions = await asyncio.to_thread(mt5.positions_get)
                if not positions:
                    return []
                out = []
                for p in positions:
                    out.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "side": "BUY" if p.type == 0 else "SELL",
                        "volume": p.volume,
                        "entry_price": p.price_open,
                        "current_price": p.price_current,
                        "stop_loss": p.sl,
                        "take_profit": p.tp,
                        "pnl": p.profit,
                        "swap": p.swap,
                        "opened_at": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                        "comment": p.comment,
                    })
                return out
            if self.mode == "bridge":
                r = await self._client.get(f"{self.bridge_url}/positions")
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning("get_positions error: %s", e)
        return []

    async def get_price(self, symbol: str) -> Optional[Dict[str, float]]:
        if not self.connected:
            return None
        try:
            if self.mode == "native" and HAS_MT5_NATIVE:
                tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
                if tick is None:
                    return None
                return {"bid": tick.bid, "ask": tick.ask, "last": tick.last}
            if self.mode == "bridge":
                r = await self._client.get(f"{self.bridge_url}/price/{symbol}")
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning("get_price error: %s", e)
        return None

    async def get_history_deals(self, days: int = 30) -> List[Dict[str, Any]]:
        if not self.connected:
            return []
        try:
            if self.mode == "native" and HAS_MT5_NATIVE:
                from datetime import timedelta
                date_from = datetime.now() - timedelta(days=days)
                deals = await asyncio.to_thread(mt5.history_deals_get, date_from, datetime.now())
                if not deals:
                    return []
                return [{
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "type": d.type,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "commission": d.commission,
                    "swap": d.swap,
                    "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
                } for d in deals]
            if self.mode == "bridge":
                r = await self._client.get(f"{self.bridge_url}/history?days={days}")
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning("get_history_deals error: %s", e)
        return []


mt5_connector = MT5Connector()
