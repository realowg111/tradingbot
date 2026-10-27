"""Connexion à un exchange crypto via ccxt (perpétuels USDT : Bybit, Binance, OKX...).

Le SL est posé comme ordre stop "reduceOnly" chez l'exchange : si le bot s'arrête,
la position reste protégée. À valider d'abord sur le testnet.
"""
from __future__ import annotations

import os

import pandas as pd

from ..risk import SymbolSpec
from ..strategy import TF_MINUTES
from .base import Broker, BrokerPosition, drop_open_candle


class CCXTBroker(Broker):
    name = "ccxt"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.map = cfg.get("symbol_map", {})
        self.ex = None
        self._stops: dict[str, str] = {}   # ticket -> id de l'ordre stop
        self._tps: dict[str, str] = {}
        self._prot: dict[str, tuple[float, float]] = {}  # ticket -> (sl, tp)

    def connect(self) -> None:
        import ccxt

        klass = getattr(ccxt, self.cfg.get("exchange", "bybit"))
        self.ex = klass({
            "apiKey": os.getenv("CCXT_API_KEY", ""), "secret": os.getenv("CCXT_API_SECRET", ""),
            "password": os.getenv("CCXT_API_PASSWORD") or None, "enableRateLimit": True,
            "options": {"defaultType": self.cfg.get("default_type", "swap")},
        })
        if self.cfg.get("testnet", True):
            self.ex.set_sandbox_mode(True)
        self.ex.load_markets()

    def _s(self, symbol: str) -> str:
        return self.map.get(symbol, symbol)

    def candles(self, symbol, tf, count):
        rows = self.ex.fetch_ohlcv(self._s(symbol), tf, limit=count + 1)
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        df = df.set_index("time").astype(float)
        return drop_open_candle(df, TF_MINUTES[tf], pd.Timestamp.now(tz="UTC"))

    def spec(self, symbol):
        m = self.ex.market(self._s(symbol))
        cs = float(m.get("contractSize") or 1.0)
        import ccxt
        p = m["precision"]["amount"]
        step = 10 ** -int(p) if self.ex.precisionMode == ccxt.DECIMAL_PLACES else float(p)
        vmin = float((m.get("limits", {}).get("amount", {}) or {}).get("min") or step)
        vmax = float((m.get("limits", {}).get("amount", {}) or {}).get("max") or 1e9)
        return SymbolSpec(symbol, value_per_point=cs, volume_min=vmin, volume_step=step, volume_max=vmax,
                          contract_size=cs)

    def quote(self, symbol):
        t = self.ex.fetch_ticker(self._s(symbol))
        bid = t.get("bid") or t["last"]
        ask = t.get("ask") or t["last"]
        return float(bid), float(ask)

    def equity(self):
        bal = self.ex.fetch_balance()
        quote = self.cfg.get("quote_currency", "USDT")
        total = float(bal.get("total", {}).get(quote) or 0.0)
        upnl = sum(float(p.get("unrealizedPnl") or 0) for p in self.ex.fetch_positions())
        return total + upnl

    def positions(self):
        out = []
        rev = {v: k for k, v in self.map.items()}
        for p in self.ex.fetch_positions():
            amt = float(p.get("contracts") or 0)
            if amt <= 0:
                continue
            sym = rev.get(p["symbol"], p["symbol"])
            side = 1 if p.get("side") == "long" else -1
            out.append(BrokerPosition(f"{sym}:{p.get('side')}", sym, side, amt, float(p.get("entryPrice") or 0), 0, 0))
        return out

    def _place_protection(self, ticket, symbol, side, amount, sl, tp):
        s = self._s(symbol)
        opp = "sell" if side == 1 else "buy"
        self._prot[ticket] = (sl, tp)
        so = self.ex.create_order(s, "market", opp, amount, None,
                                  {"stopLossPrice": self.ex.price_to_precision(s, sl), "reduceOnly": True})
        self._stops[ticket] = so["id"]
        if tp:
            to = self.ex.create_order(s, "limit", opp, amount, float(self.ex.price_to_precision(s, tp)),
                                      {"reduceOnly": True})
            self._tps[ticket] = to["id"]

    def _cancel_protection(self, ticket, symbol):
        s = self._s(symbol)
        for book in (self._stops, self._tps):
            oid = book.pop(ticket, None)
            if oid:
                try:
                    self.ex.cancel_order(oid, s)
                except Exception:
                    pass

    def open(self, symbol, side, volume, sl, tp, comment):
        s = self._s(symbol)
        amount = float(self.ex.amount_to_precision(s, volume))
        o = self.ex.create_order(s, "market", "buy" if side == 1 else "sell", amount)
        px = float(o.get("average") or o.get("price") or self.quote(symbol)[1 if side == 1 else 0])
        ticket = f"{symbol}:{'long' if side == 1 else 'short'}"
        try:
            self._place_protection(ticket, symbol, side, amount, sl, tp)
        except Exception:
            # Impossible de protéger la position : on la ferme immédiatement.
            self.ex.create_order(s, "market", "sell" if side == 1 else "buy", amount, None, {"reduceOnly": True})
            raise
        return ticket, px

    def modify(self, ticket, symbol, sl, tp):
        pos = next((p for p in self.positions() if p.ticket == ticket), None)
        if pos is None:
            return
        self._cancel_protection(ticket, symbol)
        self._place_protection(ticket, symbol, pos.side, pos.volume, sl, tp)

    def close(self, ticket, symbol, volume=None):
        pos = next((p for p in self.positions() if p.ticket == ticket), None)
        if pos is None:
            raise RuntimeError(f"Position {ticket} introuvable")
        s = self._s(symbol)
        amount = float(self.ex.amount_to_precision(s, volume or pos.volume))
        o = self.ex.create_order(s, "market", "sell" if pos.side == 1 else "buy", amount, None, {"reduceOnly": True})
        if volume is None or amount >= pos.volume:
            self._cancel_protection(ticket, symbol)
            self._prot.pop(ticket, None)
        elif ticket in self._prot:
            self.modify(ticket, symbol, *self._prot[ticket])  # stop ajusté au volume restant
        return float(o.get("average") or o.get("price") or 0.0)

