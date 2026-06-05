"""Mock MT5 paper trading engine: generates ticks, executes orders with realistic fees/slippage."""
import asyncio
import random
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Symbol specs (base price, volatility, point size, fee%, slippage_max)
SYMBOL_SPECS: Dict[str, Dict] = {
    "EURUSD": {"base": 1.0850, "vol": 0.0008, "point": 0.00001, "fee_pct": 0.0002, "slip": 0.00003, "decimals": 5},
    "GBPUSD": {"base": 1.2730, "vol": 0.0010, "point": 0.00001, "fee_pct": 0.0002, "slip": 0.00004, "decimals": 5},
    "XAUUSD": {"base": 2640.00, "vol": 3.5,    "point": 0.01,    "fee_pct": 0.0003, "slip": 0.15,    "decimals": 2},
    "US100":  {"base": 21500.0, "vol": 60.0,   "point": 0.1,     "fee_pct": 0.0003, "slip": 1.5,     "decimals": 1},
    "BTCUSD": {"base": 98000.0, "vol": 400.0,  "point": 0.5,     "fee_pct": 0.0005, "slip": 12.0,    "decimals": 1},
}


class MarketSimulator:
    """In-memory price simulator with realistic random walk + occasional spikes."""

    def __init__(self):
        self.prices: Dict[str, float] = {s: spec["base"] for s, spec in SYMBOL_SPECS.items()}
        self.history: Dict[str, List[Dict]] = {s: [] for s in SYMBOL_SPECS}
        self.trend: Dict[str, float] = {s: random.uniform(-1, 1) for s in SYMBOL_SPECS}
        self.lock = asyncio.Lock()
        # Seed initial history with random walk for indicators
        for sym, spec in SYMBOL_SPECS.items():
            p = spec["base"]
            for _ in range(120):
                p += random.gauss(0, spec["vol"] * 0.5)
                p = max(p, spec["base"] * 0.5)
                self.history[sym].append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "price": round(p, spec["decimals"]),
                })
            self.prices[sym] = self.history[sym][-1]["price"]

    async def tick(self):
        """Advance prices by one tick."""
        async with self.lock:
            for sym, spec in SYMBOL_SPECS.items():
                # Mean-reverting random walk with slowly changing trend
                if random.random() < 0.02:
                    self.trend[sym] = random.uniform(-1, 1)
                drift = self.trend[sym] * spec["vol"] * 0.15
                shock = random.gauss(0, spec["vol"])
                # Occasional volatility spike
                if random.random() < 0.005:
                    shock *= 4
                new_price = self.prices[sym] + drift + shock
                # Pull back to base if drifted too far
                base = spec["base"]
                pull = (base - new_price) * 0.002
                new_price += pull
                new_price = max(new_price, base * 0.3)
                new_price = round(new_price, spec["decimals"])
                self.prices[sym] = new_price
                self.history[sym].append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "price": new_price,
                })
                # Keep last 500 ticks per symbol
                if len(self.history[sym]) > 500:
                    self.history[sym] = self.history[sym][-500:]

    def get_price(self, symbol: str) -> Optional[float]:
        return self.prices.get(symbol)

    def get_closes(self, symbol: str, n: int = 200) -> List[float]:
        h = self.history.get(symbol, [])
        return [c["price"] for c in h[-n:]]

    def execute_order(self, symbol: str, side: str, intended_price: float) -> Dict:
        """Simulate slippage + fees and return fill info."""
        spec = SYMBOL_SPECS[symbol]
        # latency-induced slippage (random within spec slip)
        slip = random.uniform(0, spec["slip"])
        if side == "BUY":
            fill = intended_price + slip
        else:
            fill = intended_price - slip
        fill = round(fill, spec["decimals"])
        fee = abs(fill) * spec["fee_pct"]
        return {"fill_price": fill, "slippage": round(abs(fill - intended_price), spec["decimals"]), "fee": round(fee, 4)}


# Singleton market
market = MarketSimulator()
