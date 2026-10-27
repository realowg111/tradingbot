"""Gestion d'une position ouverte : TP partiel, break-even, paliers, trailing, sorties au temps.

Règle d'or : le stop ne recule jamais, il ne fait qu'avancer dans le sens du gain.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .config import ManagementConfig


@dataclass
class Position:
    id: str
    symbol: str
    group: str
    side: int
    entry: float
    sl: float
    initial_sl: float
    tp1: float
    tp2: float
    volume: float
    initial_volume: float
    opened_at: str
    setup: str = ""
    score: int = 0
    tp1_done: bool = False
    bars_held: int = 0
    mfe_r: float = 0.0          # gain latent max atteint, en R
    realized: float = 0.0       # P&L déjà encaissé (partiels)
    tickets: list = field(default_factory=list)

    @property
    def r_dist(self) -> float:
        return abs(self.entry - self.initial_sl)

    def r_at(self, price: float) -> float:
        return (price - self.entry) * self.side / self.r_dist if self.r_dist > 0 else 0.0

    def price_at_r(self, r: float) -> float:
        return self.entry + self.side * r * self.r_dist

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Action:
    kind: str                  # "partial", "move_sl", "close"
    volume: float = 0.0
    price: float = 0.0
    reason: str = ""


def better_sl(pos: Position, new_sl: float) -> bool:
    return (new_sl > pos.sl) if pos.side == 1 else (new_sl < pos.sl)


class TradeManager:
    def __init__(self, cfg: ManagementConfig, volume_step: float = 0.01, volume_min: float = 0.01):
        self.cfg = cfg
        self.volume_step = volume_step
        self.volume_min = volume_min

    def make_position(self, pid: str, sig, volume: float, group: str, opened_at: str,
                      entry: float | None = None, sl: float | None = None) -> Position:
        """entry = prix réellement exécuté. Sans sl explicite, on garde la distance du signal."""
        e = sig.entry if entry is None else entry
        if sl is None:
            r = abs(sig.entry - sig.sl)
            sl = e - sig.side * r
        r = abs(e - sl)
        return Position(
            id=pid, symbol=sig.symbol, group=group, side=sig.side, entry=e, sl=sl, initial_sl=sl,
            tp1=e + sig.side * self.cfg.tp1_r * r, tp2=e + sig.side * self.cfg.tp2_r * r,
            volume=volume, initial_volume=volume, opened_at=opened_at, setup=sig.setup, score=sig.score,
        )

    def _partial_volume(self, pos: Position) -> float:
        from .risk import floor_step
        v = floor_step(pos.initial_volume * self.cfg.tp1_close_fraction, self.volume_step)
        if v < self.volume_min or pos.volume - v < self.volume_min:
            return 0.0  # trop petit pour couper : on gère tout en bloc
        return round(v, 8)

    def on_price(self, pos: Position, price: float, atr: float) -> list[Action]:
        """Appelé à chaque prix (live) ou au plus favorable de la bougie (backtest)."""
        acts: list[Action] = []
        r_now = pos.r_at(price)
        pos.mfe_r = max(pos.mfe_r, r_now)

        if not pos.tp1_done and r_now >= self.cfg.tp1_r:
            pos.tp1_done = True
            v = self._partial_volume(pos)
            if v > 0:
                acts.append(Action("partial", v, pos.tp1, "TP1"))

        new_sl = pos.sl
        for trigger, lock in self.cfg.lock_steps:
            if pos.mfe_r >= trigger:
                cand = pos.price_at_r(lock)
                if (cand > new_sl) if pos.side == 1 else (cand < new_sl):
                    new_sl = cand
        if pos.tp1_done and atr > 0:
            cand = price - pos.side * self.cfg.trail_atr_mult * atr
            if (cand > new_sl) if pos.side == 1 else (cand < new_sl):
                new_sl = cand
        if better_sl(pos, new_sl):
            acts.append(Action("move_sl", price=new_sl, reason=f"SL -> {pos.r_at(new_sl):+.2f}R"))
        return acts

    def on_bar_close(self, pos: Position) -> list[Action]:
        """Sorties au temps : un scalp qui ne part pas est un mauvais scalp."""
        pos.bars_held += 1
        if not pos.tp1_done and pos.bars_held >= self.cfg.early_exit_bars and pos.mfe_r < self.cfg.early_exit_min_r:
            return [Action("close", reason="sortie anticipée (pas d'élan)")]
        if pos.bars_held >= self.cfg.max_bars:
            return [Action("close", reason="durée max atteinte")]
        return []
