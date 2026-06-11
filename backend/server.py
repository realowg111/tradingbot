"""Trading Bot Backend - main FastAPI app.

Endpoints prefixed with /api.
"""
import os
import io
import csv
import json
import time
import logging
import asyncio
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import psutil
from pydantic import BaseModel
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from database import (
    users_col, trades_col, positions_col, audit_col, costs_col,
    config_col, state_col, signals_col, ensure_indexes,
)
from models import (
    UserRegister, UserLogin, UserPublic, Token,
    MT5CredentialsIn, MT5CredentialsOut, MT5PathPatch,
    BotConfig, BotState, RiskConfig, StrategyConfig,
    CostItem, CostItemCreate, AuditLog,
    ModeSwitchRequest, BacktestRequest, BacktestResult, Trade,
    utc_now, uid,
)
from security import (
    hash_password, verify_password,
    create_access_token, encrypt_str, decrypt_str,
)
from deps import get_current_user
from services.bot_runner import bot_runner
from services.paper_engine import market, SYMBOL_SPECS
from services.strategies import STRATEGIES
from services.metrics import compute_metrics
from services.mt5_broker import mt5_connector
from services import live_account
from services.ws_hub import ws_hub
from services import ai_journal
from services.market_regime import regime_store, detect_regime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

app = FastAPI(title="Trading Bot API", version="1.0.0")
api = APIRouter(prefix="/api")


# --- Startup / Shutdown ---
@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    # Seed admin user
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@trading.bot")
    admin_pwd = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    existing = await users_col.find_one({"email": admin_email})
    if not existing:
        await users_col.insert_one({
            "id": uid(),
            "email": admin_email,
            "password_hash": hash_password(admin_pwd),
            "is_admin": True,
            "created_at": utc_now(),
        })
        logger.info("Admin user seeded: %s", admin_email)
    # Ensure config & state exist
    if not await config_col.find_one({}):
        await config_col.insert_one(BotConfig().model_dump())
    if not await state_col.find_one({}):
        await state_col.insert_one(BotState().model_dump())
    # Start background bot loop
    await bot_runner.start()
    logger.info("Backend ready")


@app.on_event("shutdown")
async def on_shutdown():
    await bot_runner.stop()


# --- Health ---
@api.get("/")
async def root():
    return {"service": "Trading Bot API", "status": "online", "version": "1.0.0"}


@api.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# --- Auth ---
@api.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister):
    existing = await users_col.find_one({"email": payload.email})
    if existing:
        raise HTTPException(400, "Email déjà enregistré")
    user_id = uid()
    await users_col.insert_one({
        "id": user_id,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "is_admin": False,
        "created_at": utc_now(),
    })
    token = create_access_token({"sub": user_id, "email": payload.email, "is_admin": False})
    return Token(access_token=token, user=UserPublic(id=user_id, email=payload.email, is_admin=False))


@api.post("/auth/login", response_model=Token)
async def login(payload: UserLogin):
    doc = await users_col.find_one({"email": payload.email}, {"_id": 0})
    if not doc or not verify_password(payload.password, doc["password_hash"]):
        raise HTTPException(401, "Identifiants invalides")
    token = create_access_token({"sub": doc["id"], "email": doc["email"], "is_admin": doc.get("is_admin", False)})
    return Token(
        access_token=token,
        user=UserPublic(id=doc["id"], email=doc["email"], is_admin=doc.get("is_admin", False)),
    )


@api.get("/auth/me", response_model=UserPublic)
async def me(user: UserPublic = Depends(get_current_user)):
    return user


# --- MT5 credentials (encrypted) ---
@api.post("/mt5/credentials", response_model=MT5CredentialsOut)
async def save_mt5(creds: MT5CredentialsIn, user: UserPublic = Depends(get_current_user)):
    # If password/path missing, keep existing ones (merge with stored credentials)
    password = creds.password
    path = creds.path
    if not password or not path:
        doc = await users_col.find_one({"id": user.id}, {"_id": 0, "mt5_credentials": 1})
        if doc and "mt5_credentials" in doc:
            existing = json.loads(decrypt_str(doc["mt5_credentials"]))
            password = password or existing.get("password")
            path = path or existing.get("path")
        if not password:
            raise HTTPException(400, "Mot de passe requis pour la première sauvegarde")

    encrypted = encrypt_str(json.dumps({
        "login": creds.login, "password": password,
        "server": creds.server, "broker": creds.broker,
        "path": path,
    }))
    await users_col.update_one({"id": user.id}, {"$set": {"mt5_credentials": encrypted}})
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="mt5_credentials_updated",
                                        details={"user": user.email, "login": creds.login, "server": creds.server}).model_dump())
    return MT5CredentialsOut(login=creds.login, server=creds.server, broker=creds.broker, path=path, saved=True)


@api.patch("/mt5/credentials/path", response_model=MT5CredentialsOut)
async def patch_mt5_path(payload: MT5PathPatch, user: UserPublic = Depends(get_current_user)):
    """Update ONLY the terminal path while keeping login/password/server unchanged.

    Convenient when the user discovered the right path and doesn't want to re-enter
    the broker password.
    """
    doc = await users_col.find_one({"id": user.id}, {"_id": 0, "mt5_credentials": 1})
    if not doc or "mt5_credentials" not in doc:
        raise HTTPException(404, "Aucun identifiant MT5 existant. Enregistrez d'abord login/password/serveur.")
    data = json.loads(decrypt_str(doc["mt5_credentials"]))
    data["path"] = payload.path
    encrypted = encrypt_str(json.dumps(data))
    await users_col.update_one({"id": user.id}, {"$set": {"mt5_credentials": encrypted}})
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="mt5_path_updated",
                                        details={"user": user.email, "path": payload.path}).model_dump())
    return MT5CredentialsOut(login=data["login"], server=data["server"], broker=data.get("broker"), path=payload.path, saved=True)


@api.get("/mt5/credentials", response_model=Optional[MT5CredentialsOut])
async def get_mt5(user: UserPublic = Depends(get_current_user)):
    doc = await users_col.find_one({"id": user.id}, {"_id": 0})
    if not doc or "mt5_credentials" not in doc:
        return None
    data = json.loads(decrypt_str(doc["mt5_credentials"]))
    return MT5CredentialsOut(login=data["login"], server=data["server"], broker=data.get("broker"), path=data.get("path"), saved=True)


# --- Bot config & state ---
async def _get_config() -> BotConfig:
    doc = await config_col.find_one({}, {"_id": 0})
    return BotConfig(**doc) if doc else BotConfig()


async def _get_state() -> BotState:
    doc = await state_col.find_one({}, {"_id": 0})
    return BotState(**doc) if doc else BotState()


@api.get("/bot/config", response_model=BotConfig)
async def get_config(user: UserPublic = Depends(get_current_user)):
    return await _get_config()


@api.get("/bot/state")
async def get_state(user: UserPublic = Depends(get_current_user)):
    return await _build_snapshot_data()


@api.post("/bot/toggle")
async def toggle_bot(user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    cfg.enabled = not cfg.enabled
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="bot_toggle",
                                        details={"enabled": cfg.enabled, "user": user.email}).model_dump())
    return {"enabled": cfg.enabled}


@api.post("/bot/kill-switch")
async def kill_switch(user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    state = await _get_state()
    cfg.enabled = False
    state.kill_switch_engaged = True
    state.paused_reason = "kill_switch"
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await state_col.update_one({"id": state.id}, {"$set": state.model_dump()}, upsert=True)
    await bot_runner.force_close_all(reason="kill_switch")
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="kill_switch_engaged",
                                        details={"user": user.email}).model_dump())
    return {"kill_switch": True, "all_positions_closed": True}


@api.post("/bot/kill-switch/reset")
async def kill_switch_reset(user: UserPublic = Depends(get_current_user)):
    state = await _get_state()
    state.kill_switch_engaged = False
    state.paused_reason = None
    await state_col.update_one({"id": state.id}, {"$set": state.model_dump()}, upsert=True)
    return {"kill_switch": False}


@api.post("/bot/mode")
async def switch_mode(req: ModeSwitchRequest, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    state = await _get_state()

    if req.target_mode == "real":
        # Configurable paper validation gates (can be fully disabled)
        if cfg.paper_validation_enabled:
            ps = state.paper_start
            if isinstance(ps, datetime):
                ps_dt = ps if ps.tzinfo is not None else ps.replace(tzinfo=timezone.utc)
            else:
                ps_dt = datetime.fromisoformat(str(ps))
                if ps_dt.tzinfo is None:
                    ps_dt = ps_dt.replace(tzinfo=timezone.utc)
            paper_days = (utc_now() - ps_dt).days
            if paper_days < cfg.paper_validation_days:
                raise HTTPException(400, f"Validation paper trading insuffisante: {paper_days}/{cfg.paper_validation_days} jours (modifiable dans Risque)")
            trades = await trades_col.find({"mode": "demo"}, {"_id": 0}).to_list(10000)
            if len(trades) < cfg.paper_validation_min_trades:
                raise HTTPException(400, f"Min {cfg.paper_validation_min_trades} trades demo requis (actuel: {len(trades)})")
            metrics = compute_metrics(trades, cfg.starting_balance)
            if metrics["winrate"] < cfg.paper_validation_min_winrate:
                raise HTTPException(400, f"Winrate {metrics['winrate']}% < {cfg.paper_validation_min_winrate}% requis")
        state.real_unlocked = True

    cfg.mode = req.target_mode
    cfg.enabled = False
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await state_col.update_one({"id": state.id}, {"$set": state.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="mode_switch",
                                        details={"mode": req.target_mode, "user": user.email, "validation_enabled": cfg.paper_validation_enabled}).model_dump())
    return {"mode": cfg.mode, "real_unlocked": state.real_unlocked}


@api.post("/bot/reset-paper")
async def reset_paper(user: UserPublic = Depends(get_current_user)):
    """Reset demo balance and clear positions/trades for demo mode."""
    cfg = await _get_config()
    if cfg.mode != "demo":
        raise HTTPException(400, "Reset disponible uniquement en mode demo")
    state = await _get_state()
    state.balance = cfg.starting_balance
    state.equity = cfg.starting_balance
    state.daily_start_balance = cfg.starting_balance
    state.realized_pnl = 0.0
    state.unrealized_pnl = 0.0
    state.daily_pnl = 0.0
    state.trades_today = 0
    state.kill_switch_engaged = False
    state.paused_reason = None
    state.paper_start = utc_now()
    state.last_daily_reset = utc_now()
    await state_col.update_one({"id": state.id}, {"$set": state.model_dump()}, upsert=True)
    await positions_col.delete_many({"mode": "demo"})
    await trades_col.delete_many({"mode": "demo"})
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="paper_reset", details={"user": user.email}).model_dump())
    return {"reset": True}


# --- Risk & Strategy ---
@api.put("/bot/risk", response_model=BotConfig)
async def update_risk(risk: RiskConfig, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    cfg.risk = risk
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="risk_updated",
                                        details={"user": user.email, **risk.model_dump()}).model_dump())
    return cfg


@api.put("/bot/strategy", response_model=BotConfig)
async def update_strategy(strategy: StrategyConfig, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    cfg.strategy = strategy
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="strategy_updated",
                                        details={"user": user.email, **strategy.model_dump()}).model_dump())
    return cfg


class ConfigFlagsIn(BaseModel):
    paper_validation_enabled: Optional[bool] = None
    paper_validation_days: Optional[int] = None
    paper_validation_min_trades: Optional[int] = None
    paper_validation_min_winrate: Optional[float] = None
    live_mt5_trading_enabled: Optional[bool] = None
    min_confidence_score: Optional[int] = None


@api.post("/bot/config-flags", response_model=BotConfig)
async def update_config_flags(flags: ConfigFlagsIn, user: UserPublic = Depends(get_current_user)):
    """Update top-level config flags (validation gates + live MT5 trading toggle)."""
    cfg = await _get_config()
    data = flags.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(cfg, k, v)
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="config_flags_updated",
                                        details={"user": user.email, **data}).model_dump())
    return cfg


@api.get("/strategies/list")
async def strategies_list(user: UserPublic = Depends(get_current_user)):
    return [{"id": k, "name": v["name"], "description": v["description"]} for k, v in STRATEGIES.items()]


# --- Marchés: sélection des instruments autorisés au trading ---
class SymbolSelectionIn(BaseModel):
    symbols: List[str]


class SingleModeIn(BaseModel):
    enabled: bool
    symbol: Optional[str] = None


@api.get("/market/symbols")
async def market_symbols(user: UserPublic = Depends(get_current_user)):
    """Catalogue des instruments (MT5 si connecté, sinon simulateur) + sélection actuelle."""
    cfg = await _get_config()
    if mt5_connector.connected:
        catalog = await mt5_connector.list_symbols()
    else:
        from services.paper_engine import SYMBOL_SPECS
        from services.mt5_broker import categorize_symbol
        catalog = [{
            "name": s, "description": f"{s} (simulateur)", "path": "",
            "category": categorize_symbol("", s), "digits": spec["decimals"],
            "spread_points": 0, "visible": True,
        } for s, spec in SYMBOL_SPECS.items()]
    enabled = set(cfg.symbols or [])
    for c in catalog:
        c["enabled"] = c["name"] in enabled
    return {
        "symbols": catalog,
        "selected": cfg.symbols,
        "single_symbol_mode": cfg.single_symbol_mode,
        "single_symbol": cfg.single_symbol,
        "min_confidence_score": cfg.min_confidence_score,
        "source": "mt5" if mt5_connector.connected else "sim",
    }


@api.post("/market/symbols", response_model=BotConfig)
async def update_market_symbols(req: SymbolSelectionIn, user: UserPublic = Depends(get_current_user)):
    """Met à jour la liste des marchés autorisés (effet immédiat, sans redémarrage)."""
    symbols = [s.strip().upper() for s in req.symbols if s and s.strip()]
    symbols = list(dict.fromkeys(symbols))  # dedupe, keep order
    if not symbols:
        raise HTTPException(400, "Sélectionnez au moins un marché")
    if len(symbols) > 10:
        raise HTTPException(400, "Maximum 10 marchés simultanés (charge et risque maîtrisés)")
    cfg = await _get_config()
    cfg.symbols = symbols
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="symbols_updated",
                                        details={"user": user.email, "symbols": symbols}).model_dump())
    return cfg


@api.post("/market/single-mode", response_model=BotConfig)
async def update_single_mode(req: SingleModeIn, user: UserPublic = Depends(get_current_user)):
    """Mode marché unique: ne trader qu'un seul actif (changeable à chaud)."""
    cfg = await _get_config()
    cfg.single_symbol_mode = req.enabled
    if req.symbol:
        cfg.single_symbol = req.symbol.strip().upper()
    if cfg.single_symbol_mode and not cfg.single_symbol:
        raise HTTPException(400, "Choisissez l'actif du mode marché unique")
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="single_mode_updated",
                                        details={"user": user.email, "enabled": req.enabled,
                                                 "symbol": cfg.single_symbol}).model_dump())
    return cfg


# --- Signaux du moteur de décision (score + explications) ---
@api.get("/signals/current")
async def signals_current(user: UserPublic = Depends(get_current_user)):
    """Dernière évaluation en mémoire pour chaque marché surveillé."""
    cfg = await _get_config()
    from services.decision_engine import latest_evals, effective_symbols
    symbols = effective_symbols(cfg)
    return {
        "symbols": symbols,
        "evaluations": [latest_evals[s] for s in symbols if s in latest_evals],
        "min_confidence_score": cfg.min_confidence_score,
    }


@api.get("/signals/recent")
async def signals_recent(limit: int = 30, user: UserPublic = Depends(get_current_user)):
    """Historique des signaux persistés (exécutions + presque-signaux)."""
    docs = await signals_col.find({}, {"_id": 0}).sort("ts", -1).to_list(min(limit, 100))
    return docs



async def _sim_open_positions(mode: str):
    """Internal simulator positions for the given mode, enriched with live price."""
    docs = await positions_col.find({"status": "OPEN", "mode": mode}, {"_id": 0}).sort("opened_at", -1).to_list(200)
    for d in docs:
        price = market.get_price(d["symbol"])
        d["current_price"] = price
        if price is not None:
            side = d["side"]
            entry = d["entry_price"]
            qty = d["quantity"]
            if side == "BUY":
                d["unrealized_pnl"] = round((price - entry) * qty, 2)
            else:
                d["unrealized_pnl"] = round((entry - price) * qty, 2)
        else:
            d["unrealized_pnl"] = 0.0
        d["source"] = "sim"
        if isinstance(d.get("opened_at"), datetime):
            d["opened_at"] = d["opened_at"].isoformat()
    return docs


@api.get("/positions/open")
async def open_positions(user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    if live_account.is_live(cfg):
        return await live_account.live_positions()
    return await _sim_open_positions(cfg.mode)


@api.post("/positions/{position_id}/close")
async def close_position_manual(position_id: str, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    # Live mode: position_id is the MT5 ticket -> close on the broker
    if live_account.is_live(cfg) and position_id.isdigit():
        result = await mt5_connector.close_position(int(position_id))
        await audit_col.insert_one(AuditLog(level="TRADE", event="mt5_manual_close",
                                            details={"ticket": position_id, "ok": result.get("ok"),
                                                     "error": result.get("error"), "user": user.email}).model_dump())
        if not result.get("ok"):
            raise HTTPException(400, f"Fermeture MT5 échouée: {result.get('error')}")
        # Mark the local mirror (if any) as closed
        await positions_col.update_one({"mt5_ticket": int(position_id)}, {"$set": {"status": "CLOSED"}})
        return {"closed": True, "price": result.get("price"), "source": "mt5"}

    pos = await positions_col.find_one({"id": position_id, "status": "OPEN"}, {"_id": 0})
    if not pos:
        raise HTTPException(404, "Position introuvable")
    price = market.get_price(pos["symbol"]) or pos["entry_price"]
    side = pos["side"]
    entry = pos["entry_price"]
    qty = pos["quantity"]
    fill = market.execute_order(pos["symbol"], "SELL" if side == "BUY" else "BUY", price)
    exit_price = fill["fill_price"]
    pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
    pnl -= fill["fee"]
    pnl_pct = (pnl / (entry * qty)) * 100 if entry * qty > 0 else 0

    opened_dt = pos["opened_at"] if isinstance(pos["opened_at"], datetime) else datetime.fromisoformat(str(pos["opened_at"]))
    if opened_dt.tzinfo is None:
        opened_dt = opened_dt.replace(tzinfo=timezone.utc)

    trade = Trade(
        symbol=pos["symbol"], side=side, entry_price=entry, exit_price=exit_price,
        quantity=qty, pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 4),
        fees=fill["fee"], slippage=fill["slippage"],
        strategy=pos.get("strategy", "?"), open_reason=pos.get("reason", ""),
        close_reason="manual_close",
        opened_at=opened_dt, mode=pos.get("mode", "demo"),
    )
    trade.duration_sec = (datetime.now(timezone.utc) - opened_dt).total_seconds()
    await trades_col.insert_one(trade.model_dump())
    await positions_col.update_one({"id": position_id}, {"$set": {"status": "CLOSED"}})

    state = await _get_state()
    state.balance += pnl
    state.realized_pnl += pnl
    state.daily_pnl += pnl
    await state_col.update_one({"id": state.id}, {"$set": state.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(level="TRADE", event="manual_close",
                                        details={"id": position_id, "pnl": pnl, "user": user.email}).model_dump())
    return {"closed": True, "pnl": round(pnl, 2)}


async def _resolve_trades(mode: Optional[str], cfg) -> tuple:
    """Resolve the trade list source.

    Returns (trades, source). MT5 history is used when the requested mode is
    'real' (or unspecified while the bot is in real mode) and MT5 is connected.
    """
    wants_real = mode == "real" or (mode is None and cfg.mode == "real")
    if wants_real and mt5_connector.connected:
        trades = await live_account.mt5_trades(days=90)
        return trades, "mt5"
    q = {}
    if mode:
        q["mode"] = mode
    docs = await trades_col.find(q, {"_id": 0}).sort("closed_at", -1).to_list(10000)
    return docs, "sim"


@api.get("/trades")
async def trades_list(limit: int = 100, mode: Optional[str] = None, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    trades, _ = await _resolve_trades(mode, cfg)
    return trades[:limit]


@api.get("/trades/metrics")
async def trades_metrics(mode: Optional[str] = None, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    trades, source = await _resolve_trades(mode, cfg)
    if source == "mt5":
        account = await mt5_connector.get_account_info()
        balance = account["balance"] if account else 0.0
        starting = balance - sum(t.get("pnl", 0.0) for t in trades)
        result = compute_metrics(list(reversed(trades)), starting if starting > 0 else cfg.starting_balance)
    else:
        result = compute_metrics(trades, cfg.starting_balance)
    result["source"] = source
    return result


@api.get("/trades/equity-curve")
async def equity_curve(mode: Optional[str] = None, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    trades, source = await _resolve_trades(mode, cfg)
    if source == "mt5":
        account = await mt5_connector.get_account_info()
        balance = account["balance"] if account else 0.0
        eq = balance - sum(t.get("pnl", 0.0) for t in trades)
        ordered = sorted(trades, key=lambda t: str(t.get("closed_at")))
    else:
        eq = cfg.starting_balance
        ordered = sorted(trades, key=lambda t: str(t.get("closed_at")))
    curve = [{"ts": None, "equity": round(eq, 2)}]
    for t in ordered:
        eq += t.get("pnl", 0.0)
        ts = t.get("closed_at")
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        curve.append({"ts": str(ts), "equity": round(eq, 2)})
    return curve


@api.get("/trades/export")
async def export_trades(format: str = "csv", mode: Optional[str] = None, user: UserPublic = Depends(get_current_user)):
    q = {}
    if mode:
        q["mode"] = mode
    docs = await trades_col.find(q, {"_id": 0}).sort("closed_at", -1).to_list(100000)
    if format == "json":
        body = json.dumps(docs, default=str, indent=2)
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=trades.json"})
    # CSV
    buf = io.StringIO()
    if docs:
        writer = csv.DictWriter(buf, fieldnames=list(docs[0].keys()))
        writer.writeheader()
        for d in docs:
            writer.writerow({k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()})
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=trades.csv"})


# --- Market data ---
@api.get("/market/prices")
async def market_prices(user: UserPublic = Depends(get_current_user)):
    return {s: {"price": market.get_price(s), "spec": SYMBOL_SPECS[s]} for s in SYMBOL_SPECS}


@api.get("/market/candles/{symbol}")
async def market_candles(symbol: str, n: int = 100, user: UserPublic = Depends(get_current_user)):
    closes = market.get_closes(symbol, n)
    return {"symbol": symbol, "closes": closes}


# --- Audit logs ---
@api.get("/audit/logs")
async def audit_logs(limit: int = 200, level: Optional[str] = None, user: UserPublic = Depends(get_current_user)):
    q = {}
    if level:
        q["level"] = level
    docs = await audit_col.find(q, {"_id": 0}).sort("ts", -1).to_list(limit)
    return docs


@api.get("/audit/export")
async def export_audit(format: str = "csv", user: UserPublic = Depends(get_current_user)):
    docs = await audit_col.find({}, {"_id": 0}).sort("ts", -1).to_list(100000)
    # Stringify details dict for CSV
    flat = []
    for d in docs:
        flat.append({
            "ts": d.get("ts").isoformat() if isinstance(d.get("ts"), datetime) else d.get("ts"),
            "level": d.get("level"),
            "event": d.get("event"),
            "details": json.dumps(d.get("details", {}), default=str),
        })
    if format == "json":
        return Response(content=json.dumps(flat, default=str, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=audit_logs.json"})
    buf = io.StringIO()
    if flat:
        writer = csv.DictWriter(buf, fieldnames=list(flat[0].keys()))
        writer.writeheader()
        writer.writerows(flat)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit_logs.csv"})


# --- Cost tracker ---
@api.get("/costs", response_model=List[CostItem])
async def costs_list(user: UserPublic = Depends(get_current_user)):
    docs = await costs_col.find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return [CostItem(**d) for d in docs]


@api.post("/costs", response_model=CostItem)
async def costs_create(payload: CostItemCreate, user: UserPublic = Depends(get_current_user)):
    item = CostItem(**payload.model_dump())
    await costs_col.insert_one(item.model_dump())
    return item


@api.delete("/costs/{cost_id}")
async def costs_delete(cost_id: str, user: UserPublic = Depends(get_current_user)):
    res = await costs_col.delete_one({"id": cost_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Coût introuvable")
    return {"deleted": True}


@api.get("/costs/summary")
async def costs_summary(user: UserPublic = Depends(get_current_user)):
    docs = await costs_col.find({}, {"_id": 0}).to_list(10000)
    # Compute monthly equivalent
    by_cat = {}
    monthly_total = 0.0
    once_total = 0.0
    for d in docs:
        cat = d.get("category", "other")
        amt = d.get("amount", 0.0)
        rec = d.get("recurring", "once")
        if rec == "monthly":
            m = amt
        elif rec == "yearly":
            m = amt / 12
        else:
            m = 0
            once_total += amt
        monthly_total += m
        by_cat[cat] = by_cat.get(cat, 0.0) + m
    # P&L for rentability vs costs
    state = await _get_state()
    return {
        "monthly_total": round(monthly_total, 2),
        "yearly_total": round(monthly_total * 12, 2),
        "one_off_total": round(once_total, 2),
        "by_category": {k: round(v, 2) for k, v in by_cat.items()},
        "items_count": len(docs),
        "current_realized_pnl": round(state.realized_pnl, 2),
        "net_monthly_profit": round(state.realized_pnl - monthly_total, 2),
    }


# --- Backtest ---
@api.post("/backtest/run", response_model=BacktestResult)
async def backtest_run(req: BacktestRequest, user: UserPublic = Depends(get_current_user)):
    """Run a backtest using historical synthetic data from the simulator."""
    cfg = await _get_config()
    closes = market.get_closes(req.symbol, req.candles)
    if len(closes) < 50:
        raise HTTPException(400, "Pas assez de bougies pour backtester")

    strat = STRATEGIES.get(req.strategy)
    if not strat:
        raise HTTPException(400, f"Stratégie inconnue: {req.strategy}")

    balance = req.starting_balance
    trades: List[Trade] = []
    open_pos = None
    spec = SYMBOL_SPECS.get(req.symbol, {"fee_pct": 0.0002})

    for i in range(30, len(closes)):
        window = closes[: i + 1]
        price = closes[i]
        # Manage open position
        if open_pos:
            side = open_pos["side"]
            entry = open_pos["entry"]
            qty = open_pos["qty"]
            sl = open_pos["sl"]
            tp = open_pos["tp"]
            hit_sl = (side == "BUY" and price <= sl) or (side == "SELL" and price >= sl)
            hit_tp = (side == "BUY" and price >= tp) or (side == "SELL" and price <= tp)
            if hit_sl or hit_tp:
                exit_price = price
                pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
                fee = abs(exit_price) * spec.get("fee_pct", 0.0002)
                pnl -= fee
                pnl_pct = (pnl / (entry * qty)) * 100 if entry * qty > 0 else 0
                balance += pnl
                trades.append(Trade(
                    symbol=req.symbol, side=side, entry_price=entry, exit_price=exit_price,
                    quantity=qty, pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 4),
                    fees=fee, slippage=0.0, strategy=req.strategy,
                    open_reason=open_pos.get("reason", ""),
                    close_reason="stop_loss" if hit_sl else "take_profit",
                    opened_at=open_pos["opened_at"], mode="demo",
                ))
                open_pos = None
            else:
                continue

        # Look for new signal
        sig, reason = strat["fn"](window, cfg.strategy)
        if sig is None:
            continue
        # Open new position
        risk_amount = balance * (cfg.risk.capital_allocation_pct / 100.0) * (cfg.risk.risk_per_trade_pct / 100.0)
        sl_distance = price * (cfg.risk.stop_loss_pct / 100.0)
        if sl_distance <= 0:
            continue
        qty = risk_amount / sl_distance
        if sig == "BUY":
            sl = price - sl_distance
            tp = price + (sl_distance * cfg.risk.risk_reward_ratio)
        else:
            sl = price + sl_distance
            tp = price - (sl_distance * cfg.risk.risk_reward_ratio)
        open_pos = {
            "side": sig, "entry": price, "qty": qty, "sl": sl, "tp": tp,
            "reason": reason, "opened_at": utc_now(),
        }

    metrics = compute_metrics([t.model_dump() for t in trades], req.starting_balance)
    return BacktestResult(
        symbol=req.symbol,
        strategy=req.strategy,
        starting_balance=req.starting_balance,
        ending_balance=round(balance, 2),
        total_trades=metrics["total_trades"],
        wins=metrics["wins"],
        losses=metrics["losses"],
        winrate=metrics["winrate"],
        profit_factor=metrics["profit_factor"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        sharpe=metrics["sharpe"],
        expectancy=metrics["expectancy"],
        trades=trades[-20:],  # last 20 only
    )


# --- System Health (VPS monitoring) ---
_BOOT_TIME = time.time()


@api.get("/system/health")
async def system_health(user: UserPublic = Depends(get_current_user)):
    """Return live system metrics: CPU, RAM, disk, uptime, services status."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot = psutil.boot_time()
        uptime_sec = time.time() - boot
        load_avg = list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [0, 0, 0]
    except Exception as e:
        raise HTTPException(500, f"psutil error: {e}")

    # MongoDB ping
    mongo_ok = False
    try:
        from database import client
        await client.admin.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False

    # Bot loop alive ?
    bot_alive = bot_runner.running and bot_runner.task is not None and not bot_runner.task.done()
    backend_uptime_sec = time.time() - _BOOT_TIME

    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "hostname": platform.node(),
        },
        "cpu": {
            "percent": cpu_percent,
            "count": cpu_count,
            "load_avg": load_avg,
        },
        "memory": {
            "total_mb": round(mem.total / 1024 / 1024, 1),
            "used_mb": round(mem.used / 1024 / 1024, 1),
            "available_mb": round(mem.available / 1024 / 1024, 1),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
        "uptime": {
            "system_seconds": int(uptime_sec),
            "backend_seconds": int(backend_uptime_sec),
        },
        "services": {
            "mongodb": mongo_ok,
            "bot_loop": bot_alive,
            "mt5_connected": mt5_connector.connected,
            "mt5_mode": mt5_connector.mode,
            "ws_clients": len(ws_hub.clients),
        },
    }


@api.post("/system/update")
async def system_update(user: UserPublic = Depends(get_current_user)):
    """Pull the latest code from git and restart the bot.

    Only works if the backend was deployed via git. On the Emergent platform
    the update flow is handled by the platform itself.
    """
    if not user.is_admin:
        raise HTTPException(403, "Admin uniquement")
    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / ".git").exists():
        return {"updated": False, "message": "Pas un dépôt git. Sur la plateforme Emergent, l'auto-update se fait via le bouton 'Save to GitHub' + pull manuel sur le VPS."}
    try:
        before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
        out = subprocess.check_output(["git", "pull", "--ff-only"], cwd=repo_root, text=True, stderr=subprocess.STDOUT)
        after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
        await audit_col.insert_one(AuditLog(level="SYSTEM", event="system_update",
                                            details={"user": user.email, "before": before, "after": after}).model_dump())
        return {"updated": before != after, "before": before, "after": after, "git_output": out}
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"git error: {e.output if hasattr(e, 'output') else str(e)}")


# --- MT5 Real Connection ---
@api.get("/mt5/status")
async def mt5_status(user: UserPublic = Depends(get_current_user)):
    """Returns MT5 connector status and account info if connected."""
    status_dict = mt5_connector.status()
    account = await mt5_connector.get_account_info() if mt5_connector.connected else None
    return {"status": status_dict, "account": account}


@api.post("/mt5/connect")
async def mt5_connect(user: UserPublic = Depends(get_current_user)):
    """Attempt to connect to MT5 using the credentials saved in user profile."""
    doc = await users_col.find_one({"id": user.id}, {"_id": 0})
    if not doc or "mt5_credentials" not in doc:
        raise HTTPException(400, "Aucun identifiant MT5 enregistré. Sauvegardez d'abord vos identifiants.")
    creds = json.loads(decrypt_str(doc["mt5_credentials"]))
    result = await mt5_connector.connect(
        login=creds["login"], password=creds["password"],
        server=creds["server"], broker=creds.get("broker"),
        path=creds.get("path"),
    )
    await audit_col.insert_one(AuditLog(
        level="SYSTEM", event="mt5_connect_attempt",
        details={"user": user.email, "connected": result["connected"], "mode": result["mode"], "error": result.get("last_error")},
    ).model_dump())
    return result


@api.post("/mt5/disconnect")
async def mt5_disconnect(user: UserPublic = Depends(get_current_user)):
    await mt5_connector.disconnect()
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="mt5_disconnect", details={"user": user.email}).model_dump())
    return mt5_connector.status()


@api.get("/mt5/live")
async def mt5_live(user: UserPublic = Depends(get_current_user)):
    """Live snapshot: account + positions from MT5 (if connected)."""
    if not mt5_connector.connected:
        return {"connected": False, "account": None, "positions": [], "status": mt5_connector.status()}
    account = await mt5_connector.get_account_info()
    positions = await mt5_connector.get_positions()
    return {
        "connected": True,
        "account": account,
        "positions": positions,
        "status": mt5_connector.status(),
    }


# --- WebSocket: live state stream ---
@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket, token: str):
    """Stream live state, positions and prices.

    Auth via query param `token` (JWT). Broadcasts every ~1s.
    """
    ok = await ws_hub.connect(ws, token)
    if not ok:
        return
    try:
        # Send initial snapshot immediately
        await _send_snapshot(ws)
        # Listen for client pings (keepalive)
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
                if msg == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send periodic update
                await _send_snapshot(ws)
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await ws_hub.disconnect(ws)


async def _send_snapshot(ws: WebSocket):
    """Send a full snapshot to a single client."""
    try:
        payload = {
            "type": "snapshot",
            "ts": datetime.now(timezone.utc).isoformat(),
            "data": await _build_snapshot_data(),
        }
        await ws.send_text(json.dumps(payload, default=str))
    except Exception as e:
        logger.exception("send_snapshot error: %s", e)


async def _build_snapshot_data() -> dict:
    """Single source of truth for the live snapshot (WS + REST polling).

    In real mode with MT5 connected: balance/equity/margin/positions come
    from the real MT5 account. Otherwise: internal simulator.
    """
    cfg = await _get_config()
    state = await _get_state()
    prices = {s: market.get_price(s) for s in cfg.symbols}
    resolved_state = await live_account.resolve_state(cfg, state)
    if live_account.is_live(cfg):
        positions = await live_account.live_positions()
    else:
        positions = await _sim_open_positions(cfg.mode)
    resolved_state["open_positions"] = len(positions)
    mt5_status_dict = mt5_connector.status()
    mt5_account = await mt5_connector.get_account_info() if mt5_connector.connected else None
    return {
        "state": resolved_state,
        "config_mode": cfg.mode,
        "config_enabled": cfg.enabled,
        "prices": prices,
        "positions": positions,
        "mt5_status": mt5_status_dict,
        "mt5_account": mt5_account,
    }


# --- Background WS broadcast loop ---
async def _ws_broadcast_loop():
    """Broadcast snapshot to all connected clients every 1s."""
    while True:
        await asyncio.sleep(1.0)
        if not ws_hub.clients:
            continue
        try:
            await ws_hub.broadcast("snapshot", await _build_snapshot_data())
        except Exception as e:
            logger.exception("ws_broadcast error: %s", e)


@app.on_event("startup")
async def start_broadcast():
    asyncio.create_task(_ws_broadcast_loop())
    asyncio.create_task(_mt5_autoconnect_loop())


# --- MT5 auto-reconnect: autonomie 24/7 après reboot/restart ---
async def _mt5_autoconnect_loop():
    """Reconnects MT5 automatically using the stored admin credentials.

    Runs every 60s. Only attempts when the native lib (or bridge) is available
    and credentials are saved. Logs only on state change to avoid spam.
    """
    await asyncio.sleep(10)  # let the app settle after boot
    last_error = None
    while True:
        try:
            st = mt5_connector.status()
            if not mt5_connector.connected and (st.get("has_native_lib") or st.get("has_bridge_url")):
                doc = await users_col.find_one(
                    {"is_admin": True, "mt5_credentials": {"$exists": True}},
                    {"_id": 0, "mt5_credentials": 1},
                )
                if doc:
                    creds = json.loads(decrypt_str(doc["mt5_credentials"]))
                    result = await mt5_connector.connect(
                        login=creds["login"], password=creds["password"],
                        server=creds["server"], broker=creds.get("broker"),
                        path=creds.get("path"),
                    )
                    if result["connected"]:
                        last_error = None
                        logger.info("MT5 auto-reconnect: OK")
                        await audit_col.insert_one(AuditLog(
                            level="SYSTEM", event="mt5_autoconnect_success",
                            details={"mode": result["mode"]}).model_dump())
                    elif result.get("last_error") != last_error:
                        last_error = result.get("last_error")
                        logger.warning("MT5 auto-reconnect failed: %s", last_error)
                        await audit_col.insert_one(AuditLog(
                            level="ERROR", event="mt5_autoconnect_failed",
                            details={"error": str(last_error)[:300]}).model_dump())
        except Exception as e:
            logger.warning("mt5 autoconnect loop error: %s", e)
        await asyncio.sleep(60)


# --- Redémarrage à distance du backend (VPS Windows) ---
@api.post("/system/restart")
async def system_restart(user: UserPublic = Depends(get_current_user)):
    """Restart the backend via a detached PowerShell (Windows VPS only)."""
    if not user.is_admin:
        raise HTTPException(403, "Admin uniquement")
    if os.name != "nt":
        raise HTTPException(400, "Disponible uniquement sur le VPS Windows")
    await audit_col.insert_one(AuditLog(level="SYSTEM", event="system_restart",
                                        details={"user": user.email}).model_dump())
    cmd = (
        '"Start-Sleep -Seconds 2; '
        'schtasks /End /TN TradingBotBackend 2>&1; '
        'Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force; '
        'Start-Sleep -Seconds 3; '
        'schtasks /Run /TN TradingBotBackend 2>&1" '
        '*>> C:\\trading-bot\\restart.log'
    )
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        f'powershell -NoProfile -ExecutionPolicy Bypass -Command {cmd}',
        shell=True,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"restarting": True, "message": "Backend redémarre dans ~5 secondes"}


# --- Micro-trade test 0.01 lot (vérification exécution réelle) ---
class TestTradeRequest(BaseModel):
    symbol: str = "EURUSD"
    side: str = "BUY"
    volume: float = 0.01


@api.post("/mt5/test-trade")
async def mt5_test_trade(req: TestTradeRequest, user: UserPublic = Depends(get_current_user)):
    """Open a micro position on MT5 then close it ~3s later. End-to-end execution test."""
    if not user.is_admin:
        raise HTTPException(403, "Admin uniquement")
    if not mt5_connector.connected:
        raise HTTPException(400, "MT5 non connecté")
    side = req.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(400, "side doit être BUY ou SELL")
    volume = min(max(req.volume, 0.01), 0.1)  # hard cap sécurité

    tick = await mt5_connector.get_price(req.symbol)
    if not tick or not tick.get("bid"):
        raise HTTPException(400, f"Pas de prix pour {req.symbol}")
    price = tick["ask"] if side == "BUY" else tick["bid"]
    # SL/TP larges (±0.5%) : la position sera refermée manuellement dans 3s
    if side == "BUY":
        sl, tp = price * 0.995, price * 1.005
    else:
        sl, tp = price * 1.005, price * 0.995

    open_res = await mt5_connector.place_order(req.symbol, side, volume, round(sl, 5), round(tp, 5), comment="bot TEST")
    await audit_col.insert_one(AuditLog(level="TRADE", event="test_trade_open",
                                        details={"user": user.email, "symbol": req.symbol, "side": side,
                                                 "volume": volume, **{k: str(v) for k, v in open_res.items()}}).model_dump())
    if not open_res.get("ok"):
        raise HTTPException(400, f"Ouverture échouée: {open_res.get('error')}")

    await asyncio.sleep(3)
    close_res = await mt5_connector.close_position(open_res["ticket"])
    await audit_col.insert_one(AuditLog(level="TRADE", event="test_trade_close",
                                        details={"ticket": open_res["ticket"], **{k: str(v) for k, v in close_res.items()}}).model_dump())
    return {
        "ticket": open_res["ticket"],
        "open": open_res,
        "close": close_res,
        "success": bool(open_res.get("ok") and close_res.get("ok")),
    }


# --- Market regime / Adaptive strategy ---
@api.get("/market/regime")
async def market_regime(user: UserPublic = Depends(get_current_user)):
    """Return latest detected regime per symbol (refreshed each bot tick).

    Falls back to live recomputation from the simulator if cache is empty.
    """
    snap = regime_store.all()
    if not snap:
        # Cold start fallback: compute on the fly using the simulator
        cfg = await _get_config()
        snap = {}
        for sym in cfg.symbols:
            closes = market.get_closes(sym, 200)
            if len(closes) >= 30:
                info = detect_regime(closes)
                regime_store.update(sym, info)
                snap[sym] = {
                    **info,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
    # Also include the current adaptive toggle for the UI
    cfg = await _get_config()
    return {
        "adaptive_enabled": cfg.adaptive_enabled,
        "symbols": snap,
    }


class AdaptiveToggle(BaseModel):
    enabled: bool


@api.post("/bot/adaptive")
async def toggle_adaptive(payload: AdaptiveToggle, user: UserPublic = Depends(get_current_user)):
    cfg = await _get_config()
    cfg.adaptive_enabled = bool(payload.enabled)
    cfg.updated_at = utc_now()
    await config_col.update_one({"id": cfg.id}, {"$set": cfg.model_dump()}, upsert=True)
    await audit_col.insert_one(AuditLog(
        level="SYSTEM",
        event="adaptive_toggle",
        details={"user": user.email, "enabled": cfg.adaptive_enabled},
    ).model_dump())
    return {"adaptive_enabled": cfg.adaptive_enabled}


# --- AI Journal ---
@api.get("/journal/preview")
async def journal_preview(
    days: int = 30,
    mode: Optional[str] = None,
    user: UserPublic = Depends(get_current_user),
):
    """Return aggregated stats for the chosen period (no LLM call)."""
    days = max(1, min(days, 365))
    if mode not in (None, "demo", "real"):
        mode = None
    return await ai_journal.get_stats_preview(days, mode)


@api.post("/journal/analyze")
async def journal_analyze(
    payload: dict,
    user: UserPublic = Depends(get_current_user),
):
    """Stream a Claude Sonnet 4.5 analysis of the trade history as SSE.

    Body: {"days": int, "mode": "demo"|"real"|null}
    """
    from fastapi.responses import StreamingResponse

    days = int(payload.get("days", 30))
    days = max(1, min(days, 365))
    mode = payload.get("mode")
    if mode not in (None, "demo", "real"):
        mode = None

    async def event_generator():
        try:
            async for chunk in ai_journal.stream_analysis(days, mode, user.id):
                # SSE format with json-escaped content to preserve newlines
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield "data: {\"done\": true}\n\n"
        except Exception as e:
            logger.exception("journal/analyze error: %s", e)
            yield f"data: {json.dumps({'error': str(e)[:300]})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api.get("/journal/reports")
async def journal_reports(
    limit: int = 20,
    user: UserPublic = Depends(get_current_user),
):
    limit = max(1, min(limit, 100))
    return await ai_journal.list_reports(limit=limit)


@api.get("/journal/reports/{report_id}")
async def journal_report_get(
    report_id: str,
    user: UserPublic = Depends(get_current_user),
):
    rep = await ai_journal.get_report(report_id)
    if not rep:
        raise HTTPException(404, "Rapport introuvable")
    return rep


@api.delete("/journal/reports/{report_id}")
async def journal_report_delete(
    report_id: str,
    user: UserPublic = Depends(get_current_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin requis")
    ok = await ai_journal.delete_report(report_id)
    if not ok:
        raise HTTPException(404, "Rapport introuvable")
    return {"deleted": True}


@app.on_event("startup")
async def _init_journal_indexes():
    try:
        await ai_journal.ensure_indexes()
    except Exception:
        logger.exception("journal indexes init failed")


# --- Mount router ---
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
