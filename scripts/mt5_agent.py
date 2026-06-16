"""Agent Passerelle MT5 - s'exécute sur PC/VPS Windows avec MT5.

Cet agent expose MT5 en tant qu'API REST HTTP pour les backends distants.
À déployer sur Windows (avec MT5 installé + terminal lancé).

Utilisation:
    python scripts/mt5_agent.py

Variables d'environnement:
    MT5_AGENT_HOST=0.0.0.0 (défaut)
    MT5_AGENT_PORT=5555 (défaut)
    MT5_TERMINAL_PATH=C:/Program Files/MetaTrader 5/terminal64.exe (optionnel)
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

# Essayer d'importer MetaTrader5 (Windows uniquement)
try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mt5_agent")

app = Flask(__name__)
CORS(app)

# État global
_connected = False
_login: Optional[str] = None
_server: Optional[str] = None
_last_error: Optional[str] = None
_last_heartbeat: Optional[datetime] = None


def _init_mt5(login: str, password: str, server: str, path: Optional[str] = None) -> bool:
    """Initialiser la connexion MT5."""
    global _connected, _login, _server, _last_error, _last_heartbeat

    if not HAS_MT5:
        _last_error = "Librairie MetaTrader5 non disponible (Windows + pip install MetaTrader5 requis)"
        return False

    try:
        init_kwargs = {"login": int(login), "password": password, "server": server}
        if path and Path(path).exists():
            init_kwargs["path"] = path

        ok = mt5.initialize(**init_kwargs)
        if not ok:
            err = mt5.last_error()
            _last_error = f"Initialisation MT5 échouée: {err}"
            _connected = False
            return False

        _connected = True
        _login = login
        _server = server
        _last_error = None
        _last_heartbeat = datetime.now(timezone.utc)
        logger.info("✅ MT5 connecté: login=%s server=%s", login, server)
        return True
    except Exception as e:
        _last_error = str(e)
        _connected = False
        logger.error("❌ Erreur initialisation MT5: %s", e)
        return False


def _shutdown_mt5():
    """Arrêter MT5 proprement."""
    global _connected
    if HAS_MT5 and _connected:
        try:
            mt5.shutdown()
        except Exception:
            pass
    _connected = False


def _health_check() -> bool:
    """Vérifier que MT5 est toujours vivant."""
    if not _connected or not HAS_MT5:
        return False
    try:
        term = mt5.terminal_info()
        acct = mt5.account_info()
        return term is not None and acct is not None
    except Exception:
        return False


# ============= Points d'accès HTTP =============

@app.route("/health", methods=["GET"])
def health():
    """Vérification santé du service."""
    healthy = _health_check()
    if not healthy and _connected:
        global _connected
        _connected = False
    return jsonify({
        "connected": _connected,
        "login": _login,
        "server": _server,
        "last_error": _last_error,
        "last_heartbeat": _last_heartbeat.isoformat() if _last_heartbeat else None,
    }), (200 if _connected else 503)


@app.route("/connect", methods=["POST"])
def connect():
    """Se connecter à MT5 avec identifiants."""
    try:
        data = request.get_json() or {}
        login = data.get("login")
        password = data.get("password")
        server = data.get("server")
        path = data.get("path")

        if not all([login, password, server]):
            return jsonify({"error": "Identifiants manquants (login/password/server)"}), 400

        if _connected:
            _shutdown_mt5()

        ok = _init_mt5(login, password, server, path)
        if not ok:
            return jsonify({
                "connected": False,
                "error": _last_error,
            }), 400

        return jsonify({
            "connected": True,
            "login": login,
            "server": server,
            "message": "Connecté",
        }), 200
    except Exception as e:
        logger.exception("Erreur connect")
        return jsonify({"error": str(e)}), 500


@app.route("/disconnect", methods=["POST"])
def disconnect():
    """Déconnecter de MT5."""
    _shutdown_mt5()
    return jsonify({"disconnected": True}), 200


@app.route("/account", methods=["GET"])
def get_account():
    """Récupérer les infos du compte."""
    if not _connected:
        return jsonify({"error": "Non connecté"}), 400

    try:
        info = mt5.account_info()
        if info is None:
            return jsonify({"error": "Impossible de récupérer les infos du compte"}), 500

        return jsonify({
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
            "name": info.name,
            "server": info.server,
            "login": info.login,
        }), 200
    except Exception as e:
        logger.exception("Erreur get_account")
        return jsonify({"error": str(e)}), 500


@app.route("/positions", methods=["GET"])
def get_positions():
    """Récupérer toutes les positions ouvertes."""
    if not _connected:
        return jsonify({"error": "Non connecté"}), 400

    try:
        positions = mt5.positions_get()
        if not positions:
            return jsonify([]), 200

        out = []
        for p in positions:
            out.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "side": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "entry_price": p.price_open,
                "current_price": p.price_current,
                "stop_loss": p.sl,
                "take_profit": p.tp,
                "pnl": p.profit,
                "swap": p.swap,
                "opened_at": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                "comment": p.comment,
            })
        return jsonify(out), 200
    except Exception as e:
        logger.exception("Erreur get_positions")
        return jsonify({"error": str(e)}), 500


@app.route("/price/<symbol>", methods=["GET"])
def get_price(symbol: str):
    """Récupérer bid/ask pour un symbole."""
    if not _connected:
        return jsonify({"error": "Non connecté"}), 400

    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return jsonify({"error": f"Pas de prix pour {symbol}"}), 404

        return jsonify({
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
        }), 200
    except Exception as e:
        logger.exception("Erreur get_price")
        return jsonify({"error": str(e)}), 500


@app.route("/history", methods=["GET"])
def get_history():
    """Récupérer l'historique des deals (N derniers jours)."""
    if not _connected:
        return jsonify({"error": "Non connecté"}), 400

    try:
        days = int(request.args.get("days", 30))
        date_from = datetime.now() - timedelta(days=days)
        date_to = datetime.now() + timedelta(days=2)

        deals = mt5.history_deals_get(date_from, date_to)
        if not deals:
            return jsonify([]), 200

        out = []
        for d in deals:
            out.append({
                "ticket": d.ticket,
                "position_id": d.position_id,
                "order": d.order,
                "symbol": d.symbol,
                "type": d.type,
                "entry": d.entry,
                "magic": d.magic,
                "comment": d.comment,
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "commission": d.commission,
                "swap": d.swap,
                "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
            })
        return jsonify(out), 200
    except Exception as e:
        logger.exception("Erreur get_history")
        return jsonify({"error": str(e)}), 500


@app.route("/order", methods=["POST"])
def place_order():
    """Placer un ordre au marché."""
    if not _connected:
        return jsonify({"ok": False, "error": "Non connecté"}), 400

    try:
        data = request.get_json() or {}
        symbol = data.get("symbol")
        side = data.get("side", "BUY").upper()
        volume = float(data.get("volume", 0))
        sl = float(data.get("sl", 0))
        tp = float(data.get("tp", 0))
        comment = data.get("comment", "TradingBot")

        if not symbol or side not in ("BUY", "SELL"):
            return jsonify({"ok": False, "error": "Symbole/côté invalide"}), 400

        info = mt5.symbol_info_tick(symbol)
        if info is None:
            return jsonify({"ok": False, "error": f"Pas de prix pour {symbol}"}), 400

        price = info.ask if side == "BUY" else info.bid

        request_dict = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": 234000,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request_dict)
        if result is None:
            return jsonify({
                "ok": False,
                "error": str(mt5.last_error()),
            }), 400

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return jsonify({
                "ok": False,
                "error": f"retcode={result.retcode} comment={result.comment}",
            }), 400

        return jsonify({
            "ok": True,
            "ticket": result.order,
            "price": result.price,
            "volume": result.volume,
        }), 200
    except Exception as e:
        logger.exception("Erreur place_order")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/close", methods=["POST"])
def close_position():
    """Fermer une position ouverte par ticket."""
    if not _connected:
        return jsonify({"ok": False, "error": "Non connecté"}), 400

    try:
        data = request.get_json() or {}
        ticket = int(data.get("ticket", 0))

        if not ticket:
            return jsonify({"ok": False, "error": "Ticket manquant"}), 400

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return jsonify({"ok": False, "error": "Position introuvable"}), 404

        p = positions[0]
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            return jsonify({"ok": False, "error": f"Pas de prix pour {p.symbol}"}), 400

        price = tick.bid if p.type == 0 else tick.ask

        request_dict = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": p.ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "TradingBot Fermeture",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request_dict)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return jsonify({
                "ok": False,
                "error": str(mt5.last_error()) if result is None else f"retcode={result.retcode}",
            }), 400

        return jsonify({
            "ok": True,
            "price": result.price,
        }), 200
    except Exception as e:
        logger.exception("Erreur close_position")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/candles/<symbol>", methods=["GET"])
def get_candles(symbol: str):
    """Récupérer les bougies OHLC."""
    if not _connected:
        return jsonify({"error": "Non connecté"}), 400

    try:
        timeframe = request.args.get("timeframe", "M15")
        count = int(request.args.get("count", 200))

        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)

        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if not rates or len(rates) == 0:
            return jsonify([]), 200

        out = []
        for r in rates:
            out.append({
                "time": datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["tick_volume"]),
            })
        return jsonify(out), 200
    except Exception as e:
        logger.exception("Erreur get_candles")
        return jsonify({"error": str(e)}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Point d'accès introuvable"}), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Erreur serveur: %s", e)
    return jsonify({"error": "Erreur serveur interne"}), 500


if __name__ == "__main__":
    if not HAS_MT5:
        logger.error(
            "❌ Librairie MetaTrader5 non installée!\n"
            "Installez: pip install MetaTrader5\n"
            "(Windows uniquement, nécessite un terminal MT5 lancé)"
        )
        exit(1)

    host = os.environ.get("MT5_AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("MT5_AGENT_PORT", 5555))

    logger.info("🚀 Agent Passerelle MT5 démarrage sur %s:%d", host, port)
    logger.info("ℹ️  Assurez-vous que le terminal MT5 est lancé avant la connexion!")

    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Arrêt...")
        _shutdown_mt5()
