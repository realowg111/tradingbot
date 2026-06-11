"""Tests for the multi-factor decision engine."""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import decision_engine  # noqa: E402
from models import BotConfig  # noqa: E402


def make_candles(closes, spread=0.0):
    return [{"time": None, "open": c, "high": c * 1.0005, "low": c * 0.9995, "close": c, "volume": 10} for c in closes]


def run_eval(m15_closes, h1_closes=None, cfg=None):
    cfg = cfg or BotConfig()

    async def fake_ohlc(symbol, timeframe="M15", count=200):
        if timeframe == "H1":
            return {"source": "sim", "candles": make_candles(h1_closes or m15_closes)}
        return {"source": "sim", "candles": make_candles(m15_closes)}

    import services.market_data as md
    orig = md.get_ohlc
    md.get_ohlc = fake_ohlc
    try:
        return asyncio.run(decision_engine.evaluate_symbol("TESTUSD", cfg))
    finally:
        md.get_ohlc = orig


class TestDecisionEngine:
    def test_insufficient_data(self):
        r = run_eval([1.0] * 10)
        assert r["decision"] == "NO_SIGNAL"
        assert r["score"] == 0

    def test_uptrend_generates_buy_side(self):
        closes = [1.0 + i * 0.001 for i in range(120)]  # steady uptrend
        r = run_eval(closes)
        assert r["side"] == "BUY"
        assert r["score"] > 0
        assert len(r["factors"]) == 6
        # trend factor must be max (M15 + H1 aligned)
        trend = next(f for f in r["factors"] if f["name"] == "Tendance")
        assert trend["points"] == 25

    def test_downtrend_generates_sell_side(self):
        closes = [2.0 - i * 0.001 for i in range(120)]
        r = run_eval(closes)
        assert r["side"] == "SELL"

    def test_flat_market_no_signal(self):
        closes = [1.0] * 120
        r = run_eval(closes)
        assert r["side"] is None
        assert r["decision"] == "NO_SIGNAL"

    def test_threshold_respected(self):
        closes = [1.0 + i * 0.001 for i in range(120)]
        cfg = BotConfig()
        cfg.min_confidence_score = 99  # impossible threshold
        r = run_eval(closes, cfg=cfg)
        assert r["decision"] in ("REJECT", "NO_SIGNAL")

    def test_factors_have_french_details(self):
        closes = [1.0 + i * 0.001 for i in range(120)]
        r = run_eval(closes)
        for f in r["factors"]:
            assert f["detail"], f"factor {f['name']} sans explication"
            assert "max" in f and "points" in f


class TestEffectiveSymbols:
    def test_normal_mode(self):
        cfg = BotConfig()
        cfg.symbols = ["EURUSD", "XAUUSD"]
        cfg.single_symbol_mode = False
        assert decision_engine.effective_symbols(cfg) == ["EURUSD", "XAUUSD"]

    def test_single_mode(self):
        cfg = BotConfig()
        cfg.symbols = ["EURUSD", "XAUUSD"]
        cfg.single_symbol_mode = True
        cfg.single_symbol = "BTCUSD"
        assert decision_engine.effective_symbols(cfg) == ["BTCUSD"]


class TestCategorize:
    def test_categories(self):
        from services.mt5_broker import categorize_symbol
        assert categorize_symbol("Forex\\Majors", "EURUSD") == "forex"
        assert categorize_symbol("", "GBPJPY") == "forex"
        assert categorize_symbol("Crypto", "BTCUSD") == "crypto"
        assert categorize_symbol("", "XAUUSD") == "metaux"
        assert categorize_symbol("Indexes", "US100") == "indices"
        assert categorize_symbol("", "USOIL") == "energie"
