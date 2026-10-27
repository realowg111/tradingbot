"""Connexion MetaTrader 5 (or, crypto CFD, indices). Fonctionne sous Windows (VPS).

Le module officiel `MetaTrader5` pilote le terminal installé sur la machine.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..risk import SymbolSpec
from ..strategy import TF_MINUTES
from .base import Broker, BrokerPosition, drop_open_candle


class MT5Broker(Broker):
    name = "mt5"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.magic = int(cfg.get("magic", 770077))
        self.deviation = int(cfg.get("deviation_points", 30))
        self.mt5 = None
        self._specs: dict[str, SymbolSpec] = {}

    def connect(self) -> None:
        import MetaTrader5 as mt5  # disponible seulement sous Windows

        self.mt5 = mt5
        kwargs = {}
        if os.getenv("MT5_LOGIN"):
            kwargs = {"login": int(os.environ["MT5_LOGIN"]), "password": os.environ.get("MT5_PASSWORD", ""),
                      "server": os.environ.get("MT5_SERVER", "")}
        path = self.cfg.get("path")
        ok = mt5.initialize(path, **kwargs) if path else mt5.initialize(**kwargs)
        if not ok:
            raise ConnectionError(f"MT5 initialize a échoué : {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            raise ConnectionError(f"MT5 : compte inaccessible : {mt5.last_error()}")
        if not info.trade_allowed:
            raise ConnectionError("MT5 : le trading algorithmique n'est pas autorisé (bouton Algo Trading)")

    def _ensure(self, symbol: str):
        if not self.mt5.symbol_select(symbol, True):
            raise ValueError(f"Symbole MT5 introuvable : {symbol}")

    def _tf(self, tf: str):
        m = self.mt5
        return {"1m": m.TIMEFRAME_M1, "5m": m.TIMEFRAME_M5, "15m": m.TIMEFRAME_M15, "30m": m.TIMEFRAME_M30,
                "1h": m.TIMEFRAME_H1, "4h": m.TIMEFRAME_H4, "1d": m.TIMEFRAME_D1}[tf]

    def server_offset(self, symbol: str) -> timedelta:
        """Les heures MT5 sont celles du serveur (souvent UTC+2/+3) : on estime le décalage."""
        tick = self.mt5.symbol_info_tick(symbol)
        now = datetime.now(timezone.utc).timestamp()
        hours = round((tick.time - now) / 3600) if tick else 0
        return timedelta(hours=hours)

    def candles(self, symbol, tf, count):
        self._ensure(symbol)
        rates = self.mt5.copy_rates_from_pos(symbol, self._tf(tf), 0, count + 1)
        if rates is None or len(rates) == 0:
            raise ConnectionError(f"MT5 : pas de bougies pour {symbol} : {self.mt5.last_error()}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True) - self.server_offset(symbol)
        df = df.set_index("time").rename(columns={"tick_volume": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        return drop_open_candle(df, TF_MINUTES[tf], pd.Timestamp.now(tz="UTC"))

    def spec(self, symbol):
        if symbol not in self._specs:
            self._ensure(symbol)
            i = self.mt5.symbol_info(symbol)
            vpp = i.trade_tick_value / i.trade_tick_size if i.trade_tick_size else i.trade_contract_size
            self._specs[symbol] = SymbolSpec(symbol, vpp, i.volume_min, i.volume_step, i.volume_max,
                                             i.trade_contract_size)
        return self._specs[symbol]

    def quote(self, symbol):
        self._ensure(symbol)
        t = self.mt5.symbol_info_tick(symbol)
        if t is None:
            raise ConnectionError(f"MT5 : pas de cotation pour {symbol}")
        return float(t.bid), float(t.ask)

    def equity(self):
        return float(self.mt5.account_info().equity)

    def positions(self):
        out = []
        for p in self.mt5.positions_get() or []:
            if p.magic != self.magic:
                continue
            side = 1 if p.type == self.mt5.POSITION_TYPE_BUY else -1
            out.append(BrokerPosition(str(p.ticket), p.symbol, side, p.volume, p.price_open, p.sl, p.tp))
        return out

    def _filling(self, symbol):
        mode = self.mt5.symbol_info(symbol).filling_mode
        if mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def _round(self, symbol, price):
        return round(price, self.mt5.symbol_info(symbol).digits)

    def _send(self, req):
        res = self.mt5.order_send(req)
        if res is None or res.retcode != self.mt5.TRADE_RETCODE_DONE:
            code = getattr(res, "retcode", None)
            raise RuntimeError(f"MT5 order_send refusé ({code}) : {getattr(res, 'comment', self.mt5.last_error())}")
        return res

    def open(self, symbol, side, volume, sl, tp, comment):
        bid, ask = self.quote(symbol)
        m = self.mt5
        req = {
            "action": m.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(volume),
            "type": m.ORDER_TYPE_BUY if side == 1 else m.ORDER_TYPE_SELL,
            "price": ask if side == 1 else bid, "sl": self._round(symbol, sl), "tp": self._round(symbol, tp),
            "deviation": self.deviation, "magic": self.magic, "comment": comment[:30],
            "type_time": m.ORDER_TIME_GTC, "type_filling": self._filling(symbol),
        }
        res = self._send(req)
        ticket = str(res.order)
        for p in m.positions_get(symbol=symbol) or []:
            if p.magic == self.magic and (p.ticket == res.order or p.identifier == res.order):
                ticket = str(p.ticket)
        return ticket, float(res.price or req["price"])

    def modify(self, ticket, symbol, sl, tp):
        m = self.mt5
        self._send({"action": m.TRADE_ACTION_SLTP, "position": int(ticket), "symbol": symbol,
                    "sl": self._round(symbol, sl), "tp": self._round(symbol, tp), "magic": self.magic})

    def close(self, ticket, symbol, volume=None):
        m = self.mt5
        ps = m.positions_get(ticket=int(ticket))
        if not ps:
            raise RuntimeError(f"Position {ticket} introuvable")
        p = ps[0]
        bid, ask = self.quote(symbol)
        buy = p.type == m.POSITION_TYPE_BUY
        req = {
            "action": m.TRADE_ACTION_DEAL, "symbol": symbol, "position": p.ticket,
            "volume": float(volume or p.volume), "type": m.ORDER_TYPE_SELL if buy else m.ORDER_TYPE_BUY,
            "price": bid if buy else ask, "deviation": self.deviation, "magic": self.magic,
            "comment": "bot close", "type_time": m.ORDER_TIME_GTC, "type_filling": self._filling(symbol),
        }
        res = self._send(req)
        return float(res.price or req["price"])

    def closed_pnl(self, ticket):
        deals = self.mt5.history_deals_get(position=int(ticket))
        if not deals:
            return None
        return float(sum(d.profit + d.commission + d.swap + getattr(d, "fee", 0.0) for d in deals))

    def shutdown(self):
        if self.mt5:
            self.mt5.shutdown()
