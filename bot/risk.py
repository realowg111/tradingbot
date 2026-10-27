"""Protection du capital : taille des positions et limites de perte.

Principes : risque fixe et petit par trade, jamais de martingale, réduction du
risque après des pertes, arrêt du jour après une perte max, arrêt total au-delà
du drawdown max.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

from .config import RiskConfig


@dataclass
class SymbolSpec:
    """Caractéristiques d'un contrat chez le broker."""
    name: str
    value_per_point: float      # gain en devise du compte pour +1,0 de prix avec 1 lot
    volume_min: float
    volume_step: float
    volume_max: float
    contract_size: float = 1.0


@dataclass
class RiskState:
    day: str = ""
    day_start_equity: float = 0.0
    peak_equity: float = 0.0
    consecutive_losses: int = 0
    trades_today: int = 0
    paused_until: str = ""
    halted: bool = False
    halt_reason: str = ""


def floor_step(x: float, step: float) -> float:
    if step <= 0:
        return x
    return math.floor(x / step + 1e-9) * step


class RiskManager:
    def __init__(self, cfg: RiskConfig, state: RiskState | None = None):
        self.cfg = cfg
        self.s = state or RiskState()

    # --- Cycle de vie ---
    def on_tick(self, now: datetime, equity: float) -> None:
        day = now.strftime("%Y-%m-%d")
        if self.s.day != day:
            self.s.day = day
            self.s.day_start_equity = equity
            self.s.trades_today = 0
            if self.s.halt_reason.startswith("jour"):
                self.s.halted, self.s.halt_reason = False, ""
        if self.s.peak_equity <= 0:
            self.s.peak_equity = equity
        self.s.peak_equity = max(self.s.peak_equity, equity)

        if self.s.day_start_equity > 0:
            day_pnl = (equity - self.s.day_start_equity) / self.s.day_start_equity * 100
            if day_pnl <= -self.cfg.max_daily_loss_pct and not self.s.halted:
                self._halt(f"jour : perte de {day_pnl:.2f} %")
            lock = self.cfg.daily_profit_lock_pct
            if lock > 0 and day_pnl >= lock and not self.s.halted:
                self._halt(f"jour : objectif +{day_pnl:.2f} % sécurisé")
        dd = self.drawdown_pct(equity)
        if dd >= self.cfg.max_drawdown_pct and not self.s.halt_reason.startswith("total"):
            self._halt(f"total : drawdown {dd:.2f} % >= {self.cfg.max_drawdown_pct} %")

    def _halt(self, reason: str) -> None:
        self.s.halted, self.s.halt_reason = True, reason

    def drawdown_pct(self, equity: float) -> float:
        if self.s.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.s.peak_equity - equity) / self.s.peak_equity * 100)

    def on_trade_closed(self, pnl: float, now: datetime) -> None:
        if pnl < 0:
            self.s.consecutive_losses += 1
            if self.s.consecutive_losses >= self.cfg.loss_streak_pause:
                until = now + timedelta(minutes=self.cfg.loss_streak_pause_minutes)
                self.s.paused_until = until.isoformat()
        elif pnl > 0:
            self.s.consecutive_losses = 0

    def on_trade_opened(self) -> None:
        self.s.trades_today += 1

    # --- Autorisations ---
    def can_open(self, now: datetime, open_positions: list, symbol: str, group: str) -> tuple[bool, str]:
        if self.s.halted:
            return False, f"arrêt ({self.s.halt_reason})"
        if self.s.paused_until:
            until = datetime.fromisoformat(self.s.paused_until)
            if now < until:
                return False, f"pause après {self.s.consecutive_losses} pertes jusqu'à {until:%H:%M} UTC"
            self.s.paused_until = ""
        if self.s.trades_today >= self.cfg.max_trades_per_day:
            return False, "nombre max de trades du jour atteint"
        if len(open_positions) >= self.cfg.max_open_positions:
            return False, "nombre max de positions ouvertes"
        if any(p.symbol == symbol for p in open_positions):
            return False, "déjà une position sur cet actif"
        if group and sum(1 for p in open_positions if p.group == group) >= self.cfg.max_positions_per_group:
            return False, f"déjà une position dans le groupe {group}"
        return True, ""

    def risk_pct(self, equity: float) -> float:
        pct = self.cfg.risk_per_trade_pct
        if self.s.consecutive_losses >= 2:
            pct *= self.cfg.loss_streak_risk_factor
        if self.drawdown_pct(equity) >= self.cfg.max_drawdown_pct / 2:
            pct *= self.cfg.drawdown_risk_factor
        return min(pct, self.cfg.max_risk_per_trade_pct)

    def position_size(self, equity: float, entry: float, sl: float, spec: SymbolSpec,
                      cost_per_lot: float = 0.0) -> tuple[float, float]:
        """Volume tel que la perte au SL (frais compris) ne dépasse pas le risque autorisé.

        Retourne (volume, montant risqué). Volume 0 si même le lot minimum risque trop.
        """
        risk_amount = equity * self.risk_pct(equity) / 100
        loss_per_lot = abs(entry - sl) * spec.value_per_point + cost_per_lot
        if loss_per_lot <= 0:
            return 0.0, 0.0
        vol = floor_step(risk_amount / loss_per_lot, spec.volume_step)
        max_notional = equity * self.cfg.max_leverage
        notional_per_lot = entry * spec.contract_size
        if notional_per_lot > 0:
            vol = min(vol, floor_step(max_notional / notional_per_lot, spec.volume_step))
        vol = min(vol, spec.volume_max)
        if vol < spec.volume_min:
            return 0.0, 0.0
        vol = round(vol, 8)
        return vol, vol * loss_per_lot

    def to_dict(self) -> dict:
        return asdict(self.s)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
