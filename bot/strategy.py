"""Stratégie de scalping par confluence : biais institutionnel H1 + déclencheur M5.

Deux déclencheurs, toujours dans le sens du biais H1 :
  1. Balayage de liquidité + reprise (stop hunt sous un plus bas évident puis retour) ;
  2. Pullback de tendance sur l'EMA21 / zone de valeur avec bougie de confirmation.

Un trade n'est pris que si le score de confluence atteint min_score et que tous
les filtres de sécurité passent (spread, volatilité, session, annonces, place
jusqu'à la prochaine liquidité). Voir STRATEGIE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import indicators as ind
from . import smc
from .config import StrategyConfig, SymbolConfig

TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}


@dataclass
class Signal:
    symbol: str
    side: int               # +1 achat, -1 vente
    entry: float
    sl: float
    score: int
    setup: str
    atr: float
    reasons: list = field(default_factory=list)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)


def _htf_frame(htf: pd.DataFrame, k: int) -> pd.DataFrame:
    h = pd.DataFrame(index=htf.index)
    close = htf["close"]
    e50 = ind.ema(close, 50)
    e200 = ind.ema(close, 200)
    slope = e50 - e50.shift(5)
    bias = np.where((close > e50) & (e50 > e200) & (slope > 0), 1,
                    np.where((close < e50) & (e50 < e200) & (slope < 0), -1, 0))
    sh_ev, sl_ev = smc.confirmed_swings(htf, k)
    h["bias"] = bias
    h["struct"] = smc.structure(sh_ev, sl_ev)
    h["adx"] = ind.adx(htf)
    h["swing_high"] = sh_ev.ffill()
    h["swing_low"] = sl_ev.ffill()
    h["range_hi"] = htf["high"].rolling(48, min_periods=10).max()
    h["range_lo"] = htf["low"].rolling(48, min_periods=10).min()
    return h


def _align(ltf_index: pd.DatetimeIndex, ltf_min: int, h: pd.DataFrame, htf_min: int, prefix: str) -> pd.DataFrame:
    """Aligne le HTF sur le LTF en n'utilisant que des bougies HTF déjà clôturées."""
    left = pd.DataFrame({"key": ltf_index + timedelta(minutes=ltf_min)}, index=ltf_index)
    right = h.copy()
    right["key"] = h.index + timedelta(minutes=htf_min)
    right = right.sort_values("key")
    m = pd.merge_asof(left.reset_index(), right.reset_index(drop=True), on="key", direction="backward")
    m = m.set_index(m.columns[0]).drop(columns=["key"])
    m.index.name = None
    return m.add_prefix(prefix)


def prepare(ltf: pd.DataFrame, htf: pd.DataFrame, cfg: StrategyConfig, ltf_tf: str = "5m",
            htf_tf: str = "1h", ref_htf: pd.DataFrame | None = None) -> pd.DataFrame:
    """Calcule toutes les colonnes utiles une fois pour toutes (rapide en backtest)."""
    c = ltf.copy()
    k = cfg.swing_k
    c["atr"] = ind.atr(c)
    c["ema9"] = ind.ema(c["close"], 9)
    c["ema21"] = ind.ema(c["close"], 21)
    c["ema50"] = ind.ema(c["close"], 50)
    c["rsi"] = ind.rsi(c["close"])
    c["vwap"] = ind.session_vwap(c)
    c["rvol"] = ind.relative_volume(c)
    c["atr_rank"] = c["atr"].rolling(200, min_periods=50).rank(pct=True)

    sh_ev, sl_ev = smc.confirmed_swings(c, k)
    c["swing_high"] = sh_ev.ffill()
    c["swing_low"] = sl_ev.ffill()
    pdh, pdl = smc.daily_levels(c)
    ah, al = smc.asian_range(c)
    sb, ss = smc.sweeps(c, [c["swing_low"], pdl, al], [c["swing_high"], pdh, ah])
    lb = cfg.sweep_lookback
    c["sweep_bull"] = sb.astype(int).rolling(lb, min_periods=1).max().astype(bool)
    c["sweep_bear"] = ss.astype(int).rolling(lb, min_periods=1).max().astype(bool)
    c["sweep_low"] = c["low"].rolling(lb, min_periods=1).min()
    c["sweep_high"] = c["high"].rolling(lb, min_periods=1).max()
    fb, fs = smc.fvg(c)
    c["fvg_bull"] = fb.astype(int).rolling(10, min_periods=1).max().astype(bool)
    c["fvg_bear"] = fs.astype(int).rolling(10, min_periods=1).max().astype(bool)
    db, ds = smc.displacement(c, c["atr"])
    c["disp_bull"] = db.astype(int).rolling(6, min_periods=1).max().astype(bool)
    c["disp_bear"] = ds.astype(int).rolling(6, min_periods=1).max().astype(bool)
    c["low5"] = c["low"].rolling(6, min_periods=1).min()
    c["high5"] = c["high"].rolling(6, min_periods=1).max()
    c["low3"] = c["low"].rolling(4, min_periods=1).min()
    c["high3"] = c["high"].rolling(4, min_periods=1).max()
    c["rsi_min5"] = c["rsi"].rolling(6, min_periods=1).min()
    c["rsi_max5"] = c["rsi"].rolling(6, min_periods=1).max()
    c["prev_high"] = c["high"].shift(1)
    c["prev_low"] = c["low"].shift(1)

    lm, hm = TF_MINUTES[ltf_tf], TF_MINUTES[htf_tf]
    c = c.join(_align(c.index, lm, _htf_frame(htf, k), hm, "h_"))
    if ref_htf is not None and len(ref_htf) > 0:
        c = c.join(_align(c.index, lm, _htf_frame(ref_htf, k)[["bias"]], hm, "ref_"))
    else:
        c["ref_bias"] = np.nan
    return c


def _in_sessions(ts: datetime, sym: SymbolConfig) -> bool:
    h = ts.hour + ts.minute / 60
    if sym.no_new_trades_friday_after is not None and ts.weekday() == 4 and h >= sym.no_new_trades_friday_after:
        return False
    if ts.weekday() == 5 and sym.group == "gold":
        return False
    return any(a <= h < b for a, b in sym.sessions)


def _in_news(ts: datetime, cfg: StrategyConfig) -> bool:
    for item in cfg.news_blackout:
        t = pd.Timestamp(item, tz="UTC")
        if abs((pd.Timestamp(ts) - t).total_seconds()) <= cfg.news_blackout_minutes * 60:
            return True
    return False


def _in_killzone(ts: datetime) -> bool:
    """London open 7h-10h UTC et New York 12h-16h UTC : là où les institutions agissent."""
    return 7 <= ts.hour < 10 or 12 <= ts.hour < 16


def signal_at(c: pd.DataFrame, i: int, sym: SymbolConfig, cfg: StrategyConfig,
              spread: float | None = None, ts: datetime | None = None) -> Signal | None:
    """Évalue la bougie clôturée i. Retourne un Signal ou None."""
    if i < 210:
        return None
    r = c.iloc[i]
    ts = ts or (c.index[i] + timedelta(minutes=5)).to_pydatetime()
    a = r["atr"]
    if not np.isfinite(a) or a <= 0 or np.isnan(r["h_bias"]):
        return None

    # --- Filtres de sécurité (veto) ---
    spread = sym.spread if spread is None else spread
    if spread > cfg.max_spread_atr * a:
        return None
    if not (0.15 <= (r["atr_rank"] if np.isfinite(r["atr_rank"]) else 0.5) <= 0.97):
        return None  # marché mort ou en panique
    if not _in_sessions(ts, sym) or _in_news(ts, cfg):
        return None
    side = int(r["h_bias"])
    if side == 0:
        return None  # pas de biais clair : on ne force rien
    if np.isfinite(r["ref_bias"]) and sym.ref and r["ref_bias"] * sym.ref.get("sign", 1) == -side:
        return None  # l'actif directeur va dans l'autre sens

    long = side == 1
    close, open_ = r["close"], r["open"]
    confirm = (close > r["prev_high"] and close > open_) if long else (close < r["prev_low"] and close < open_)
    if not confirm:
        return None

    # --- Déclencheurs ---
    setup, sl = None, None
    buf = cfg.sl_buffer_atr * a
    if (r["sweep_bull"] if long else r["sweep_bear"]):
        setup = "sweep"
        sl = r["sweep_low"] - buf if long else r["sweep_high"] + buf
    else:
        stacked = (r["ema9"] > r["ema21"] > r["ema50"]) if long else (r["ema9"] < r["ema21"] < r["ema50"])
        touched = (r["low3"] <= r["ema21"] + 0.25 * a) if long else (r["high3"] >= r["ema21"] - 0.25 * a)
        held = close > r["ema50"] if long else close < r["ema50"]
        rsi_reset = (35 <= r["rsi_min5"] <= 52) if long else (48 <= r["rsi_max5"] <= 65)
        if stacked and touched and held and rsi_reset:
            setup = "pullback"
            sl = r["low5"] - buf if long else r["high5"] + buf
    if setup is None:
        return None

    entry = close
    dist = abs(entry - sl)
    if dist < cfg.min_sl_atr * a:
        dist = cfg.min_sl_atr * a
        sl = entry - dist if long else entry + dist
    if dist > cfg.max_sl_atr * a:
        return None

    # Place avant la prochaine liquidité HTF (on ne vise pas dans un mur)
    target_lv = r["h_swing_high"] if long else r["h_swing_low"]
    if np.isfinite(target_lv):
        room = (target_lv - entry) if long else (entry - target_lv)
        if 0 < room < cfg.min_room_r * dist:
            return None

    # --- Score de confluence (sur 14) ---
    score, why = 2, ["biais H1 (EMA50/200 + pente)"]
    if r["h_struct"] == side:
        score += 1; why.append("structure H1 HH/HL" if long else "structure H1 LH/LL")
    if setup == "sweep":
        score += 2; why.append("balayage de liquidité")
    else:
        score += 1; why.append("pullback EMA21")
    if (close > r["vwap"]) if long else (close < r["vwap"]):
        score += 1; why.append("bon côté du VWAP")
    if _in_killzone(ts):
        score += 1; why.append("killzone London/NY")
    if r["fvg_bull"] if long else r["fvg_bear"]:
        score += 1; why.append("fair value gap")
    if r["disp_bull"] if long else r["disp_bear"]:
        score += 1; why.append("bougie de déplacement")
    if (40 <= r["rsi"] <= 68) if long else (32 <= r["rsi"] <= 60):
        score += 1; why.append("RSI non extrême")
    if r["h_adx"] >= 20:
        score += 1; why.append("ADX H1 >= 20")
    if np.isfinite(r["ref_bias"]) and sym.ref and r["ref_bias"] * sym.ref.get("sign", 1) == side:
        score += 1; why.append(f"inter-marché {sym.ref.get('name')} aligné")
    if r["rvol"] >= 1.5:
        score += 1; why.append("volume relatif élevé")
    lo, hi = r["h_range_lo"], r["h_range_hi"]
    if np.isfinite(lo) and hi > lo:
        pos = (entry - lo) / (hi - lo)
        if (pos <= 0.5) if long else (pos >= 0.5):
            score += 1; why.append("zone discount" if long else "zone premium")

    if score < cfg.min_score:
        return None
    return Signal(sym.name, side, float(entry), float(sl), int(score), setup, float(a), why)
