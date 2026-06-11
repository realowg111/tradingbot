"""Regression tests for live_account MT5 deal aggregation and period stats."""
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.live_account import period_pnl, _to_dt, _duration  # noqa: E402


def iso(dt):
    return dt.isoformat()


NOW = datetime.now(timezone.utc)


def make_trade(pnl, closed_at):
    return {"pnl": pnl, "closed_at": iso(closed_at)}


class TestPeriodPnl:
    def test_today_week_month(self):
        trades = [
            make_trade(10.0, NOW - timedelta(minutes=1)),      # today
            make_trade(-5.0, NOW - timedelta(days=3)),         # week
            make_trade(20.0, NOW - timedelta(days=15)),        # month
            make_trade(100.0, NOW - timedelta(days=60)),       # outside
        ]
        r = period_pnl(trades)
        assert r["pnl_today"] == 10.0
        assert r["pnl_week"] == 5.0
        assert r["pnl_month"] == 25.0

    def test_empty(self):
        r = period_pnl([])
        assert r == {"pnl_today": 0.0, "pnl_week": 0.0, "pnl_month": 0.0}

    def test_invalid_dates_ignored(self):
        r = period_pnl([{"pnl": 5.0, "closed_at": "garbage"}, {"pnl": 3.0, "closed_at": None}])
        assert r["pnl_month"] == 0.0


class TestHelpers:
    def test_to_dt_iso(self):
        d = _to_dt("2026-02-01T10:00:00+00:00")
        assert d.year == 2026 and d.tzinfo is not None

    def test_to_dt_naive_gets_utc(self):
        d = _to_dt("2026-02-01T10:00:00")
        assert d.tzinfo is not None

    def test_duration(self):
        a = "2026-02-01T10:00:00+00:00"
        b = "2026-02-01T11:30:00+00:00"
        assert _duration(a, b) == 5400.0


class TestMt5TradeAggregation:
    """Test the deal grouping logic by monkeypatching the connector."""

    def test_grouping(self, monkeypatch):
        import asyncio
        import services.live_account as la

        deals = [
            # Position 111: BUY in, closed with TP
            {"position_id": 111, "entry": 0, "type": 0, "symbol": "EURUSD", "price": 1.1000,
             "volume": 0.1, "profit": 0, "commission": -0.5, "swap": 0,
             "time": iso(NOW - timedelta(hours=2)), "comment": "bot RSI"},
            {"position_id": 111, "entry": 1, "type": 1, "symbol": "EURUSD", "price": 1.1050,
             "volume": 0.1, "profit": 50.0, "commission": -0.5, "swap": -0.1,
             "time": iso(NOW - timedelta(hours=1)), "comment": "tp 1.1050"},
            # Position 222: still open (only IN deal)
            {"position_id": 222, "entry": 0, "type": 1, "symbol": "XAUUSD", "price": 2600.0,
             "volume": 0.01, "profit": 0, "commission": 0, "swap": 0,
             "time": iso(NOW), "comment": ""},
            # Balance operation (position_id 0) must be ignored
            {"position_id": 0, "entry": 0, "type": 2, "symbol": "", "price": 0,
             "volume": 0, "profit": 500.0, "commission": 0, "swap": 0,
             "time": iso(NOW - timedelta(days=5)), "comment": "deposit"},
        ]

        async def fake_history(days=90):
            return deals

        monkeypatch.setattr(la.mt5_connector, "get_history_deals", fake_history)
        trades = asyncio.run(la.mt5_trades(days=90))

        assert len(trades) == 1  # only position 111 is closed
        t = trades[0]
        assert t["id"] == "111"
        assert t["side"] == "BUY"
        assert t["pnl"] == round(50.0 - 0.5 - 0.1 - 0.5, 2)  # profit + swap + both commissions
        assert t["close_reason"] == "take_profit"
        assert t["origin"] == "bot"
        assert t["strategy"] == "RSI"
        assert t["source"] == "mt5"

    def test_manual_trade_origin(self, monkeypatch):
        import asyncio
        import services.live_account as la

        deals = [
            {"position_id": 333, "entry": 0, "type": 1, "symbol": "BTCUSD", "price": 98000.0,
             "volume": 0.01, "profit": 0, "commission": 0, "swap": 0,
             "time": iso(NOW - timedelta(hours=3)), "comment": ""},
            {"position_id": 333, "entry": 1, "type": 0, "symbol": "BTCUSD", "price": 97500.0,
             "volume": 0.01, "profit": 5.0, "commission": 0, "swap": 0,
             "time": iso(NOW - timedelta(hours=2)), "comment": "sl 97500"},
        ]

        async def fake_history(days=90):
            return deals

        monkeypatch.setattr(la.mt5_connector, "get_history_deals", fake_history)
        trades = asyncio.run(la.mt5_trades(days=90))
        assert len(trades) == 1
        assert trades[0]["origin"] == "manual"
        assert trades[0]["side"] == "SELL"
        assert trades[0]["close_reason"] == "stop_loss"
