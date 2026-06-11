"""Multi-factor decision engine with confidence scoring (0-100).

A trade is NEVER opened on a single indicator. Each opportunity is scored
across 6 independent factor families; execution requires the total score to
reach the configurable threshold (cfg.min_confidence_score).

Factors (max points):
  1. Tendance multi-timeframe M15+H1 (25)
  2. Momentum RSI + MACD            (15)
  3. Structure: cassures & S/R      (20)
  4. Volatilité ATR                 (15)
  5. Spread & session de liquidité  (15)
  6. Régime de marché               (10)

Every evaluation produces a French explanation per factor, visible in the UI.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from services import market_data
from services.mt5_broker import mt5_connector
from services.strategies import ema, rsi, macd, atr
from services.market_regime import detect_regime, regime_store

logger = logging.getLogger("decision_engine")

# In-memory latest evaluation per symbol (for the live UI)
latest_evals: Dict[str, Dict[str, Any]] = {}
_eval_ts: Dict[str, float] = {}

EVAL_INTERVAL_SEC = 60  # one evaluation per symbol per minute


def _factor(name: str, points: float, max_pts: float, ok: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "points": round(points, 1), "max": max_pts, "ok": ok, "detail": detail}


async def evaluate_symbol(symbol: str, cfg, category: str = "autres") -> Dict[str, Any]:
    """Full multi-factor evaluation. Returns the signal record (not persisted)."""
    result: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "ts": datetime.now(timezone.utc).isoformat(),
        "side": None,
        "score": 0,
        "threshold": getattr(cfg, "min_confidence_score", 70),
        "decision": "NO_SIGNAL",
        "blocking": [],
        "factors": [],
        "source": "sim",
    }

    m15 = await market_data.get_ohlc(symbol, "M15", 200)
    h1 = await market_data.get_ohlc(symbol, "H1", 120)
    result["source"] = m15["source"]
    candles = m15["candles"]
    closes = [c["close"] for c in candles]
    if len(closes) < 60:
        result["factors"].append(_factor("Données", 0, 0, False, f"Données insuffisantes ({len(closes)} bougies M15)"))
        return result
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price = closes[-1]
    a = atr(highs, lows, closes, 14) or (price * 0.001)

    factors: List[Dict[str, Any]] = []
    blocking: List[str] = []

    # ---------- 1. Tendance multi-timeframe (25) ----------
    e20, e50 = ema(closes, 20), ema(closes, 50)
    h1_closes = [c["close"] for c in h1["candles"]]
    e20_h1 = ema(h1_closes, 20) if len(h1_closes) >= 50 else None
    e50_h1 = ema(h1_closes, 50) if len(h1_closes) >= 50 else None

    dead_zone = 0.1 * a
    side: Optional[str] = None
    if e20 is not None and e50 is not None and abs(e20 - e50) > dead_zone:
        side = "BUY" if e20 > e50 else "SELL"

    if side is None:
        factors.append(_factor("Tendance", 0, 25, False, "Pas de tendance claire sur M15 (EMA20 ≈ EMA50)"))
    else:
        h1_side = None
        if e20_h1 is not None and e50_h1 is not None:
            h1_side = "BUY" if e20_h1 > e50_h1 else "SELL"
        if h1_side == side:
            factors.append(_factor("Tendance", 25, 25, True, f"Tendance {('haussière' if side == 'BUY' else 'baissière')} alignée M15 + H1"))
        elif h1_side is None:
            factors.append(_factor("Tendance", 12, 25, True, f"Tendance M15 {('haussière' if side == 'BUY' else 'baissière')}, H1 indisponible"))
        else:
            factors.append(_factor("Tendance", 8, 25, False, "M15 et H1 en désaccord (contre-tendance)"))

    # ---------- 2. Momentum (15) ----------
    r = rsi(closes, 14)
    m = macd(closes)
    mom_pts = 0.0
    mom_details = []
    if r is not None and side:
        if side == "BUY" and 45 <= r <= 70:
            mom_pts += 8
            mom_details.append(f"RSI {r:.0f} favorable à l'achat")
        elif side == "SELL" and 30 <= r <= 55:
            mom_pts += 8
            mom_details.append(f"RSI {r:.0f} favorable à la vente")
        elif (side == "BUY" and r > 75) or (side == "SELL" and r < 25):
            mom_details.append(f"RSI {r:.0f} extrême (risque de retournement)")
        else:
            mom_pts += 3
            mom_details.append(f"RSI {r:.0f} neutre")
    if m is not None and side:
        _, _, hist = m
        if (side == "BUY" and hist > 0) or (side == "SELL" and hist < 0):
            mom_pts += 7
            mom_details.append("MACD confirme la direction")
        else:
            mom_details.append("MACD ne confirme pas")
    factors.append(_factor("Momentum", mom_pts, 15, mom_pts >= 10, " · ".join(mom_details) or "Indisponible"))

    # ---------- 3. Structure du marché (20) ----------
    struct_pts = 0.0
    struct_detail = "Pas de configuration structurelle"
    if side:
        lookback_highs = highs[-31:-1]
        lookback_lows = lows[-31:-1]
        recent_high = max(lookback_highs)
        recent_low = min(lookback_lows)
        if side == "BUY":
            if price > recent_high:
                struct_pts = 20
                struct_detail = f"Cassure haussière du plus haut récent ({recent_high:.5g})"
            elif price - recent_low < 0.8 * a:
                struct_pts = 14
                struct_detail = f"Rebond proche du support ({recent_low:.5g})"
            else:
                dist = (recent_high - price) / a if a else 99
                struct_pts = 8 if dist > 1.5 else 4
                struct_detail = "En range sous la résistance" if dist <= 1.5 else "Espace disponible avant résistance"
        else:
            if price < recent_low:
                struct_pts = 20
                struct_detail = f"Cassure baissière du plus bas récent ({recent_low:.5g})"
            elif recent_high - price < 0.8 * a:
                struct_pts = 14
                struct_detail = f"Rejet proche de la résistance ({recent_high:.5g})"
            else:
                dist = (price - recent_low) / a if a else 99
                struct_pts = 8 if dist > 1.5 else 4
                struct_detail = "En range au-dessus du support" if dist <= 1.5 else "Espace disponible avant support"
    factors.append(_factor("Structure", struct_pts, 20, struct_pts >= 12, struct_detail))

    # ---------- 4. Volatilité (15) ----------
    rel_atr = a / price if price else 0
    if rel_atr > 0.02:
        factors.append(_factor("Volatilité", 0, 15, False, f"Volatilité EXTRÊME (ATR {rel_atr*100:.2f}% du prix) — entrées suspendues"))
        blocking.append("volatilite_extreme")
    elif rel_atr < 0.00005:
        factors.append(_factor("Volatilité", 3, 15, False, "Marché atone (volatilité quasi nulle)"))
    else:
        factors.append(_factor("Volatilité", 15, 15, True, f"Volatilité saine (ATR {rel_atr*100:.3f}% du prix)"))

    # ---------- 5. Spread & session (15) ----------
    spread_pts = 0.0
    spread_details = []
    if mt5_connector.connected:
        spread_pct = await mt5_connector.get_spread_pct(symbol)
        max_spread = cfg.risk.max_spread_pct
        if spread_pct is None:
            spread_details.append("Spread indisponible")
        elif spread_pct <= max_spread:
            spread_pts += 10
            spread_details.append(f"Spread OK ({spread_pct:.4f}%)")
        else:
            spread_details.append(f"Spread anormal ({spread_pct:.4f}% > {max_spread}%)")
            blocking.append("spread_anormal")
    else:
        spread_pts += 10
        spread_details.append("Simulateur (spread non applicable)")
    now = datetime.now(timezone.utc)
    is_weekend = now.weekday() >= 5
    is_rollover = now.hour == 21 and now.minute >= 45 or (now.hour == 22 and now.minute <= 15)
    if category == "crypto":
        spread_pts += 5
        spread_details.append("Crypto: marché 24/7")
    elif is_weekend:
        spread_details.append("Week-end: marché fermé")
        blocking.append("marche_ferme")
    elif is_rollover:
        spread_details.append("Rollover (22h UTC): liquidité réduite")
    else:
        spread_pts += 5
        spread_details.append("Session liquide")
    factors.append(_factor("Spread & liquidité", spread_pts, 15, spread_pts >= 10, " · ".join(spread_details)))

    # ---------- 6. Régime de marché (10) ----------
    regime_info = detect_regime(closes)
    regime_store.update(symbol, regime_info)
    regime = regime_info.get("regime", "UNKNOWN")
    if regime == "TREND" and side:
        factors.append(_factor("Régime", 10, 10, True, "Régime TENDANCE: favorable au suivi de tendance"))
    elif regime == "RANGE":
        factors.append(_factor("Régime", 5, 10, True, "Régime RANGE: signaux de cassure à confirmer"))
    elif regime == "VOLATILE":
        factors.append(_factor("Régime", 0, 10, False, "Régime VOLATILE: prudence"))
    else:
        factors.append(_factor("Régime", 5, 10, True, f"Régime {regime}"))

    # ---------- Score & décision ----------
    score = round(sum(f["points"] for f in factors))
    result.update({
        "side": side, "score": score, "factors": factors, "blocking": blocking,
        "regime": regime, "atr": a, "price": price,
    })

    if side is None:
        result["decision"] = "NO_SIGNAL"
        result["summary"] = "Aucune direction exploitable — aucune position ouverte."
    elif blocking:
        result["decision"] = "REJECT"
        result["summary"] = f"Signal {side} rejeté: " + ", ".join(blocking)
    elif score >= result["threshold"]:
        result["decision"] = "EXECUTE"
        result["summary"] = f"Signal {side} validé: score {score}/{100} ≥ seuil {result['threshold']}"
    else:
        result["decision"] = "REJECT"
        result["summary"] = f"Signal {side} rejeté: score {score} < seuil {result['threshold']}"

    latest_evals[symbol] = result
    return result


def should_evaluate(symbol: str) -> bool:
    """Throttle: max one evaluation per symbol per EVAL_INTERVAL_SEC."""
    import time
    now = time.time()
    if now - _eval_ts.get(symbol, 0) >= EVAL_INTERVAL_SEC:
        _eval_ts[symbol] = now
        return True
    return False


def effective_symbols(cfg) -> List[str]:
    """Markets the bot is allowed to analyze/trade (user-controlled)."""
    if getattr(cfg, "single_symbol_mode", False) and getattr(cfg, "single_symbol", None):
        return [cfg.single_symbol]
    return list(cfg.symbols or [])
