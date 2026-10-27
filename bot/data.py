"""Chargement, rééchantillonnage et génération de données OHLCV."""
from __future__ import annotations

import numpy as np
import pandas as pd

PANDAS_RULE = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1D"}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Index datetime UTC (ouverture de bougie), colonnes open/high/low/close/volume."""
    df = df.rename(columns=str.lower)
    if "tick_volume" in df and "volume" not in df:
        df = df.rename(columns={"tick_volume": "volume"})
    if "volume" not in df:
        df["volume"] = 0.0
    if not isinstance(df.index, pd.DatetimeIndex):
        col = "time" if "time" in df else df.columns[0]
        t = df[col]
        if np.issubdtype(t.dtype, np.number):
            unit = "ms" if t.iloc[0] > 1e11 else "s"
            idx = pd.to_datetime(t, unit=unit, utc=True)
        else:
            idx = pd.to_datetime(t, utc=True)
        df = df.set_index(idx).drop(columns=[col])
    elif df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def load_csv(path: str) -> pd.DataFrame:
    return normalize(pd.read_csv(path))


def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    out = df.resample(PANDAS_RULE[tf], label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open"])


def synthetic(n: int = 60_000, start: float = 2000.0, seed: int = 1, tf_minutes: int = 5,
              vol: float = 0.0012) -> pd.DataFrame:
    """Prix simulé avec régimes de tendance et sessions (pour tester la mécanique, pas la rentabilité)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq=f"{tf_minutes}min", tz="UTC")
    hours = idx.hour.to_numpy()
    sess = np.where((hours >= 7) & (hours < 16), 1.6, 0.7)
    regime = np.zeros(n)
    drift = 0.0
    for i in range(n):
        if i % 600 == 0:
            drift = rng.choice([-1, 0, 1]) * vol * 0.06
        regime[i] = drift
    rets = regime + rng.standard_t(4, n) * vol * sess / np.sqrt(2)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.r_[start, close[:-1]]
    span = np.abs(rng.normal(0, vol * 0.6, n)) * close * sess
    high = np.maximum(open_, close) + span * rng.random(n)
    low = np.minimum(open_, close) - span * rng.random(n)
    volume = (rng.lognormal(3, 0.5, n) * sess).round()
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)
