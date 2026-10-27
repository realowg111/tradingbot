from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bot import backtest as bt
from bot.brokers.base import Broker, BrokerPosition
from bot.config import load_config
from bot.data import resample, synthetic
from bot.engine import Engine
from bot.manager import TradeManager
from bot.risk import RiskManager, SymbolSpec
from bot.strategy import Signal, prepare, signal_at

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(tmp_path):
    c = load_config(ROOT / "config.example.toml")
    c.bot.state_file = str(tmp_path / "state.json")
    c.bot.journal_file = str(tmp_path / "journal.csv")
    return c


GOLD = SymbolSpec("XAUUSD", value_per_point=100, volume_min=0.01, volume_step=0.01, volume_max=50, contract_size=100)


# --- Risque -------------------------------------------------------------------

def test_position_size_respects_risk(cfg):
    rm = RiskManager(cfg.risk)
    vol, risked = rm.position_size(10_000, 2000.0, 1995.0, GOLD)  # 5 $ de stop
    assert vol == 0.1                                          # 0,5 % de 10 000 = 50 $ -> 0,1 lot
    assert risked <= 50.0 + 1e-9


def test_position_size_skips_when_min_lot_too_risky(cfg):
    rm = RiskManager(cfg.risk)
    vol, _ = rm.position_size(100, 2000.0, 1950.0, GOLD)       # 0,01 lot risquerait 50 $ sur 100 $
    assert vol == 0


def test_risk_reduced_after_losses_and_daily_halt(cfg):
    rm = RiskManager(cfg.risk)
    now = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    rm.on_tick(now, 10_000)
    rm.on_trade_closed(-50, now)
    rm.on_trade_closed(-50, now)
    assert rm.risk_pct(10_000) == pytest.approx(0.25)
    rm.on_tick(now, 10_000 * (1 - cfg.risk.max_daily_loss_pct / 100) - 1)
    assert rm.s.halted and rm.s.halt_reason.startswith("jour")
    rm.on_tick(now + timedelta(days=1), 9_740)                  # nouveau jour : reprise
    assert not rm.s.halted


def test_loss_streak_pause_and_kill_switch(cfg):
    rm = RiskManager(cfg.risk)
    now = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    rm.on_tick(now, 10_000)
    for _ in range(cfg.risk.loss_streak_pause):
        rm.on_trade_closed(-10, now)
    ok, why = rm.can_open(now, [], "XAUUSD", "gold")
    assert not ok and "pause" in why
    rm.on_tick(now + timedelta(days=2), 10_000 * (1 - cfg.risk.max_drawdown_pct / 100))
    assert rm.s.halted and rm.s.halt_reason.startswith("total")
    rm.on_tick(now + timedelta(days=3), 9_500)                  # le kill switch ne se lève pas seul
    assert rm.s.halted


# --- Gestion de position --------------------------------------------------------

def make_pos(cfg, side=1):
    tm = TradeManager(cfg.management, 0.01, 0.01)
    sig = Signal("XAUUSD", side, 2000.0, 2000.0 - side * 10, 9, "sweep", 5.0)
    return tm, tm.make_position("1", sig, 1.0, "gold", "t")


@pytest.mark.parametrize("side", [1, -1])
def test_tp1_partial_breakeven_and_trailing(cfg, side):
    tm, p = make_pos(cfg, side)
    acts = tm.on_price(p, 2000 + side * 6.5, atr=5)            # +0,65R : SL remonte à -0,5R
    assert [a.kind for a in acts] == ["move_sl"]
    p.sl = acts[0].price
    assert p.r_at(p.sl) == pytest.approx(-0.5)
    acts = tm.on_price(p, 2000 + side * 10, atr=5)             # TP1 : 50 % encaissé + SL au-dessus de l'entrée
    kinds = [a.kind for a in acts]
    assert kinds == ["partial", "move_sl"] and acts[0].volume == 0.5
    p.sl = acts[1].price
    assert p.r_at(p.sl) > 0
    acts = tm.on_price(p, 2000 + side * 22, atr=5)             # trailing ATR
    p.sl = acts[-1].price
    assert p.r_at(p.sl) == pytest.approx(1.6)
    assert tm.on_price(p, 2000 + side * 15, atr=5) == []       # le stop ne recule jamais


def test_time_exits(cfg):
    tm, p = make_pos(cfg)
    for _ in range(cfg.management.early_exit_bars - 1):
        assert tm.on_bar_close(p) == []
    assert tm.on_bar_close(p)[0].kind == "close"


# --- Stratégie : pas de données futures ---------------------------------------------

def test_no_lookahead(cfg):
    df = synthetic(6000, seed=7)
    full = prepare(df, resample(df, "1h"), cfg.strategy)
    sym = cfg.symbol("XAUUSD")
    checked = 0
    for i in range(1500, 6000, 211):
        cut = df.iloc[: i + 1]
        part = prepare(cut, resample(cut, "1h"), cfg.strategy)
        cols = ["atr", "swing_high", "swing_low", "sweep_bull", "h_bias", "h_swing_high", "vwap"]
        a, b = full[cols].iloc[i], part[cols].iloc[-1]
        for col in cols:
            assert (pd.isna(a[col]) and pd.isna(b[col])) or a[col] == pytest.approx(b[col]), col
        assert (signal_at(full, i, sym, cfg.strategy) is None) == (signal_at(part, i, sym, cfg.strategy) is None)
        checked += 1
    assert checked > 10


def test_backtest_runs_and_never_exceeds_drawdown_limit(cfg):
    df = synthetic(30_000, seed=11)
    trades, curve = bt.run(df, cfg.symbol("XAUUSD"), cfg)
    s = bt.stats(trades, curve, 10_000)
    assert s["trades"] > 20
    # le kill switch coupe avant que la perte ne dépasse largement la limite
    assert s["max_drawdown_%"] > -(cfg.risk.max_drawdown_pct + 2)
    assert all(t.r > -1.6 for t in trades)                       # aucune perte au-delà du risque prévu (+frais)


# --- Moteur complet sur un flux rejoué ---------------------------------------------

class ReplayFeed(Broker):
    """Flux de prix rejoué à partir d'un DataFrame M5 (pour tester le moteur en accéléré)."""
    name = "replay"

    def __init__(self, df):
        self.df = df
        self.t = df.index[300]
        self.spread = 0.25

    def connect(self): pass

    def _upto(self):
        return self.df[self.df.index + pd.Timedelta(minutes=5) <= self.t]

    def candles(self, symbol, tf, count):
        d = self._upto()
        return (d if tf == "5m" else resample(d, tf)).iloc[-count:]

    def spec(self, symbol): return GOLD

    def quote(self, symbol):
        px = self._upto()["close"].iloc[-1]
        return px - self.spread / 2, px + self.spread / 2

    def equity(self): return 0
    def positions(self): return []
    def open(self, *a): raise NotImplementedError
    def modify(self, *a): raise NotImplementedError
    def close(self, *a): raise NotImplementedError


def test_engine_paper_loop(cfg):
    cfg.symbols = [cfg.symbol("XAUUSD")]
    df = synthetic(9000, seed=5)
    feed = ReplayFeed(df)
    eng = Engine(cfg, broker=feed, clock=lambda: feed.t.to_pydatetime())
    eng.broker.connect()
    for _ in range(4000):
        feed.t += pd.Timedelta(minutes=5)
        eng.step()
    journal = pd.read_csv(cfg.bot.journal_file)
    assert len(journal) > 5
    assert eng.broker.balance == pytest.approx(10_000 + journal["pnl"].sum(), abs=1)
    # Le flux saute d'une bougie entière par cycle (comme un gap) : le stop peut glisser,
    # mais jamais au-delà de ~2R.
    assert (journal["r"] > -2.5).all()
    assert journal["r"].median() > -1.2
    # reprise après redémarrage : l'état est relu
    eng.save()
    eng2 = Engine(cfg, broker=feed, clock=lambda: feed.t.to_pydatetime())
    assert eng2.broker.balance == pytest.approx(eng.broker.balance)
