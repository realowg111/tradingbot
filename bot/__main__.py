"""Ligne de commande du bot.

  python -m bot run                       lance le bot en continu (paper ou live selon config)
  python -m bot backtest --data XAUUSD=data/XAUUSD_M5.csv --data BTCUSD=data/BTCUSD_M5.csv
  python -m bot fetch --days 180          télécharge l'historique M5 depuis le broker configuré
  python -m bot status                    état du bot (capital, positions, arrêt éventuel)
  python -m bot reset-halt                relance le trading après un kill switch (décision humaine)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config, load_env


def cmd_run(cfg, args):
    from .engine import Engine
    from .notifier import setup_logging

    setup_logging(cfg.bot.log_file)
    if cfg.bot.mode == "live" and not args.yes_live:
        print("Mode LIVE : argent réel. Relancer avec --yes-live pour confirmer.")
        sys.exit(1)
    Engine(cfg).run()


def cmd_backtest(cfg, args):
    import pandas as pd

    from . import backtest as bt
    from .data import load_csv, synthetic

    data = {}
    for item in args.data or []:
        name, path = item.split("=", 1)
        data[name] = load_csv(path)
    if args.synthetic:
        for i, s in enumerate(cfg.symbols):
            data[s.name] = synthetic(args.synthetic, start=2000 if s.group == "gold" else 50000, seed=i + 1)
    if not data:
        print("Donner --data SYMBOLE=fichier.csv (bougies M5) ou --synthetic N")
        sys.exit(1)

    all_trades = []
    for name, df in data.items():
        sym = cfg.symbol(name)
        ref = data.get(sym.ref["name"]) if sym.ref else None
        trades, curve = bt.run(df, sym, cfg, ref, equity=args.equity)
        all_trades += trades
        print(f"\n=== {name} ({df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}) ===")
        for k, v in bt.stats(trades, curve, args.equity).items():
            print(f"  {k:24s} {v}")
        if trades:
            f = bt.trades_frame(trades)
            print("  par setup :")
            print(f.groupby("setup")["r"].agg(trades="count", esperance_R="mean").round(3).to_string())
    if args.out and all_trades:
        bt.trades_frame(all_trades).to_csv(args.out, index=False)
        print(f"\nTrades exportés dans {args.out}")


def cmd_fetch(cfg, args):
    import pandas as pd

    from .engine import make_feed

    feed = make_feed(cfg)
    feed.connect()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bars = args.days * 288
    for s in cfg.symbols:
        if cfg.bot.broker == "mt5":
            df = feed.candles(s.name, "5m", bars)
        else:  # ccxt : pagination par paquets
            import time
            since = int((pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=args.days)).timestamp() * 1000)
            rows = []
            while True:
                chunk = feed.ex.fetch_ohlcv(feed._s(s.name), "5m", since=since, limit=1000)
                if not chunk:
                    break
                rows += chunk
                since = chunk[-1][0] + 1
                if len(chunk) < 2:
                    break
                time.sleep(feed.ex.rateLimit / 1000)
            df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
            df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
            df = df.drop_duplicates("time").set_index("time")
        path = out / f"{s.name}_M5.csv"
        df.to_csv(path, index_label="time")
        print(f"{s.name} : {len(df)} bougies -> {path}")
    feed.shutdown()


def cmd_status(cfg, args):
    p = Path(cfg.bot.state_file)
    if not p.exists():
        print("Aucun état sauvegardé (le bot n'a pas encore tourné).")
        return
    st = json.loads(p.read_text())
    r = st.get("risk", {})
    print(f"Dernière sauvegarde : {st.get('saved_at')}")
    print(f"Arrêté : {r.get('halted')} {r.get('halt_reason', '')}")
    print(f"Pertes consécutives : {r.get('consecutive_losses')} | trades aujourd'hui : {r.get('trades_today')}")
    print(f"Plus haut du capital : {r.get('peak_equity')}")
    for pos in st.get("positions", {}).values():
        print(f"  {pos['symbol']} {'achat' if pos['side'] == 1 else 'vente'} {pos['volume']} @ {pos['entry']} "
              f"SL {pos['sl']:.5g} TP1 fait : {pos['tp1_done']}")


def cmd_reset_halt(cfg, args):
    p = Path(cfg.bot.state_file)
    st = json.loads(p.read_text())
    r = st.setdefault("risk", {})
    print(f"Levée de l'arrêt : {r.get('halt_reason')}")
    r.update(halted=False, halt_reason="", paused_until="", consecutive_losses=0)
    if args.new_peak:
        r["peak_equity"] = 0.0  # le plus haut repart du capital actuel
    p.write_text(json.dumps(st, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bot", description="Bot scalper or + crypto")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--env", default=".env")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--yes-live", action="store_true")
    b = sub.add_parser("backtest")
    b.add_argument("--data", action="append", help="SYMBOLE=chemin.csv (bougies M5)")
    b.add_argument("--synthetic", type=int, default=0, help="nb de bougies simulées (test de mécanique)")
    b.add_argument("--equity", type=float, default=10_000.0)
    b.add_argument("--out", default="")
    f = sub.add_parser("fetch")
    f.add_argument("--days", type=int, default=180)
    f.add_argument("--out-dir", default="data")
    sub.add_parser("status")
    h = sub.add_parser("reset-halt")
    h.add_argument("--new-peak", action="store_true", help="repartir du capital actuel comme nouveau plus haut")

    args = ap.parse_args(argv)
    load_env(args.env)
    cfg = load_config(args.config)
    {"run": cmd_run, "backtest": cmd_backtest, "fetch": cmd_fetch, "status": cmd_status,
     "reset-halt": cmd_reset_halt}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
