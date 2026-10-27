"""Backtest bougie par bougie avec exactement la même stratégie et la même gestion qu'en live.

Hypothèses prudentes : entrée à l'ouverture de la bougie suivante (pas de
look-ahead), spread payé à l'entrée et à la sortie, glissement sur les stops,
et si une bougie touche à la fois le stop et l'objectif, on suppose le stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from .config import Config, SymbolConfig
from .data import resample
from .manager import TradeManager
from .risk import RiskManager, SymbolSpec
from .strategy import TF_MINUTES, prepare, signal_at


@dataclass
class Trade:
    symbol: str
    side: int
    setup: str
    score: int
    opened: pd.Timestamp
    closed: pd.Timestamp
    entry: float
    sl: float
    volume: float
    risk_amount: float
    pnl: float
    tp1_hit: bool
    exit_reason: str

    @property
    def r(self) -> float:
        return self.pnl / self.risk_amount if self.risk_amount > 0 else 0.0


def spec_from_cfg(sym: SymbolConfig) -> SymbolSpec:
    return SymbolSpec(sym.name, value_per_point=sym.contract_size, volume_min=sym.volume_min,
                      volume_step=sym.volume_step, volume_max=sym.volume_max, contract_size=sym.contract_size)


def run(ltf: pd.DataFrame, sym: SymbolConfig, cfg: Config, ref_ltf: pd.DataFrame | None = None,
        equity: float = 10_000.0, slippage: float | None = None) -> tuple[list[Trade], pd.Series]:
    st, mg = cfg.strategy, cfg.management
    ltf_min = TF_MINUTES[cfg.bot.ltf]
    htf = resample(ltf, cfg.bot.htf)
    ref_htf = resample(ref_ltf, cfg.bot.htf) if ref_ltf is not None else None
    c = prepare(ltf, htf, st, cfg.bot.ltf, cfg.bot.htf, ref_htf)

    spec = spec_from_cfg(sym)
    rm = RiskManager(cfg.risk)
    tm = TradeManager(mg, sym.volume_step, sym.volume_min)
    half = sym.spread / 2
    slip = sym.spread * 0.2 if slippage is None else slippage
    vpp = spec.value_per_point
    comm = sym.commission_per_lot

    O, H, L, C, A = (c[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
    idx = c.index
    trades: list[Trade] = []
    curve = np.full(len(c), np.nan)
    pos = None
    pos_risk = 0.0
    pending = None
    next_allowed = 0

    def close_part(vol: float, price: float) -> float:
        return (price - pos.entry) * pos.side * vol * vpp - comm * vol

    def finish(i: int, price: float, reason: str):
        nonlocal pos, equity
        pnl = close_part(pos.volume, price)
        equity += pnl
        total = pos.realized + pnl
        t_close = idx[i] + timedelta(minutes=ltf_min)
        trades.append(Trade(sym.name, pos.side, pos.setup, pos.score, pd.Timestamp(pos.opened_at), t_close,
                            pos.entry, pos.initial_sl, pos.initial_volume, pos_risk, total, pos.tp1_done, reason))
        rm.on_trade_closed(total, t_close.to_pydatetime())
        pos = None

    for i in range(len(c)):
        bar_end = (idx[i] + timedelta(minutes=ltf_min)).to_pydatetime()

        # 1) Entrée au prix d'ouverture de cette bougie
        if pending is not None:
            sig = pending
            pending = None
            fill = O[i] + sig.side * (half + slip)
            vol, risk_amt = rm.position_size(equity, sig.entry, sig.sl, spec, cost_per_lot=comm + 2 * half * vpp)
            if vol > 0:
                pos = tm.make_position(f"{sym.name}-{i}", sig, vol, sym.group, idx[i].isoformat(), entry=fill)
                pos_risk = risk_amt
                rm.on_trade_opened()

        # 2) Gestion de la position sur la bougie
        if pos is not None:
            lng = pos.side == 1
            adverse = L[i] - half if lng else H[i] + half
            fav = H[i] - half if lng else L[i] + half
            atr_prev = A[i - 1]
            if (adverse <= pos.sl) if lng else (adverse >= pos.sl):
                finish(i, pos.sl - pos.side * slip, "stop")
            elif (fav >= pos.tp2) if lng else (fav <= pos.tp2):
                finish(i, pos.tp2, "TP2")
            else:
                for act in tm.on_price(pos, fav, atr_prev):
                    if act.kind == "partial":
                        pnl = close_part(act.volume, act.price)
                        equity += pnl
                        pos.realized += pnl
                        pos.volume = round(pos.volume - act.volume, 8)
                    elif act.kind == "move_sl":
                        pos.sl = act.price
                close_bid = C[i] - half if lng else C[i] + half
                if (close_bid <= pos.sl) if lng else (close_bid >= pos.sl):
                    finish(i, pos.sl - pos.side * slip, "stop suiveur")
                else:
                    for act in tm.on_bar_close(pos):
                        if act.kind == "close":
                            finish(i, close_bid, act.reason)
                            break

        floating = 0.0
        if pos is not None:
            floating = (C[i] - pos.side * half - pos.entry) * pos.side * pos.volume * vpp
        rm.on_tick(bar_end, equity + floating)
        curve[i] = equity + floating

        # 3) Recherche d'un nouveau signal (exécuté à la bougie suivante)
        if pos is None and pending is None and i >= next_allowed and i + 1 < len(c):
            sig = signal_at(c, i, sym, st, ts=bar_end)
            if sig is not None:
                ok, _ = rm.can_open(bar_end, [], sym.name, sym.group)
                if ok:
                    pending = sig
                    next_allowed = i + st.signal_cooldown_bars
        if rm.s.halted and rm.s.halt_reason.startswith("total"):
            if pos is not None:
                finish(i, C[i] - pos.side * half, "kill switch")
            curve[i:] = equity
            break

    return trades, pd.Series(curve, index=idx).ffill()


def stats(trades: list[Trade], curve: pd.Series, start_equity: float) -> dict:
    if not trades:
        return {"trades": 0}
    r = np.array([t.r for t in trades])
    pnl = np.array([t.pnl for t in trades])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    peak = curve.cummax()
    dd = ((curve - peak) / peak).min() * 100
    days = max(1, (curve.index[-1] - curve.index[0]).days)
    return {
        "trades": len(trades),
        "trades_par_jour": round(len(trades) / days, 2),
        "taux_reussite_%": round(100 * len(wins) / len(trades), 1),
        "trades_non_perdants_%": round(float(100 * np.mean(r > -0.15)), 1),
        "tp1_atteint_%": round(float(100 * np.mean([t.tp1_hit for t in trades])), 1),
        "gain_moyen_R": round(float(r[r > 0].mean()) if (r > 0).any() else 0, 2),
        "perte_moyenne_R": round(float(r[r < 0].mean()) if (r < 0).any() else 0, 2),
        "esperance_R": round(float(r.mean()), 3),
        "profit_factor": round(float(wins.sum() / -losses.sum()) if len(losses) else float("inf"), 2),
        "rendement_%": round(float((curve.iloc[-1] / start_equity - 1) * 100), 2),
        "max_drawdown_%": round(float(dd), 2),
        "pire_serie_pertes": int(max((len(s) for s in "".join("L" if x < 0 else "W" for x in pnl).split("W")), default=0)),
    }


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    rows = [{**t.__dict__, "r": round(t.r, 3)} for t in trades]
    return pd.DataFrame(rows)
