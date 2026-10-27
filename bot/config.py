"""Chargement de la configuration (TOML) et des secrets (.env)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.5
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.5
    max_drawdown_pct: float = 8.0
    daily_profit_lock_pct: float = 0.0
    max_open_positions: int = 3
    max_positions_per_group: int = 1
    max_trades_per_day: int = 20
    loss_streak_pause: int = 3
    loss_streak_pause_minutes: int = 120
    loss_streak_risk_factor: float = 0.5
    drawdown_risk_factor: float = 0.5
    max_leverage: float = 10.0


@dataclass
class ManagementConfig:
    tp1_r: float = 1.0
    tp1_close_fraction: float = 0.5
    tp2_r: float = 2.5
    lock_steps: list = field(default_factory=lambda: [[0.6, -0.5], [1.0, 0.1], [1.5, 0.7], [2.0, 1.2]])
    trail_atr_mult: float = 1.2
    early_exit_bars: int = 12
    early_exit_min_r: float = 0.3
    max_bars: int = 48


@dataclass
class StrategyConfig:
    min_score: int = 8
    swing_k: int = 3
    sweep_lookback: int = 3
    min_sl_atr: float = 0.6
    max_sl_atr: float = 2.5
    sl_buffer_atr: float = 0.15
    min_room_r: float = 1.2
    max_spread_atr: float = 0.15
    signal_cooldown_bars: int = 6
    news_blackout: list = field(default_factory=list)
    news_blackout_minutes: int = 30


@dataclass
class SymbolConfig:
    name: str
    group: str = ""
    sessions: list = field(default_factory=lambda: [[0, 24]])
    no_new_trades_friday_after: int | None = None
    ref: dict | None = None
    spread: float = 0.0
    commission_per_lot: float = 0.0
    contract_size: float = 1.0
    volume_step: float = 0.01
    volume_min: float = 0.01
    volume_max: float = 100.0


@dataclass
class BotConfig:
    mode: str = "paper"
    broker: str = "mt5"
    poll_seconds: float = 5
    ltf: str = "5m"
    htf: str = "1h"
    paper_starting_equity: float = 10000.0
    state_file: str = "state/state.json"
    journal_file: str = "state/journal.csv"
    log_file: str = "state/bot.log"
    close_positions_on_shutdown: bool = False


@dataclass
class Config:
    bot: BotConfig
    risk: RiskConfig
    management: ManagementConfig
    strategy: StrategyConfig
    symbols: list[SymbolConfig]
    mt5: dict
    ccxt: dict
    telegram: dict

    def symbol(self, name: str) -> SymbolConfig:
        for s in self.symbols:
            if s.name == name:
                return s
        raise KeyError(name)


def _pick(cls, data: dict | None):
    data = data or {}
    known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
    return cls(**known)


def load_env(path: str | Path = ".env") -> None:
    """Lit un fichier .env simple (CLE=valeur) sans dépendance externe."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    symbols = [_pick(SymbolConfig, s) for s in raw.get("symbols", [])]
    if not symbols:
        raise ValueError("Aucun actif défini dans [[symbols]]")
    cfg = Config(
        bot=_pick(BotConfig, raw.get("bot")),
        risk=_pick(RiskConfig, raw.get("risk")),
        management=_pick(ManagementConfig, raw.get("management")),
        strategy=_pick(StrategyConfig, raw.get("strategy")),
        symbols=symbols,
        mt5=raw.get("mt5", {}),
        ccxt=raw.get("ccxt", {}),
        telegram=raw.get("telegram", {}),
    )
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    r = cfg.risk
    if not 0 < r.risk_per_trade_pct <= r.max_risk_per_trade_pct <= 2.0:
        raise ValueError("risk_per_trade_pct doit être > 0 et <= max_risk_per_trade_pct (<= 2 %)")
    if r.max_daily_loss_pct <= r.risk_per_trade_pct:
        raise ValueError("max_daily_loss_pct doit dépasser le risque d'un trade")
    m = cfg.management
    if not 0 < m.tp1_r < m.tp2_r:
        raise ValueError("Il faut 0 < tp1_r < tp2_r")
    if not 0 < m.tp1_close_fraction < 1:
        raise ValueError("tp1_close_fraction doit être entre 0 et 1")
    if cfg.bot.mode not in ("paper", "live"):
        raise ValueError("mode doit être 'paper' ou 'live'")
