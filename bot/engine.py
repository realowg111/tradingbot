"""Moteur autonome : tourne en continu, gère les positions à chaque cotation,
cherche des entrées à chaque clôture de bougie, se reconnecte seul et
sauvegarde son état pour reprendre après un redémarrage.
"""
from __future__ import annotations

import json
import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .brokers.base import Broker
from .brokers.paper import PaperBroker
from .config import Config, SymbolConfig
from .manager import Action, Position, TradeManager
from .notifier import Journal, Notifier
from .risk import RiskManager, RiskState
from .strategy import TF_MINUTES, prepare, signal_at

log = logging.getLogger("bot")


def make_feed(cfg: Config) -> Broker:
    if cfg.bot.broker == "mt5":
        from .brokers.mt5 import MT5Broker
        return MT5Broker(cfg.mt5)
    if cfg.bot.broker == "ccxt":
        from .brokers.ccxt_broker import CCXTBroker
        return CCXTBroker(cfg.ccxt)
    raise ValueError(f"broker inconnu : {cfg.bot.broker}")


class Engine:
    def __init__(self, cfg: Config, broker: Broker | None = None, clock=None):
        self.cfg = cfg
        self.now = clock or (lambda: datetime.now(timezone.utc))
        self.state_path = Path(cfg.bot.state_file)
        st = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        feed = broker or make_feed(cfg)
        if cfg.bot.mode == "paper" and not isinstance(feed, PaperBroker):
            feed = PaperBroker(feed, cfg.symbols, cfg.bot.paper_starting_equity, st.get("paper"))
        self.broker = feed
        self.risk = RiskManager(cfg.risk, RiskState(**st.get("risk", {})))
        self.positions: dict[str, Position] = {k: Position(**v) for k, v in st.get("positions", {}).items()}
        self.last_bar: dict[str, str] = st.get("last_bar", {})
        self.next_allowed: dict[str, str] = st.get("next_allowed", {})
        self.atr: dict[str, float] = st.get("atr", {})
        self.notifier = Notifier(cfg.telegram)
        self.journal = Journal(cfg.bot.journal_file)
        self.running = True
        self._last_heartbeat = 0.0
        self._tms: dict[str, TradeManager] = {}

    # --- Persistance ---
    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "saved_at": self.now().isoformat(),
            "risk": self.risk.to_dict(),
            "positions": {k: p.to_dict() for k, p in self.positions.items()},
            "last_bar": self.last_bar, "next_allowed": self.next_allowed, "atr": self.atr,
        }
        if isinstance(self.broker, PaperBroker):
            data["paper"] = self.broker.export()
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(self.state_path)  # écriture atomique : pas d'état corrompu en cas de coupure

    def tm(self, symbol: str) -> TradeManager:
        if symbol not in self._tms:
            sp = self.broker.spec(symbol)
            self._tms[symbol] = TradeManager(self.cfg.management, sp.volume_step, sp.volume_min)
        return self._tms[symbol]

    # --- Boucle principale ---
    def run(self) -> None:
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)
        self._connect()
        self.reconcile()
        self.notifier.send(f"Bot démarré ({self.cfg.bot.mode}, {self.broker.name}) — capital {self.broker.equity():.2f}")
        errors = 0
        while self.running:
            try:
                self.step()
                errors = 0
                time.sleep(self.cfg.bot.poll_seconds)
            except Exception as e:
                errors += 1
                wait = min(300, 5 * 2 ** min(errors, 6))
                log.exception("Erreur (%s consécutives), nouvelle tentative dans %ss : %s", errors, wait, e)
                if errors in (3, 10, 30):
                    self.notifier.send(f"⚠️ {errors} erreurs de suite : {e}")
                time.sleep(wait)
                if errors >= 3:
                    self._connect()
        self.shutdown()

    def _stop(self, *_):
        log.info("Arrêt demandé")
        self.running = False

    def _connect(self) -> None:
        delay = 5
        while self.running:
            try:
                self.broker.connect()
                return
            except Exception as e:
                log.error("Connexion impossible (%s), nouvel essai dans %ss", e, delay)
                time.sleep(delay)
                delay = min(delay * 2, 300)

    def shutdown(self) -> None:
        if self.cfg.bot.close_positions_on_shutdown:
            for p in list(self.positions.values()):
                self._close(p, "arrêt du bot")
        self.save()
        self.broker.shutdown()
        self.notifier.send("Bot arrêté (les positions ouvertes gardent leur SL chez le broker)")

    def step(self) -> None:
        now = self.now()
        equity = self.broker.equity()
        was_halted = self.risk.s.halted
        self.risk.on_tick(now, equity)
        if self.risk.s.halted and not was_halted:
            self.notifier.send(f"🛑 Trading suspendu : {self.risk.s.halt_reason}")
        if self.risk.s.halted and self.risk.s.halt_reason.startswith("total"):
            for p in list(self.positions.values()):
                self._close(p, "kill switch drawdown")

        self.sync_closed(now)
        for sym in self.cfg.symbols:
            try:
                self._manage_symbol(sym, now)
            except Exception as e:
                log.exception("%s : %s", sym.name, e)
        self.save()
        if time.time() - self._last_heartbeat > 300:
            self._last_heartbeat = time.time()
            log.info("♥ capital %.2f | DD %.2f %% | positions %d | trades jour %d%s", equity,
                     self.risk.drawdown_pct(equity), len(self.positions), self.risk.s.trades_today,
                     f" | {self.risk.s.halt_reason}" if self.risk.s.halted else "")

    # --- Par actif ---
    def _manage_symbol(self, sym: SymbolConfig, now: datetime) -> None:
        bid, ask = self.broker.quote(sym.name)
        self.sync_closed(now)  # un stop a pu être touché entre deux cycles
        atr = self.atr.get(sym.name, 0.0)
        for p in [p for p in self.positions.values() if p.symbol == sym.name]:
            price = bid if p.side == 1 else ask
            for act in self.tm(sym.name).on_price(p, price, atr):
                self._apply(p, act)
        self._on_bar(sym, now, bid, ask)

    def _on_bar(self, sym: SymbolConfig, now: datetime, bid: float, ask: float) -> None:
        cfg = self.cfg
        ltf = self.broker.candles(sym.name, cfg.bot.ltf, 600)
        if len(ltf) < 250:
            return
        last = ltf.index[-1].isoformat()
        if self.last_bar.get(sym.name) == last:
            return
        self.last_bar[sym.name] = last
        tfm = TF_MINUTES[cfg.bot.ltf]
        if now - ltf.index[-1].to_pydatetime() > pd.Timedelta(minutes=3 * tfm):
            return  # marché fermé ou flux figé : on n'ouvre rien

        htf = self.broker.candles(sym.name, cfg.bot.htf, 300)
        ref = self.broker.candles(sym.ref["name"], cfg.bot.htf, 300) if sym.ref else None
        c = prepare(ltf, htf, cfg.strategy, cfg.bot.ltf, cfg.bot.htf, ref)
        self.atr[sym.name] = float(c["atr"].iloc[-1])

        for p in [p for p in self.positions.values() if p.symbol == sym.name]:
            for act in self.tm(sym.name).on_bar_close(p):
                self._apply(p, act)

        if self.next_allowed.get(sym.name, "") > now.isoformat():
            return
        sig = signal_at(c, len(c) - 1, sym, cfg.strategy, spread=ask - bid, ts=now)
        if sig is None:
            return
        ok, why = self.risk.can_open(now, list(self.positions.values()), sym.name, sym.group)
        if not ok:
            log.info("%s : signal %s ignoré (%s)", sym.name, sig.setup, why)
            return
        self._open(sym, sig, now, bid, ask)

    def _open(self, sym: SymbolConfig, sig, now: datetime, bid: float, ask: float) -> None:
        spec = self.broker.spec(sym.name)
        entry = ask if sig.side == 1 else bid
        r = abs(sig.entry - sig.sl)
        sl = entry - sig.side * r
        tp2 = entry + sig.side * self.cfg.management.tp2_r * r
        equity = self.broker.equity()
        vol, risk_amt = self.risk.position_size(equity, entry, sl, spec,
                                                cost_per_lot=sym.commission_per_lot + (ask - bid) * spec.value_per_point)
        if vol <= 0:
            log.info("%s : lot minimum trop risqué pour ce stop, trade ignoré", sym.name)
            return
        ticket, fill = self.broker.open(sym.name, sig.side, vol, sl, tp2, f"scalp {sig.setup} {sig.score}")
        pos = self.tm(sym.name).make_position(ticket, sig, vol, sym.group, now.isoformat(), entry=fill, sl=sl)
        pos.tp2 = tp2
        pos.tickets = [ticket]
        self.positions[ticket] = pos
        self.risk.on_trade_opened()
        cool = pd.Timestamp(now) + pd.Timedelta(minutes=TF_MINUTES[self.cfg.bot.ltf] * self.cfg.strategy.signal_cooldown_bars)
        self.next_allowed[sym.name] = cool.isoformat()
        self.notifier.send(
            f"{'🟢 ACHAT' if sig.side == 1 else '🔴 VENTE'} {sym.name} {vol} lot @ {fill:.5g}\n"
            f"SL {sl:.5g} | TP1 {pos.tp1:.5g} | TP2 {tp2:.5g} | risque {risk_amt:.2f}\n"
            f"{sig.setup}, score {sig.score}/14 : {', '.join(sig.reasons)}")

    def _apply(self, p: Position, act: Action) -> None:
        try:
            if act.kind == "partial":
                px = self.broker.close(p.id, p.symbol, act.volume)
                vpp = self.broker.spec(p.symbol).value_per_point
                p.realized += (px - p.entry) * p.side * act.volume * vpp
                p.volume = round(p.volume - act.volume, 8)
                self.notifier.send(f"💰 {p.symbol} TP1 : {act.volume} lot encaissé @ {px:.5g}")
            elif act.kind == "move_sl":
                self.broker.modify(p.id, p.symbol, act.price, p.tp2)
                p.sl = act.price
                log.info("%s %s", p.symbol, act.reason)
            elif act.kind == "close":
                self._close(p, act.reason)
        except Exception as e:
            if act.kind == "partial":
                p.tp1_done = False  # on retentera l'encaissement partiel
            log.warning("%s : action %s échouée (%s), nouvel essai au prochain cycle", p.symbol, act.kind, e)

    def _close(self, p: Position, reason: str) -> None:
        try:
            px = self.broker.close(p.id, p.symbol)
        except Exception as e:
            log.warning("%s : fermeture impossible (%s)", p.symbol, e)
            return
        vpp = self.broker.spec(p.symbol).value_per_point
        est = p.realized + (px - p.entry) * p.side * p.volume * vpp
        pnl = self.broker.closed_pnl(p.id)
        self._finalize(p, est if pnl is None else pnl, reason)

    def sync_closed(self, now: datetime) -> None:
        """Positions fermées côté broker (SL/TP touchés) : on les enregistre."""
        live = {bp.ticket for bp in self.broker.positions()}
        for p in list(self.positions.values()):
            if p.id not in live:
                pnl = self.broker.closed_pnl(p.id)
                if pnl is None:
                    vpp = self.broker.spec(p.symbol).value_per_point
                    pnl = p.realized + (p.sl - p.entry) * p.side * p.volume * vpp
                if pnl > 0 and p.mfe_r >= self.cfg.management.tp2_r * 0.95:
                    reason = "TP2"
                else:
                    reason = "stop suiveur" if p.tp1_done else "stop"
                self._finalize(p, pnl, reason)

    def _finalize(self, p: Position, pnl: float, reason: str) -> None:
        now = self.now()
        risk_amt = p.r_dist * p.initial_volume * self.broker.spec(p.symbol).value_per_point
        r = pnl / risk_amt if risk_amt else 0.0
        self.risk.on_trade_closed(pnl, now)
        self.journal.write({
            "closed_at": now.isoformat(), "symbol": p.symbol, "side": p.side, "setup": p.setup, "score": p.score,
            "opened_at": p.opened_at, "entry": p.entry, "initial_sl": p.initial_sl, "volume": p.initial_volume,
            "risk_amount": round(risk_amt, 2), "pnl": round(pnl, 2), "r": round(r, 2), "tp1_hit": p.tp1_done,
            "reason": reason,
        })
        self.positions.pop(p.id, None)
        self.notifier.send(f"{'✅' if pnl > 0 else '❌' if pnl < 0 else '➖'} {p.symbol} fermé ({reason}) : "
                           f"{pnl:+.2f} ({r:+.2f}R)")

    def reconcile(self) -> None:
        """Au démarrage : aligne l'état sauvegardé sur les positions réelles du broker."""
        self.sync_closed(self.now())
        known = set(self.positions)
        for bp in self.broker.positions():
            if bp.ticket in known:
                continue
            if not bp.sl:
                log.warning("Position %s %s sans stop : fermeture par sécurité", bp.symbol, bp.ticket)
                try:
                    self.broker.close(bp.ticket, bp.symbol)
                except Exception as e:
                    log.error("Fermeture impossible : %s", e)
                continue
            log.warning("Position %s %s inconnue reprise en gestion", bp.symbol, bp.ticket)
            sym = next((s for s in self.cfg.symbols if s.name == bp.symbol), None)
            r = abs(bp.entry - bp.sl)
            self.positions[bp.ticket] = Position(
                id=bp.ticket, symbol=bp.symbol, group=sym.group if sym else "", side=bp.side, entry=bp.entry,
                sl=bp.sl, initial_sl=bp.sl, tp1=bp.entry + bp.side * self.cfg.management.tp1_r * r,
                tp2=bp.tp or bp.entry + bp.side * self.cfg.management.tp2_r * r, volume=bp.volume,
                initial_volume=bp.volume, opened_at=self.now().isoformat(), setup="repris")
