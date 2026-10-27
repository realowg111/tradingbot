"""Interface commune à tous les brokers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from ..risk import SymbolSpec


@dataclass
class BrokerPosition:
    ticket: str
    symbol: str
    side: int
    volume: float
    entry: float
    sl: float
    tp: float


class Broker(ABC):
    name = "base"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def candles(self, symbol: str, tf: str, count: int) -> pd.DataFrame:
        """Bougies CLÔTURÉES uniquement, index UTC = heure d'ouverture."""

    @abstractmethod
    def spec(self, symbol: str) -> SymbolSpec: ...

    @abstractmethod
    def quote(self, symbol: str) -> tuple[float, float]:
        """(bid, ask)"""

    @abstractmethod
    def equity(self) -> float: ...

    @abstractmethod
    def positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def open(self, symbol: str, side: int, volume: float, sl: float, tp: float, comment: str) -> tuple[str, float]:
        """Ordre au marché avec SL/TP posés côté broker. Retourne (ticket, prix d'exécution)."""

    @abstractmethod
    def modify(self, ticket: str, symbol: str, sl: float, tp: float) -> None: ...

    @abstractmethod
    def close(self, ticket: str, symbol: str, volume: float | None = None) -> float:
        """Ferme tout ou partie. Retourne le prix d'exécution."""

    def closed_pnl(self, ticket: str) -> float | None:
        """P&L réalisé d'une position fermée par le broker (SL/TP), si disponible."""
        return None

    def shutdown(self) -> None:
        pass


def drop_open_candle(df: pd.DataFrame, tf_minutes: int, now: pd.Timestamp) -> pd.DataFrame:
    """Retire la dernière bougie si elle n'est pas encore clôturée."""
    if len(df) and df.index[-1] + pd.Timedelta(minutes=tf_minutes) > now:
        return df.iloc[:-1]
    return df
