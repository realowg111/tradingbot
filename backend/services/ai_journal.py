"""AI Trading Journal service.

Aggregates closed trades, computes performance stats, and uses Claude Sonnet 4.5
(via Emergent LLM Key) to produce a French-language analysis with actionable
optimization recommendations.
"""
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, AsyncGenerator, Dict, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from database import trades_col, db  # noqa: E402
from models import uid, utc_now  # noqa: E402

logger = logging.getLogger("ai_journal")

reports_col = db["journal_reports"]

DEFAULT_MODEL_PROVIDER = "anthropic"
DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929"  # Claude Sonnet 4.5

SYSTEM_PROMPT = """Tu es un coach de trading algorithmique expert, spécialisé en Forex et CFD.
Ton rôle est d'analyser l'historique de trades d'un bot de trading automatisé et de fournir
une analyse professionnelle en français, structurée et actionnable.

Tu DOIS répondre en français uniquement, avec une structure Markdown propre :

# Synthèse globale
(2-3 phrases : performance générale, points clés)

## 🎯 Forces identifiées
- (liste avec données chiffrées)

## ⚠️ Faiblesses & risques
- (liste avec données chiffrées : ex. "Stratégie X : winrate 28% sur 25 trades")

## 📊 Analyse par stratégie
(Pour chaque stratégie : winrate, profit factor, recommandation continuer/ajuster/désactiver)

## 💱 Analyse par symbole
(Pour chaque symbole : performance, recommandation)

## 🔧 Recommandations d'optimisation
1. (Recommandation concrète #1 — paramètre à ajuster, valeur suggérée)
2. (Recommandation concrète #2)
3. ...

## 🚦 Verdict & priorités
(Action immédiate la plus impactante, en 1-2 phrases)

Sois précis, chiffré, et pragmatique. Ne fais pas de blabla générique."""


async def _gather_trades(period_days: int, mode: Optional[str] = None) -> List[Dict]:
    """Fetch closed trades within the period."""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    query: Dict = {"closed_at": {"$gte": since}}
    if mode:
        query["mode"] = mode
    cursor = trades_col.find(query, {"_id": 0}).sort("closed_at", -1)
    trades = await cursor.to_list(length=2000)
    return trades


def _compute_stats(trades: List[Dict]) -> Dict:
    """Compute aggregate statistics for trades."""
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "avg_duration_min": 0.0,
            "by_symbol": {},
            "by_strategy": {},
            "by_side": {"BUY": 0, "SELL": 0},
            "by_close_reason": {},
        }

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses)) or 1e-9
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    winrate = (len(wins) / len(trades)) * 100
    pf = gross_win / gross_loss
    avg_win = (gross_win / len(wins)) if wins else 0
    avg_loss = (-gross_loss / len(losses)) if losses else 0
    expectancy = (winrate / 100) * avg_win + ((100 - winrate) / 100) * avg_loss
    avg_dur = sum(t.get("duration_sec", 0) for t in trades) / len(trades) / 60.0

    by_symbol: Dict[str, Dict] = {}
    by_strategy: Dict[str, Dict] = {}
    by_close: Dict[str, int] = {}
    by_side = {"BUY": 0, "SELL": 0}

    for t in trades:
        sym = t.get("symbol", "?")
        strat = t.get("strategy", "?")
        side = t.get("side", "?")
        reason = t.get("close_reason", "?")
        pnl = t.get("pnl", 0)

        s = by_symbol.setdefault(sym, {"n": 0, "wins": 0, "pnl": 0.0})
        s["n"] += 1
        s["pnl"] += pnl
        if pnl > 0:
            s["wins"] += 1

        st = by_strategy.setdefault(strat, {"n": 0, "wins": 0, "pnl": 0.0, "gw": 0.0, "gl": 0.0})
        st["n"] += 1
        st["pnl"] += pnl
        if pnl > 0:
            st["wins"] += 1
            st["gw"] += pnl
        else:
            st["gl"] += abs(pnl)

        by_side[side] = by_side.get(side, 0) + 1
        by_close[reason] = by_close.get(reason, 0) + 1

    # Add winrate & PF to symbol/strategy buckets
    for s in by_symbol.values():
        s["winrate"] = round((s["wins"] / s["n"]) * 100, 1)
        s["pnl"] = round(s["pnl"], 2)
    for s in by_strategy.values():
        s["winrate"] = round((s["wins"] / s["n"]) * 100, 1)
        s["profit_factor"] = round((s["gw"] / s["gl"]) if s["gl"] > 0 else 0.0, 2)
        s["pnl"] = round(s["pnl"], 2)
        s.pop("gw", None)
        s.pop("gl", None)

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(winrate, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / len(trades), 2),
        "best_trade": round(max((t.get("pnl", 0) for t in trades)), 2),
        "worst_trade": round(min((t.get("pnl", 0) for t in trades)), 2),
        "profit_factor": round(pf, 2),
        "expectancy": round(expectancy, 2),
        "avg_duration_min": round(avg_dur, 1),
        "by_symbol": by_symbol,
        "by_strategy": by_strategy,
        "by_side": by_side,
        "by_close_reason": by_close,
    }


def _build_prompt(stats: Dict, period_days: int, sample_trades: List[Dict]) -> str:
    """Build the user prompt for the LLM."""
    # Keep only essential fields for the sample to limit token usage
    sample = []
    for t in sample_trades[:30]:
        sample.append({
            "symbol": t.get("symbol"),
            "side": t.get("side"),
            "strategy": t.get("strategy"),
            "pnl": round(t.get("pnl", 0), 2),
            "pnl_pct": round(t.get("pnl_pct", 0), 2),
            "duration_sec": int(t.get("duration_sec", 0)),
            "close_reason": t.get("close_reason"),
            "open_reason": t.get("open_reason"),
            "mode": t.get("mode"),
        })

    return f"""Analyse l'historique de trading suivant (période = {period_days} jours).

STATISTIQUES GLOBALES :
{json.dumps(stats, indent=2, ensure_ascii=False)}

ÉCHANTILLON DES {len(sample)} DERNIERS TRADES (sur {stats['total_trades']}) :
{json.dumps(sample, indent=2, ensure_ascii=False)}

Produis ton rapport d'analyse au format Markdown selon la structure imposée."""


async def get_stats_preview(period_days: int = 30, mode: Optional[str] = None) -> Dict:
    """Public: return aggregated stats without running the LLM."""
    trades = await _gather_trades(period_days, mode)
    stats = _compute_stats(trades)
    return {"period_days": period_days, "mode": mode, "stats": stats}


async def stream_analysis(
    period_days: int = 30,
    mode: Optional[str] = None,
    user_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream the LLM analysis as plain text deltas.

    Saves the full report in MongoDB once complete.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY missing from backend .env")

    trades = await _gather_trades(period_days, mode)
    stats = _compute_stats(trades)

    if stats["total_trades"] == 0:
        msg = (
            "# Aucune donnée\n\n"
            f"Aucun trade clôturé n'a été trouvé sur les **{period_days} derniers jours**"
            + (f" (mode : `{mode}`)" if mode else "")
            + ".\n\n"
            "Lance le bot en mode démo ou réel pour générer de l'historique, "
            "puis reviens ici pour obtenir une analyse IA."
        )
        yield msg
        # Save empty report
        await reports_col.insert_one({
            "id": uid(),
            "user_id": user_id,
            "period_days": period_days,
            "mode": mode,
            "stats": stats,
            "report_md": msg,
            "model": f"{DEFAULT_MODEL_PROVIDER}/{DEFAULT_MODEL_NAME}",
            "created_at": utc_now(),
        })
        return

    prompt = _build_prompt(stats, period_days, trades)

    session_id = f"journal-{uid()}"
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=SYSTEM_PROMPT,
    ).with_model(DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME)

    user_msg = UserMessage(text=prompt)
    full_text = ""
    try:
        async for ev in chat.stream_message(user_msg):
            if isinstance(ev, TextDelta):
                full_text += ev.content
                yield ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.exception("AI Journal streaming failed: %s", e)
        err = f"\n\n> ⚠️ Erreur LLM : {str(e)[:300]}"
        full_text += err
        yield err

    # Persist
    try:
        await reports_col.insert_one({
            "id": uid(),
            "user_id": user_id,
            "period_days": period_days,
            "mode": mode,
            "stats": stats,
            "report_md": full_text,
            "model": f"{DEFAULT_MODEL_PROVIDER}/{DEFAULT_MODEL_NAME}",
            "created_at": utc_now(),
        })
    except Exception:
        logger.exception("Failed to persist journal report")


async def list_reports(user_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
    query: Dict = {}
    if user_id:
        query["user_id"] = user_id
    cursor = reports_col.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_report(report_id: str) -> Optional[Dict]:
    return await reports_col.find_one({"id": report_id}, {"_id": 0})


async def delete_report(report_id: str) -> bool:
    res = await reports_col.delete_one({"id": report_id})
    return res.deleted_count > 0


async def ensure_indexes():
    await reports_col.create_index([("created_at", -1)])
    await reports_col.create_index([("user_id", 1), ("created_at", -1)])
