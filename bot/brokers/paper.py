"""Broker simulé : prix réels du flux (MT5 ou ccxt), ordres fictifs.

Les SL/TP sont vérifiés à chaque cotation, comme le ferait le serveur du broker.
"""
from __future__ import annotations

import itertools

import pandas as pd

from ..config import SymbolConfig
from ..risk import SymbolSpec
from .base import Broker, BrokerPosition


class PaperBroker(Broker):
    name = "paper"

    def __init__(self, feed: Broker, symbols: list[SymbolConfig], starting_equity: float, state: dict | None = None):
        self.feed = feed
        self.syms = {s.name: s for s in symbols}
        state = state or {}
        self.balance = float(state.get("balance", starting_equity))
        self._pos: dict[str, BrokerPosition] = {
            p["ticket"]: BrokerPosition(**p) for p in state.get("positions", [])
        }
        self._closed: dict[str, float] = {}
        self._pnl_open: dict[str, float] = {}
        self._ids = itertools.count(int(state.get("next_id", 1)))

    def connect(self) -> None:
        self.feed.connect()

    def export(self) -> dict:
        return {"balance": self.balance, "positions": [p.__dict__ for p in self._pos.values()],
                "next_id": next(self._ids)}

    def candles(self, symbol, tf, count):
        return self.feed.candles(symbol, tf, count)

    def spec(self, symbol) -> SymbolSpec:
        try:
            return self.feed.spec(symbol)
        except Exception:
            s = self.syms[symbol]
            return SymbolSpec(symbol, s.contract_size, s.volume_min, s.volume_step, s.volume_max, s.contract_size)

    def quote(self, symbol):
        bid, ask = self.feed.quote(symbol)
        self._check_stops(symbol, bid, ask)
        return bid, ask

    def _vpp(self, symbol):
        return self.spec(symbol).value_per_point

    def _comm(self, symbol, vol):
        s = self.syms.get(symbol)
        return (s.commission_per_lot if s else 0.0) * vol

    def _check_stops(self, symbol, bid, ask):
        for p in list(self._pos.values()):
            if p.symbol != symbol:
                continue
            px = bid if p.side == 1 else ask
            hit_sl = p.sl and ((px <= p.sl) if p.side == 1 else (px >= p.sl))
            hit_tp = p.tp and ((px >= p.tp) if p.side == 1 else (px <= p.tp))
            if hit_sl or hit_tp:
                pnl = self._realize(p, p.volume, px)
                self._closed[p.ticket] = self._pnl_open.pop(p.ticket, 0.0) + pnl
                del self._pos[p.ticket]

    def _realize(self, p: BrokerPosition, vol: float, px: float) -> float:
        pnl = (px - p.entry) * p.side * vol * self._vpp(p.symbol) - self._comm(p.symbol, vol)
        self.balance += pnl
        return pnl

    def equity(self) -> float:
        eq = self.balance
        for p in self._pos.values():
            bid, ask = self.feed.quote(p.symbol)
            px = bid if p.side == 1 else ask
            eq += (px - p.entry) * p.side * p.volume * self._vpp(p.symbol)
        return eq

    def positions(self):
        return list(self._pos.values())

    def open(self, symbol, side, volume, sl, tp, comment):
        bid, ask = self.feed.quote(symbol)
        px = ask if side == 1 else bid
        t = f"P{next(self._ids)}"
        self._pos[t] = BrokerPosition(t, symbol, side, volume, px, sl, tp)
        self._pnl_open[t] = 0.0
        return t, px

    def modify(self, ticket, symbol, sl, tp):
        p = self._pos[ticket]
        p.sl, p.tp = sl, tp

    def close(self, ticket, symbol, volume=None):
        p = self._pos[ticket]
        bid, ask = self.feed.quote(symbol)
        px = bid if p.side == 1 else ask
        vol = p.volume if volume is None or volume >= p.volume else volume
        pnl = self._realize(p, vol, px)
        self._pnl_open[ticket] = self._pnl_open.get(ticket, 0.0) + pnl
        p.volume = round(p.volume - vol, 8)
        if p.volume <= 0:
            self._closed[ticket] = self._pnl_open.pop(ticket, 0.0)
            del self._pos[ticket]
        return px

    def closed_pnl(self, ticket):
        return self._closed.get(ticket)

    def shutdown(self):
        self.feed.shutdown()
