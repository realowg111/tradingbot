"""Live account resolver: single source of truth for account data.

When mode=real AND MT5 is connected, all account data (balance, equity,
margin, positions, trade history, stats) comes from MT5.
Otherwise the internal paper simulator is used.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from services.mt5_broker import mt5_connector

logger = logging.getLogger("live_account")


def is_live(cfg) -> bool:
    """True when the real MT5 account is the source of truth."""
    return cfg.mode == "real" and mt5_connector.connected


async def resolve_state(cfg, state) -> Dict[str, Any]:
    """Build the state payload for the frontend.

    In live mode the balance/equity/margin come straight from MT5.
    The sim fields (kill_switch, paused_reason, trades_today...) are kept.
    """
    data = state.model_dump()
    data["source"] = "sim"
    data["margin"] = 0.0
    data["free_margin"] = data["balance"]
    data["account_currency"] = "USD"
    data["leverage"] = None

    if not is_live(cfg):
        return data

    account = await mt5_connector.get_account_info()
    if not account:
        data["source"] = "mt5_stale"
        return data

    floating = account.get("profit", 0.0) or 0.0
    data.update({
        "source": "mt5",
        "balance": account["balance"],
        "equity": account["equity"],
        "margin": account.get("margin", 0.0),
        "free_margin": account.get("free_margin", 0.0),
        "unrealized_pnl": round(floating, 2),
        "account_currency": account.get("currency", "USD"),
        "leverage": account.get("leverage"),
    })

    # Daily P&L = today's closed deals + floating P&L (cached 10s to avoid
    # hammering MT5 history from the 1s broadcast loop)
    try:
        import time as _time
        now_ts = _time.time()
        if _daily_cache["ts"] and now_ts - _daily_cache["ts"] < 10:
            realized_today = _daily_cache["realized"]
        else:
            trades = await mt5_trades(days=2)
            today = datetime.now(timezone.utc).date()
            realized_today = sum(
                t["pnl"] for t in trades
                if _to_dt(t.get("closed_at")) and _to_dt(t["closed_at"]).date() == today
            )
            _daily_cache["ts"] = now_ts
            _daily_cache["realized"] = realized_today
        data["daily_pnl"] = round(realized_today + floating, 2)
        data["realized_pnl"] = round(realized_today, 2)
        # Accurate daily reference: balance at start of day = balance - realized today
        data["daily_start_balance"] = round(account["balance"] - realized_today, 2)
    except Exception as e:
        logger.warning("daily pnl mt5 error: %s", e)
    return data


_daily_cache: Dict[str, Any] = {"ts": 0, "realized": 0.0}


async def live_positions() -> List[Dict[str, Any]]:
    """MT5 open positions mapped to the app Position shape (incl. manual trades)."""
    raw = await mt5_connector.get_positions()
    out = []
    for p in raw:
        comment = (p.get("comment") or "").strip()
        is_bot = comment.lower().startswith("bot")
        out.append({
            "id": str(p["ticket"]),
            "mt5_ticket": p["ticket"],
            "symbol": p["symbol"],
            "side": p["side"],
            "entry_price": p["entry_price"],
            "current_price": p.get("current_price"),
            "quantity": p["volume"],
            "stop_loss": p.get("stop_loss", 0.0),
            "take_profit": p.get("take_profit", 0.0),
            "unrealized_pnl": round((p.get("pnl") or 0.0) + (p.get("swap") or 0.0), 2),
            "strategy": comment[4:].strip() if is_bot else (comment or "Manuel"),
            "origin": "bot" if is_bot else "manual",
            "reason": comment,
            "opened_at": p.get("opened_at"),
            "status": "OPEN",
            "mode": "real",
            "source": "mt5",
        })
    return out


async def mt5_trades(days: int = 90) -> List[Dict[str, Any]]:
    """Build closed-trade records from MT5 deal history (grouped by position).

    Includes ALL account activity (bot + manual), per user preference.
    """
    deals = await mt5_connector.get_history_deals(days=days)
    if not deals:
        return []

    by_pos: Dict[int, Dict[str, List]] = {}
    for d in deals:
        # entry: 0=IN, 1=OUT, 2=INOUT (reversal), 3=OUT_BY
        pid = d.get("position_id") or 0
        if pid == 0:
            continue
        grp = by_pos.setdefault(pid, {"in": [], "out": []})
        if d.get("entry") == 0:
            grp["in"].append(d)
        elif d.get("entry") in (1, 2, 3):
            grp["out"].append(d)

    trades: List[Dict[str, Any]] = []
    for pid, grp in by_pos.items():
        if not grp["out"]:
            continue  # still open
        ins, outs = grp["in"], grp["out"]
        pnl = sum((o.get("profit") or 0) + (o.get("commission") or 0) + (o.get("swap") or 0) for o in outs)
        pnl += sum((i.get("commission") or 0) for i in ins)
        volume = sum(o.get("volume") or 0 for o in outs)
        entry_price = ins[0]["price"] if ins else 0.0
        exit_price = outs[-1]["price"]
        opened_at = ins[0]["time"] if ins else outs[0]["time"]
        closed_at = outs[-1]["time"]
        # deal type on the IN leg: 0=BUY, 1=SELL
        side = "BUY" if (ins and ins[0].get("type") == 0) else "SELL"
        comment = (outs[-1].get("comment") or "").lower()
        if "sl" in comment:
            close_reason = "stop_loss"
        elif "tp" in comment:
            close_reason = "take_profit"
        else:
            close_reason = "close"
        in_comment = (ins[0].get("comment") or "").strip() if ins else ""
        is_bot = in_comment.lower().startswith("bot")
        notional = entry_price * volume if entry_price and volume else 0
        trades.append({
            "id": str(pid),
            "symbol": outs[-1].get("symbol", ""),
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": volume,
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / notional) * 100, 4) if notional else 0.0,
            "fees": round(abs(sum((d.get("commission") or 0) for d in ins + outs)), 2),
            "slippage": 0.0,
            "strategy": in_comment[4:].strip() if is_bot else (in_comment or "Manuel"),
            "origin": "bot" if is_bot else "manual",
            "open_reason": in_comment,
            "close_reason": close_reason,
            "opened_at": opened_at,
            "closed_at": closed_at,
            "duration_sec": _duration(opened_at, closed_at),
            "mode": "real",
            "source": "mt5",
        })
    trades.sort(key=lambda t: str(t["closed_at"]), reverse=True)
    return trades


def period_pnl(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    """P&L for today / last 7 days / last 30 days from closed trades."""
    now = datetime.now(timezone.utc)
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    p_today = p_week = p_month = 0.0
    for t in trades:
        dt = _to_dt(t.get("closed_at"))
        if not dt:
            continue
        pnl = t.get("pnl", 0.0)
        if dt.date() == today:
            p_today += pnl
        if dt >= week_ago:
            p_week += pnl
        if dt >= month_ago:
            p_month += pnl
    return {
        "pnl_today": round(p_today, 2),
        "pnl_week": round(p_week, 2),
        "pnl_month": round(p_month, 2),
    }


def _to_dt(v) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _duration(a, b) -> float:
    da, db = _to_dt(a), _to_dt(b)
    if da and db:
        return (db - da).total_seconds()
    return 0.0
