"""MT5 Bridge Agent - Run this on a Windows machine with MT5 installed.

This small HTTP server exposes MT5 data so that a remote Linux backend
can synchronize live account/positions/prices through the bridge.

USAGE (on Windows with Python 3.11+ and MetaTrader5 terminal installed):
    pip install MetaTrader5 fastapi uvicorn
    python mt5_agent.py --port 5555

Then in your backend .env (Linux):
    MT5_BRIDGE_URL=http://<your-windows-ip>:5555

SECURITY NOTES:
- Default binds to 127.0.0.1 only. Use --host 0.0.0.0 + a firewall + SSH
  tunnel or VPN to expose to the backend safely.
- The agent stores no credentials. The backend pushes them on /connect.
- Add a shared secret via BRIDGE_SECRET env var if exposing externally.
"""
import argparse
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("MetaTrader5 lib not installed. Run: pip install MetaTrader5")

BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET")

app = FastAPI(title="MT5 Bridge Agent")


class ConnectIn(BaseModel):
    login: str
    password: str
    server: str


def _check_secret(authorization: Optional[str] = Header(None)):
    if BRIDGE_SECRET:
        expected = f"Bearer {BRIDGE_SECRET}"
        if authorization != expected:
            raise HTTPException(401, "Invalid secret")


@app.get("/health")
def health(authorization: Optional[str] = Header(None)):
    _check_secret(authorization)
    info = mt5.terminal_info()
    return {"ok": True, "connected": info is not None}


@app.post("/connect")
def connect(payload: ConnectIn, authorization: Optional[str] = Header(None)):
    _check_secret(authorization)
    ok = mt5.initialize(login=int(payload.login), password=payload.password, server=payload.server)
    if not ok:
        return {"connected": False, "error": str(mt5.last_error())}
    return {"connected": True}


@app.get("/account")
def account(authorization: Optional[str] = Header(None)):
    _check_secret(authorization)
    info = mt5.account_info()
    if info is None:
        raise HTTPException(503, "Not connected")
    return {
        "balance": info.balance, "equity": info.equity, "margin": info.margin,
        "free_margin": info.margin_free, "profit": info.profit, "currency": info.currency,
        "leverage": info.leverage, "name": info.name, "server": info.server, "login": info.login,
    }


@app.get("/positions")
def positions(authorization: Optional[str] = Header(None)):
    _check_secret(authorization)
    pos = mt5.positions_get() or []
    return [{
        "ticket": p.ticket, "symbol": p.symbol, "side": "BUY" if p.type == 0 else "SELL",
        "volume": p.volume, "entry_price": p.price_open, "current_price": p.price_current,
        "stop_loss": p.sl, "take_profit": p.tp, "pnl": p.profit, "swap": p.swap,
        "opened_at": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
        "comment": p.comment,
    } for p in pos]


@app.get("/price/{symbol}")
def price(symbol: str, authorization: Optional[str] = Header(None)):
    _check_secret(authorization)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise HTTPException(404, f"No tick for {symbol}")
    return {"bid": tick.bid, "ask": tick.ask, "last": tick.last}


@app.get("/history")
def history(days: int = 30, authorization: Optional[str] = Header(None)):
    _check_secret(authorization)
    date_from = datetime.now() - timedelta(days=days)
    deals = mt5.history_deals_get(date_from, datetime.now()) or []
    return [{
        "ticket": d.ticket, "symbol": d.symbol, "type": d.type, "volume": d.volume,
        "price": d.price, "profit": d.profit, "commission": d.commission, "swap": d.swap,
        "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
    } for d in deals]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5555)
    args = parser.parse_args()
    print(f"▶ MT5 Bridge Agent listening on {args.host}:{args.port}")
    print(f"  Secret: {'enabled' if BRIDGE_SECRET else 'DISABLED (set BRIDGE_SECRET env var)'}")
    uvicorn.run(app, host=args.host, port=args.port)
