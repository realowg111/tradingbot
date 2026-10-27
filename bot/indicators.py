"""Indicateurs techniques, tous causaux (aucune donnée future)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(df).ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP réinitialisé chaque jour (UTC). Sans volume, on pondère chaque bougie à 1."""
    vol = df["volume"] if "volume" in df and df["volume"].sum() > 0 else pd.Series(1.0, index=df.index)
    vol = vol.where(vol > 0, 1.0)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.floor("D")
    pv = (tp * vol).groupby(day).cumsum()
    v = vol.groupby(day).cumsum()
    return pv / v


def relative_volume(df: pd.DataFrame, n: int = 20) -> pd.Series:
    if "volume" not in df or df["volume"].sum() <= 0:
        return pd.Series(1.0, index=df.index)
    avg = df["volume"].rolling(n, min_periods=5).mean().shift(1)
    return (df["volume"] / avg.replace(0, np.nan)).fillna(1.0)
