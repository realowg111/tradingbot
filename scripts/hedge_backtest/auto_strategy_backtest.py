"""Search for a robust, low-maintenance automated strategy (crypto + gold).

Weekly data: BTC/ETH since 2017, SOL since 2020, XAUUSD since 2022 (MoonX).
All parameters are fixed a priori (textbook values), then a sensitivity grid
shows whether results depend on lucky parameters.

Costs: perps 0.06%/side + funding 0.03%/day paid by longs (received by shorts);
gold CFD 0.03%/side + 0.01%/day swap on both sides. Trades at next bar open
(approximated by next close-to-close return), no look-ahead.
"""
import os, sys, itertools
import numpy as np, pandas as pd

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COST = {"BTC": (0.0006, 0.0003, False), "ETH": (0.0006, 0.0003, False),
        "SOL": (0.0006, 0.0003, False), "XAUUSD": (0.0003, 0.0001, True)}
PPY = 52  # weekly bars

def load_w(sym):
    df = pd.read_csv(f"{D}/{sym}_1w.csv")
    s = pd.Series(df["close"].values, index=pd.to_datetime(df["time"], unit="ms"))
    return s.resample("W-SUN").last()   # align crypto (Mon) and gold (Thu) weeks

def prices(syms):
    return pd.concat({s: load_w(s) for s in syms}, axis=1)

def backtest(w, px):
    """w = target weights decided at close of week t, applied to week t+1."""
    r = px.pct_change()
    w = w.reindex(index=px.index, columns=px.columns).fillna(0)
    held = w.shift(1).fillna(0)
    gross = (held * r.fillna(0)).sum(axis=1)
    cost = pd.Series(0.0, index=px.index)
    for s in px.columns:
        fee, fund, both = COST[s]
        turn = w[s].diff().fillna(w[s]).abs().shift(1).fillna(0)
        carry = held[s].abs() if both else held[s]
        cost += turn * fee + carry * fund * 7
    net = gross - cost
    live = held.abs().sum(axis=1).gt(0).cummax()      # start when strategy first trades
    net = net[live]
    return (1 + net).cumprod(), net

def stats(eq, net, name):
    yrs = len(net) / PPY
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    sh = net.mean() / net.std() * np.sqrt(PPY) if net.std() > 0 else 0
    worst_w = net.min()
    yearly = (1 + net).groupby(net.index.year).prod() - 1
    return dict(strat=name, start=str(eq.index[0].date()), cagr=cagr, maxdd=dd, sharpe=sh,
                worst_week=worst_w, pos_years=f"{(yearly > 0).sum()}/{len(yearly)}",
                total=eq.iloc[-1] - 1)

def realized_vol(px, n=12):
    return px.pct_change().rolling(n).std() * np.sqrt(PPY)

# ---------- strategies ----------
def buy_hold(px, syms):
    return pd.DataFrame({s: (1 / len(syms)) for s in syms}, index=px.index)[syms].where(px[syms].notna(), 0)

def tsmom(px, syms, lookbacks=(4, 12, 26, 52), target_vol=0.20, long_short=False, max_gross=2.0):
    """Time-series momentum, blended lookbacks, inverse-vol sized, portfolio vol target."""
    sig = sum(np.sign(px[syms].pct_change(lb)) for lb in lookbacks) / len(lookbacks)  # -1..1
    if not long_short:
        sig = sig.clip(lower=0)
    vol = realized_vol(px[syms])
    n_live = px[syms].notna().sum(axis=1).clip(lower=1)
    # equal share of the vol budget per asset; x1.3 compensates diversification (~0.5 correlation)
    w = (sig * (target_vol / vol)).div(n_live, axis=0) * 1.3
    gross = w.abs().sum(axis=1)
    w = w.div(np.maximum(gross / max_gross, 1), axis=0)
    return w.fillna(0)

def donchian(px, syms, entry=20, exit_=10, target_vol=0.20, max_gross=2.0):
    """Turtle-style long-only breakout on weekly closes, vol-sized."""
    out = pd.DataFrame(0.0, index=px.index, columns=syms)
    for s in syms:
        p = px[s]
        hi, lo = p.rolling(entry).max().shift(1), p.rolling(exit_).min().shift(1)
        pos, cur = [], 0
        for i in range(len(p)):
            if np.isnan(p.iloc[i]) or np.isnan(hi.iloc[i]): pos.append(0); continue
            if cur == 0 and p.iloc[i] > hi.iloc[i]: cur = 1
            elif cur == 1 and p.iloc[i] < lo.iloc[i]: cur = 0
            pos.append(cur)
        out[s] = pos
    vol = realized_vol(px[syms])
    n = px[syms].notna().sum(axis=1).clip(lower=1)
    w = (out * (target_vol / vol)).div(n, axis=0) * 1.3
    gross = w.abs().sum(axis=1)
    return w.div(np.maximum(gross / max_gross, 1), axis=0).fillna(0)

def dual_momentum(px, risky=("BTC", "XAUUSD"), lb=12):
    """Hold the asset with the best 12-week return if positive, else cash (Quantpedia BTC/gold)."""
    m = px[list(risky)].pct_change(lb)
    best = m.fillna(-np.inf).idxmax(axis=1)
    w = pd.DataFrame(0.0, index=px.index, columns=list(risky))
    for t in px.index:
        b = best.get(t)
        if isinstance(b, str) and m.loc[t, b] > 0:
            w.loc[t, b] = 1.0
    return w

def scale(w, k):
    return w * k

def show(rows):
    df = pd.DataFrame(rows)
    for c in ("cagr", "maxdd", "worst_week", "total"):
        df[c] = df[c].map(lambda x: f"{x:+.1%}")
    df["sharpe"] = df["sharpe"].map(lambda x: f"{x:.2f}")
    print(df.to_string(index=False))

if __name__ == "__main__":
    pd.set_option("display.width", 220)
    C3 = ["BTC", "ETH", "SOL"]
    ALL = ["BTC", "ETH", "SOL", "XAUUSD"]

    print("=== A. Crypto only, since 2017 (BTC/ETH; SOL from 2020) ===")
    px = prices(C3)
    rows = []
    for name, w in [
        ("Buy&Hold BTC", buy_hold(px, ["BTC"])),
        ("Buy&Hold panier BTC/ETH/SOL", buy_hold(px, C3)),
        ("Trend TSMOM long-only (vol 20%)", tsmom(px, C3)),
        ("Trend TSMOM long/short (vol 20%)", tsmom(px, C3, long_short=True)),
        ("Donchian 20/10 long-only (vol 20%)", donchian(px, C3)),
    ]:
        rows.append(stats(*backtest(w, px), name))
    show(rows)

    print("\n=== B. Crypto + gold, since 2022-11 (common history) ===")
    px4 = prices(ALL).loc["2022-11-20":].ffill(limit=1)
    rows = []
    cands = {
        "Buy&Hold BTC": buy_hold(px4, ["BTC"]),
        "Buy&Hold or": buy_hold(px4, ["XAUUSD"]),
        "Trend TSMOM long-only 4 actifs (vol 20%)": tsmom(px4, ALL),
        "Trend TSMOM long/short 4 actifs (vol 20%)": tsmom(px4, ALL, long_short=True),
        "Donchian 20/10 4 actifs (vol 20%)": donchian(px4, ALL),
        "Dual momentum BTC/or/cash": dual_momentum(px4),
    }
    for name, w in cands.items():
        rows.append(stats(*backtest(w, px4), name))
    show(rows)

    print("\n=== C. Robustness of TSMOM long-only (crypto since 2017): CAGR / MaxDD ===")
    for lbs in [(4,), (12,), (26,), (52,), (4, 12), (12, 26, 52), (4, 12, 26, 52)]:
        line = []
        for tv in (0.10, 0.20, 0.30):
            eq, net = backtest(tsmom(px, C3, lookbacks=lbs, target_vol=tv), px)
            s = stats(eq, net, "")
            line.append(f"vol{int(tv*100)}%: {s['cagr']:+.0%}/{s['maxdd']:+.0%}")
        print(f"  lookbacks {str(lbs):16s} " + "  ".join(line))
    print("  Donchian grid (entry/exit): " + ", ".join(
        f"{e}/{x}: {stats(*backtest(donchian(px, C3, e, x), px), '')['cagr']:+.0%}"
        for e, x in [(10, 5), (20, 10), (30, 15), (52, 26)]))

    print("\n=== D. Year by year, TSMOM long-only crypto (vol 20%) vs Buy&Hold BTC ===")
    eq, net = backtest(tsmom(px, C3), px)
    eqb, netb = backtest(buy_hold(px, ["BTC"]), px)
    y1 = (1 + net).groupby(net.index.year).prod() - 1
    y2 = (1 + netb).groupby(netb.index.year).prod() - 1
    print("  " + "  ".join(f"{y}: {a:+.0%} (BTC {b:+.0%})" for y, a, b in zip(y1.index, y1, y2.reindex(y1.index))))

    print("\n=== E. Prop-firm sizing: TSMOM long-only 4 assets, scaled down (since 2022-11) ===")
    print("  typical rules: max total loss 10%, daily loss 5% (weekly bars: worst week shown as proxy)")
    rows = []
    base = tsmom(px4, ALL)
    for k in (1.0, 0.5, 0.35, 0.25):
        rows.append(stats(*backtest(scale(base, k), px4), f"taille x{k}"))
    show(rows)
    print("  same on crypto-only since 2017:")
    rows = []
    base = tsmom(px, C3)
    for k in (0.5, 0.35, 0.25):
        rows.append(stats(*backtest(scale(base, k), px), f"taille x{k}"))
    show(rows)
