"""Telegram Copy Trader.

Takes parsed signals and:
- Validates them (risk guards, whitelist, anti-duplicate)
- Routes them to MT5 (live) or shadow mode (no execution)
- Stores everything in MongoDB collection telegram_signals
- Implements 50/50 multi-TP partial: 1st leg closes at TP1, 2nd leg is the runner
  (TP=TP2 if numeric, else far TP for trailing logic).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from database import telegram_signals_col, telegram_state_col, config_col, state_col, audit_col, positions_col
from models import utc_now, uid, BotConfig, BotState, Position
from services.mt5_broker import mt5_connector
from services.signal_parser import parse_signal
from services.ws_hub import ws_hub

logger = logging.getLogger("telegram_copy")


async def _get_state() -> Dict[str, Any]:
    """Telegram-specific state in DB: enabled, shadow_mode, channels, last seen ids."""
    doc = await telegram_state_col.find_one({}) or {}
    return {
        "enabled": doc.get("enabled", True),
        "shadow_mode": doc.get("shadow_mode", True),
        "channels": doc.get("channels", []),
        "symbols_whitelist": doc.get("symbols_whitelist", []),
        "risk_pct_override": doc.get("risk_pct_override"),
        "split_legs": bool(doc.get("split_legs", True)),
        "max_entry_drift_pct": float(doc.get("max_entry_drift_pct", 0.5)),  # 0.5% drift max from signal entry
    }


async def set_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    cur = await telegram_state_col.find_one({}) or {}
    cur.update({k: v for k, v in patch.items() if v is not None})
    if "_id" in cur:
        await telegram_state_col.replace_one({"_id": cur["_id"]}, cur)
    else:
        await telegram_state_col.insert_one(cur)
    return await _get_state()


async def _resolve_mt5_symbol(symbol_hint: str) -> Optional[str]:
    """Try to find the matching tradable MT5 symbol (suffixes vary by broker)."""
    if not symbol_hint:
        return None
    if not mt5_connector.connected:
        return symbol_hint  # best guess; will fail later if invalid
    try:
        all_syms = await mt5_connector.list_symbols()
        upper = symbol_hint.upper()
        # 1) exact match
        for s in all_syms:
            if s["name"].upper() == upper:
                return s["name"]
        # 2) startswith match (handles XAUUSD.r, XAUUSDm, XAUUSD#, etc.)
        cands = [s for s in all_syms if s["name"].upper().startswith(upper)]
        if cands:
            cands.sort(key=lambda x: len(x["name"]))
            return cands[0]["name"]
        # 3) contains
        for s in all_syms:
            if upper in s["name"].upper():
                return s["name"]
    except Exception as e:
        logger.warning("resolve_mt5_symbol error: %s", e)
    return symbol_hint


async def _log(level: str, event: str, details: dict):
    try:
        await audit_col.insert_one({
            "id": uid(),
            "ts": utc_now(),
            "level": level,
            "event": event,
            "details": details,
        })
    except Exception:
        pass


async def _broadcast(payload: dict):
    try:
        await ws_hub.broadcast({"type": "telegram_signal", "data": payload})
    except Exception:
        pass


async def _compute_volume(cfg: BotConfig, state: BotState, ref_price: float, sl: float, mt5_symbol: str, risk_mult: float) -> Optional[float]:
    if not (ref_price and sl):
        return None
    sl_distance = abs(ref_price - sl)
    if sl_distance <= 0:
        return None
    # Sizing balance: prefer live MT5 balance
    sizing_balance = state.balance
    account = await mt5_connector.get_account_info()
    if account and account.get("balance"):
        sizing_balance = account["balance"]
    allocated = sizing_balance * (cfg.risk.capital_allocation_pct / 100.0)
    risk_amount = allocated * (cfg.risk.risk_per_trade_pct / 100.0) * float(risk_mult)
    info = await mt5_connector.get_symbol_info(mt5_symbol)
    if not info or not info.get("contract_size"):
        return 0.01
    contract = info["contract_size"]
    vol_min = info.get("volume_min") or 0.01
    vol_step = info.get("volume_step") or 0.01
    vol_max = min(info.get("volume_max") or 1.0, 1.0)
    lots = risk_amount / (sl_distance * contract)
    if vol_step > 0:
        lots = max(vol_min, int(lots / vol_step) * vol_step)
    return round(min(max(lots, vol_min), vol_max), 2)


async def process_message(text: str, meta: dict) -> None:
    """Main entry: called for each new Telegram message."""
    # Anti-duplicate by (chat_id, message_id)
    chat_id = meta.get("chat_id")
    message_id = meta.get("message_id")
    if chat_id is not None and message_id is not None:
        if await telegram_signals_col.find_one({"chat_id": chat_id, "message_id": message_id}):
            return

    parsed = await parse_signal(text)

    doc = {
        "id": uid(),
        "ts": utc_now(),
        "chat_id": chat_id,
        "chat_title": meta.get("chat_title"),
        "message_id": message_id,
        "raw_text": text,
        "parsed": parsed,
        "status": "received",   # received -> parsed -> shadow|executed|rejected
        "reject_reason": None,
        "mt5_orders": [],
        "executed": False,
    }

    state_tg = await _get_state()
    if not state_tg["enabled"]:
        doc["status"] = "rejected"
        doc["reject_reason"] = "telegram_disabled"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    if not parsed["is_signal"]:
        doc["status"] = "rejected"
        doc["reject_reason"] = "not_a_signal"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Whitelist check (after normalization)
    wl = state_tg.get("symbols_whitelist") or []
    if wl and parsed["symbol"] not in [s.upper() for s in wl]:
        doc["status"] = "rejected"
        doc["reject_reason"] = f"symbol_not_in_whitelist:{parsed['symbol']}"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Shadow mode -> just store + notify, no execution
    if state_tg["shadow_mode"]:
        doc["status"] = "shadow"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        await _log("TELEGRAM", "shadow_signal", {"signal": parsed, "chat": meta.get("chat_title")})
        return

    # ---- Live execution path ----
    cfg_doc = await config_col.find_one({}) or {}
    cfg = BotConfig(**{k: v for k, v in cfg_doc.items() if k != "_id"})
    state_doc = await state_col.find_one({}) or {}
    state = BotState(**{k: v for k, v in state_doc.items() if k != "_id"})

    # Mode real + live_mt5 needed
    if not (cfg.mode == "real" and state.real_unlocked and cfg.live_mt5_trading_enabled and mt5_connector.connected):
        doc["status"] = "rejected"
        doc["reject_reason"] = "live_mt5_unavailable"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Kill switch
    if state.kill_switch:
        doc["status"] = "rejected"
        doc["reject_reason"] = "kill_switch_active"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Resolve broker symbol
    mt5_symbol = await _resolve_mt5_symbol(parsed["symbol"])
    if not mt5_symbol:
        doc["status"] = "rejected"
        doc["reject_reason"] = f"symbol_unresolved:{parsed['symbol']}"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Current price
    tick = await mt5_connector.get_price(mt5_symbol)
    if not tick:
        doc["status"] = "rejected"
        doc["reject_reason"] = "no_tick"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return
    side = parsed["side"]
    cur_price = tick["ask"] if side == "BUY" else tick["bid"]

    # Spread guard
    spread_pct = await mt5_connector.get_spread_pct(mt5_symbol)
    if spread_pct is not None and spread_pct > cfg.risk.max_spread_pct:
        doc["status"] = "rejected"
        doc["reject_reason"] = f"spread_too_wide:{round(spread_pct,4)}"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Entry drift guard (if signal had a fixed entry far from current price, skip)
    sig_entry = parsed.get("entry")
    if sig_entry and sig_entry > 0:
        drift_pct = abs(cur_price - sig_entry) / sig_entry * 100.0
        if drift_pct > state_tg["max_entry_drift_pct"]:
            doc["status"] = "rejected"
            doc["reject_reason"] = f"entry_drift:{round(drift_pct,3)}%"
            await telegram_signals_col.insert_one(doc)
            await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
            return

    sl = parsed["sl"]
    tps = parsed["tps"] or []
    # Pick TP1 + a 2nd target (TP2 if numeric, else runner = far TP based on RR)
    numeric_tps = [t for t in tps if t.get("value") is not None]
    has_runner = any(t.get("runner") for t in tps)
    tp1_val = numeric_tps[0]["value"] if numeric_tps else None
    tp2_val = None
    runner_leg = False
    if len(numeric_tps) >= 2:
        tp2_val = numeric_tps[1]["value"]
    elif has_runner and tp1_val is not None:
        # Runner: target = entry + 3x distance(tp1-entry) on signal direction
        dist = abs(tp1_val - cur_price) if tp1_val else 0
        if dist > 0:
            tp2_val = cur_price + 3 * dist if side == "BUY" else cur_price - 3 * dist
            runner_leg = True

    if tp1_val is None:
        doc["status"] = "rejected"
        doc["reject_reason"] = "no_tp_resolved"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Sanity: SL must be on the right side relative to entry/side
    if side == "BUY" and sl >= cur_price:
        doc["status"] = "rejected"
        doc["reject_reason"] = "sl_above_entry_on_buy"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return
    if side == "SELL" and sl <= cur_price:
        doc["status"] = "rejected"
        doc["reject_reason"] = "sl_below_entry_on_sell"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Compute volume (half-risk per leg if split_legs=True)
    split = state_tg["split_legs"] and tp2_val is not None
    risk_mult = 0.5 if split else 1.0
    vol_leg = await _compute_volume(cfg, state, cur_price, sl, mt5_symbol, risk_mult)
    if not vol_leg or vol_leg <= 0:
        doc["status"] = "rejected"
        doc["reject_reason"] = "volume_zero"
        await telegram_signals_col.insert_one(doc)
        await _broadcast({"id": doc["id"], "status": doc["status"], "reject_reason": doc["reject_reason"], "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title")})
        return

    # Place orders
    comment_base = f"TG-{(meta.get('chat_title') or 'RentaTrade')[:14]}"
    legs = [("TP1", tp1_val, False)]
    if split and tp2_val is not None:
        legs.append(("TP2" if not runner_leg else "RUN", tp2_val, runner_leg))

    orders_log = []
    for leg_name, leg_tp, leg_runner in legs:
        result = await mt5_connector.place_order(
            mt5_symbol, side, vol_leg, sl, leg_tp, comment=f"{comment_base} {leg_name}"
        )
        orders_log.append({"leg": leg_name, "runner": leg_runner, "tp": leg_tp, "sl": sl, "vol": vol_leg, "result": result})
        if result.get("ok"):
            # Track in positions collection for parity with bot trades
            try:
                pos = Position(
                    symbol=mt5_symbol,
                    side=side,
                    entry_price=result.get("price", cur_price),
                    quantity=vol_leg,
                    stop_loss=sl,
                    take_profit=leg_tp,
                    strategy="telegram_copy",
                    reason=f"[MT5#{result.get('ticket')}] {meta.get('chat_title')} {leg_name}",
                    mode=cfg.mode,
                )
                pdoc = pos.model_dump()
                pdoc["mt5_ticket"] = result.get("ticket")
                pdoc["source"] = "telegram_rentatrade"
                pdoc["telegram_runner"] = leg_runner
                pdoc["telegram_signal_id"] = doc["id"]
                await positions_col.insert_one(pdoc)
            except Exception:
                logger.exception("track position error")
        else:
            await _log("ERROR", "telegram_order_failed", {"symbol": mt5_symbol, "side": side, "leg": leg_name, "error": result.get("error")})

    any_ok = any(o["result"].get("ok") for o in orders_log)
    doc["executed"] = any_ok
    doc["status"] = "executed" if any_ok else "failed"
    if not any_ok:
        doc["reject_reason"] = orders_log[0]["result"].get("error") if orders_log else "all_orders_failed"
    doc["mt5_orders"] = orders_log
    doc["resolved_symbol"] = mt5_symbol
    await telegram_signals_col.insert_one(doc)
    await _broadcast({"id": doc["id"], "status": doc["status"], "executed": any_ok, "reject_reason": doc.get("reject_reason"), "parsed": parsed, "raw_text": text[:300], "chat_title": meta.get("chat_title"), "orders": [{"leg": o["leg"], "ok": o["result"].get("ok"), "ticket": o["result"].get("ticket"), "error": o["result"].get("error")} for o in orders_log]})
    await _log("TELEGRAM", "signal_executed" if any_ok else "signal_failed", {"symbol": mt5_symbol, "orders": orders_log, "signal_id": doc["id"]})
