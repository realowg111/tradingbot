"""MT5 Broker Connector.

This module attempts to use the official MetaTrader5 Python library
(only available on Windows) to provide a live connection to MT5.

IMPORTANT:
- The MT5 desktop terminal MUST be running BEFORE the Python lib can attach to it.
- On a Windows VPS with the backend running as a Windows Service (SYSTEM account),
  the service CANNOT see an MT5 terminal launched in an interactive user session.
  Either: (a) configure the service to run as the same Windows user that runs MT5,
  or (b) pass the explicit `path` to terminal64.exe so the lib auto-launches MT5.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
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


# Common install paths to probe when no explicit path is given.
COMMON_MT5_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe",
    r"C:\Program Files\MetaTrader 5 RoboForex\terminal64.exe",
    r"C:\Program Files\RoboForex MT5 Terminal\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
]


def _autodetect_mt5_path() -> Optional[str]:
    """Look for an installed MT5 terminal64.exe in common locations."""
    # 1) explicit env var wins
    env_path = os.environ.get("MT5_TERMINAL_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    # 2) probe known paths
    for p in COMMON_MT5_PATHS:
        if Path(p).exists():
            return p
    # 3) scan Program Files for any "terminal64.exe" under a folder matching MetaTrader
    program_dirs = [r"C:\Program Files", r"C:\Program Files (x86)"]
    for pd in program_dirs:
        try:
            base = Path(pd)
            if not base.exists():
                continue
            for sub in base.iterdir():
                name = sub.name.lower()
                if "metatrader" in name or "roboforex" in name or "mt5" in name:
                    candidate = sub / "terminal64.exe"
                    if candidate.exists():
                        return str(candidate)
        except Exception:
            continue
    return None


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
        self.terminal_path: Optional[str] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._password: Optional[str] = None
        self._client = httpx.AsyncClient(timeout=8.0)

    # ----- Connection lifecycle -----
    async def connect(self, login: str, password: str, server: str, broker: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
        """Attempt to connect to MT5. Returns status dict.

        ``path`` is the optional path to terminal64.exe. If provided (or
        auto-detected), the lib will auto-launch MT5 if it's not already running.
        """
        self.account_login = login
        self.server = server
        self.broker = broker
        self._password = password

        if HAS_MT5_NATIVE:
            # Resolve terminal path: explicit > env > autodetect
            resolved_path = path or _autodetect_mt5_path()
            if resolved_path:
                self.terminal_path = resolved_path
            return await self._connect_native(login, password, server, resolved_path)
        if self.bridge_url:
            return await self._connect_bridge(login, password, server)

        self.connected = False
        self.mode = "unavailable"
        self.last_error = (
            "MT5 indisponible : la librairie MetaTrader5 n'est pas installée (Windows requis) "
            "et aucun MT5_BRIDGE_URL n'est configuré. Le simulateur reste actif."
        )
        return self.status()

    async def _connect_native(self, login: str, password: str, server: str, path: Optional[str] = None) -> Dict[str, Any]:
        try:
            # Build kwargs: include path only if available
            init_kwargs: Dict[str, Any] = {
                "login": int(login),
                "password": password,
                "server": server,
            }
            if path:
                init_kwargs["path"] = path

            ok = await asyncio.to_thread(lambda: mt5.initialize(**init_kwargs))
            if not ok:
                err = mt5.last_error()
                self.connected = False
                self.last_error = self._humanize_init_error(err, path)
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

    @staticmethod
    def _humanize_init_error(err: tuple, path: Optional[str]) -> str:
        code, msg = err if isinstance(err, tuple) and len(err) == 2 else (None, str(err))
        # Map common cryptic MT5 errors into actionable messages (FR)
        if code == -10003 or "terminal" in str(msg).lower() and "not found" in str(msg).lower():
            base = (
                "Le terminal MetaTrader 5 est introuvable ou n'est pas démarré. "
            )
            if not path:
                base += (
                    "Astuce : ouvre MT5 manuellement sur le VPS (double-clic sur l'icône) "
                    "et relance la connexion. Ou indique le chemin complet vers terminal64.exe "
                    "dans le champ 'Chemin terminal' ci-dessous."
                )
            else:
                base += (
                    f"Le chemin testé est : {path}. Vérifie qu'il existe et que MT5 64-bit est bien installé."
                )
            return base
        if code == -10004 or "auth" in str(msg).lower():
            return "Authentification refusée. Vérifie le numéro de compte, le mot de passe et le nom du serveur."
        if code == -10005 or "ipc timeout" in str(msg).lower():
            return (
                "IPC timeout : la lib Python n'arrive pas à communiquer avec le terminal MT5. "
                f"Chemin utilisé : {path or '(autodétecté)'}. Vérifie que : "
                "1) le chemin pointe vers TON terminal (ex: RoboForex), pas un autre MT5 installé ; "
                "2) le terminal MT5 est ouvert dans ta session Windows ; "
                "3) le backend tourne dans la session interactive (Tâche planifiée, pas un Service)."
            )
        return f"MT5 initialize failed: code={code} msg={msg}"

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
        autodetected = _autodetect_mt5_path() if HAS_MT5_NATIVE else None
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
            "terminal_path": self.terminal_path,
            "autodetected_path": autodetected,
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
                            await self._connect_native(self.account_login, self._password, self.server, self.terminal_path)
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
                # Wide window with future margin: broker server time can be ahead of UTC
                date_from = datetime.now() - timedelta(days=days)
                date_to = datetime.now() + timedelta(days=2)
                deals = await asyncio.to_thread(mt5.history_deals_get, date_from, date_to)
                if not deals:
                    return []
                return [{
                    "ticket": d.ticket,
                    "position_id": d.position_id,
                    "order": d.order,
                    "symbol": d.symbol,
                    "type": d.type,
                    "entry": d.entry,
                    "magic": d.magic,
                    "comment": d.comment,
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

    async def get_spread_pct(self, symbol: str) -> Optional[float]:
        """Relative spread in % of price (e.g. 0.002 = 0.002%). None if unavailable."""
        tick = await self.get_price(symbol)
        if not tick or not tick.get("bid") or not tick.get("ask"):
            return None
        mid = (tick["bid"] + tick["ask"]) / 2
        if mid <= 0:
            return None
        return ((tick["ask"] - tick["bid"]) / mid) * 100

    # ----- Trading: place / close orders on MT5 -----
    async def place_order(self, symbol: str, side: str, volume: float, sl: float, tp: float, comment: str = "TradingBot") -> Dict[str, Any]:
        """Place a market order on MT5. Returns {'ok': bool, 'ticket'?, 'price'?, 'error'?}"""
        if not self.connected:
            return {"ok": False, "error": "MT5 non connecte"}
        try:
            if self.mode == "native" and HAS_MT5_NATIVE:
                def _send():
                    info = mt5.symbol_info_tick(symbol)
                    if info is None:
                        return {"ok": False, "error": f"Pas de tick pour {symbol}"}
                    price = info.ask if side == "BUY" else info.bid
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": float(volume),
                        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
                        "price": price,
                        "sl": float(sl),
                        "tp": float(tp),
                        "deviation": 20,
                        "magic": 234000,
                        "comment": comment,
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result is None:
                        return {"ok": False, "error": str(mt5.last_error())}
                    if result.retcode != mt5.TRADE_RETCODE_DONE:
                        return {"ok": False, "error": f"retcode={result.retcode} comment={result.comment}"}
                    return {"ok": True, "ticket": result.order, "price": result.price, "volume": result.volume}
                return await asyncio.to_thread(_send)
            if self.mode == "bridge":
                r = await self._client.post(f"{self.bridge_url}/order", json={
                    "symbol": symbol, "side": side, "volume": volume, "sl": sl, "tp": tp, "comment": comment,
                })
                return r.json() if r.status_code == 200 else {"ok": False, "error": r.text}
        except Exception as e:
            logger.exception("place_order error")
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Mode connecteur inconnu"}

    async def close_position(self, ticket: int) -> Dict[str, Any]:
        """Close an open position by its MT5 ticket."""
        if not self.connected:
            return {"ok": False, "error": "MT5 non connecte"}
        try:
            if self.mode == "native" and HAS_MT5_NATIVE:
                def _close():
                    positions = mt5.positions_get(ticket=ticket)
                    if not positions:
                        return {"ok": False, "error": "Position introuvable"}
                    p = positions[0]
                    tick = mt5.symbol_info_tick(p.symbol)
                    price = tick.bid if p.type == 0 else tick.ask
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": p.symbol,
                        "volume": p.volume,
                        "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                        "position": p.ticket,
                        "price": price,
                        "deviation": 20,
                        "magic": 234000,
                        "comment": "TradingBot Close",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                        return {"ok": False, "error": str(mt5.last_error()) if result is None else f"retcode={result.retcode}"}
                    return {"ok": True, "price": result.price}
                return await asyncio.to_thread(_close)
            if self.mode == "bridge":
                r = await self._client.post(f"{self.bridge_url}/close", json={"ticket": ticket})
                return r.json() if r.status_code == 200 else {"ok": False, "error": r.text}
        except Exception as e:
            logger.exception("close_position error")
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Mode connecteur inconnu"}


mt5_connector = MT5Connector()
