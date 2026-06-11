"""Market data resolver: REAL MT5 candles when connected, simulator fallback.

The decision engine must NEVER take live decisions on simulated data:
the source is always returned so callers can enforce that rule.
"""
import time
from typing import Dict, List, Any

from services.mt5_broker import mt5_connector
from services.paper_engine import market

_CACHE_TTL = 15  # seconds
_cache: Dict[str, Dict[str, Any]] = {}


async def get_ohlc(symbol: str, timeframe: str = "M15", count: int = 200) -> Dict[str, Any]:
    """Returns {"source": "mt5"|"sim", "candles": [{open,high,low,close,volume,time}]}"""
    key = f"{symbol}:{timeframe}:{count}"
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    if mt5_connector.connected:
        candles = await mt5_connector.get_candles(symbol, timeframe, count)
        if candles:
            data = {"source": "mt5", "candles": candles}
            _cache[key] = {"ts": now, "data": data}
            return data

    # Simulator fallback (demo mode): closes only, OHLC approximated
    closes = market.get_closes(symbol, count)
    candles = [{"time": None, "open": c, "high": c, "low": c, "close": c, "volume": 0} for c in closes]
    data = {"source": "sim", "candles": candles}
    _cache[key] = {"ts": now, "data": data}
    return data
