"""Market Regime Detection & Adaptive Strategy Selection.

Detects the current market regime per symbol (TREND_UP, TREND_DOWN, RANGE, VOLATILE)
from recent price action, and provides helpers to adapt strategy selection and
position sizing dynamically.

The detector works on plain closing prices, so it works equally well with the
in-memory simulator and the live MT5 feed (both expose `get_closes`).
"""
from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Tuple

logger = logging.getLogger("market_regime")

Regime = Literal["TREND_UP", "TREND_DOWN", "RANGE", "VOLATILE", "UNKNOWN"]

# Tunable thresholds
VOLATILE_STDEV_PCT = 0.040    # >4% relative volatility -> VOLATILE
TREND_SLOPE_PCT = 0.50        # |EMA slope| > 0.5% over lookback -> TREND
LOOKBACK = 50

# Multipliers / strategy preferences per regime
REGIME_RISK_MULT: Dict[str, float] = {
    "TREND_UP": 1.0,
    "TREND_DOWN": 1.0,
    "RANGE": 0.75,
    "VOLATILE": 0.5,
    "UNKNOWN": 1.0,
}

# When adaptive mode is ON, only these strategies fire per regime
REGIME_STRATEGY_FILTER: Dict[str, List[str]] = {
    "TREND_UP": ["ema_macd", "multi"],
    "TREND_DOWN": ["ema_macd", "multi"],
    "RANGE": ["bollinger", "rsi"],
    "VOLATILE": ["multi"],          # consensus only
    "UNKNOWN": ["multi"],
}


def _ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def _ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    out = [e]
    for v in values[period:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _stdev_pct(closes: List[float]) -> float:
    if not closes:
        return 0.0
    mean = sum(closes) / len(closes)
    if mean == 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in closes) / len(closes)
    return math.sqrt(var) / mean


def _slope_pct(values: List[float]) -> float:
    """Return the % slope of values from first to last (relative to mean)."""
    if len(values) < 2:
        return 0.0
    first, last = values[0], values[-1]
    mean = (first + last) / 2 if (first + last) > 0 else 1
    return ((last - first) / mean) * 100.0


def _range_pct(closes: List[float]) -> float:
    if not closes:
        return 0.0
    hi = max(closes)
    lo = min(closes)
    mean = sum(closes) / len(closes) or 1
    return ((hi - lo) / mean) * 100.0


def detect_regime(closes: List[float], lookback: int = LOOKBACK) -> Dict:
    """Detect the regime from a closing price series.

    Returns dict {regime, confidence, metrics}.
    """
    if not closes or len(closes) < max(20, lookback // 2):
        return {
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "metrics": {"reason": "insufficient_data", "n": len(closes)},
        }

    window = closes[-lookback:]
    vol_pct = _stdev_pct(window)
    rng_pct = _range_pct(window)
    ema_s = _ema_series(window, max(8, lookback // 5))
    ema_slope = _slope_pct(ema_s) if len(ema_s) >= 5 else _slope_pct(window)

    metrics = {
        "stdev_pct": round(vol_pct * 100, 4),
        "range_pct": round(rng_pct, 4),
        "ema_slope_pct": round(ema_slope, 4),
        "n": len(window),
    }

    # 1) Volatile takes precedence
    if vol_pct >= VOLATILE_STDEV_PCT:
        conf = min(1.0, vol_pct / (VOLATILE_STDEV_PCT * 2))
        return {"regime": "VOLATILE", "confidence": round(conf, 3), "metrics": metrics}

    # 2) Trend
    if abs(ema_slope) >= TREND_SLOPE_PCT:
        regime: Regime = "TREND_UP" if ema_slope > 0 else "TREND_DOWN"
        conf = min(1.0, abs(ema_slope) / (TREND_SLOPE_PCT * 3))
        return {"regime": regime, "confidence": round(conf, 3), "metrics": metrics}

    # 3) Default = RANGE
    # Confidence proportional to how flat the slope and how narrow the range
    flatness = 1.0 - min(1.0, abs(ema_slope) / TREND_SLOPE_PCT)
    return {"regime": "RANGE", "confidence": round(flatness, 3), "metrics": metrics}


def filter_strategies(regime: str, enabled: List[str]) -> List[str]:
    """Return the subset of `enabled` strategies preferred for this regime.

    Falls back to the original list if no overlap exists (so we never disable
    the bot entirely by accident).
    """
    preferred = REGIME_STRATEGY_FILTER.get(regime, [])
    if not preferred:
        return enabled
    overlap = [s for s in enabled if s in preferred]
    return overlap or enabled


def risk_multiplier(regime: str) -> float:
    return REGIME_RISK_MULT.get(regime, 1.0)


class RegimeStore:
    """In-memory cache of latest regimes per symbol. Updated by bot_runner."""

    def __init__(self):
        self._state: Dict[str, Dict] = {}

    def update(self, symbol: str, regime_dict: Dict) -> None:
        self._state[symbol] = {
            **regime_dict,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get(self, symbol: str) -> Optional[Dict]:
        return self._state.get(symbol)

    def all(self) -> Dict[str, Dict]:
        return dict(self._state)


regime_store = RegimeStore()
