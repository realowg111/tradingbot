"""Aggressive-but-controlled variants of the trend strategy (crypto, weekly, since 2018).

Levers tested:
- higher volatility target (20% -> 60%) and leverage cap (1x -> 3x)
- faster signal (4/12 weeks instead of 4/12/26/52)
- drawdown brake: exposure scaled down as the account falls from its peak,
  and a hard stop (go to cash) beyond a max drawdown, re-armed at a new signal.
"""
import numpy as np, pandas as pd
import auto_strategy_backtest as a

C3 = ["BTC", "ETH", "SOL"]

def weights(px, lookbacks, tv, cap):
    return a.tsmom(px, C3, lookbacks=lookbacks, target_vol=tv, max_gross=cap)

def run_with_brake(w, px, brake_start=None, hard_stop=None, cooldown=4):
    """Path-dependent: scale weights by drawdown. brake_start=0.10 -> linear cut from -10%
    to zero at hard_stop; after a hard stop, stay in cash `cooldown` weeks then restart
    with peak reset (so the account can recover)."""
    r = px.pct_change().fillna(0)
    w = w.reindex(index=px.index, columns=px.columns).fillna(0)
    eq, peak, held = 1.0, 1.0, pd.Series(0.0, index=px.columns)
    out, cool, started = [], 0, False
    for i, t in enumerate(px.index):
        # P&L of the week with positions held from last close
        ret = float((held * r.loc[t]).sum())
        cost = 0.0
        for s in px.columns:
            fee, fund, both = a.COST[s]
            cost += (abs(held[s]) if both else held[s]) * fund * 7
        eq *= 1 + ret - cost
        peak = max(peak, eq)
        dd = eq / peak - 1
        # decide new target
        k = 1.0
        if cool > 0:
            cool -= 1; k = 0.0
            if cool == 0: peak = eq
        elif hard_stop is not None and dd <= -hard_stop:
            k, cool = 0.0, cooldown
        elif brake_start is not None and dd < -brake_start:
            k = max(0.0, 1 - (-dd - brake_start) / (hard_stop - brake_start))
        target = w.loc[t] * k
        turn = (target - held).abs()
        fees = sum(turn[s] * a.COST[s][0] for s in px.columns)
        eq *= 1 - fees
        held = target
        if not started and target.abs().sum() > 0: started = True
        if started: out.append((t, eq))
    s = pd.Series(dict(out))
    return s, s.pct_change().fillna(s.iloc[0] - 1)

def row(name, eq, net):
    st = a.stats(eq, net, name)
    y = (1 + net).groupby(net.index.year).prod() - 1
    st["pire_annee"] = y.min()
    st["meilleure_annee"] = y.max()
    st["mois_neg"] = f"{((1 + net).resample('ME').prod() - 1).lt(0).mean():.0%}"
    return st

if __name__ == "__main__":
    pd.set_option("display.width", 240)
    px = a.prices(C3)
    rows = []
    configs = [
        ("Actuelle (vol20, 1x, 4/12/26/52)", (4, 12, 26, 52), 0.20, 1.0, None, None),
        ("Vol40, 2x", (4, 12, 26, 52), 0.40, 2.0, None, None),
        ("Vol60, 3x", (4, 12, 26, 52), 0.60, 3.0, None, None),
        ("Rapide 4/12, vol40, 2x", (4, 12), 0.40, 2.0, None, None),
        ("Rapide 4/12, vol60, 3x", (4, 12), 0.60, 3.0, None, None),
        ("Rapide 4/12, vol40, 2x + frein 10%/25%", (4, 12), 0.40, 2.0, 0.10, 0.25),
        ("Rapide 4/12, vol60, 3x + frein 10%/25%", (4, 12), 0.60, 3.0, 0.10, 0.25),
        ("Rapide 4/12, vol60, 3x + frein 15%/30%", (4, 12), 0.60, 3.0, 0.15, 0.30),
        ("Vol40, 2x + frein 10%/25%", (4, 12, 26, 52), 0.40, 2.0, 0.10, 0.25),
    ]
    for name, lb, tv, cap, bs, hs in configs:
        w = weights(px, lb, tv, cap)
        if bs is None:
            eq, net = a.backtest(w, px)
        else:
            eq, net = run_with_brake(w, px, bs, hs)
        rows.append(row(name, eq, net))
    df = pd.DataFrame(rows)
    for c in ("cagr", "maxdd", "worst_week", "total", "pire_annee", "meilleure_annee"):
        df[c] = df[c].map(lambda x: f"{x:+.0%}")
    df["sharpe"] = df["sharpe"].map(lambda x: f"{x:.2f}")
    print(df[["strat", "cagr", "maxdd", "worst_week", "pire_annee", "meilleure_annee", "mois_neg", "pos_years", "sharpe", "total"]].to_string(index=False))

    print("\nYear by year (best controlled candidate vs current):")
    for name, lb, tv, cap, bs, hs in [configs[0], configs[5], configs[6]]:
        w = weights(px, lb, tv, cap)
        eq, net = (a.backtest(w, px) if bs is None else run_with_brake(w, px, bs, hs))
        y = (1 + net).groupby(net.index.year).prod() - 1
        print(f"  {name:42s} " + "  ".join(f"{k}:{v:+.0%}" for k, v in y.items()))

    print("\nRobustness of 'Rapide vol60 3x + frein 10/25' to the signal window:")
    for lb in [(4,), (8,), (12,), (4, 12), (4, 8, 12), (4, 12, 26), (4, 12, 26, 52)]:
        eq, net = run_with_brake(weights(px, lb, 0.60, 3.0), px, 0.10, 0.25)
        s = a.stats(eq, net, "")
        print(f"  {str(lb):16s} CAGR {s['cagr']:+.0%}  MaxDD {s['maxdd']:+.0%}  pire semaine {s['worst_week']:+.0%}")

    print("\nSame start date for all (fair comparison) — CAGR / MaxDD / worst week:")
    periods = [("2018-09-09", None, "2018->2026"), ("2022-01-01", None, "2022->2026"), ("2024-01-01", None, "2024->2026")]
    for name, lb, tv, cap, bs, hs in configs:
        w = weights(px, lb, tv, cap)
        eq, net = (a.backtest(w, px) if bs is None else run_with_brake(w, px, bs, hs))
        parts = []
        for start, _, lab in periods:
            n = net.loc[start:]; e = (1 + n).cumprod()
            s = a.stats(e, n, "")
            parts.append(f"{lab}: {s['cagr']:+.0%}/{s['maxdd']:+.0%}/{s['worst_week']:+.0%}")
        print(f"  {name:42s} " + "   ".join(parts))
