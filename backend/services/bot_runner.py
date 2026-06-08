"""Background bot loop: ticks the market, runs strategies, manages positions/risk."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from database import (
    positions_col,
    trades_col,
    audit_col,
    config_col,
    state_col,
)
from models import BotConfig, BotState, Position, Trade, AuditLog, utc_now
from services.paper_engine import market, SYMBOL_SPECS
from services.strategies import STRATEGIES, detect_volatility

logger = logging.getLogger("bot_runner")


class BotRunner:
    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.running = False
        self.tick_interval = 2.0  # seconds between simulator ticks

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("BotRunner loop started")

    async def stop(self):
        self.running = False
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=3)
            except asyncio.TimeoutError:
                self.task.cancel()
            self.task = None

    async def _loop(self):
        while self.running:
            try:
                await self._step()
            except Exception as e:
                logger.exception("Loop error: %s", e)
                await self._log("ERROR", "loop_error", {"error": str(e)})
            await asyncio.sleep(self.tick_interval)

    async def _step(self):
        await market.tick()

        cfg = await self._get_config()
        state = await self._get_state()

        # Daily reset (mutates state in-place)
        await self._daily_reset(state)

        # Manage open positions: check SL/TP (mutates state in-place)
        await self._manage_positions(cfg, state)

        # Skip new trades if bot disabled or paused or kill switch
        if not cfg.enabled or state.kill_switch_engaged:
            await self._update_state(state)
            return

        # Daily drawdown check
        dd_pct = ((state.daily_start_balance - state.equity) / state.daily_start_balance) * 100 if state.daily_start_balance > 0 else 0
        if dd_pct >= cfg.risk.daily_drawdown_limit_pct:
            if state.paused_reason != "daily_drawdown":
                await self._log("RISK", "daily_drawdown_hit", {"dd_pct": dd_pct})
                state.paused_reason = "daily_drawdown"
            await self._update_state(state)
            return

        # Max trades per day
        if state.trades_today >= cfg.risk.max_trades_per_day:
            state.paused_reason = "max_trades_per_day"
            await self._update_state(state)
            return

        # Real mode requires unlock
        if cfg.mode == "real" and not state.real_unlocked:
            state.paused_reason = "real_mode_not_unlocked"
            await self._update_state(state)
            return

        state.paused_reason = None

        # Run strategies per symbol (state is mutated in-place by _open_position)
        for symbol in cfg.symbols:
            # Re-check max open positions inside loop (since we may open more)
            open_count = await positions_col.count_documents({"status": "OPEN", "mode": cfg.mode})
            if open_count >= cfg.risk.max_open_positions:
                break
            # Skip if we already have a position open on this symbol & mode
            existing = await positions_col.find_one({"symbol": symbol, "status": "OPEN", "mode": cfg.mode})
            if existing:
                continue

            closes = market.get_closes(symbol, 200)
            if len(closes) < 30:
                continue

            # Volatility filter
            vol = detect_volatility(closes)
            spec = SYMBOL_SPECS.get(symbol, {})
            # Pause on extreme volatility (relative > 0.05 = 5%)
            if cfg.risk.volatility_pause and vol > 0.05:
                await self._log("RISK", "volatility_pause", {"symbol": symbol, "vol": vol})
                continue

            # Aggregate signals from enabled strategies
            enabled = cfg.strategy.enabled or ["multi"]
            signals = []
            for strat_id in enabled:
                strat = STRATEGIES.get(strat_id)
                if not strat:
                    continue
                sig, reason = strat["fn"](closes, cfg.strategy)
                if sig:
                    signals.append((strat_id, sig, reason))

            if not signals:
                continue

            # Vote
            buy_votes = sum(1 for _, s, _ in signals if s == "BUY")
            sell_votes = sum(1 for _, s, _ in signals if s == "SELL")
            if buy_votes == 0 and sell_votes == 0:
                continue
            if buy_votes == sell_votes:
                continue
            side = "BUY" if buy_votes > sell_votes else "SELL"
            chosen = [(sid, r) for sid, s, r in signals if s == side]
            strat_used = ",".join(sid for sid, _ in chosen)
            reason = " | ".join(r for _, r in chosen)

            # Open position (mutates state in-place: balance fee, trades_today)
            await self._open_position(cfg, state, symbol, side, strat_used, reason)

        await self._update_state(state)

    async def _open_position(self, cfg: BotConfig, state: BotState, symbol: str, side: str, strategy: str, reason: str):
        price = market.get_price(symbol)
        if price is None:
            return
        # Position sizing: risk_per_trade_pct of allocated capital
        allocated = state.balance * (cfg.risk.capital_allocation_pct / 100.0)
        risk_amount = allocated * (cfg.risk.risk_per_trade_pct / 100.0)
        # Stop loss distance as % of price
        sl_distance = price * (cfg.risk.stop_loss_pct / 100.0)
        if sl_distance <= 0:
            return
        quantity = risk_amount / sl_distance
        if quantity <= 0:
            return

        # Determine if we route to MT5 live trading or simulator
        live_mt5 = (
            cfg.mode == "real"
            and state.real_unlocked
            and cfg.live_mt5_trading_enabled
            and mt5_connector.connected
        )

        if live_mt5:
            # Pull current MT5 price for accurate SL/TP
            mt5_tick = await mt5_connector.get_price(symbol)
            if mt5_tick:
                ref_price = mt5_tick["ask"] if side == "BUY" else mt5_tick["bid"]
            else:
                ref_price = price
            if side == "BUY":
                sl = round(ref_price - sl_distance, 6)
                tp = round(ref_price + (sl_distance * cfg.risk.risk_reward_ratio), 6)
            else:
                sl = round(ref_price + sl_distance, 6)
                tp = round(ref_price - (sl_distance * cfg.risk.risk_reward_ratio), 6)
            # Volume in lots (MT5) — convert quantity heuristically (cap to broker min)
            volume_lots = max(0.01, round(quantity / 100000, 2))
            result = await mt5_connector.place_order(symbol, side, volume_lots, sl, tp, comment=f"Bot {strategy}")
            if not result.get("ok"):
                await self._log("ERROR", "mt5_order_failed", {"symbol": symbol, "side": side, "error": result.get("error")})
                return
            entry = result.get("price", ref_price)
            # Record locally as well for tracking parity
            pos = Position(
                symbol=symbol, side=side, entry_price=entry, quantity=volume_lots,
                stop_loss=sl, take_profit=tp, strategy=strategy, reason=f"[MT5#{result.get('ticket')}] {reason}",
                mode=cfg.mode,
            )
            doc = pos.model_dump()
            doc["mt5_ticket"] = result.get("ticket")
            await positions_col.insert_one(doc)
            state.trades_today += 1
            await self._log("TRADE", "mt5_open_position", {
                "id": pos.id, "ticket": result.get("ticket"), "symbol": symbol, "side": side,
                "entry": entry, "volume_lots": volume_lots, "sl": sl, "tp": tp,
                "strategy": strategy, "reason": reason,
            })
            return

        # ---- Simulator path (default) ----
        fill = market.execute_order(symbol, side, price)
        entry = fill["fill_price"]
        if side == "BUY":
            sl = round(entry - sl_distance, 6)
            tp = round(entry + (sl_distance * cfg.risk.risk_reward_ratio), 6)
        else:
            sl = round(entry + sl_distance, 6)
            tp = round(entry - (sl_distance * cfg.risk.risk_reward_ratio), 6)

        pos = Position(
            symbol=symbol, side=side, entry_price=entry, quantity=round(quantity, 4),
            stop_loss=sl, take_profit=tp, strategy=strategy, reason=reason,
            mode=cfg.mode,
        )
        doc = pos.model_dump()
        await positions_col.insert_one(doc)
        # Deduct fee
        state.balance -= fill["fee"]
        state.trades_today += 1
        await self._log("TRADE", "open_position", {
            "id": pos.id, "symbol": symbol, "side": side, "entry": entry,
            "qty": pos.quantity, "sl": sl, "tp": tp, "strategy": strategy,
            "reason": reason, "fee": fill["fee"], "mode": cfg.mode,
        })

    async def _manage_positions(self, cfg: BotConfig, state: BotState):
        cursor = positions_col.find({"status": "OPEN"}, {"_id": 0})
        unrealized = 0.0
        async for p in cursor:
            symbol = p["symbol"]
            price = market.get_price(symbol)
            if price is None:
                continue
            side = p["side"]
            entry = p["entry_price"]
            qty = p["quantity"]
            sl = p["stop_loss"]
            tp = p["take_profit"]

            # Unrealized PnL
            if side == "BUY":
                pnl = (price - entry) * qty
            else:
                pnl = (entry - price) * qty
            unrealized += pnl

            # Hit SL or TP?
            hit_sl = (side == "BUY" and price <= sl) or (side == "SELL" and price >= sl)
            hit_tp = (side == "BUY" and price >= tp) or (side == "SELL" and price <= tp)
            if hit_sl or hit_tp:
                close_reason = "stop_loss" if hit_sl else "take_profit"
                fill = market.execute_order(symbol, "SELL" if side == "BUY" else "BUY", price)
                exit_price = fill["fill_price"]
                if side == "BUY":
                    pnl_final = (exit_price - entry) * qty
                else:
                    pnl_final = (entry - exit_price) * qty
                pnl_final -= fill["fee"]
                pnl_pct = (pnl_final / (entry * qty)) * 100 if entry * qty > 0 else 0

                trade = Trade(
                    symbol=symbol, side=side, entry_price=entry, exit_price=exit_price,
                    quantity=qty, pnl=round(pnl_final, 2), pnl_pct=round(pnl_pct, 4),
                    fees=fill["fee"], slippage=fill["slippage"],
                    strategy=p.get("strategy", "?"), open_reason=p.get("reason", ""),
                    close_reason=close_reason,
                    opened_at=p["opened_at"] if isinstance(p["opened_at"], datetime) else datetime.fromisoformat(str(p["opened_at"])),
                    mode=p.get("mode", "demo"),
                )
                opened_dt = trade.opened_at if isinstance(trade.opened_at, datetime) else datetime.fromisoformat(str(trade.opened_at))
                if opened_dt.tzinfo is None:
                    opened_dt = opened_dt.replace(tzinfo=timezone.utc)
                trade.duration_sec = (datetime.now(timezone.utc) - opened_dt).total_seconds()

                await trades_col.insert_one(trade.model_dump())
                await positions_col.update_one({"id": p["id"]}, {"$set": {"status": "CLOSED"}})

                state.balance += pnl_final
                state.realized_pnl += pnl_final
                state.daily_pnl += pnl_final

                await self._log("TRADE", "close_position", {
                    "id": p["id"], "symbol": symbol, "side": side,
                    "entry": entry, "exit": exit_price, "pnl": pnl_final,
                    "reason": close_reason, "mode": p.get("mode", "demo"),
                })

        state.unrealized_pnl = round(unrealized, 2)
        state.equity = round(state.balance + unrealized, 2)
        state.open_positions = await positions_col.count_documents({"status": "OPEN"})

    async def force_close_all(self, reason: str = "kill_switch"):
        cfg = await self._get_config()
        state = await self._get_state()
        cursor = positions_col.find({"status": "OPEN"}, {"_id": 0})
        async for p in cursor:
            symbol = p["symbol"]
            price = market.get_price(symbol) or p["entry_price"]
            side = p["side"]
            entry = p["entry_price"]
            qty = p["quantity"]
            fill = market.execute_order(symbol, "SELL" if side == "BUY" else "BUY", price)
            exit_price = fill["fill_price"]
            if side == "BUY":
                pnl_final = (exit_price - entry) * qty
            else:
                pnl_final = (entry - exit_price) * qty
            pnl_final -= fill["fee"]
            pnl_pct = (pnl_final / (entry * qty)) * 100 if entry * qty > 0 else 0

            opened_dt = p["opened_at"] if isinstance(p["opened_at"], datetime) else datetime.fromisoformat(str(p["opened_at"]))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)

            trade = Trade(
                symbol=symbol, side=side, entry_price=entry, exit_price=exit_price,
                quantity=qty, pnl=round(pnl_final, 2), pnl_pct=round(pnl_pct, 4),
                fees=fill["fee"], slippage=fill["slippage"],
                strategy=p.get("strategy", "?"), open_reason=p.get("reason", ""),
                close_reason=reason,
                opened_at=opened_dt,
                mode=p.get("mode", "demo"),
            )
            trade.duration_sec = (datetime.now(timezone.utc) - opened_dt).total_seconds()
            await trades_col.insert_one(trade.model_dump())
            await positions_col.update_one({"id": p["id"]}, {"$set": {"status": "CLOSED"}})

            state.balance += pnl_final
            state.realized_pnl += pnl_final
            state.daily_pnl += pnl_final

        state.unrealized_pnl = 0.0
        state.equity = round(state.balance, 2)
        state.open_positions = 0
        await self._update_state(state)
        await self._log("SYSTEM", "force_close_all", {"reason": reason})

    async def _daily_reset(self, state: BotState):
        now = datetime.now(timezone.utc)
        last = state.last_daily_reset if isinstance(state.last_daily_reset, datetime) else datetime.fromisoformat(str(state.last_daily_reset))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now.date() > last.date():
            state.daily_start_balance = state.balance
            state.daily_pnl = 0.0
            state.trades_today = 0
            state.last_daily_reset = now
            state.paused_reason = None
            await self._log("SYSTEM", "daily_reset", {"daily_start_balance": state.balance})

    async def _get_config(self) -> BotConfig:
        doc = await config_col.find_one({}, {"_id": 0})
        if not doc:
            cfg = BotConfig()
            await config_col.insert_one(cfg.model_dump())
            return cfg
        return BotConfig(**doc)

    async def _get_state(self) -> BotState:
        doc = await state_col.find_one({}, {"_id": 0})
        if not doc:
            state = BotState()
            await state_col.insert_one(state.model_dump())
            return state
        return BotState(**doc)

    async def _update_state(self, state: BotState):
        state.updated_at = utc_now()
        await state_col.update_one({"id": state.id}, {"$set": state.model_dump()}, upsert=True)

    async def _log(self, level: str, event: str, details: dict):
        log = AuditLog(level=level, event=event, details=details)
        await audit_col.insert_one(log.model_dump())
        logger.info("[%s] %s %s", level, event, details)


bot_runner = BotRunner()
