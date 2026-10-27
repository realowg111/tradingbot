"""Lecture "institutionnelle" du prix (Smart Money Concepts), sans données futures.

- swings confirmés (fractales) : un plus haut à l'indice i n'est connu qu'à i + k ;
- structure de marché : plus hauts / plus bas croissants ou décroissants ;
- balayages de liquidité : mèche au-delà d'un niveau évident puis clôture de retour ;
- fair value gaps (déséquilibres) et bougies de déplacement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def confirmed_swings(df: pd.DataFrame, k: int) -> tuple[pd.Series, pd.Series]:
    """Swings haut / bas (événements), datés à la bougie où ils deviennent connus (i + k)."""
    win = 2 * k + 1
    is_high = df["high"] == df["high"].rolling(win, center=True).max()
    is_low = df["low"] == df["low"].rolling(win, center=True).min()
    sh = df["high"].where(is_high).shift(k)
    sl = df["low"].where(is_low).shift(k)
    return sh, sl


def structure(swing_high_events: pd.Series, swing_low_events: pd.Series) -> pd.Series:
    """+1 si les deux derniers swings montent (HH + HL), -1 s'ils baissent, 0 sinon."""
    hi = swing_high_events.to_numpy()
    lo = swing_low_events.to_numpy()
    out = np.zeros(len(hi))
    last_h = prev_h = last_l = prev_l = np.nan
    for i in range(len(hi)):
        if not np.isnan(hi[i]):
            prev_h, last_h = last_h, hi[i]
        if not np.isnan(lo[i]):
            prev_l, last_l = last_l, lo[i]
        if np.isnan(prev_h) or np.isnan(prev_l):
            continue
        if last_h > prev_h and last_l > prev_l:
            out[i] = 1
        elif last_h < prev_h and last_l < prev_l:
            out[i] = -1
    return pd.Series(out, index=swing_high_events.index)


def fvg(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Fair value gaps haussiers / baissiers formés à la bougie i (trou entre i-2 et i)."""
    bull = df["low"] > df["high"].shift(2)
    bear = df["high"] < df["low"].shift(2)
    return bull.fillna(False), bear.fillna(False)


def displacement(df: pd.DataFrame, atr: pd.Series, mult: float = 1.3) -> tuple[pd.Series, pd.Series]:
    """Grande bougie impulsive qui clôture près de son extrême : trace d'ordres institutionnels."""
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    strong = body > mult * atr
    bull = strong & (df["close"] > df["open"]) & ((df["high"] - df["close"]) / rng < 0.25)
    bear = strong & (df["close"] < df["open"]) & ((df["close"] - df["low"]) / rng < 0.25)
    return bull.fillna(False), bear.fillna(False)


def sweeps(df: pd.DataFrame, levels_low: list[pd.Series], levels_high: list[pd.Series]):
    """Balayage haussier : la mèche passe sous un niveau de liquidité et la bougie clôture au-dessus."""
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    for lv in levels_low:
        lv = lv.shift(1)  # niveau connu avant la bougie
        bull |= (df["low"] < lv) & (df["close"] > lv)
    for lv in levels_high:
        lv = lv.shift(1)
        bear |= (df["high"] > lv) & (df["close"] < lv)
    return bull.fillna(False), bear.fillna(False)


def daily_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Plus haut / plus bas de la veille (UTC), alignés sur chaque bougie."""
    day = df.index.floor("D")
    g = df.groupby(day).agg(high=("high", "max"), low=("low", "min"))
    prev = g.shift(1)
    return prev["high"].reindex(day).set_axis(df.index), prev["low"].reindex(day).set_axis(df.index)


def asian_range(df: pd.DataFrame, start: int = 0, end: int = 6) -> tuple[pd.Series, pd.Series]:
    """Range de la session asiatique du jour, disponible seulement après sa clôture."""
    day = df.index.floor("D")
    h = df.index.hour
    in_asia = (h >= start) & (h < end)
    sub = df[in_asia]
    g = sub.groupby(sub.index.floor("D")).agg(high=("high", "max"), low=("low", "min"))
    hi = g["high"].reindex(day).set_axis(df.index)
    lo = g["low"].reindex(day).set_axis(df.index)
    after = h >= end
    return hi.where(after), lo.where(after)
